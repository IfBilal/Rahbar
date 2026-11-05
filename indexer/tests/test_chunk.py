"""Stage 3 (chunk): structure-aware, bounded, overlapping, traceable."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.chunk import amplification, chunk, chunk_id, is_heading, sections, tokens
from pipeline.clean import clean
from pipeline.extract import extract
from pipeline.models import Document, Page

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"
SENT = "Students must complete the required work on time to keep their standing."   # 12 tokens


def _doc(*texts: str, superseded: bool = False) -> Document:
    return Document(source="rules.pdf", doc_version="2026-06", superseded=superseded,
                    pages=[Page(source="rules.pdf", page=i, text=t) for i, t in enumerate(texts, 1)])


@pytest.mark.parametrize("line,standalone,expected", [
    ("## 1. Attendance", False, (2, "1. Attendance")),
    ("5. Academic Assessment", False, (1, "5. Academic Assessment")),
    ("XII.Policy on Generative AI Based Tools", False, (1, "XII.Policy on Generative AI Based Tools")),
    ("CODE OF CONDUCT", False, (1, "CODE OF CONDUCT")),
    ("Attendance Requirements", True, (2, "Attendance Requirements")),
    ("Eligibility criteria for a technical start-up", True,
     (2, "Eligibility criteria for a technical start-up")),
])
def test_headings_are_detected(line: str, standalone: bool, expected: tuple) -> None:
    assert is_heading(line, standalone) == expected


@pytest.mark.parametrize("line,standalone", [
    ("1.21 Students are required to maintain 100% attendance", True),   # a clause
    ("a) All classes are rescheduled", True),                             # a list item
    ("9) Good Academic Practice as stated", True),
    ("5. Above are just the", False),                                     # numbered prose
    ("Attendance Requirements", False),                                   # inside a paragraph
    ("This sentence ends with a full stop.", True),
    ("A+ | 4.00 | C+ | 2.33", True),                                      # a table row
    ("SGPA = (P1*C1 + P2*C2 + P3*C3 + P4*C4)/C", True),                  # a formula
    ("", True),
])
def test_non_headings_are_not(line: str, standalone: bool) -> None:
    assert is_heading(line, standalone) is None


def test_sections_follow_the_heading_path() -> None:
    doc = _doc("5. Academic Assessment\n\nAcademic Warning/Probation\n\n5.4 Minimum CGPA is 2.00.\n"
               "5.5 Warning is issued.\n\nRepeating a Course\n\n5.9 A student may repeat any course.")
    got = [(s.label, len(s.paras)) for s in sections(doc)]
    assert got == [("5. Academic Assessment > Academic Warning/Probation", 2),
                   ("5. Academic Assessment > Repeating a Course", 1)]


def test_paragraph_continues_across_a_page_break() -> None:
    doc = _doc("Attendance Requirements\n\n1.21 Students are required to maintain 100% attendance in",
               "lectures and labs.\n1.22 Failure renders the student ineligible.")
    paras = sections(doc)[0].paras
    assert paras[0].text.endswith("attendance in lectures and labs.") and paras[0].page == 1
    assert paras[1].page == 2


def test_chunks_respect_size_and_carry_metadata() -> None:
    body = " ".join([SENT] * 40)                          # 480 tokens, one paragraph
    doc = _doc(f"Attendance Requirements\n\n{body}", superseded=True)
    out = chunk(doc, size=100, overlap=20)
    assert len(out) >= 5
    for c in out:
        label, text = c.text.split("\n", 1)
        assert label == c.section == "Attendance Requirements"
        assert tokens(text) <= 100
        assert c.metadata() == {"source": "rules.pdf", "section": c.section, "page": 1,
                                "doc_version": "2026-06", "superseded": True}


def test_neighbours_share_the_overlap() -> None:
    body = " ".join(f"Sentence number {i} is here." for i in range(60))   # 300 tokens
    out = chunk(_doc(f"Heading One\n\n{body}"), size=60, overlap=15)
    for a, b in zip(out, out[1:]):
        tail = a.text.split()[-15:]
        assert b.text.split("\n", 1)[1].split()[:15] == tail


def test_no_overlap_means_no_shared_text() -> None:
    body = " ".join(f"Sentence number {i} is here." for i in range(60))
    out = chunk(_doc(f"Heading One\n\n{body}"), size=60, overlap=0)
    words = [w for c in out for w in c.text.split("\n", 1)[1].split()]
    assert words == body.split()


def test_overlap_never_crosses_a_section() -> None:
    doc = _doc("First Section\n\n" + " ".join([SENT] * 10) + "\n\nSecond Section\n\nShort text here.")
    out = chunk(doc, size=50, overlap=20)
    second = [c for c in out if c.section == "Second Section"]
    assert len(second) == 1 and second[0].text == "Second Section\nShort text here."


def test_a_long_definition_is_split_on_sentences_not_mid_sentence() -> None:
    definition = " ".join([SENT] * 30)
    out = chunk(_doc(f"Definitions\n\n{definition}"), size=50, overlap=0)
    for c in out:
        assert c.text.split("\n", 1)[1].endswith("standing.")


def test_a_giant_sentence_falls_back_to_word_windows() -> None:
    giant = " ".join(["word"] * 250)
    out = chunk(_doc(f"Long One\n\n{giant}"), size=100, overlap=10)
    assert all(tokens(c.text.split("\n", 1)[1]) <= 100 for c in out)


def test_table_rows_stay_whole() -> None:
    rows = "\n".join(f"Campus {i} | {i} | {i * 2} | {i * 3}" for i in range(40))
    out = chunk(_doc(f"Faculty Summary\n\n{rows}"), size=60, overlap=0)
    for c in out:
        for line in c.text.split("\n")[1:]:
            assert line.startswith("Campus ") and line.count("|") == 3


def test_chunk_page_is_where_its_new_text_starts() -> None:
    doc = _doc("Rules\n\n1.1 " + " ".join([SENT] * 4), "1.2 " + " ".join([SENT] * 4))
    out = chunk(doc, size=60, overlap=10)
    assert out[0].page == 1 and out[-1].page == 2


def test_ids_are_stable_and_unique() -> None:
    doc = _doc("Rules\n\n" + " ".join([SENT] * 20))
    a, b = chunk(doc, 50, 10), chunk(doc, 50, 10)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)
    assert chunk_id("Fee Page.html", "2026", 3, "x").startswith("fee-page-html-2026-0003-")


@pytest.mark.parametrize("size,overlap", [(0, 0), (5, 0), (100, 100), (100, -1)])
def test_bad_settings_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk(_doc("x"), size, overlap)


def test_fixture_sections_match_the_ci_golden_set() -> None:
    labels = set()
    for name in ("academic-rules-2026.md", "fees-2026.md", "academic-rules-2023.md"):
        doc = clean(extract(str(FIXTURES / name), "v", False))
        labels |= {c.section for c in chunk(doc, 120, 20)}
    for wanted in ("1. Attendance", "2. Academic warning", "3. Repeating a course", "1. Tuition"):
        assert any(wanted in label for label in labels), wanted


def test_amplification_is_stored_over_original() -> None:
    doc = _doc("Heading One\n\n" + " ".join(f"w{i}" for i in range(100)))
    no_overlap = amplification(chunk(doc, 50, 0), [doc])
    with_overlap = amplification(chunk(doc, 50, 25), [doc])
    assert 1.0 <= no_overlap < with_overlap
