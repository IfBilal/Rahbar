"""Diff two suite results (docs/a3-ragops/09 section 5, 14 section 5.2).

    python -m ragops.suite.diff BEFORE.json AFTER.json [--allow-corpus-change]

Reports each metric's change and, per question, what moved (recall, abstention, citation
validity), split into the COMMON subset (backward compatibility: must not regress) and the
NEW subset (forward adaptability: questions that only exist in AFTER). A corpus-digest change
is refused unless --allow-corpus-change is given; that flag exists only for the drift
experiment (E3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .flatten import flatten
from .metrics import mean


def per_question_changes(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    qa = {r["id"]: r for r in a.get("per_question", [])}
    qb = {r["id"]: r for r in b.get("per_question", [])}
    changes = []
    for qid in sorted(set(qa) & set(qb)):
        for key in ("recall@5", "recall@3", "rr", "judge_label", "answered_from_context"):
            if qa[qid].get(key) != qb[qid].get(key):
                changes.append({"id": qid, "field": key, "before": qa[qid].get(key),
                                "after": qb[qid].get(key)})
    return changes


def subset_recall(rows: list[dict[str, Any]], ids: set[str]) -> float | None:
    vals = [r.get("recall@5") for r in rows if r["id"] in ids and r.get("recall@5") is not None]
    m = mean(vals)
    return None if m is None else round(m, 4)


def diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    fa, fb = flatten(a), flatten(b)
    metrics = []
    for m in sorted(set(fa) | set(fb)):
        x, y = fa.get(m), fb.get(m)
        metrics.append({"metric": m, "before": x, "after": y,
                        "delta": None if x is None or y is None else round(y - x, 4)})
    ids_a = {r["id"] for r in a.get("per_question", [])}
    ids_b = {r["id"] for r in b.get("per_question", [])}
    common, new = ids_a & ids_b, ids_b - ids_a
    return {"metrics": metrics, "changes": per_question_changes(a, b),
            "common_recall@5": {"before": subset_recall(a.get("per_question", []), common),
                                "after": subset_recall(b.get("per_question", []), common),
                                "n": len(common)},
            "new_recall@5": {"after": subset_recall(b.get("per_question", []), new),
                             "n": len(new), "ids": sorted(new)},
            "retired": sorted(ids_a - ids_b)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diff two suite results.")
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--allow-corpus-change", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        a = json.loads(args.before.read_text(encoding="utf-8"))
        b = json.loads(args.after.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read a result: {exc}", file=sys.stderr)
        return 2
    if a.get("corpus_digest") != b.get("corpus_digest") and not args.allow_corpus_change:
        print("REFUSED: the corpus digest differs (the corpus changed between the runs). "
              "Pass --allow-corpus-change only for the drift experiment (E3).", file=sys.stderr)
        return 2
    d = diff(a, b)
    if args.json:
        print(json.dumps(d, indent=2))
        return 0
    print(f"{'METRIC':<46} {'BEFORE':>10} {'AFTER':>10} {'DELTA':>10}")
    for m in d["metrics"]:
        if m["delta"] not in (0, 0.0):
            f = lambda v: "-" if v is None else f"{v:.4f}"  # noqa: E731
            print(f"{m['metric']:<46} {f(m['before']):>10} {f(m['after']):>10} {f(m['delta']):>10}")
    c, n = d["common_recall@5"], d["new_recall@5"]
    print(f"\nbackward compatibility (common subset, n={c['n']}): recall@5 {c['before']} -> {c['after']}")
    print(f"forward adaptability (new questions, n={n['n']}): recall@5 {n['after']}  {n['ids']}")
    print(f"retired (in BEFORE only): {d['retired']}")
    print(f"{len(d['changes'])} per-question change(s):")
    for ch in d["changes"][:40]:
        print(f"  {ch['id']} {ch['field']}: {ch['before']} -> {ch['after']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
