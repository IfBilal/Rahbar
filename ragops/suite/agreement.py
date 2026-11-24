"""Hand labels versus the judge (docs/a3-ragops/06 section 6.3).

    python -m ragops.suite.agreement sample RESULT.json [--n 12] [--seed 7]
    python -m ragops.suite.agreement score  RESULT.json eval/judge_labels.jsonl [--write]

`sample` prints answers to label WITHOUT showing the judge's label, spread over the judge's
labels and including abstentions. `score` compares the human labels with the judge's, prints
raw agreement (3-class and binary supported-vs-not) and Cohen's kappa, and with --write stores
them in the result's `levels.endpoint.judge`. Eight labels give a wide interval: the numbers
are printed with their sample size.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from .metrics import agreement, cohen_kappa


def sample(result: dict[str, Any], n: int, seed: int) -> list[dict[str, Any]]:
    rows = [r for r in result.get("per_question", []) if r.get("answer") is not None]
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = r.get("judge_label") or ("abstained" if not r.get("answered_from_context") else "other")
        buckets.setdefault(key, []).append(r)
    picked: list[dict[str, Any]] = []
    while len(picked) < n and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(picked) < n:
                picked.append(buckets[key].pop(rng.randrange(len(buckets[key]))))
    rng.shuffle(picked)
    return picked


def score(result: dict[str, Any], labels: list[dict[str, Any]]) -> dict[str, Any]:
    judge = {r["id"]: r.get("judge_label") for r in result.get("per_question", [])}
    pairs = [(str(lab["human_label"]), str(judge[lab["question_id"]]))
             for lab in labels
             if lab.get("result_run") in (None, result.get("run_id"))
             and judge.get(lab["question_id"])]
    h, j = [p[0] for p in pairs], [p[1] for p in pairs]
    hb = ["supported" if x == "supported" else "other" for x in h]
    jb = ["supported" if x == "supported" else "other" for x in j]
    return {"n": len(pairs), "agreement_3class": agreement(h, j), "agreement": agreement(hb, jb),
            "cohen_kappa": cohen_kappa(hb, jb),
            "disagreements": [{"human": a, "judge": b} for a, b in pairs if a != b]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge-versus-human agreement.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("result", type=Path)
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--seed", type=int, default=7)
    c = sub.add_parser("score")
    c.add_argument("result", type=Path)
    c.add_argument("labels", type=Path)
    c.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = json.loads(args.result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.result}: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "sample":
        for r in sample(result, args.n, args.seed):
            print(f"--- {r['id']}  (run {result.get('run_id')})\nANSWER: {r.get('answer')}\n")
        return 0
    try:
        labels = [json.loads(x) for x in args.labels.read_text(encoding="utf-8").splitlines()
                  if x.strip()]
    except (OSError, ValueError) as exc:
        print(f"cannot read labels: {exc}", file=sys.stderr)
        return 2
    out = score(result, labels)
    print(json.dumps(out, indent=2))
    if args.write:
        block = result["levels"]["endpoint"].setdefault("judge", {})
        block.update({"hand_labels": out["n"], "agreement": out["agreement"],
                      "cohen_kappa": out["cohen_kappa"]})
        args.result.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
