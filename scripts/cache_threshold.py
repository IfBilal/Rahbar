#!/usr/bin/env python3
"""Choose CACHE_THRESHOLD with data (case study 3.3): embed question pairs with the pinned
model exactly as the API does, and report hits and false hits per candidate threshold.
The rule: the lowest threshold with zero false hits.

    python scripts/cache_threshold.py --ollama http://localhost:11434
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.retrieval.embedder import OllamaEmbedder  # noqa: E402

# Same meaning, different words: a hit here saves a generation.
PARAPHRASES = [
    ("What is the deadline to withdraw from a course?",
     "When is the last day I can withdraw from a course?"),
    ("What minimum CGPA does an undergraduate need to avoid academic warning?",
     "What CGPA do I need to stay off academic warning?"),
    ("What is the paper rechecking fee per course?",
     "How much does it cost to get a paper rechecked?"),
    ("How many courses can a student repeat in a summer semester?",
     "What is the maximum number of courses I can repeat in summer?"),
    ("What does clause 1.21 of the academic rules require?",
     "What does rule 1.21 of the academic regulations say?"),
    ("What percentage of tuition fee is refunded if I leave within the first 15 days of classes?",
     "How much tuition do I get back if I drop out in the first 15 days?"),
]
# Different answers that look alike: a hit here serves a wrong answer to everyone.
NEAR_MISSES = [
    ("What is the deadline to withdraw from a course?",
     "What is the deadline to add or drop a course?"),
    ("What is the deadline to withdraw from a course?",
     "Under the older 2023 rules, what was the deadline to withdraw from a course?"),
    ("What is the paper rechecking fee per course?",
     "What is the campus transfer fee?"),
    ("What minimum CGPA does an undergraduate need to avoid academic warning?",
     "What minimum CGPA does an MS student need to avoid academic warning?"),
    ("What is the tuition fee per credit hour for BS?",
     "What is the tuition fee per credit hour for MS?"),
    ("How many courses can a student repeat in a summer semester?",
     "How many courses can a student take in a regular semester?"),
    ("Which students are placed on the Rector's List of Honors?",
     "Which students are placed on the Dean's List of Honors?"),
    ("What is the retake final exam fee per course?",
     "What is the retake sessional exam fee per course?"),
]
THRESHOLDS = (0.85, 0.90, 0.92, 0.95, 0.97)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--model", default="nomic-embed-text")
    a = ap.parse_args()
    e = OllamaEmbedder(a.ollama, a.model)
    rows = [(kind, q1, q2, cosine(e.embed(q1), e.embed(q2)))
            for kind, pairs in (("paraphrase", PARAPHRASES), ("near-miss", NEAR_MISSES))
            for q1, q2 in pairs]
    for kind, q1, q2, s in sorted(rows, key=lambda r: -r[3]):
        print(f"{s:.4f}  {kind:<10}  {q1}  |  {q2}")
    print()
    print("threshold  paraphrase hits  false hits (near-misses at or above)")
    chosen = None
    for t in THRESHOLDS:
        hits = sum(1 for k, *_, s in rows if k == "paraphrase" and s >= t)
        false = [(q2, round(s, 4)) for k, q1, q2, s in rows if k == "near-miss" and s >= t]
        print(f"  {t:.2f}     {hits}/{len(PARAPHRASES)}               {len(false)}  {false[:2]}")
        if not false and chosen is None:
            chosen = t
    print(f"\nlowest threshold with zero false hits: {chosen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
