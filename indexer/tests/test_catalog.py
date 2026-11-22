"""Metadata resolution: catalog > embedded > derived, never mtime."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from pipeline.catalog import (
    InboxFile, derive_doc_id, derive_title, find_date, find_date_in_filename, find_version,
    is_newer, load_catalog, resolve_metadata, scan_inbox, sha256_file, version_key,
)


def _file(tmp_path: Path, name: str, text: str) -> InboxFile:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return InboxFile(rel=name, path=p, sha=sha256_file(p), size=p.stat().st_size, batch="A")


def test_doc_id_ignores_version_year_and_month_words() -> None:
    assert derive_doc_id("Academic Rules 2023", "x.pdf") == "academic-rules"
    assert derive_doc_id("Academic Rules, June 2026 Edition", "x.pdf") == "academic-rules"
    assert derive_doc_id(None, "Library_Rules_v2.pdf") == "library-rules"
    assert derive_doc_id("Student Handbook", "a.pdf") == "student-handbook"


def test_dates_and_versions_are_found_and_normalised() -> None:
    assert find_date("Effective 2026-06-01 by order") == "2026-06-01"
    assert find_date("Issued on 5 March 2025.") == "2025-03-05"
    assert find_date("Revised June 2026") == "2026-06"
    assert find_date("Academic Year 2024 rules") == "2024"
    assert find_date("We have 2024 students and 1999 staff") is None      # bare years are not dates
    assert find_version("Policy v2.1 (final)") == "v2.1"
    assert find_version("Version: 3") == "v3"
    assert find_version("nothing here") is None


def test_version_ordering_within_a_kind() -> None:
    assert is_newer("2026-06", "2023-08")
    assert is_newer("2026-06-02", "2026-06")
    assert not is_newer("2023", "2026")
    assert is_newer("v2.10", "v2.9")
    assert version_key("2026-06")[0] == 2 and version_key("v1.0")[0] == 1
    assert not is_newer("2026-06", "2026-06")


def test_catalog_wins_over_embedded_and_derived(tmp_path: Path) -> None:
    f = _file(tmp_path, "a.md", "---\ntitle: Embedded Title\ndoc_version: 9\n---\n# Heading\nEffective 2020-01-01\n")
    row = {"title": "Catalog Title", "doc_version": "2026-06", "doc_id": "my-series"}
    m = resolve_metadata(f, ["# Heading\nEffective 2020-01-01"], {"a.md": row})
    assert (m.title.value, m.title.route) == ("Catalog Title", "catalog")
    assert (m.version.value, m.version.route) == ("2026-06", "catalog")
    assert m.doc_id == "my-series"
    assert m.date.route == "derived" and m.date.value == "2020-01-01"


def test_embedded_front_matter_and_html_are_used(tmp_path: Path) -> None:
    md = _file(tmp_path, "b.md", "---\ntitle: Fee Policy\ndate: 2026-03\n---\nBody text here.\n")
    m = resolve_metadata(md, ["Body text here."])
    assert m.title.route == "embedded" and m.title.value == "Fee Policy"
    assert m.version.value == "2026-03"                  # label falls back to the date
    html = _file(tmp_path, "c.html", "<html><head><title> Grading  Page </title>"
                 "<meta name='date' content='2026'></head><body>x</body></html>")
    h = resolve_metadata(html, ["x"])
    assert h.title.value == "Grading Page" and h.date.value == "2026"


def test_unseen_file_with_no_catalog_derives_what_it_can(tmp_path: Path) -> None:
    f = _file(tmp_path, "Hostel_Policy_2025.txt",
              "Hostel Allotment Policy\nIssued 12 January 2025\nStudents apply in June.")
    m = resolve_metadata(f, [f.path.read_text()])
    assert m.title.value == "Hostel Allotment Policy" and m.title.route == "derived"
    assert m.date.value == "2025-01-12"
    assert m.doc_id == "hostel-policy"          # a series id never comes from a title read off the page


def test_nothing_resolvable_is_reported_missing_and_mtime_is_ignored(tmp_path: Path) -> None:
    f = _file(tmp_path, "notes.txt", "just some words with no heading and no date at all")
    os.utime(f.path, (1_700_000_000, 1_700_000_000))     # a perfectly good mtime exists
    m = resolve_metadata(f, [f.path.read_text()])
    assert m.date.value is None and m.date.route == "missing"
    assert m.version.value is None and m.version.route == "missing"


def test_scan_inbox_skips_hidden_readme_and_unsupported_and_tags_batches(tmp_path: Path) -> None:
    (tmp_path / "keep.md").write_text("x")
    (tmp_path / ".hidden.md").write_text("x")
    (tmp_path / "README.md").write_text("x")
    (tmp_path / "image.png").write_bytes(b"x")
    (tmp_path / "_batch.yaml").write_text(yaml.safe_dump({"documents": []}))
    sub = tmp_path / "batch-b"
    sub.mkdir()
    (sub / "new.txt").write_text("y")
    files = {f.rel: f for f in scan_inbox(tmp_path)}
    assert set(files) == {"keep.md", "batch-b/new.txt"}
    assert files["keep.md"].batch == "A" and files["batch-b/new.txt"].batch == "B"


def test_batch_yaml_declares_batch_and_rows(tmp_path: Path) -> None:
    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "a.md").write_text("x")
    (folder / "_batch.yaml").write_text(yaml.safe_dump(
        {"batch": "c", "documents": [{"file": "a.md", "title": "T"}]}))
    rows, _ = load_catalog(tmp_path)
    assert rows["drop/a.md"]["title"] == "T" and rows["a.md"]["title"] == "T"
    assert scan_inbox(tmp_path)[0].batch == "C"


# ---- found by running the unseen-document path over the real nine-document corpus (T07)
def test_real_world_date_forms_are_recognised() -> None:
    assert find_date("Policy 30.05.2022/FacultyEntrepreneurshipPolicy") == "2022-05-30"
    assert find_date("Annual Report 2019-20") == "2019-20"
    assert find_date("Annual Report 2023-2024") == "2023-24"
    assert find_date("Budget 2023-08 summary") == "2023-08"          # ISO month wins over a range
    assert find_date("Reference 2019-77 and 12 items") is None        # not a plausible academic year
    assert find_date("order of 31/12/2025") == "2025-12-31"


def test_a_year_in_the_file_name_counts_but_no_name_means_no_date() -> None:
    assert find_date_in_filename("annual-report-2023-24.pdf") == "2023-24"
    assert find_date_in_filename("academic-rules-handbook-jun-2026.pdf") == "2026-06"
    assert find_date_in_filename("undergraduate-academic-rules-aug-2023.pdf") == "2023-08"
    assert find_date_in_filename("Prospectus 2026.pdf") == "2026"
    assert find_date_in_filename("untitled-notes.txt") is None
    assert find_date_in_filename("notes.txt") is None


def test_junk_titles_are_skipped() -> None:
    assert derive_title("final layout.cdr\nAcademic Rules Handbook\ntext.") == "Academic Rules Handbook"
    assert derive_title("Microsoft Word - Annual.Report-2019-20\nANNUAL REPORT") == "ANNUAL REPORT"
    assert derive_title("1\n2\n\n") is None
    assert derive_title("This line is a whole sentence that ends with a full stop.") is None


def test_two_documents_with_the_same_cover_header_do_not_become_one_series(tmp_path: Path) -> None:
    """The real corpus: three PDFs open with 'FAST National University'. A series id taken from
    that derived title would make them versions of one document and let one replace another."""
    header = "FAST National University\nof Computer and Emerging Sciences\n"
    a = _file(tmp_path, "student-handbook-jun-2026.md", header + "Student handbook text. " * 20)
    b = _file(tmp_path, "academic-rules-handbook-jun-2026.md", header + "Academic rules text. " * 20)
    ma, mb = resolve_metadata(a, [a.path.read_text()]), resolve_metadata(b, [b.path.read_text()])
    assert ma.title.value == mb.title.value and ma.title.route == "derived"
    assert ma.doc_id == "student-handbook" and mb.doc_id == "academic-rules-handbook"
    assert ma.version.value == mb.version.value == "2026-06"          # from the file name


def test_an_unseen_annual_report_resolves_a_version_without_any_catalog(tmp_path: Path) -> None:
    f = _file(tmp_path, "annual-report-2019-20.txt", "ANNUAL REPORT\nThe institute grew steadily.")
    m = resolve_metadata(f, [f.path.read_text()])
    assert m.version.value == "2019-20" and m.doc_id == "annual-report"
    assert m.title.value == "ANNUAL REPORT"


def test_an_embedded_pdf_creation_date_is_the_last_resort(tmp_path: Path, monkeypatch) -> None:
    f = _file(tmp_path, "report.txt", "Some Heading\nwords without any date at all in them")
    monkeypatch.setattr("pipeline.catalog.embedded_metadata", lambda p: {"pdf_date": "2025-02"})
    m = resolve_metadata(f, [f.path.read_text()])
    assert (m.date.value, m.date.route) == ("2025-02", "embedded")
