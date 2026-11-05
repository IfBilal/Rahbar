"""Step 7: the citation guard. Every citation must be a chunk retrieved for this request."""

from __future__ import annotations

import pytest

from app.schemas import Answer, Citation
from app.services.guard import GuardError, check_answer, is_follow_up, match_passage

from .fakes import declined, grounded, passage

P = [passage(1, section="4. Registration > Withdrawal from a Course", page=22),
     passage(2, section="1. Introduction > Attendance Requirements", page=10)]


def _answer(text: str, citations: list[Citation], answered: bool = True) -> Answer:
    return Answer(reasoning="r", answer=text, citations=citations,
                  answered_from_context=answered, confidence="medium")


def test_valid_answer_passes_and_markers_become_readable_citations() -> None:
    out = check_answer(grounded(P[0], "Last day of the makeup week [A]."), P)
    assert out.answer == ("Last day of the makeup week "
                          "[rules.pdf / 4. Registration > Withdrawal from a Course].")
    assert out.citations == [Citation(source="rules.pdf", section=P[0].section, page=22)]


def test_shortened_section_maps_to_the_real_chunk() -> None:
    out = check_answer(_answer("x [B]", [Citation(source="rules.pdf",
                                                  section="Attendance Requirements", page=10)]), P)
    assert [c.section for c in out.citations] == [P[1].section]


@pytest.mark.parametrize("citation", [
    Citation(source="made-up-policy.pdf", section="1. Attendance", page=1),   # fabricated
    Citation(source="rules.pdf", section="9.9 Nonexistent", page=1),          # wrong section
    Citation(source="rules.pdf", section="9.9", page=1),                      # clause not retrieved
])
def test_fabricated_citations_are_rejected(citation: Citation) -> None:
    with pytest.raises(GuardError, match="does not match"):
        check_answer(_answer("x", [citation]), P)


def test_markers_must_point_at_real_passages() -> None:
    with pytest.raises(GuardError, match="'G'"):
        check_answer(_answer("x [G]", [Citation(source="rules.pdf", section=P[0].section,
                                                page=22)]), P)


def test_grounded_claim_without_any_citation_is_rejected() -> None:
    with pytest.raises(GuardError, match="nothing is cited"):
        check_answer(_answer("It is allowed.", []), P)


def test_markers_alone_are_enough_citations() -> None:
    out = check_answer(_answer("It is in [B].", []), P)
    assert out.citations[0].section == P[1].section


def test_declined_answer_drops_citations() -> None:
    out = check_answer(_answer("Not covered.", [Citation(source="x", section="y")],
                               answered=False), P)
    assert out.citations == [] and out.answer == "Not covered."
    assert check_answer(declined(), P).answered_from_context is False


def test_declining_while_citing_evidence_is_contradictory() -> None:
    with pytest.raises(GuardError, match="false but the answer cites"):
        check_answer(_answer("Attendance is not optional [B].", [], answered=False), P)


def test_match_passage_without_page_uses_source_and_section() -> None:
    assert match_passage(Citation(source="rules.pdf", section=P[1].section), P) is P[1]


@pytest.mark.parametrize("question,expected", [
    ("What about the 2023 rules?", True),
    ("And for summer semester?", True),
    ("Is it mandatory?", True),
    ("Can you repeat what you said?", True),
    ("What minimum CGPA does an undergraduate need to avoid academic warning?", False),
    ("What does clause 1.21 of the academic rules require?", False),
    ("How many grade points is a B- worth?", False),
])
def test_follow_up_detection(question: str, expected: bool) -> None:
    assert is_follow_up(question) is expected


def test_bracketed_numbers_are_not_citations_and_are_removed() -> None:
    """Measured on the cluster: with numbered evidence a 3B model wrote [6] for clause 6.6.
    Evidence ids are now letters; a bracketed number is dropped, never trusted."""
    out = check_answer(_answer("Repeat at most 2 courses [6] in summer [A].", []), P)
    assert out.answer == f"Repeat at most 2 courses in summer [rules.pdf / {P[0].section}]."
    assert [c.section for c in out.citations] == [P[0].section]


def test_an_answer_without_markers_gets_its_validated_citations_inline() -> None:
    out = check_answer(_answer("Admission is closed after three semesters.",
                               [Citation(source="rules.pdf", section=P[1].section, page=10)]), P)
    assert out.answer == ("Admission is closed after three semesters. "
                          f"[rules.pdf / {P[1].section}]")


def test_a_real_section_with_a_wrong_page_is_served_with_the_real_page() -> None:
    """Measured: llama3.2:3b cited '6. Rules for Summer Semester' with page 6 (the section
    number). The chunk is real and retrieved; the served citation carries its real page."""
    out = check_answer(_answer("x [A]", [Citation(source="rules.pdf", section=P[0].section,
                                                  page=99)]), P)
    assert out.citations == [Citation(source="rules.pdf", section=P[0].section, page=22)]


def test_a_clause_number_maps_to_the_passage_that_contains_it() -> None:
    passages = [passage(1, section="1. Introduction > Academic Year", page=7,
                        text="1.2 Academic Year of the University starts in August.")]
    out = check_answer(_answer("It starts in August.", [Citation(source="rules.pdf",
                                                                 section="1.2", page=7)]), passages)
    assert out.citations[0].section == "1. Introduction > Academic Year"
