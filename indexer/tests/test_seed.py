"""The seed step: copy the fetched corpus into the inbox once, with a catalog."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.catalog import scan_inbox, load_catalog
from pipeline.seed import seed


def test_seed_copies_once_and_writes_a_catalog_with_series(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "rules-2023.pdf").write_bytes(b"%PDF-old")
    (raw / "rules-2026.pdf").write_bytes(b"%PDF-new")
    (raw / "_index.json").write_text(json.dumps([
        {"file": "rules-2023.pdf", "name": "Undergraduate Academic Rules (Aug 2023)",
         "doc_version": "2023-08", "superseded": True},
        {"file": "rules-2026.pdf", "name": "Academic Rules Handbook (Jun 2026)",
         "doc_version": "2026-06", "superseded": False},
        {"file": "missing.pdf", "name": "Gone", "doc_version": "1"}]))
    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump({"documents": [
        {"name": "Undergraduate Academic Rules (Aug 2023)", "doc_id": "academic-rules"},
        {"name": "Academic Rules Handbook (Jun 2026)", "doc_id": "academic-rules"}]}))
    inbox = tmp_path / "inbox"
    assert seed(inbox, raw, sources) == 2
    rows, _ = load_catalog(inbox)
    assert rows["rules-2023.pdf"]["doc_id"] == rows["rules-2026.pdf"]["doc_id"] == "academic-rules"
    assert rows["rules-2026.pdf"]["doc_version"] == "2026-06"
    assert {f.rel for f in scan_inbox(inbox)} == {"rules-2023.pdf", "rules-2026.pdf"}
    (inbox / "rules-2023.pdf").write_bytes(b"changed by hand")
    assert seed(inbox, raw, sources) == 0                         # already seeded: touches nothing
    assert (inbox / "rules-2023.pdf").read_bytes() == b"changed by hand"
