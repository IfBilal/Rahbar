"""The golden set: loading, validating, and choosing which questions run
(docs/a3-ragops/06 section 3).

    python -m ragops.suite.golden --validate eval/golden.jsonl [--ledger ledger.json]

Exit 0 when the set is valid and meets every quota, 1 with a list of violations otherwise.
The PDF's minimums: >= 25 questions; >= 15 answerable (each with a ground-truth document and
page); >= 5 unanswerable; >= 5 hard; >= 8 written by hand; every question labelled human or
synthetic; >= 8 synthetic questions reviewed by hand. The plan builds >= 30 so that both the
disjoint and the overlapping reading of those counts are met.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CATEGORIES = {"answerable", "unanswerable", "hard"}
HARD_KINDS = {"paraphrase", "multi_chunk", "batch_b"}
ORIGINS = {"human", "synthetic"}
REVIEW_OK = {"ok", "edited"}
REQUIRED = ("id", "question", "category", "answerable", "origin", "gold")

QUOTAS = {"total": 25, "answerable": 15, "unanswerable": 5, "hard": 5, "human": 8,
          "synthetic_reviewed": 8}


def load_golden(path: Path) -> list[dict[str, Any]]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(f"{path}:{n}: not valid JSON ({exc})") from exc
    return rows


def golden_hash(path: Path) -> str:
    """Hash of the file's questions (not whitespace): recorded in every result file."""
    rows = load_golden(path)
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def ledger_pages(ledger: dict[str, Any]) -> dict[str, int]:
    """{document file name -> page count} for every document version the ledger knows."""
    pages: dict[str, int] = {}
    for entry in (ledger.get("documents") or {}).values():
        for rec in (entry.get("versions") or {}).values():
            if rec.get("status") in ("current", "archived"):
                pages[str(rec.get("file_name", "")).lower()] = int(rec.get("pages") or 0)
    return pages


def validate(rows: list[dict[str, Any]], docs: dict[str, int] | None = None,
             ) -> tuple[list[str], dict[str, int]]:
    """Return (violations, quota counts). `docs` (file name -> page count) enables the
    check that every gold document exists and every gold page is inside it."""
    bad: list[str] = []
    seen_ids: set[str] = set()
    seen_q: set[str] = set()
    counts = {"total": len(rows), "answerable": 0, "unanswerable": 0, "hard": 0, "human": 0,
              "synthetic": 0, "synthetic_reviewed": 0, "answerable_incl_hard": 0}
    for i, row in enumerate(rows, start=1):
        qid = str(row.get("id", f"#{i}"))
        for key in REQUIRED:
            if key not in row:
                bad.append(f"{qid}: missing field {key!r}")
        if qid in seen_ids:
            bad.append(f"{qid}: duplicate id")
        seen_ids.add(qid)
        text = " ".join(str(row.get("question", "")).lower().split())
        if text in seen_q:
            bad.append(f"{qid}: duplicate question text")
        seen_q.add(text)
        cat = row.get("category")
        if cat not in CATEGORIES:
            bad.append(f"{qid}: category must be one of {sorted(CATEGORIES)}")
        else:
            counts[cat] += 1
        gold = row.get("gold") or []
        answerable = bool(row.get("answerable"))
        if cat == "unanswerable" and answerable:
            bad.append(f"{qid}: an unanswerable question cannot be answerable")
        if cat in ("answerable", "hard") and not answerable:
            bad.append(f"{qid}: category {cat} must have answerable=true")
        if answerable and not gold:
            bad.append(f"{qid}: answerable but gold is empty (document and page are required)")
        if not answerable and gold:
            bad.append(f"{qid}: unanswerable but gold is not empty")
        if answerable:
            counts["answerable_incl_hard"] += 1
        for g in gold:
            if not g.get("doc") or not isinstance(g.get("page"), int) or g["page"] < 1:
                bad.append(f"{qid}: gold needs a document and an integer page >= 1: {g}")
            elif docs is not None:
                pages = docs.get(str(g["doc"]).lower())
                if pages is None:
                    bad.append(f"{qid}: gold document {g['doc']!r} is not in the ledger")
                elif pages and g["page"] > pages:
                    bad.append(f"{qid}: gold page {g['page']} is beyond {g['doc']} ({pages} pages)")
        if cat == "hard" and row.get("hard_kind") not in HARD_KINDS:
            bad.append(f"{qid}: hard question needs hard_kind in {sorted(HARD_KINDS)}")
        origin = row.get("origin")
        if origin not in ORIGINS:
            bad.append(f"{qid}: origin must be human or synthetic")
        elif origin == "human":
            counts["human"] += 1
        else:
            counts["synthetic"] += 1
            review = row.get("review") or {}
            if review.get("verdict") in REVIEW_OK and review.get("by") and review.get("date"):
                counts["synthetic_reviewed"] += 1
            else:
                bad.append(f"{qid}: synthetic question has no hand review (by, date, verdict ok|edited)")
    for name, minimum in QUOTAS.items():
        if counts[name] < minimum:
            bad.append(f"quota: {name} is {counts[name]}, the PDF requires at least {minimum}")
    return bad, counts


def applicable(row: dict[str, Any], batches: set[str]) -> tuple[bool, str]:
    """Does this question run when the ingested batches are `batches`? Batch-B questions need
    their batch; a question retired by a batch stops being valid once that batch is ingested."""
    need = {str(b).upper() for b in row.get("requires_batch") or []}
    if not need <= {b.upper() for b in batches}:
        return False, f"requires batch {sorted(need - {b.upper() for b in batches})} not ingested"
    retired = row.get("retired_by_batch")
    if retired and str(retired).upper() in {b.upper() for b in batches}:
        return False, f"retired by batch {retired}"
    return True, ""


def select(rows: list[dict[str, Any]], batches: set[str]
           ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    run: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        ok, why = applicable(row, batches)
        if ok:
            run.append(row)
        else:
            skipped.append({"id": str(row.get("id")), "reason": why})
    return run, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate the golden set.")
    ap.add_argument("--validate", type=Path, required=True, metavar="GOLDEN.jsonl")
    ap.add_argument("--ledger", type=Path, help="ledger.json: also check gold documents and pages")
    args = ap.parse_args(argv)
    try:
        rows = load_golden(args.validate)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    docs = None
    if args.ledger:
        docs = ledger_pages(json.loads(args.ledger.read_text(encoding="utf-8")))
    problems, counts = validate(rows, docs)
    print("golden set quotas (PDF minimum in brackets):")
    for name, minimum in QUOTAS.items():
        print(f"  {name:<20} {counts[name]:>3}  [{minimum}]")
    print(f"  {'answerable incl. hard':<20} {counts['answerable_incl_hard']:>3}")
    print(f"hash {golden_hash(args.validate)}")
    for p in problems:
        print(f"VIOLATION {p}")
    print("VALID" if not problems else f"INVALID: {len(problems)} violation(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
