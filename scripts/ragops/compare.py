#!/usr/bin/env python3
"""Side-by-side comparison of suite results for the change experiment (Part C1), as Markdown.

    python scripts/ragops/compare.py baseline=eval/results/A.json cand-x=eval/results/B.json[+module=eval/results/M.json] ...

Each column is a result file; `+module=FILE` substitutes the module level from another run (used where the
module level of the original run measured the wrong model, see docs/a3-evidence/C/C1-module-minilm-corrected.txt).
The gate verdict row is read from `<result>.decision.json` next to each candidate file, when present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROWS = [
    ("module", "paraphrase mean cosine", ("module", "paraphrase_mean_cos")),
    ("module", "unrelated mean cosine", ("module", "unrelated_mean_cos")),
    ("module", "gap", ("module", "gap")),
    ("module", "embed ms per chunk (mean)", ("module", "embed_ms_mean")),
    ("component", "recall@3", ("component", "clean", "recall@3")),
    ("component", "recall@5", ("component", "clean", "recall@5")),
    ("component", "MRR", ("component", "clean", "mrr")),
    ("component", "nDCG@5", ("component", "clean", "ndcg@5")),
    ("component", "noisy recall@5", ("component", "noisy", "recall@5")),
    ("endpoint", "faithfulness (judge)", ("endpoint", "faithfulness")),
    ("endpoint", "abstention correctness", ("endpoint", "abstention_correctness")),
    ("endpoint", "false abstention rate", ("endpoint", "false_abstention_rate")),
    ("endpoint", "citation validity", ("endpoint", "citation_validity")),
    ("endpoint", "latency p50 (s)", ("endpoint", "latency_p50_s")),
    ("endpoint", "latency p95 (s)", ("endpoint", "latency_p95_s")),
]


def dig(levels: dict, path: tuple[str, ...]):
    cur = levels
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def fmt(v) -> str:
    return "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def main(argv: list[str]) -> int:
    cols = []
    for arg in argv:
        label, _, spec = arg.partition("=")
        main_file, _, module_file = spec.partition("+module=")
        res = json.loads(Path(main_file).read_text())
        levels = dict(res["levels"])
        if module_file:
            levels["module"] = json.loads(Path(module_file).read_text())["levels"]["module"]
        dec = Path(main_file.replace(".json", ".decision.json"))
        verdict = json.loads(dec.read_text())["overall"].upper() if dec.exists() else "(baseline)"
        cols.append((label, levels, res.get("target", {}), verdict, bool(module_file)))
    print("| Level | Metric | " + " | ".join(c[0] for c in cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    print("| target | embedding model | " + " | ".join(str(c[2].get("embed_model")) for c in cols) + " |")
    for level, name, path in ROWS:
        print(f"| {level} | {name} | " + " | ".join(fmt(dig(c[1], path)) for c in cols) + " |")
    print("| **gate** | **verdict** | " + " | ".join(f"**{c[3]}**" for c in cols) + " |")
    notes = [c[0] for c in cols if c[4]]
    if notes:
        print(f"\nModule level for {', '.join(notes)} is from the corrected module-only run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
