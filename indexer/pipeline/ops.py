"""Operations on what the lake already holds: restore, delete, count, status, build-index,
unregister (docs/a3-ragops/05 sections 7 and 2, 07 section 3). Like `sync`, these are run
by the ingestion Job, so the Job stays the only writer of the vector store.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .catalog import sha256_file
from .chunk import chunk
from .clean import clean
from .incremental import (
    Extractor, Target, archive_version, chunk_rows, delete_chunks, flip_metadata, where_doc,
)
from .lake import Lake
from .ledger import ARCHIVED, CURRENT, DELETED, Ledger


class OpError(RuntimeError):
    """The requested document or version does not exist (exit code 4)."""


def _bump(targets: list[Target], changed: bool) -> dict[str, dict[str, Any]]:
    return {t.index.name: {"revision": t.index.bump_revision() if changed else t.index.revision(),
                           "revision_bumped": changed} for t in targets}


def _summary(command: str, run_id: str, started: float, **extra: Any) -> dict[str, Any]:
    return {"type": "ingest_summary", "schema": 1, "run_id": run_id, "command": command,
            "seconds": round(time.perf_counter() - started, 2), **extra}


# ------------------------------------------------------------------------------- restore
def restore(lake: Lake, ledger: Ledger, targets: list[Target], doc_id: str, version: str,
            run_id: str) -> dict[str, Any]:
    """Make an archived version current again and archive the one that was current
    (rollback, A2-05). Flipping metadata needs no embedding; restoring a DELETED version
    re-embeds it from its snapshot because its chunks were removed."""
    started = time.perf_counter()
    rec = ledger.get(doc_id, version)
    if rec is None:
        raise OpError(f"unknown version {doc_id}@{version}")
    if rec["status"] == CURRENT:
        return _summary("restore", run_id, started, restored=f"{doc_id}@{version}", noop=True,
                        chunks_embedded=0, exit=0)
    embedded = 0
    current = ledger.current_version(doc_id)
    if current and current != version:
        archive_version(targets, ledger, lake, doc_id, current)
    if rec["status"] == DELETED:
        rows = lake.read_chunks(doc_id, version)
        for t in targets:
            vectors = t.embed([r["text"] for r in rows]) if rows else []
            t.index.add([r["chunk_id"] for r in rows], [r["text"] for r in rows], vectors,
                        [{**r["metadata"], "superseded": False, "status": "current"} for r in rows])
            rec.setdefault("indexed", {})[t.index.name] = [r["chunk_id"] for r in rows]
            embedded += len(rows)
    else:
        flip_metadata(targets, ledger, lake, doc_id, version, archived=False)
    lake.restore_version(doc_id, version)
    ledger.set_status(doc_id, version, CURRENT)
    return _summary("restore", run_id, started, restored=f"{doc_id}@{version}",
                    archived=f"{doc_id}@{current}" if current and current != version else None,
                    chunks_embedded=embedded, indexes=_bump(targets, True), exit=0)


# ------------------------------------------------------------------------------- delete
def delete(lake: Lake, ledger: Ledger, targets: list[Target], doc_id: str,
           version: str | None, run_id: str) -> dict[str, Any]:
    """Remove a document's chunks from every index, tombstone and archive its bytes, and
    take its file out of the inbox so the next `sync` does not bring it back."""
    started = time.perf_counter()
    chosen = [(v, r) for v, r in ledger.versions(doc_id).items()
              if r["status"] in (CURRENT, ARCHIVED) and (version is None or v == version)]
    if not chosen:
        raise OpError(f"nothing to delete for {doc_id}" + (f"@{version}" if version else ""))
    removed = 0
    for v, rec in chosen:
        removed += delete_chunks(targets, rec)
        lake.tombstone(doc_id, v, run_id)
        ledger.set_status(doc_id, v, DELETED)
        path = rec.get("inbox_path")
        if path:
            f = lake.inbox / path
            if f.exists() and sha256_file(f) == rec.get("content_sha"):
                f.unlink()
            ledger.forget_path(path)
    return _summary("delete", run_id, started, deleted=[f"{doc_id}@{v}" for v, _ in chosen],
                    chunks_deleted=removed, chunks_embedded=0, indexes=_bump(targets, True),
                    exit=0)


# ------------------------------------------------------------------------------- count
def count(ledger: Ledger, targets: list[Target], doc_id: str | None = None) -> dict[str, Any]:
    """Read-only proof of "no orphans": chunks per document version, the index total, the
    total the ledger expects, and the difference in both directions."""
    out: dict[str, Any] = {"indexes": {}}
    for t in targets:
        expected: dict[str, str] = {}
        per_doc: dict[str, int] = {}
        for d, v, rec in ledger.iter_versions():
            ids = rec.get("indexed", {}).get(t.index.name, [])
            for i in ids:
                expected[i] = f"{d}@{v}"
            if doc_id is None or d == doc_id:
                per_doc[f"{d}@{v}"] = t.index.count_where(where_doc(d, v))
        if doc_id and not any(k.startswith(doc_id + "@") for k in per_doc):
            per_doc[f"{doc_id}@*"] = t.index.count_where(where_doc(doc_id))
        actual = set(t.index.all_ids())
        out["indexes"][t.index.name] = {
            "index": t.index.name, "chroma_total": len(actual),
            "ledger_expected_total": len(expected), "per_doc": per_doc,
            "orphans": sorted(actual - set(expected)), "missing": sorted(set(expected) - actual)}
    return out


def status(ledger: Ledger, targets: list[Target]) -> dict[str, Any]:
    docs: dict[str, list[str]] = {}
    for d, v, rec in ledger.iter_versions((CURRENT, ARCHIVED, DELETED)):
        docs.setdefault(d, []).append(f"{v}:{rec['status']}")
    return {"documents": docs, "quarantined": len(ledger.data["quarantine"]),
            "batches": ledger.data["batches"], "digest": ledger.digest(),
            "indexes": {t.index.name: t.index.info() for t in targets}}


# ------------------------------------------------------------------------------- build-index
def build_index(lake: Lake, ledger: Ledger, target: Target, live: Target, extract: Extractor,
                ocr: bool, run_id: str, register: bool = True) -> dict[str, Any]:
    """Build a NEW collection from the verified documents in the lake (a candidate: another
    embedding model or chunk size). The live collection is never touched. Chunk snapshots
    are reused when the chunk parameters match the live index, otherwise the original file
    stored in the lake is re-extracted and re-chunked."""
    started = time.perf_counter()
    same_chunks = (target.chunk_size, target.chunk_overlap) == (live.chunk_size, live.chunk_overlap)
    embedded = 0
    for doc_id, version, rec in ledger.iter_versions((CURRENT, ARCHIVED)):
        archived = rec["status"] == ARCHIVED
        if same_chunks:
            rows = lake.read_chunks(doc_id, version)
        else:
            base = lake.version_dir(doc_id, version, archived=archived)
            original = base / rec["file_name"]
            raw = extract(str(original), version, archived, ocr)
            raw.doc_version = version
            pieces = chunk(clean(raw), target.chunk_size, target.chunk_overlap, doc_id=doc_id,
                           content_sha=rec["content_sha"])
            for p in pieces:
                p.revision, p.ingest_run = rec.get("ledger_revision", 1), run_id
            rows = chunk_rows(pieces)
        if not rows:
            continue
        vectors = target.embed([r["text"] for r in rows])
        target.index.add([r["chunk_id"] for r in rows], [r["text"] for r in rows], vectors,
                         [{**r["metadata"], "superseded": archived,
                           "status": "archived" if archived else "current",
                           "ingest_run": run_id} for r in rows])
        rec.setdefault("indexed", {})[target.index.name] = [r["chunk_id"] for r in rows]
        embedded += len(rows)
    rev = target.index.bump_revision()
    if register:
        ledger.indexes[target.index.name] = {
            "role": target.role, "registry": f"{target.index.name}-registry",
            "embed_model": target.embed_model, "embed_version": target.embed_version,
            "chunk_size": target.chunk_size, "chunk_overlap": target.chunk_overlap,
            "chunks": target.index.count(), "revision": rev}
    return _summary("build-index", run_id, started, collection=target.index.name,
                    chunks_embedded=embedded, chunks_written=embedded,
                    indexes={target.index.name: {"revision": rev, "revision_bumped": True}}, exit=0)


def unregister(ledger: Ledger, target: Target, run_id: str) -> dict[str, Any]:
    """Drop a rejected candidate: remove its collection and forget it in the ledger."""
    started = time.perf_counter()
    name = target.index.name
    if ledger.indexes.get(name, {}).get("role") == "live":
        raise OpError(f"{name} is the live index and cannot be unregistered")
    target.index.drop()
    ledger.indexes.pop(name, None)
    for _, _, rec in ledger.iter_versions((CURRENT, ARCHIVED, DELETED)):
        rec.get("indexed", {}).pop(name, None)
    return _summary("unregister", run_id, started, collection=name, exit=0)


def read_report(lake: Lake, kind: str, run: str | None, markdown: bool) -> str:
    folder = lake.reports / kind
    suffix = ".md" if markdown else ".json"
    files = sorted(folder.glob(f"*{suffix}"))
    if run:
        files = [f for f in files if f.name.startswith(run)]
    if not files:
        raise OpError(f"no {kind} report found" + (f" for {run}" if run else ""))
    return Path(files[-1]).read_text(encoding="utf-8")
