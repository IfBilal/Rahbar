"""The data lake on the PVC: inbox, verified versions, archive, quarantine, reports.

Layout (docs/a3-ragops/04 section 4.1), under DATA_DIR (`/data` in the Job):

    inbox/                         desired corpus: drop files here
    lake/docs/<doc_id>/<version>/  verified original + chunks.jsonl + meta.json + docvec.json
    archive/<doc_id>/<version>/    superseded or deleted versions, kept for rollback
    quarantine/<run_id>/<file>     rejected files, each with <file>.reason.json
    ledger/ledger.json             see ledger.py
    reports/{verification,ingest}/ one report per run

Version directories are immutable once written: a changed document with the same version
label sends the old bytes to the archive first. Moves are `os.replace`, so they are atomic
on one volume; a crash leaves a file in its old place or its new one, never half-moved.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class Lake:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.docs = self.root / "lake" / "docs"
        self.archive = self.root / "archive"
        self.quarantine = self.root / "quarantine"
        self.ledger_dir = self.root / "ledger"
        self.reports = self.root / "reports"

    def ensure(self) -> None:
        for d in (self.inbox, self.docs, self.archive, self.quarantine, self.ledger_dir,
                  self.reports / "verification", self.reports / "ingest"):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def version_dir(self, doc_id: str, version: str, archived: bool = False) -> Path:
        return (self.archive if archived else self.docs) / doc_id / version

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    # ------------------------------------------------------------------ write a version
    def store_version(self, doc_id: str, version: str, source_file: Path,
                      chunks: list[dict[str, Any]], meta: dict[str, Any],
                      docvec: dict[str, Any]) -> Path:
        """Write a verified document version. If the directory already exists (the same
        version label with different bytes) the old one is archived first."""
        target = self.version_dir(doc_id, version)
        if target.exists():
            self._archive_dir(target, self.version_dir(doc_id, version, archived=True),
                              keep_as=f"{version}~{meta.get('previous_sha', 'old')[:8]}")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target / source_file.name)
        with open(target / "chunks.jsonl", "w", encoding="utf-8") as fh:
            for row in chunks:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        _write_json(target / "meta.json", meta)
        _write_json(target / "docvec.json", docvec)
        return target

    # ------------------------------------------------------------------ archive / restore
    def _archive_dir(self, src: Path, dst: Path, keep_as: str | None = None) -> Path:
        if dst.exists():                       # never overwrite history
            dst = dst.with_name(keep_as or f"{dst.name}~{int(time.time())}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return dst

    def archive_version(self, doc_id: str, version: str) -> Path:
        src = self.version_dir(doc_id, version)
        if not src.exists():
            raise FileNotFoundError(f"no lake version {doc_id}@{version}")
        return self._archive_dir(src, self.version_dir(doc_id, version, archived=True))

    def restore_version(self, doc_id: str, version: str) -> Path:
        src = self.version_dir(doc_id, version, archived=True)
        if not src.exists():
            raise FileNotFoundError(f"no archived version {doc_id}@{version}")
        dst = self.version_dir(doc_id, version)
        if dst.exists():
            raise FileExistsError(f"{doc_id}@{version} is already in the lake")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return dst

    def tombstone(self, doc_id: str, version: str, run_id: str) -> Path:
        """Delete = archive plus a tombstone, so a delete can be reversed (paper 4.2.3)."""
        dst = self.archive_version(doc_id, version) if self.version_dir(doc_id, version).exists() \
            else self.version_dir(doc_id, version, archived=True)
        if dst.exists():
            _write_json(dst / "tombstone.json", {"deleted_by_run": run_id,
                                                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                     time.gmtime())})
        return dst

    # ------------------------------------------------------------------ quarantine
    def quarantine_file(self, file: Path, run_id: str, reason: dict[str, Any]) -> Path:
        """Move a rejected file out of the inbox (so the next run does not retry it
        forever) and write why next to it."""
        folder = self.quarantine / run_id
        folder.mkdir(parents=True, exist_ok=True)
        dst = folder / file.name
        n = 1
        while dst.exists():
            dst = folder / f"{file.stem}~{n}{file.suffix}"
            n += 1
        os.replace(file, dst)
        _write_json(dst.with_name(dst.name + ".reason.json"), reason)
        return dst

    # ------------------------------------------------------------------ read back
    def read_chunks(self, doc_id: str, version: str) -> list[dict[str, Any]]:
        """Chunk snapshots, from the lake or (if archived) the archive. The trace tool
        rebuilds prompts from these, so they must stay readable after an update."""
        for base in (self.version_dir(doc_id, version),
                     self.version_dir(doc_id, version, archived=True)):
            f = base / "chunks.jsonl"
            if f.exists():
                return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()
                        if line.strip()]
        raise FileNotFoundError(f"no chunk snapshot for {doc_id}@{version}")

    def read_docvec(self, doc_id: str, version: str) -> dict[str, Any] | None:
        for base in (self.version_dir(doc_id, version),
                     self.version_dir(doc_id, version, archived=True)):
            f = base / "docvec.json"
            if f.exists():
                data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
                return data
        return None

    def write_report(self, kind: str, run_id: str, name: str, body: str | dict[str, Any]) -> Path:
        path = self.reports / kind / f"{run_id}{name}"
        if isinstance(body, str):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        else:
            _write_json(path, body)
        return path
