"""Metadata resolution: catalog > embedded > derived, never mtime."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from pipeline.catalog import (
    InboxFile, derive_doc_id, find_date, find_version, is_newer, load_catalog,
    resolve_metadata, scan_inbox, sha256_file, version_key,
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
    assert m.doc_id == "hostel-allotment-policy"


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
