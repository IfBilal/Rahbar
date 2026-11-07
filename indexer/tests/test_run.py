"""The Job entry point over the CI fixture corpus, with fake embedding and store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import run
from pipeline.config import get_settings

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def test_pipeline_indexes_the_fixtures_with_metadata(monkeypatch) -> None:
    monkeypatch.setenv("CORPUS_DIR", str(FIXTURES))
    monkeypatch.setenv("CHUNK_SIZE", "120")
    monkeypatch.setenv("CHUNK_OVERLAP", "20")
    captured = {}

    def fake_store(chunks, vectors, settings):
        captured["chunks"], captured["vectors"] = chunks, vectors
        return len(chunks)

    monkeypatch.setattr("pipeline.embed.embed", lambda texts, s: [[1.0, 0.0]] * len(texts))
    monkeypatch.setattr("pipeline.store.store", fake_store)
    count = run.run_pipeline(get_settings())
    chunks = captured["chunks"]
    assert count == len(chunks) > 6
    assert {c.source for c in chunks} == {"academic-rules-2023.md", "academic-rules-2026.md",
                                          "fees-2026.md"}
    old = [c for c in chunks if c.source == "academic-rules-2023.md"]
    assert old and all(c.superseded and c.doc_version == "2023" for c in old)
    assert not any("README" in c.source for c in chunks)


def test_empty_corpus_fails_the_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path))
    with pytest.raises(SystemExit):
        run.run_pipeline(get_settings())


def test_discover_prefers_the_fetch_index(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "_index.json").write_text(json.dumps(
        [{"file": "a.pdf", "doc_version": "2023-08", "superseded": True}]))
    assert run.discover(str(tmp_path)) == [(tmp_path / "a.pdf", "2023-08", True)]


def test_main_logs_json_and_exits_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run, "run_pipeline", lambda s: 42)
    monkeypatch.setattr("sys.argv", ["pipeline.run"])
    assert run.main() == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert lines[-1]["msg"] == "indexer finished" and lines[-1]["chunks"] == 42


def test_ocr_switch_reads_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    assert get_settings().ocr_enabled is False
    monkeypatch.delenv("OCR_ENABLED")
    assert get_settings().ocr_enabled is True


def test_every_indexer_log_line_carries_the_run_id(capsys) -> None:
    run.log("chunked", source="a.pdf")
    run.log("indexer finished", chunks=3)
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert {x["request_id"] for x in lines} == {run.RUN_ID} and run.RUN_ID
