"""Golden-set validation and batch-aware selection."""

from __future__ import annotations

import json
from pathlib import Path

from ragops.suite.golden import applicable, golden_hash, load_golden, main, select, validate


def q(i: int, cat: str = "answerable", origin: str = "human", **kw) -> dict:
    row = {"id": f"g{i:03d}", "question": f"question number {i}?", "category": cat,
           "answerable": cat != "unanswerable", "origin": origin,
           "gold": [] if cat == "unanswerable" else [{"doc": "rules.pdf", "page": 3}]}
    if cat == "hard":
        row["hard_kind"] = "paraphrase"
    if origin == "synthetic":
        row["review"] = {"by": "member-a", "date": "2026-11-24", "verdict": "ok"}
    row.update(kw)
    return row


def full_set() -> list[dict]:
    rows = [q(i) for i in range(1, 17)]                                   # 16 answerable
    rows += [q(20 + i, "unanswerable") for i in range(6)]                 # 6 unanswerable
    rows += [q(40 + i, "hard") for i in range(8)]                         # 8 hard
    for k, row in enumerate(rows):
        if k % 3 == 0:
            row["origin"] = "synthetic"
            row["review"] = {"by": "member-b", "date": "2026-11-24", "verdict": "edited"}
    return rows


def test_a_set_meeting_every_quota_is_valid() -> None:
    problems, counts = validate(full_set())
    assert problems == [] and counts["total"] == 30 and counts["answerable_incl_hard"] == 24
    assert counts["human"] >= 8 and counts["synthetic_reviewed"] >= 8


def test_each_quota_is_enforced() -> None:
    rows = [q(i) for i in range(1, 11)]
    problems, _ = validate(rows)
    text = " ".join(problems)
    for name in ("total", "answerable", "unanswerable", "hard", "synthetic_reviewed"):
        assert f"quota: {name}" in text


def test_structural_rules() -> None:
    rows = full_set()
    rows[0]["gold"] = []
    rows[1]["gold"] = [{"doc": "rules.pdf", "page": 0}]
    rows[20]["gold"] = [{"doc": "x.pdf", "page": 1}]
    rows[2]["question"] = rows[3]["question"]
    rows[4]["id"] = rows[5]["id"]
    rows[45 - 20]["hard_kind"] = "nonsense"
    rows[6].pop("origin")
    synth = next(r for r in rows if r["origin"] == "synthetic")
    synth["review"] = {}
    text = " | ".join(validate(rows)[0])
    for needle in ("gold is empty", "integer page", "unanswerable but gold", "duplicate question",
                   "duplicate id", "hard_kind", "origin must be", "no hand review"):
        assert needle in text, needle


def test_gold_documents_and_pages_are_checked_against_the_ledger() -> None:
    rows = full_set()
    rows[0]["gold"] = [{"doc": "ghost.pdf", "page": 1}]
    rows[1]["gold"] = [{"doc": "rules.pdf", "page": 99}]
    problems, _ = validate(rows, {"rules.pdf": 20})
    text = " | ".join(problems)
    assert "not in the ledger" in text and "beyond rules.pdf" in text


def test_batch_aware_selection() -> None:
    old = q(1, retired_by_batch="B")
    new = q(2, requires_batch=["B"])
    plain = q(3)
    assert applicable(plain, {"A"})[0] and applicable(old, {"A"})[0]
    assert not applicable(new, {"A"})[0] and applicable(new, {"A", "B"})[0]
    run, skipped = select([old, new, plain], {"A", "B"})
    assert [r["id"] for r in run] == ["g003", "g002"] or {r["id"] for r in run} == {"g002", "g003"}
    assert skipped == [{"id": "g001", "reason": "retired by batch B"}]


def test_cli_and_hash(tmp_path: Path, capsys) -> None:
    path = tmp_path / "golden.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in full_set()) + "\n")
    assert main(["--validate", str(path)]) == 0 and "VALID" in capsys.readouterr().out
    h = golden_hash(path)
    assert h == golden_hash(path) and len(load_golden(path)) == 30
    path.write_text(path.read_text().replace("question number 1?", "question number one?"))
    assert golden_hash(path) != h
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(q(1)) + "\n")
    assert main(["--validate", str(bad)]) == 1
    assert main(["--validate", str(tmp_path / "nope.jsonl")]) == 2


def test_a_batch_b_question_is_not_checked_against_a_ledger_that_has_only_batch_a() -> None:
    """First cluster run: the suite refused to start because the Batch B questions cite documents
    that cannot be in the ledger before Batch B is ingested. `select` skips them anyway."""
    rows = full_set()
    rows[-1]["gold"] = [{"doc": "library-borrowing-rules.md", "page": 1}]
    rows[-1]["requires_batch"] = ["B"]
    docs = {"rules.pdf": 20}
    assert validate(rows, docs)[0]                                   # without batches: flagged (old behaviour)
    assert validate(rows, docs, {"A"})[0] == []                      # Batch A only: not checked yet
    problems = validate(rows, {**docs}, {"A", "B"})[0]               # after Batch B is ingested: checked again
    assert any("library-borrowing-rules.md" in p and "not in the ledger" in p for p in problems)
