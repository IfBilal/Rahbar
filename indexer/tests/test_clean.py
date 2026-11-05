"""Stage 2 (clean): strip repeating artefacts, keep structure and exact terms."""

from __future__ import annotations

from pipeline.clean import clean, clean_text, line_shape, repeating_lines
from pipeline.models import Document, Page

HEADER = "NATIONAL UNIVERSITY OF COMPUTER AND EMERGING SCIENCES"


def _doc(*texts: str) -> Document:
    return Document(source="h.pdf", doc_version="2026", superseded=False,
                    pages=[Page(source="h.pdf", page=i, text=t) for i, t in enumerate(texts, 1)])


def test_running_header_and_alternating_folio_are_removed() -> None:
    pages = [f"{HEADER}\n1.{i} Clause text number {i}.\n"
             + (f"Undergraduate Rules 2026 {i}" if i % 2 else f"{i} Undergraduate Rules 2026")
             for i in range(1, 7)]
    out = clean(_doc(*pages))
    for p in out.pages:
        assert HEADER not in p.text
        assert "Undergraduate Rules" not in p.text
        assert p.text.startswith(f"1.{p.page} Clause text")     # clause number kept


def test_folio_masking() -> None:
    assert line_shape("Rules 2026 7") == line_shape("8 Rules 2026") == "rules"
    assert line_shape("Rules 2026 III") == "rules"
    assert line_shape("1.21 Students") == "#.# students"


def test_short_documents_keep_their_lines() -> None:
    assert repeating_lines(["A\nB", "A\nC"]) == set()


def test_page_numbers_and_leaders() -> None:
    text = "Intro text.\n7\nPage 13 of 85\nIV\nAttendance Requirements......4"
    assert clean_text(text, set()) == "Intro text.\nAttendance Requirements 4"


def test_contents_page_is_dropped_but_prose_is_not() -> None:
    toc = "\n".join(["Table of Contents", "1. Medium of Instruction 1", "Academic Year 1",
                     "Attendance Requirements 4", "2. Grading and GPA Calculations 5",
                     "Grade Points 6", "3. Admission Policy 8"])
    assert clean_text(toc, set()) == "Table of Contents"
    prose = "Minimum CGPA required is 2.00 for semester 3"
    assert clean_text(prose, set()) == prose


def test_hyphenation_ligatures_and_blank_runs() -> None:
    out = clean(_doc("The regu-\nlations deﬁne it.\n\n\n\nNext para."))
    assert out.pages[0].text == "The regulations define it.\n\nNext para."


def test_tables_fees_and_clause_numbers_survive() -> None:
    text = "Paper Rechecking Fee | Rs. 500\n5.4 Minimum CGPA required to avoid academic warning is 2.00"
    assert clean_text(text, set()) == text


def test_metadata_and_ocr_flag_are_preserved() -> None:
    doc = Document(source="s.pdf", doc_version="2023-08", superseded=True,
                   pages=[Page(source="s.pdf", page=1, text="x", ocr=True)])
    out = clean(doc)
    assert (out.source, out.doc_version, out.superseded) == ("s.pdf", "2023-08", True)
    assert out.pages[0].ocr is True and out.pages[0].page == 1
