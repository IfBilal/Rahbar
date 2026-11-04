"""The evaluation is a CI gate, so its arithmetic is tested like production code."""

from __future__ import annotations

import pytest

from run_eval import (MAX_RECALL5_DROP, citation_validity, gate, load_golden, recall_at_k,
                      summarise)

HB = "academic-rules-handbook-jun-2026.pdf"


def ref(source: str, section: str, page: int | None = 1) -> dict:
    return {"chunk_id": "x", "source": source, "section": section, "page": page, "score": 0.8}


def test_recall_matches_section_paths_and_curly_quotes() -> None:
    gold = [{"source": HB, "section": "Rector's List of Honors"}]
    got = [ref(HB, "7. Awards and the Honor System > Rector’s List of Honors")]
    assert recall_at_k(gold, got, 5) == 1.0


def test_recall_counts_only_the_top_k() -> None:
    gold = [{"source": HB, "section": "Grade Points"}, {"source": "grading-page.html",
                                                         "section": "Letter grades for BBA"}]
    got = [ref("x.pdf", "a")] * 3 + [ref(HB, "2. Grading > Grade Points"),
                                     ref("grading-page.html", "Letter grades for BBA & BS")]
    assert recall_at_k(gold, got, 3) == 0.0
    assert recall_at_k(gold, got, 4) == 0.5
    assert recall_at_k(gold, got, 5) == 1.0


def test_recall_needs_the_same_source() -> None:
    gold = [{"source": HB, "section": "Withdrawal from a Course"}]
    old = [ref("undergraduate-academic-rules-aug-2023.pdf", "4. Registration > Withdrawal from a Course")]
    assert recall_at_k(gold, old, 5) == 0.0


def test_recall_is_undefined_for_must_abstain() -> None:
    assert recall_at_k([], [ref(HB, "x")], 5) is None


def test_citation_validity_checks_source_section_and_page() -> None:
    response = {"retrieved": [ref(HB, "A", 3), ref(HB, "B", None)],
                "citations": [{"source": HB, "section": "A", "page": 3},
                              {"source": HB, "section": "A", "page": 9},         # wrong page
                              {"source": HB, "section": "B", "page": None},
                              {"source": "made-up.pdf", "section": "A", "page": 3}]}
    assert citation_validity(response) == 0.5
    assert citation_validity({"retrieved": [], "citations": []}) is None


def _row(qid: str, kind: str, answered: bool, citations: list, retrieved: list,
         relevant: list | None = None, must_abstain: bool = False, answer: str = "") -> dict:
    return {"id": qid, "type": kind, "must_abstain": must_abstain, "relevant": relevant or [],
            "expect": "2.00" if kind == "ordinary" else None, "seconds": 1.0,
            "response": {"answer": answer, "answered_from_context": answered,
                         "citations": citations, "retrieved": retrieved}}


def test_summarise_pools_citations_and_breaks_down_by_type() -> None:
    good = ref(HB, "5. Academic Assessment > Academic Warning/Probation")
    rows = [
        _row("q1", "ordinary", True, [{"source": HB, "section": good["section"], "page": 1}],
             [good], [{"source": HB, "section": "Academic Warning/Probation"}], answer="CGPA 2.00"),
        _row("e1", "exact", True, [{"source": "fake.pdf", "section": "x", "page": 1}],
             [ref("x.pdf", "y")], [{"source": HB, "section": "Attendance Requirements"}]),
        _row("a1", "abstain", False, [], [ref("x.pdf", "y")], must_abstain=True),
    ]
    out = summarise(rows)
    assert out["recall@5"] == 0.5 and out["recall_by_type"]["ordinary"]["recall@5"] == 1.0
    assert out["recall_by_type"]["exact"]["recall@5"] == 0.0
    assert out["recall_by_type"]["abstain"]["recall@5"] is None       # not counted as 1.0
    assert out["citation_validity"] == 0.5 and out["abstention_correctness"] == 1.0
    assert out["expect_found_rate"] == 1.0


def test_an_answer_without_citations_counts_against_validity() -> None:
    rows = [_row("q1", "ordinary", True, [], [ref(HB, "S")], [{"source": HB, "section": "S"}])]
    out = summarise(rows)
    assert out["answered_without_citation"] == 1 and out["citation_validity"] == 0.0


def _results(r5: float = 0.8, abstain: float = 1.0, cv: float = 1.0) -> dict:
    return {"recall@5": r5, "abstention_correctness": abstain, "citation_validity": cv,
            "per_question": [{"id": "a1", "type": "abstain", "answered_from_context": abstain < 1}]}


def test_gate_passes_a_healthy_run() -> None:
    assert gate(_results(), {"recall@5": 0.8}) == []
    assert gate(_results(), None) == []


def test_gate_boundary_is_exactly_five_points() -> None:
    assert gate(_results(r5=0.80 - MAX_RECALL5_DROP), {"recall@5": 0.80}) == []
    assert gate(_results(r5=0.7499), {"recall@5": 0.80})


@pytest.mark.parametrize("kwargs,needle", [
    ({"abstain": 0.6667}, "a1"),
    ({"cv": 0.9499}, "citation validity"),
])
def test_gate_failures_name_the_problem(kwargs: dict, needle: str) -> None:
    failures = gate(_results(**kwargs), {"recall@5": 0.8})
    assert len(failures) == 1 and needle in failures[0]


def test_gate_fails_when_nothing_was_measured() -> None:
    assert gate({"recall@5": None}, None)


def test_golden_sets_have_the_required_mix() -> None:
    from pathlib import Path
    here = Path(__file__).resolve().parents[1]
    golden = load_golden(here / "golden.yaml")
    kinds = [q["type"] for q in golden]
    assert len(golden) >= 15
    for kind, minimum in {"ordinary": 8, "version": 2, "exact": 2, "abstain": 2,
                          "injection": 1}.items():
        assert kinds.count(kind) >= minimum, kind
    for q in golden:
        assert bool(q.get("must_abstain")) == (q["type"] == "abstain")
        assert q.get("relevant") or q["type"] == "abstain"
    assert len(load_golden(here / "fixtures" / "golden.fixture.yaml")) == 6
