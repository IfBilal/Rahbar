"""The ingestion Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run --dummy    # week 1: three fake chunks, no model needed
    python -m pipeline.run            # Assignment 02: rebuild a whole new index generation

Assignment 03 (docs/a3-ragops/05 and 14 section 1), over the data lake on the PVC:

    python -m pipeline.run sync                 # verify, quarantine, update incrementally
    python -m pipeline.run verify-only          # run the four checks, change nothing
    python -m pipeline.run restore <doc>@<ver>  # roll an archived version back to current
    python -m pipeline.run delete <doc> [--version V]
    python -m pipeline.run count [--doc-id ID]  # orphan proof, read-only
    python -m pipeline.run status | report [--last|--run ID] [--md]
    python -m pipeline.run build-index --collection C --embed-model M [--chunk-size N ...]
    python -m pipeline.run unregister --collection C

Every command ends with ONE JSON summary line. Exit codes: 0 done, 1 done with documents
quarantined (the Job wrapper treats it as success), 2 usage, 3 fatal (lock held, ledger
unreadable, Chroma or Ollama unavailable), 4 unknown document or version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import IndexerSettings, get_settings
from .models import Chunk


# One id per indexer run (the Job's pod name), on every line, like the API's request_id (4.8).
RUN_ID = os.environ.get("HOSTNAME") or f"indexer-{os.getpid()}"


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, "request_id": RUN_ID,
                      **fields}), flush=True)


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers (used by eval/fixtures)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def discover(corpus_dir: str) -> list[tuple[Path, str, bool]]:
    """List (path, doc_version, superseded) for every document to index.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when
    present. Otherwise read Markdown front matter (the CI fixtures work this way).
    """
    root = Path(corpus_dir)
    index = root / "_index.json"
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        return [(root / e["file"], str(e.get("doc_version", "unknown")),
                 bool(e.get("superseded", False))) for e in entries]
    found = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in {".pdf", ".md", ".html", ".txt"}:
            continue
        if path.name.lower().startswith("readme"):
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        found.append((path, meta.get("doc_version", "unknown"),
                      meta.get("superseded", "false").lower() == "true"))
    return found


def run_pipeline(settings: IndexerSettings) -> int:
    from .chunk import amplification, chunk
    from .clean import clean
    from .embed import embed
    from .extract import extract
    from .store import store

    documents = discover(settings.corpus_dir)
    if not documents:
        raise SystemExit(f"no documents found in {settings.corpus_dir}")
    all_chunks: list[Chunk] = []
    cleaned = []
    for path, doc_version, superseded in documents:
        started = time.perf_counter()
        raw = extract(str(path), doc_version, superseded, ocr=settings.ocr_enabled)
        doc = clean(raw)
        pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap)
        empty = [p.page for p in doc.pages if not p.text.strip()]
        log("chunked", source=path.name, doc_version=doc_version, superseded=superseded,
            pages=len(doc.pages), ocr_pages=[p.page for p in raw.pages if p.ocr],
            empty_pages=empty, chunks=len(pieces), seconds=round(time.perf_counter() - started, 1))
        cleaned.append(doc)
        all_chunks.extend(pieces)
    log("chunking done", chunks=len(all_chunks), chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap, amplification=amplification(all_chunks, cleaned))
    started = time.perf_counter()
    vectors = embed([c.text for c in all_chunks], settings)
    log("embedded", vectors=len(vectors), dimension=len(vectors[0]) if vectors else 0,
        model=settings.embed_model, seconds=round(time.perf_counter() - started, 1))
    return store(all_chunks, vectors, settings)

# ===================================================================== Assignment 03
def _utc() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def make_embedder(settings: IndexerSettings, shorten: bool = False):  # type: ignore[no-untyped-def]
    """`shorten` is for candidate indexes only (see embed.embed): the live index stays strict."""
    from .embed import embed

    def run_embed(texts: list[str]) -> list[list[float]]:
        return embed(texts, settings, shorten_on_overflow=shorten)
    return run_embed


def build_targets(settings: IndexerSettings, ledger, client):  # type: ignore[no-untyped-def]
    """The live index plus every registered, non-frozen candidate, each with its own embedder."""
    import dataclasses

    from .incremental import Target
    from .index import ChromaIndex

    version = os.environ.get("EMBED_VERSION", "")
    live = Target(ChromaIndex(client, settings.collection, settings, version),
                  make_embedder(settings), settings.embed_model, settings.chunk_size,
                  settings.chunk_overlap, version, "live")
    targets = [live]
    for name, info in sorted(ledger.indexes.items()):
        if name == settings.collection or info.get("frozen"):
            continue
        s = dataclasses.replace(settings, collection=name, embed_model=info["embed_model"],
                                chunk_size=int(info["chunk_size"]),
                                chunk_overlap=int(info["chunk_overlap"]))
        targets.append(Target(ChromaIndex(client, name, s, info.get("embed_version", "")),
                              make_embedder(s, shorten=info.get("role") != "live"), s.embed_model, s.chunk_size, s.chunk_overlap,
                              info.get("embed_version", ""), info.get("role", "candidate")))
    return targets


def _emit(summary: dict) -> None:  # type: ignore[type-arg]
    print(json.dumps(summary, sort_keys=True), flush=True)


def run_command(args: argparse.Namespace, settings: IndexerSettings, client=None) -> int:  # type: ignore[no-untyped-def]
    """Dispatch one Assignment 03 command. `client` is injectable for tests."""
    from . import ops
    from .extract import extract
    from .incremental import SyncConfig, sync
    from .lake import Lake
    from .ledger import Ledger, LedgerError, LockHeld, ledger_lock
    from .report import render_markdown
    from .verify import Thresholds

    lake = Lake(os.environ.get("DATA_DIR", "/data"))
    lake.ensure()
    run_id = f"ingest-{_utc()}-{RUN_ID[-4:]}"
    cmd = args.command
    try:
        if cmd == "report":
            print(ops.read_report(lake, args.kind, args.run, args.md))
            return 0
        if client is None and cmd != "verify-only":
            from .store import get_client
            client = get_client(settings)
        writes = cmd in {"sync", "restore", "delete", "build-index", "unregister"}
        lock = ledger_lock(lake.ledger_dir / "ingest.lock", run_id, os.environ.get("HOSTNAME", ""),
                           int(os.environ.get("LOCK_TTL_SECONDS", 7200))) if writes else None
        with (lock if lock else _nullcontext()):
            ledger = Ledger.load(lake.ledger_dir / "ledger.json")
            if cmd == "verify-only":
                return _verify_only(lake, ledger, settings, run_id)
            targets = build_targets(settings, ledger, client)
            if cmd == "sync":
                cfg = SyncConfig(run_id=run_id, thresholds=Thresholds.from_env(), extract=extract,
                                 ocr=settings.ocr_enabled, git_sha=os.environ.get("APP_VERSION", ""))
                res = sync(lake, ledger, targets, cfg, targets[0].embed)
                lake.write_report("verification", run_id, ".json", res.verification)
                lake.write_report("verification", run_id, ".md", render_markdown(res.verification))
                lake.write_report("ingest", run_id, ".json", res.summary)
                ledger.save()
                _emit(res.summary)
                return res.exit_code
            if cmd == "restore":
                doc_id, _, version = args.target.partition("@")
                summary = ops.restore(lake, ledger, targets, doc_id, version, run_id)
            elif cmd == "delete":
                summary = ops.delete(lake, ledger, targets, args.doc_id, args.version, run_id)
            elif cmd == "count":
                _emit(ops.count(ledger, targets, args.doc_id))
                return 0
            elif cmd == "status":
                _emit(ops.status(ledger, targets))
                return 0
            elif cmd == "build-index":
                summary = _build_index(args, settings, lake, ledger, targets, client, run_id)
            else:   # unregister
                summary = _unregister(args, settings, ledger, client, run_id)
            lake.write_report("ingest", run_id, ".json", summary)
            ledger.save()
            _emit(summary)
            return int(summary.get("exit", 0))
    except ops.OpError as exc:
        log("operation failed", error=str(exc))
        return 4
    except (LockHeld, LedgerError) as exc:
        log("fatal", error=str(exc))
        return 3
    except Exception as exc:       # Chroma or Ollama down, embedding failure: fail the Job
        log("fatal", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        return 3
    return 2


class _nullcontext:                # contextlib.nullcontext, kept tiny to avoid another import
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def _verify_only(lake, ledger, settings, run_id: str) -> int:  # type: ignore[no-untyped-def]
    """Run the four checks over the inbox without changing anything: a dry run for rehearsal."""
    from .catalog import load_catalog, scan_inbox
    from .extract import extract
    from .incremental import _extract, SyncConfig
    from .report import build_verification_report, render_markdown
    from .verify import RunSeen, Thresholds, verify_document

    th = Thresholds.from_env()
    cfg = SyncConfig(run_id=run_id, thresholds=th, extract=extract, ocr=settings.ocr_enabled)
    rows, _ = load_catalog(lake.inbox)
    seen, docs = RunSeen(), []
    try:
        embed = make_embedder(settings)
        embed(["ping"])
    except Exception:
        embed = None
    for f in scan_inbox(lake.inbox):
        ctx, _doc = _extract(f, cfg, rows)
        v = verify_document(ctx, ledger, th, embed, lambda d, ver: lake.read_docvec(d, ver), seen)
        docs.append({"file": f.rel, "sha256": f.sha, "pages": ctx.page_count,
                     "resolved": ctx.meta.as_dict(), "outcome": v.outcome, "destination": "",
                     "checks": {k: c.as_dict() for k, c in v.checks.items()}})
    report = build_verification_report(run_id, settings.embed_model, "", th.as_dict(), docs, [], [])
    print(render_markdown(report))
    _emit({"type": "ingest_summary", "schema": 1, "run_id": run_id, "command": "verify-only",
           "documents": len(docs), "exit": 0})
    return 0


def _build_index(args, settings, lake, ledger, targets, client, run_id):  # type: ignore[no-untyped-def]
    import dataclasses

    from . import ops
    from .extract import extract
    from .incremental import Target
    from .index import ChromaIndex

    s = dataclasses.replace(settings, collection=args.collection, embed_model=args.embed_model,
                            chunk_size=args.chunk_size or settings.chunk_size,
                            chunk_overlap=args.chunk_overlap if args.chunk_overlap is not None
                            else settings.chunk_overlap)
    version = os.environ.get("EMBED_VERSION_CANDIDATE", "")
    target = Target(ChromaIndex(client, args.collection, s, version), make_embedder(s, shorten=True),
                    s.embed_model, s.chunk_size, s.chunk_overlap, version, "candidate")
    from .embed import STATS
    STATS["shortened"] = 0
    summary = ops.build_index(lake, ledger, target, targets[0], extract, settings.ocr_enabled, run_id,
                              register=args.register)
    summary["chunks_shortened"] = STATS["shortened"]
    if STATS["shortened"]:
        log("candidate embedding model refused some chunks as too long; embedded from a halved text",
            chunks_shortened=STATS["shortened"], model=args.embed_model)
    return summary


def _unregister(args, settings, ledger, client, run_id):  # type: ignore[no-untyped-def]
    from . import ops
    from .incremental import Target
    from .index import ChromaIndex

    info = ledger.indexes.get(args.collection, {})
    target = Target(ChromaIndex(client, args.collection, settings), make_embedder(settings),
                    info.get("embed_model", settings.embed_model), 0, 0)
    return ops.unregister(ledger, target, run_id)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and maintain the RAHBAR index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("sync", help="verify, quarantine and update incrementally")
    sub.add_parser("verify-only", help="run the four checks, change nothing")
    sub.add_parser("status", help="ledger summary")
    p = sub.add_parser("restore", help="make an archived version current")
    p.add_argument("target", help="<doc_id>@<version>")
    p = sub.add_parser("delete", help="remove a document from the index")
    p.add_argument("doc_id")
    p.add_argument("--version")
    p = sub.add_parser("count", help="chunks per document and orphan check (read-only)")
    p.add_argument("--doc-id")
    p = sub.add_parser("report", help="print a stored report")
    p.add_argument("--kind", default="verification", choices=["verification", "ingest"])
    p.add_argument("--run")
    p.add_argument("--last", action="store_true")
    p.add_argument("--md", action="store_true")
    p = sub.add_parser("build-index", help="build a candidate collection from the lake")
    p.add_argument("--collection", required=True)
    p.add_argument("--embed-model", required=True)
    p.add_argument("--chunk-size", type=int)
    p.add_argument("--chunk-overlap", type=int)
    p.add_argument("--register", action="store_true", default=True)
    p = sub.add_parser("unregister", help="drop a candidate collection")
    p.add_argument("--collection", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit 1 is reserved for 'finished, some documents quarantined' (job_entry.sh maps it to success), so an
    uncaught exception anywhere here must never surface as 1 (a traceback exits 1 by default): it is 3."""
    args = _parser().parse_args(argv)
    try:
        return _main(args)
    except Exception as exc:
        log("fatal", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        return 3


def _main(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.command:
        return run_command(args, settings)
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        pod=os.environ.get("HOSTNAME", "-"))
    started = time.perf_counter()
    try:
        if args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
        else:
            count = run_pipeline(settings)
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2
    log("indexer finished", chunks=count, seconds=round(time.perf_counter() - started, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
