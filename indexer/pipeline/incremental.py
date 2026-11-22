"""Incremental ingestion: reconcile the inbox, the ledger and the vector index(es).

This is the engine behind `python -m pipeline.run sync` (docs/a3-ragops/05 section 6, paper
4.2.3-4.2.4). The unit of change is the document:

    unchanged file            nothing at all: no extract, no verify, no embedding
    new / changed file        extract -> verify (four checks) -> chunk -> embed -> index
    newer version of a series the older version is ARCHIVED (metadata flip, no re-embedding)
    file removed from inbox   its chunks are deleted, its bytes archived under a tombstone
    failed verification       quarantined; never chunked, never indexed

Order of writes per accepted document: embed first (so an embedding failure leaves the old
state intact), then lake, then the index, and the ledger is written last by the caller, so
a crash leaves the ledger behind the index and the next run's repair step heals it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .catalog import InboxFile, ResolvedMeta, load_catalog, resolve_metadata, scan_inbox, version_key
from .chunk import chunk
from .clean import clean
from .index import VectorIndex
from .lake import Lake
from .ledger import ARCHIVED, CURRENT, DELETED, Ledger
from .models import Chunk, Document
from .report import build_verification_report
from .verify import DocContext, RunSeen, Thresholds, Verification, verify_document

Embedder = Callable[[list[str]], list[list[float]]]
Extractor = Callable[[str, str, bool, bool], Document]


@dataclass
class Target:
    """One index to keep current: the live collection, or a registered candidate."""
    index: VectorIndex
    embed: Embedder
    embed_model: str
    chunk_size: int
    chunk_overlap: int
    embed_version: str = ""
    role: str = "live"


@dataclass
class SyncConfig:
    run_id: str
    thresholds: Thresholds
    extract: Extractor
    ocr: bool = True
    git_sha: str = ""
    image: str = ""


@dataclass
class SyncResult:
    summary: dict[str, Any]
    verification: dict[str, Any]
    exit_code: int


def where_doc(doc_id: str, version: str | None = None) -> dict[str, Any]:
    if version is None:
        return {"doc_id": doc_id}
    return {"$and": [{"doc_id": doc_id}, {"doc_version": version}]}


def _counters() -> dict[str, Any]:
    keys = ("docs_seen docs_unchanged docs_new docs_updated docs_superseded docs_deleted "
            "docs_quarantined docs_renamed chunks_embedded chunks_reused chunks_written "
            "chunks_deleted verification_embeddings repairs").split()
    return {k: 0 for k in keys}


# ---------------------------------------------------------------------------------- helpers
def chunk_rows(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [{"chunk_id": c.id, "text": c.text, "source": c.source, "section": c.section,
             "page": c.page, "doc_id": c.doc_id, "doc_version": c.doc_version,
             "chunk_sha": c.chunk_sha, "metadata": c.metadata()} for c in chunks]


def flip_metadata(targets: list[Target], ledger: Ledger, lake: Lake, doc_id: str, version: str,
                  archived: bool) -> int:
    """Mark a version's chunks archived (superseded=True) or current (superseded=False) in
    every index, from the lake snapshot, passing the FULL metadata so the result is the
    same whether Chroma merges or replaces. No embedding happens. Returns chunks touched."""
    rows = lake.read_chunks(doc_id, version)
    rec = ledger.get(doc_id, version) or {}
    touched = 0
    for t in targets:
        ids = set(rec.get("indexed", {}).get(t.index.name, []))
        chosen = [r for r in rows if r["chunk_id"] in ids]
        if not chosen:
            continue
        metas = [{**r["metadata"], "superseded": archived,
                  "status": "archived" if archived else "current"} for r in chosen]
        t.index.update_metadata([r["chunk_id"] for r in chosen], metas)
        touched += len(chosen)
    return touched


def delete_chunks(targets: list[Target], rec: dict[str, Any]) -> int:
    removed = 0
    for t in targets:
        ids = rec.get("indexed", {}).get(t.index.name, [])
        if ids:
            t.index.delete(list(ids))
            removed += len(ids)
    return removed


def archive_version(targets: list[Target], ledger: Ledger, lake: Lake, doc_id: str,
                    version: str) -> int:
    n = flip_metadata(targets, ledger, lake, doc_id, version, archived=True)
    lake.archive_version(doc_id, version)
    ledger.set_status(doc_id, version, ARCHIVED)
    return n


# ---------------------------------------------------------------------------------- repair
def repair(targets: list[Target], ledger: Ledger, lake: Lake, run_id: str) -> int:
    """Heal a run that died between the index and the ledger: for every ledger version,
    make each index hold exactly the chunk ids the ledger expects."""
    fixed = 0
    for doc_id, version, rec in ledger.iter_versions():
        for t in targets:
            expected = set(rec.get("indexed", {}).get(t.index.name, []))
            if not expected:
                continue
            actual = set(t.index.ids_where(where_doc(doc_id, version)))
            extra = sorted(actual - expected)
            missing = sorted(expected - actual)
            if extra:
                t.index.delete(extra)
                fixed += len(extra)
            if missing:
                rows = {r["chunk_id"]: r for r in lake.read_chunks(doc_id, version)}
                todo = [rows[i] for i in missing if i in rows]
                if todo:
                    vectors = t.embed([r["text"] for r in todo])
                    archived = rec["status"] == ARCHIVED
                    t.index.add([r["chunk_id"] for r in todo], [r["text"] for r in todo], vectors,
                                [{**r["metadata"], "superseded": archived,
                                  "status": "archived" if archived else "current",
                                  "ingest_run": run_id} for r in todo])
                    fixed += len(todo)
    return fixed


# ---------------------------------------------------------------------------------- extraction
def _extract(f: InboxFile, cfg: SyncConfig, rows: dict[str, dict[str, Any]]) -> tuple[DocContext, Document | None]:
    doc: Document | None = None
    error: str | None = None
    try:
        doc = cfg.extract(str(f.path), "unknown", False, cfg.ocr)
        pages = [p.text for p in doc.pages]
        ocr_pages = sum(1 for p in doc.pages if p.ocr)
    except Exception as exc:           # a hostile or corrupt file must never crash the Job
        pages, ocr_pages, error = [], 0, f"{type(exc).__name__}: {str(exc)[:200]}"
    meta: ResolvedMeta = resolve_metadata(f, pages, rows)
    return DocContext(file=f.rel, path=f.path, sha=f.sha, meta=meta, pages=pages,
                      extraction_error=error, ocr_pages=ocr_pages), doc


# ---------------------------------------------------------------------------------- the sync
def sync(lake: Lake, ledger: Ledger, targets: list[Target], cfg: SyncConfig,
         verify_embed: Embedder | None) -> SyncResult:
    started = time.perf_counter()
    c = _counters()
    changed_targets: set[str] = set()
    per_index = {t.index.name: {"chunks_embedded": 0, "chunks_written": 0, "chunks_deleted": 0}
                 for t in targets}
    doc_reports: list[dict[str, Any]] = []
    reevaluated: list[dict[str, Any]] = []
    unchanged: list[str] = []
    seen = RunSeen()
    probe = {"windows": 0}

    def counted_embed(texts: list[str]) -> list[list[float]]:
        probe["windows"] += len(texts)
        assert verify_embed is not None
        return verify_embed(texts)

    # 1. heal a previous run that died half-way
    healed = repair(targets, ledger, lake, cfg.run_id)
    c["repairs"] = healed
    if healed:
        changed_targets.update(t.index.name for t in targets)

    # 2. what does the inbox say now?
    files = scan_inbox(lake.inbox)
    rows, _ = load_catalog(lake.inbox)
    c["docs_seen"] = len(files)
    present = {f.rel for f in files}
    shas_present = {f.sha for f in files}

    # 3. removals and renames
    for rel, entry in list(ledger.inbox_index.items()):
        if rel in present:
            continue
        if entry["sha"] in shas_present:
            continue                                   # renamed: handled below, no work here
        rec = ledger.get(entry["doc_id"], entry["version"])
        if rec and rec["status"] in (CURRENT, ARCHIVED):
            n = delete_chunks(targets, rec)
            for t in targets:
                per_index[t.index.name]["chunks_deleted"] += len(
                    rec.get("indexed", {}).get(t.index.name, []))
            c["chunks_deleted"] += n
            lake.tombstone(entry["doc_id"], entry["version"], cfg.run_id)
            ledger.set_status(entry["doc_id"], entry["version"], DELETED)
            c["docs_deleted"] += 1
            changed_targets.update(t.index.name for t in targets)
        ledger.forget_path(rel)

    # 4. classify what is left; unchanged files cost nothing
    work: list[tuple[InboxFile, str]] = []
    for f in files:
        known = ledger.inbox_index.get(f.rel)
        if known and known["sha"] == f.sha:
            unchanged.append(f.rel)
            c["docs_unchanged"] += 1
            continue
        if not known:
            old_path = next((p for p, e in ledger.inbox_index.items()
                             if e["sha"] == f.sha and p not in present), None)
            if old_path:                               # same bytes, new name: a rename
                moved = ledger.inbox_index.pop(old_path)
                ledger.remember_path(f.rel, f.sha, moved["doc_id"], moved["version"])
                c["docs_renamed"] += 1
                continue
        work.append((f, "changed" if known else "new"))

    # 5. extract, then process each series oldest version first (05 section 4.3)
    prepared: list[tuple[InboxFile, str, DocContext, Document | None]] = []
    for f, kind in work:
        ctx, doc = _extract(f, cfg, rows)
        prepared.append((f, kind, ctx, doc))
    # Series stay together and run oldest version first; between series the first-seen file
    # (sorted path order) wins, so which of two near-duplicates is kept is deterministic.
    first_rel: dict[str, str] = {}
    for f, _, ctx, _ in prepared:
        first_rel[ctx.meta.doc_id] = min(f.rel, first_rel.get(ctx.meta.doc_id, f.rel))
    prepared.sort(key=lambda x: (first_rel[x[2].meta.doc_id], x[2].meta.doc_id,
                                 version_key(x[2].meta.version.value or ""), x[0].rel))

    for f, kind, ctx, doc in prepared:
        ver = verify_document(ctx, ledger, cfg.thresholds,
                              counted_embed if verify_embed else None,
                              lambda d, v: lake.read_docvec(d, v), seen)
        entry_report = {"file": f.rel, "sha256": f.sha, "pages": ctx.page_count,
                        "resolved": ctx.meta.as_dict(),
                        "checks": {k: v.as_dict() for k, v in ver.checks.items()},
                        "outcome": ver.outcome, "destination": ""}
        if ver.outcome == "quarantined":
            dst = lake.quarantine_file(f.path, cfg.run_id, {
                "file": f.rel, "sha256": f.sha, "codes": ver.codes, "reasons": ver.reasons,
                "resolved": ctx.meta.as_dict(), "run_id": cfg.run_id})
            ledger.quarantine_log(f.rel, f.sha, ver.codes, cfg.run_id)
            ledger.forget_path(f.rel)     # the file left the inbox; an earlier good version stays
            entry_report["destination"] = lake.rel(dst)
            c["docs_quarantined"] += 1
            doc_reports.append(entry_report)
            continue
        assert doc is not None
        ok = _accept(lake, ledger, targets, cfg, f, kind, ctx, doc, ver, c, per_index,
                     changed_targets, reevaluated)
        entry_report["destination"] = ok
        doc_reports.append(entry_report)
        seen.shas[f.sha] = f"{ctx.meta.doc_id}@{ctx.meta.version.value}"
        if ver.text_sha:
            seen.text_shas[ver.text_sha] = f"{ctx.meta.doc_id}@{ctx.meta.version.value}"
        if ver.docvec:
            seen.docvecs.append((ctx.meta.doc_id, ctx.meta.version.value or "", ver.docvec))
    c["verification_embeddings"] = probe["windows"]

    # 6. publish: a new data revision for every index that changed, then the ledger
    bumped: dict[str, dict[str, Any]] = {}
    for t in targets:
        changed = t.index.name in changed_targets
        rev = t.index.bump_revision() if changed else t.index.revision()
        bumped[t.index.name] = {"revision": rev, "revision_bumped": changed, **per_index[t.index.name]}
        ledger.indexes[t.index.name] = {
            "role": t.role, "registry": f"{t.index.name}-registry", "embed_model": t.embed_model,
            "embed_version": t.embed_version, "chunk_size": t.chunk_size,
            "chunk_overlap": t.chunk_overlap, "chunks": t.index.count(), "revision": rev}
    report = build_verification_report(
        cfg.run_id, targets[0].embed_model, targets[0].embed_version, cfg.thresholds.as_dict(),
        doc_reports, reevaluated, unchanged, cfg.git_sha, cfg.image)
    exit_code = 1 if c["docs_quarantined"] else 0
    summary = {"type": "ingest_summary", "schema": 1, "run_id": cfg.run_id, "command": "sync",
               **c, "seconds": round(time.perf_counter() - started, 2), "indexes": bumped,
               "exit": exit_code}
    return SyncResult(summary=summary, verification=report, exit_code=exit_code)


# ---------------------------------------------------------------------------------- accept one
def _accept(lake: Lake, ledger: Ledger, targets: list[Target], cfg: SyncConfig, f: InboxFile,
            kind: str, ctx: DocContext, raw: Document, ver: Verification, c: dict[str, Any],
            per_index: dict[str, dict[str, int]], changed: set[str],
            reevaluated: list[dict[str, Any]]) -> str:
    meta = ctx.meta
    doc_id, version = meta.doc_id, meta.version.value or "unknown"
    revision = 1 + max((r.get("ledger_revision", 0) for r in ledger.versions(doc_id).values()),
                       default=0)
    raw.doc_version = version
    cleaned = clean(raw)
    old = ledger.get(doc_id, version)

    # embed everything first: a failure here leaves the old state untouched (05 section 9)
    built: list[tuple[Target, list[Chunk], list[list[float]]]] = []
    for t in targets:
        pieces = chunk(cleaned, t.chunk_size, t.chunk_overlap, doc_id=doc_id, content_sha=f.sha)
        for p in pieces:
            p.revision, p.ingest_run = revision, cfg.run_id
        vectors = t.embed([p.text for p in pieces]) if pieces else []
        built.append((t, pieces, vectors))

    # replace an earlier copy with the same version label (an in-place revision)
    if old and old["status"] in (CURRENT, ARCHIVED):
        removed = delete_chunks(targets, old)
        c["chunks_deleted"] += removed
        for t in targets:
            per_index[t.index.name]["chunks_deleted"] += len(old.get("indexed", {}).get(t.index.name, []))
        c["docs_updated"] += 1
    else:
        c["docs_new"] += 1

    # supersede older versions of the series (recency R-SUPERSEDES)
    for old_doc, old_ver in ver.supersedes:
        archive_version(targets, ledger, lake, old_doc, old_ver)
        reevaluated.append({"doc": f"{old_doc}@{old_ver}", "check": "recency", "status": "fail",
                            "code": "R-SUPERSEDED-BY",
                            "reason": f"a newer version exists: {doc_id}@{version}",
                            "outcome": "archived"})
        c["docs_superseded"] += 1
        changed.update(t.index.name for t in targets)

    primary_rows = chunk_rows(built[0][1])
    lake_meta = {"doc_id": doc_id, "doc_version": version, "content_sha": f.sha,
                 "file_name": f.path.name, "pages": ctx.page_count, "resolved": meta.as_dict(),
                 "ledger_revision": revision, "ingest_run": cfg.run_id,
                 "previous_sha": (old or {}).get("content_sha", "")}
    lake_dir = lake.store_version(doc_id, version, f.path, primary_rows, lake_meta,
                                  ver.docvec or {})
    indexed: dict[str, list[str]] = {}
    for t, pieces, vectors in built:
        t.index.add([p.id for p in pieces], [p.text for p in pieces], vectors,
                    [p.metadata() for p in pieces])
        indexed[t.index.name] = [p.id for p in pieces]
        c["chunks_embedded"] += len(pieces)
        c["chunks_written"] += len(pieces)
        per_index[t.index.name]["chunks_embedded"] += len(pieces)
        per_index[t.index.name]["chunks_written"] += len(pieces)
        changed.add(t.index.name)
    ledger.put(doc_id, version, {
        "status": CURRENT, "batch": meta.batch, "inbox_path": f.rel, "file_name": f.path.name,
        "content_sha": f.sha, "text_sha": ver.text_sha, "ledger_revision": revision,
        "pages": ctx.page_count, "resolved": meta.as_dict(),
        "chunk_ids": indexed[targets[0].index.name], "chunk_count": len(built[0][1]),
        "indexed": indexed, "lake_path": lake.rel(lake_dir),
        "docvec": lake.rel(lake_dir / "docvec.json"), "ingested_run": cfg.run_id,
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "archived_at": None, "deleted_at": None}, series_title=meta.title.value)
    ledger.remember_path(f.rel, f.sha, doc_id, version)
    ledger.note_batch(meta.batch)
    return lake.rel(lake_dir)


def default_extractor() -> Extractor:
    from .extract import extract
    return extract
