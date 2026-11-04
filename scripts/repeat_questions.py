#!/usr/bin/env python3
"""Ask a few golden questions several times and record what changes between runs
(failure experiment F: temperature). Standard library only.

    python scripts/repeat_questions.py --api http://<ingress-ip> --runs 2 --out f.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

QUESTIONS = {
    "q01": ("What minimum CGPA does an undergraduate need to avoid academic warning?", "2.0"),
    "v01": ("What is the deadline to withdraw from a course?", "makeup week"),
    "e02": ("What is the paper rechecking fee per course?", "500"),
}
FALLBACK = "I could not produce a reliable"


def ask(api: str, question: str) -> tuple[dict, float]:
    req = urllib.request.Request(f"{api}/api/ask", json.dumps({"question": question}).encode(),
                                 {"Host": "rahbar.local", "Content-Type": "application/json"})
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r), time.perf_counter() - started


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for qid, (question, expect) in QUESTIONS.items():
        for run in range(1, a.runs + 1):
            r, seconds = ask(a.api, question)
            retrieved = {(x["source"], x["section"], x["page"]) for x in r["retrieved"]}
            row = {"id": qid, "run": run, "seconds": round(seconds, 1),
                   "answered_from_context": r["answered_from_context"],
                   "fallback": r["answer"].startswith(FALLBACK),
                   "expect_found": expect.lower() in r["answer"].lower(),
                   "citations_valid": all((c["source"], c["section"], c["page"]) in retrieved
                                          for c in r["citations"]),
                   "answer": r["answer"]}
            rows.append(row)
            print(f"{qid} run {run}: {seconds:6.1f}s answered={row['answered_from_context']} "
                  f"fallback={row['fallback']} expect={row['expect_found']} :: {r['answer'][:160]}",
                  flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    n = len(rows)
    print(f"\nexpect found {sum(r['expect_found'] for r in rows)}/{n}, fallbacks "
          f"{sum(r['fallback'] for r in rows)}/{n}, distinct answers per question "
          f"{ {q: len({r['answer'] for r in rows if r['id'] == q}) for q in QUESTIONS} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
