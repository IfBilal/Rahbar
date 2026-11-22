"""Calibrate the verification thresholds on real documents (docs/a3-ragops/05 §4, task T07).

    python -m pipeline.calibrate corpus/raw [--embed] [--no-ocr] [--out docs/a3-evidence/verify-calibration.md]

Runs the extraction and the quality and completeness measurements on every document in a
folder WITHOUT any catalog (so it also shows what the unseen-document path resolves), prints one
row per document, and the pairwise shingle-Jaccard matrix. With --embed it also prints the
document-vector cosine matrix (needs Ollama). Set each threshold between the worst legitimate
document and the planted problem, and commit the output as the calibration evidence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .catalog import resolve_metadata, scan_inbox
from .config import get_settings
from .extract import extract
from .incremental import SyncConfig, _extract
from .verify import (
    Thresholds, build_docvec, check_completeness, check_quality, cosine, jaccard_estimate,
    text_stats,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure verification signals on real documents.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--embed", action="store_true", help="also compute document vectors (Ollama)")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--out", type=Path, help="also write the report as Markdown")
    args = ap.parse_args()
    th = Thresholds.from_env()
    cfg = SyncConfig(run_id="calibrate", thresholds=th, extract=extract, ocr=not args.no_ocr)
    files = scan_inbox(args.folder)
    rows, vecs = [], {}
    embed = None
    if args.embed:
        from .embed import embed as run_embed
        settings = get_settings()
        embed = lambda texts: run_embed(texts, settings)          # noqa: E731
    lines = ["| document | pages | chars | chars/page | word ratio | wordlike | alpha | quality | completeness | title (route) | version | doc_id |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |"]
    for f in files:
        ctx, _ = _extract(f, cfg, {})
        meta = resolve_metadata(f, ctx.pages, {})
        ctx.meta = meta
        st = text_stats(ctx.text)
        q, c = check_quality(ctx, th), check_completeness(ctx, th)
        signals = ",".join(s["signal"] for s in c.evidence.get("signals", [])) or "-"
        lines.append(
            f"| {f.rel} | {ctx.page_count} | {int(st['chars'])} | "
            f"{st['chars'] / max(ctx.page_count, 1):.0f} | {st['word_ratio']:.2f} | "
            f"{st['wordlike_ratio']:.2f} | {st['alpha_share']:.2f} | {q.code} | {c.code} [{signals}] | "
            f"{(meta.title.value or '-')[:38]} ({meta.title.route}) | {meta.version.value or '-'} "
            f"({meta.version.route}) | {meta.doc_id} |")
        vecs[f.rel] = build_docvec(ctx.pages, embed) if embed and ctx.pages else \
            {"vector": [], "sketch": __import__("pipeline.verify", fromlist=["sketch"]).sketch(ctx.text)}
        rows.append(f.rel)
    out = ["# Verification calibration", "", *lines, "", "## Shingle Jaccard (estimate)", "",
           "| | " + " | ".join(r[:14] for r in rows) + " |", "| --- |" + " --- |" * len(rows)]
    for a in rows:
        out.append(f"| {a[:14]} | " + " | ".join(
            f"{jaccard_estimate(vecs[a]['sketch'], vecs[b]['sketch']):.2f}" for b in rows) + " |")
    if embed:
        out += ["", "## Document-vector cosine", "", "| | " + " | ".join(r[:14] for r in rows) + " |",
                "| --- |" + " --- |" * len(rows)]
        for a in rows:
            out.append(f"| {a[:14]} | " + " | ".join(
                f"{cosine(vecs[a]['vector'], vecs[b]['vector']):.3f}" if vecs[a]["vector"] and
                vecs[b]["vector"] else "-" for b in rows) + " |")
    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
