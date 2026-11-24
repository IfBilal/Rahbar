"""The ledger: what the data lake holds and what each Chroma index was built from.

Chroma knows chunks. It does not know documents, versions, why a file was rejected, or
what the inbox looked like last time. The ledger does (docs/a3-ragops/04 sections 4.2-4.4,
schema in docs/a3-ragops/14 section 2). It is one small JSON file on the data PVC, written
atomically (temp file, fsync, rename) with the previous good copy kept as `.bak`, and
guarded by a single-writer lock file (`O_EXCL`), so two ingestion runs can never interleave.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = 1
CURRENT, ARCHIVED, DELETED = "current", "archived", "deleted"
_LIVE = (CURRENT, ARCHIVED)


class LedgerError(RuntimeError):
    """The ledger cannot be read or written safely. The Job exits 3."""


class LockHeld(LedgerError):
    """Another ingestion run holds the lock."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "updated_at": _now(), "digest": "", "batches": [],
            "documents": {}, "inbox_index": {}, "quarantine": [], "indexes": {}}


@dataclass
class Ledger:
    path: Path
    data: dict[str, Any]

    # ------------------------------------------------------------------ load / save
    @classmethod
    def load(cls, path: Path) -> Ledger:
        """Read the ledger, falling back to the `.bak` copy. A missing file is a new
        ledger; a file that exists but cannot be parsed (and has no good backup) is fatal."""
        path = Path(path)
        backup = path.with_suffix(path.suffix + ".bak")
        errors: list[str] = []
        for candidate in (path, backup):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if data.get("schema") != SCHEMA:
                    raise ValueError(f"unknown ledger schema {data.get('schema')!r}")
                return cls(path, data)
            except (OSError, ValueError) as exc:
                errors.append(f"{candidate.name}: {exc}")
        if errors:
            raise LedgerError("ledger unreadable and no good backup: " + "; ".join(errors))
        return cls(path, _empty())

    def save(self) -> None:
        self.data["updated_at"] = _now()
        self.data["digest"] = self.digest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self.data, indent=2, sort_keys=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if self.path.exists():
            os.replace(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ documents
    @property
    def documents(self) -> dict[str, dict[str, Any]]:
        return self.data["documents"]

    def versions(self, doc_id: str) -> dict[str, dict[str, Any]]:
        return self.documents.get(doc_id, {}).get("versions", {})

    def get(self, doc_id: str, version: str) -> dict[str, Any] | None:
        return self.versions(doc_id).get(version)

    def put(self, doc_id: str, version: str, record: dict[str, Any],
            series_title: str | None = None) -> None:
        entry = self.documents.setdefault(doc_id, {"series_title": series_title or doc_id,
                                                   "versions": {}})
        if series_title:
            entry["series_title"] = series_title
        entry["versions"][version] = record

    def current_version(self, doc_id: str) -> str | None:
        for version, rec in self.versions(doc_id).items():
            if rec["status"] == CURRENT:
                return version
        return None

    def set_status(self, doc_id: str, version: str, status: str) -> None:
        rec = self.versions(doc_id)[version]
        rec["status"] = status
        stamp = _now()
        if status == ARCHIVED:
            rec["archived_at"] = stamp
        elif status == DELETED:
            rec["deleted_at"] = stamp
        elif status == CURRENT:
            rec["archived_at"] = None
            rec["deleted_at"] = None

    def iter_versions(self, statuses: tuple[str, ...] = _LIVE
                      ) -> Iterator[tuple[str, str, dict[str, Any]]]:
        for doc_id in sorted(self.documents):
            for version in sorted(self.documents[doc_id]["versions"]):
                rec = self.documents[doc_id]["versions"][version]
                if rec["status"] in statuses:
                    yield doc_id, version, rec

    def find_by_sha(self, sha: str, statuses: tuple[str, ...] = _LIVE
                    ) -> tuple[str, str, dict[str, Any]] | None:
        for doc_id, version, rec in self.iter_versions(statuses):
            if rec.get("content_sha") == sha:
                return doc_id, version, rec
        return None

    def find_by_text_sha(self, sha: str) -> tuple[str, str, dict[str, Any]] | None:
        for doc_id, version, rec in self.iter_versions():
            if rec.get("text_sha") == sha:
                return doc_id, version, rec
        return None

    # ------------------------------------------------------------------ inbox, quarantine
    @property
    def inbox_index(self) -> dict[str, dict[str, str]]:
        return self.data["inbox_index"]

    def remember_path(self, path: str, sha: str, doc_id: str, version: str) -> None:
        self.inbox_index[path] = {"sha": sha, "doc_id": doc_id, "version": version}

    def forget_path(self, path: str) -> None:
        self.inbox_index.pop(path, None)

    def quarantine_log(self, file: str, sha: str, codes: list[str], run_id: str) -> bool:
        """Record a rejection. Returns True when the same bytes were rejected before."""
        repeat = any(q["sha"] == sha for q in self.data["quarantine"])
        self.data["quarantine"].append({"file": file, "sha": sha, "codes": codes,
                                        "run_id": run_id, "ts": _now(), "repeat": repeat})
        return repeat

    def was_quarantined(self, sha: str) -> bool:
        return any(q["sha"] == sha for q in self.data["quarantine"])

    # ------------------------------------------------------------------ indexes, batches
    @property
    def indexes(self) -> dict[str, dict[str, Any]]:
        return self.data["indexes"]

    def note_batch(self, batch: str) -> None:
        if batch not in self.data["batches"]:
            self.data["batches"] = sorted([*self.data["batches"], batch])

    def digest(self) -> str:
        """Corpus-state digest: documents that are retrievable or restorable, not
        quarantined or deleted. Result files record it so runs on different data are
        never compared by accident."""
        rows = sorted((d, v, r.get("content_sha", ""), r["status"])
                      for d, v, r in self.iter_versions())
        return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


@contextlib.contextmanager
def ledger_lock(path: Path, run_id: str, pod: str = "", ttl_seconds: int = 7200
                ) -> Iterator[None]:
    """Single-writer lock (docs/a3-ragops/05 section 9). Created with O_EXCL; a lock older
    than `ttl_seconds` is treated as left behind by a dead run and broken with a log line
    by the caller (we raise nothing for it, we just take the lock)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o640)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
            holder = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            age, holder = 0.0, {}
        if age < ttl_seconds:
            raise LockHeld(f"ingest lock held by {holder.get('pod') or 'another run'} "
                           f"({holder.get('run_id', '?')}), {int(age)}s old") from None
        path.unlink(missing_ok=True)
        fd = os.open(path, flags, 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"pod": pod, "run_id": run_id, "started_at": _now()}, fh)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
