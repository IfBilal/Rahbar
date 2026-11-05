#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Given: talking to the API, reading the golden set, writing results.json, the exit
code. Ours: recall_at_k, citation_validity, summarise and gate (docs/PIPELINE.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _norm(text: str | None) -> str:
    """Compare labels the way a reader would: case, curly quotes and spacing ignored."""
    text = unicodedata.normalize("NFKC", text or "").replace("\u2019", "'").replace("\u2018", "'")
    return " ".join(text.lower().split())


def _matches(gold: dict, ref: dict) -> bool:
    """A retrieved passage matches a golden (source, section) pair when the source is the
    same file and the passage's section label contains the golden section. The chunker
    labels sections with their heading path, so 'Academic Warning/Probation' matches
    '5. Academic Assessment > Academic Warning/Probation'."""
    return (_norm(gold.get("source")) == _norm(ref.get("source"))
            and _norm(gold.get("section")) in _norm(ref.get("section")))


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions)."""
    if not relevant:
        return None
    top = retrieved[:k]
    found = sum(1 for gold in relevant if any(_matches(gold, ref) for ref in top))
    return found / len(relevant)


def _cites(citation: dict, ref: dict) -> bool:
    same = (_norm(citation.get("source")) == _norm(ref.get("source"))
            and _norm(citation.get("section")) == _norm(ref.get("section")))
    return same and (citation.get("page") is None or citation.get("page") == ref.get("page"))


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    valid = sum(1 for c in citations if any(_cites(c, ref) for ref in retrieved))
    return valid / len(citations)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    per_question = []
    cited = valid = uncited_answers = 0
    abstain_total = abstain_ok = 0
    for row in rows:
        resp = row["response"]
        retrieved = resp.get("retrieved") or []
        answered = bool(resp.get("answered_from_context"))
        citations = resp.get("citations") or []
        cv = citation_validity(resp)
        cited += len(citations)
        valid += round((cv or 0) * len(citations))
        if answered and not citations:
            uncited_answers += 1            # a grounded claim with no citation counts as invalid
        if row["must_abstain"]:
            abstain_total += 1
            abstain_ok += not answered
        expect = row.get("expect")
        per_question.append({
            "id": row["id"], "type": row["type"],
            "recall@3": recall_at_k(row["relevant"], retrieved, 3),
            "recall@5": recall_at_k(row["relevant"], retrieved, 5),
            "answered_from_context": answered,
            "citations": len(citations), "citation_validity": cv,
            "expect_found": (expect.lower() in (resp.get("answer") or "").lower())
            if expect else None,
            "cached": bool(resp.get("cached", False)),
            "seconds": row.get("seconds"),
            # for the manual generation review of 5.3 (correct? grounded? on-topic?)
            "answer": (resp.get("answer") or "")[:400],
        })

    def recall(key: str, kind: str | None = None) -> float | None:
        return _mean([q[key] for q in per_question
                      if q[key] is not None and (kind is None or q["type"] == kind)])

    kinds = sorted({q["type"] for q in per_question})
    denominator = cited + uncited_answers
    expects = [q["expect_found"] for q in per_question if q["expect_found"] is not None]
    return {
        "recall@3": recall("recall@3"),
        "recall@5": recall("recall@5"),
        "recall_by_type": {k: {"recall@3": recall("recall@3", k), "recall@5": recall("recall@5", k),
                               "questions": sum(q["type"] == k for q in per_question)}
                           for k in kinds},
        "citation_validity": round(valid / denominator, 4) if denominator else None,
        "citations_checked": cited,
        "answered_without_citation": uncited_answers,
        "abstention_correctness": round(abstain_ok / abstain_total, 4) if abstain_total else None,
        "must_abstain_questions": abstain_total,
        "expect_found_rate": _mean([float(x) for x in expects]),
        "per_question": per_question,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures = []
    current = results.get("recall@5")
    if current is None:
        failures.append("recall@5 could not be computed: no answerable golden questions")
    elif baseline and baseline.get("recall@5") is not None:
        floor = baseline["recall@5"] - MAX_RECALL5_DROP
        if current < floor - 1e-9:
            failures.append(f"recall@5 {current:.3f} fell more than {MAX_RECALL5_DROP:.0%} "
                            f"below the baseline {baseline['recall@5']:.3f}")
    abstention = results.get("abstention_correctness")
    if abstention is not None and abstention < REQUIRED_ABSTENTION:
        wrong = [q["id"] for q in results.get("per_question", [])
                 if q["type"] == "abstain" and q["answered_from_context"]]
        failures.append(f"abstention correctness {abstention:.0%}: must-abstain questions "
                        f"answered from context: {', '.join(wrong) or '?'}")
    validity = results.get("citation_validity")
    if validity is not None and validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.1%} is below {MIN_CITATION_VALIDITY:.0%}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=300.0, headers=headers) as client:   # CPU-only generation is slow
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    results = summarise(rows)
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    failures = gate(results, baseline)
    if baseline is None:
        print("\nno baseline yet: the recall gate is skipped until one is committed")

    results["golden"] = args.golden.name  # no machine-specific absolute path in committed results
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    print(f"  recall@3 {results['recall@3']}  recall@5 {results['recall@5']}  "
          f"citation validity {results['citation_validity']}  "
          f"abstention {results['abstention_correctness']}")
    for kind, values in results["recall_by_type"].items():
        print(f"  {kind:<10} recall@3 {values['recall@3']}  recall@5 {values['recall@5']}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
