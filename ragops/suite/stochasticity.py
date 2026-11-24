"""Compare two runs of the same suite (docs/a3-ragops/06 section 7, contract 14 section 5.2).

    python -m ragops.suite.stochasticity run1.json run2.json [--out table.md]

Prints metric, run1, run2, |delta| and an explanation column. The explanations are the
EXPECTED pattern to test, not a verdict: a non-zero delta in a retrieval metric is a finding to
investigate (cache? index changed between runs? ties?) before it goes in the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .flatten import flatten

EXPLAIN = (("latency", "wall-clock time cannot be fixed; always differs"),
           ("embed_ms", "wall-clock time cannot be fixed; always differs"),
           ("retrieval_ms", "wall-clock time cannot be fixed; always differs"),
           ("determinism", "float rounding inside the embedding service"),
           ("faithfulness", "generation or judge wording can differ across runs"),
           ("citation", "depends on the generated answer"),
           ("abstention", "depends on the generated answer"),
           ("fallback", "depends on the generated answer"),
           ("tokens", "depends on the generated answer"))
EXPECT_ZERO = ("module.paraphrase", "module.unrelated", "module.gap", "module.pair_accuracy",
               "component.")


def explain(metric: str, delta: float | None) -> str:
    if delta is None:
        return "missing in one run"
    for key, why in EXPLAIN:
        if key in metric:
            return why if delta else "identical"
    if delta == 0:
        return "identical"
    if any(metric.startswith(p) for p in EXPECT_ZERO):
        return "UNEXPECTED: retrieval and embedding should be identical - investigate"
    return "differs"


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    fa, fb = flatten(a), flatten(b)
    rows = []
    for metric in sorted(set(fa) | set(fb)):
        x, y = fa.get(metric), fb.get(metric)
        delta = None if x is None or y is None else round(abs(x - y), 6)
        rows.append({"metric": metric, "run1": x, "run2": y, "abs_delta": delta,
                     "explanation": explain(metric, delta)})
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    out = [f"{'METRIC':<46} {'RUN1':>10} {'RUN2':>10} {'|DELTA|':>10}  EXPLANATION"]
    for r in rows:
        f = lambda v: "-" if v is None else f"{v:.4f}"  # noqa: E731
        out.append(f"{r['metric']:<46} {f(r['run1']):>10} {f(r['run2']):>10} "
                   f"{f(r['abs_delta']):>10}  {r['explanation']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stochasticity table for two suite runs.")
    ap.add_argument("run1", type=Path)
    ap.add_argument("run2", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    try:
        a = json.loads(args.run1.read_text(encoding="utf-8"))
        b = json.loads(args.run2.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read a result: {exc}", file=sys.stderr)
        return 2
    notes = []
    for k in ("config_hash", "golden_hash", "corpus_digest", "seed"):
        if a.get(k) != b.get(k):
            notes.append(f"WARNING: {k} differs between the runs ({a.get(k)!r} vs {b.get(k)!r})")
    text = render(compare(a, b))
    print("\n".join(notes + [text]))
    if args.out:
        args.out.write_text("```\n" + "\n".join(notes + [text]) + "\n```\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
