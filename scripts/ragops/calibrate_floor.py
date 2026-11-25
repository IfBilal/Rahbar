#!/usr/bin/env python3
"""Calibrate a candidate's RELEVANCE_FLOOR with the Assignment-02 method (docs/a3-ragops/07 2.3).

Cosine scores are not comparable across embedding models, so nomic's 0.60 cannot be reused. The
method: the highest floor that keeps every answerable golden question's relevant passage above it.
For each answerable question the best score among retrieved chunks that match a gold (document,
page) is taken; the floor is the largest multiple of 0.05 at or below (lowest such score - 0.02).
Questions whose gold passage is not in the top-k at all are listed and excluded (no floor can save
them; they show up as recall misses in the suite). Unanswerable questions are shown for reference:
their top-1 score against the floor says how much of the abstention job the floor does alone.

    kubectl -n rahbar port-forward svc/api-candidate 8002:8000 &
    EVAL_TOKEN=$(kubectl get secret ragops-eval-token -n rahbar -o jsonpath='{.data.token}' | base64 -d) \
      python scripts/ragops/calibrate_floor.py --url http://localhost:8002 --batches A
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import httpx


def suggest_floor(lowest_gold_score: float, margin: float = 0.02, step: float = 0.05) -> float:
    """Largest multiple of `step` that is <= lowest_gold_score - margin (never below 0)."""
    return max(0.0, round(math.floor((lowest_gold_score - margin) / step + 1e-9) * step, 2))


def best_gold_score(candidates: list[dict], gold: list[dict]) -> float | None:
    wanted = {(g["doc"].lower(), g["page"]) for g in gold}
    scores = [c["score"] for c in candidates if (str(c["source"]).lower(), c["page"]) in wanted]
    return max(scores) if scores else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    ap.add_argument("--batches", default="A")
    ap.add_argument("--k", type=int, default=20)
    a = ap.parse_args()
    token = os.environ.get("EVAL_TOKEN", "")
    http = httpx.Client(timeout=120.0, headers={"X-Eval-Token": token} if token else {})
    batches = {b.strip().upper() for b in a.batches.split(",")}
    rows = [json.loads(ln) for ln in a.golden.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    gold_scores: list[float] = []
    print(f"{'id':6s} {'category':12s} {'best gold score':>16s}  top-1 score")
    unans_top1: list[float] = []
    for r in rows:
        need = {str(b).upper() for b in r.get("requires_batch") or []}
        if not need <= batches or (r.get("retired_by_batch") and str(r["retired_by_batch"]).upper() in batches):
            continue
        resp = http.post(f"{a.url}/api/retrieve", json={"question": r["question"], "k": a.k})
        resp.raise_for_status()
        cands = resp.json()["candidates"]
        top1 = cands[0]["score"] if cands else float("nan")
        if r["answerable"]:
            s = best_gold_score(cands, r["gold"])
            print(f"{r['id']:6s} {r['category']:12s} {('NOT IN TOP-' + str(a.k)) if s is None else f'{s:.4f}':>16s}  {top1:.4f}")
            if s is not None:
                gold_scores.append(s)
        else:
            unans_top1.append(top1)
            print(f"{r['id']:6s} {r['category']:12s} {'-':>16s}  {top1:.4f}")
    if not gold_scores:
        print("no answerable question had its gold passage in the top-k", file=sys.stderr)
        return 1
    lowest = min(gold_scores)
    floor = suggest_floor(lowest)
    print(f"\nanswerable questions with gold in top-{a.k}: {len(gold_scores)}; lowest best-gold score {lowest:.4f}")
    print(f"suggested RELEVANCE_FLOOR = {floor:.2f}  (largest multiple of 0.05 <= {lowest:.4f} - 0.02)")
    if unans_top1:
        above = sum(1 for t in unans_top1 if t >= floor)
        print(f"unanswerable questions: top-1 scores {min(unans_top1):.4f}..{max(unans_top1):.4f}; "
              f"{above} of {len(unans_top1)} are at or above the floor (the model must abstain on those)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
