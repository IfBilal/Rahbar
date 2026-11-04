"""Stage 1 (extract): every format, 1-based pages, OCR routing, tables, columns."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline import extract as ex
from pipeline.extract import extract, html_to_text, render_table, strip_front_matter

from .pdfmaker import image_pdf, text_pdf

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"
PARA = "Students are required to attend every lecture of every course they take."


def test_markdown_drops_front_matter_and_keeps_headings() -> None:
    doc = extract(str(FIXTURES / "academic-rules-2026.md"), "2026", False)
    assert [p.page for p in doc.pages] == [1]
    text = doc.pages[0].text
    assert not text.startswith("---") and "doc_version" not in text
    assert "## 1. Attendance" in text and "80 percent" in text
    assert doc.source == "academic-rules-2026.md" and doc.doc_version == "2026"


def test_strip_front_matter_leaves_plain_text_alone() -> None:
    assert strip_front_matter("# Title\nbody") == "# Title\nbody"
    assert strip_front_matter("---\na: b\n---\n\n# T") == "# T"


def test_text_file_is_one_page(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Line one.\nLine two.", encoding="utf-8")
    doc = extract(str(f), "1", True)
    assert doc.superseded is True and doc.pages[0].text == "Line one.\nLine two."


def test_unsupported_type_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "x.docx"
    f.write_bytes(b"PK")
    with pytest.raises(ValueError, match="unsupported"):
        extract(str(f), "1", False)


def test_html_headings_tables_and_noise() -> None:
    html = """<html><head><title>T</title><script>var x=1;</script></head><body>
    <nav>Home | Admissions</nav>
    <h2>Miscellaneous   Fees</h2>
    <table><tr><th>Charge</th><th>Amount</th></tr>
      <tr><td>Paper Rechecking Fee</td>
          <td>Rs. 500</td></tr></table>
    <p>These fees are
       non-refundable.</p><footer>copyright</footer></body></html>"""
    text = html_to_text(html)
    assert "## Miscellaneous Fees" in text
    assert "Charge | Amount" in text
    assert "Paper Rechecking Fee | Rs. 500" in text          # cell association kept
    assert "These fees are non-refundable." in text           # source line breaks collapse
    for noise in ("var x", "Home | Admissions", "copyright"):
        assert noise not in text


def test_render_table_merges_wrapped_cells_and_skips_blanks() -> None:
    rows = [["Campuses", None, "Assoc.\nProfs.", ""], ["Islamabad", "", "14", None]]
    assert render_table(rows) == "Campuses | Assoc. Profs.\nIslamabad | 14"


def test_real_table_filter() -> None:
    assert ex._real_table([["a", "b"], ["c", "d"]])
    assert not ex._real_table([["only one cell"], ["x"]])
    assert not ex._real_table([["a", "b"]])


def test_pdf_with_text_layer(tmp_path: Path) -> None:
    pdf = text_pdf(tmp_path / "rules.pdf", [
        [(50, 60, "1. Introduction"), (50, 100, "1.1 " + PARA)],
        [(50, 60, "Attendance Requirements"), (50, 100, "1.21 " + PARA)],
    ])
    doc = extract(str(pdf), "2026-06", False)
    assert [p.page for p in doc.pages] == [1, 2]
    assert not any(p.ocr for p in doc.pages)
    assert "1.21 Students are required" in doc.pages[1].text
    assert doc.pages[1].source == "rules.pdf"


def test_vertical_gap_becomes_a_blank_line(tmp_path: Path) -> None:
    pdf = text_pdf(tmp_path / "g.pdf", [[(50, 60, "Heading Line Here"),
                                        (50, 120, PARA), (50, 134, PARA)]])
    lines = extract(str(pdf), "1", False).pages[0].text.splitlines()
    assert lines[1] == "" and lines[2] == PARA and lines[3] == PARA


def test_text_outside_the_page_box_is_ignored(tmp_path: Path) -> None:
    """The FAST handbooks carry the facing page's text at negative x."""
    pdf = text_pdf(tmp_path / "spread.pdf", [[(-400, 100, "Neighbour page text " * 3),
                                             (50, 100, PARA)]])
    text = extract(str(pdf), "1", False).pages[0].text
    assert "Neighbour" not in text and PARA in text


def test_two_columns_are_read_one_after_the_other(tmp_path: Path) -> None:
    left = [(40, 60 + 14 * i, f"Left column line number {i} about attendance") for i in range(12)]
    right = [(330, 60 + 14 * i, f"Right column line number {i} about fees") for i in range(12)]
    pdf = text_pdf(tmp_path / "cols.pdf", [left + right])
    text = extract(str(pdf), "1", False).pages[0].text
    assert "attendance Right" not in text                      # no glued lines
    assert text.index("Left column line number 11") < text.index("Right column line number 0")


def test_scanned_page_is_routed_to_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = image_pdf(tmp_path / "scan.pdf", ["Faculty Entrepreneurship Policy"])
    calls: list[int] = []

    def fake_ocr(path: Path, number: int) -> str:
        calls.append(number)
        return "Faculty Entrepreneurship Policy"

    monkeypatch.setattr(ex, "ocr_page", fake_ocr)
    doc = extract(str(pdf), "2022-05", False)
    assert calls == [1]
    assert doc.pages[0].ocr is True and "Entrepreneurship" in doc.pages[0].text


def test_scan_without_ocr_is_an_honest_empty_page(tmp_path: Path) -> None:
    """Failure experiment A: the page is kept (and logged as empty), never invented."""
    pdf = image_pdf(tmp_path / "scan.pdf", ["anything"])
    doc = extract(str(pdf), "1", False, ocr=False)
    assert len(doc.pages) == 1 and doc.pages[0].text == "" and doc.pages[0].ocr is False


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs the tesseract binary "
                    "(present in the indexer image and the CI test job)")
def test_real_ocr_reads_a_scan(tmp_path: Path) -> None:
    pdf = image_pdf(tmp_path / "scan.pdf", ["ACADEMIC RULES 2023", "ATTENDANCE REQUIREMENTS"])
    doc = extract(str(pdf), "2023-08", True)
    assert doc.pages[0].ocr is True
    assert "ATTENDANCE" in doc.pages[0].text.upper()
