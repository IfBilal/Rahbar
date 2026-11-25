"""Coverage (docs/a3-ragops/09 section 8) and baseline promotion (07 section 9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ragops.coverage import coverage as cov
from ragops.gate.promote import main as promote_main, promote
from ragops.tests.fakes import FakeEmbedder

GOLDEN = [{"id": "g001", "question": "what cgpa avoids academic warning"},
          {"id": "g002", "question": "how do i pay the semester fee"}]


def live(*rows):
    return [{"id": f"l{i}", "query": q, "domain": d} for i, (q, d) in enumerate(rows, 1)]


def cfg(tau=0.5, share=0.85, model="nomic-embed-text"):
    return {"similarity_threshold": tau, "min_share": share, "embed_model": model,
            "cluster_similarity": 0.5}


def test_identical_text_is_fully_covered_and_unrelated_is_not() -> None:
    rows = cov.best_matches(FakeEmbedder(), GOLDEN,
                            live(("what cgpa avoids academic warning", "in"),
                                 ("bus timing banana route", "out")))
    assert rows[0]["best_similarity"] == 1.0 and rows[0]["best_golden_id"] == "g001"
    assert rows[1]["best_similarity"] < 0.3


def test_the_share_boundary_exactly_min_share_passes() -> None:
    queries = live(*[("what cgpa avoids academic warning", "in")] * 17,
                   *[("zebra giraffe lion", "out")] * 3)
    rep = cov.run(FakeEmbedder(), GOLDEN, queries, cfg(share=0.85), "g", "l")
    assert rep["share"] == 0.85 and rep["verdict"] == "OK"
    rep = cov.run(FakeEmbedder(), GOLDEN, queries, cfg(share=0.86), "g", "l")
    assert rep["verdict"] == "GAP" and len(rep["uncovered"]) == 3


def test_uncovered_queries_are_grouped_into_topics_deterministically() -> None:
    qs = live(("bus route timing gate", "out"), ("bus timing main gate", "out"),
              ("scholarship deadline merit", "out"))
    a = cov.run(FakeEmbedder(), GOLDEN, qs, cfg(), "g", "l")
    b = cov.run(FakeEmbedder(), GOLDEN, qs, cfg(), "g", "l")
    assert a["topics"] == b["topics"]
    sizes = sorted(len(t["queries"]) for t in a["topics"])
    assert sizes == [1, 2] and any(t["single"] for t in a["topics"])
    assert "COVERAGE GAP" in cov.render(a)


def test_tfidf_cross_check_and_sensitivity_are_reported() -> None:
    rep = cov.run(FakeEmbedder(), GOLDEN, live(("what cgpa avoids warning", "in")), cfg(), "g", "l")
    assert 0.0 <= rep["tfidf_cross_check"]["share"] <= 1.0
    assert set(rep["sensitivity"]) == {"-0.05", "+0.05"}


def test_live_set_validation() -> None:
    gq = {"what cgpa avoids academic warning"}
    bad = cov.validate_live(live(("What  CGPA avoids academic warning", "in"), ("x", "maybe")), gq)
    assert any("identical to a golden" in b for b in bad) and any("domain" in b for b in bad)
    assert cov.split_warnings(live(("a", "in"))) != []


def test_threshold_must_be_calibrated_and_match_the_model(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"similarity_threshold": None, "min_share": 0.85}))
    with pytest.raises(cov.CoverageError, match="not calibrated"):
        cov.load_config(p, "nomic-embed-text")
    p.write_text(yaml.safe_dump(cfg(model="nomic-embed-text")))
    with pytest.raises(cov.CoverageError, match="recalibrate"):
        cov.load_config(p, "mxbai-embed-large")
    assert cov.load_config(p, "nomic-embed-text")["similarity_threshold"] == 0.5


def test_calibration_picks_the_f1_maximum_and_the_conservative_floor() -> None:
    pairs = ([{"similarity": s, "human": "covered"} for s in (0.9, 0.85, 0.8, 0.72)]
             + [{"similarity": s, "human": "not_covered"} for s in (0.75, 0.6, 0.5, 0.4)])
    tau, table = cov.calibrate(pairs)
    assert tau == 0.72 and table[0]["tau"] == 0.4   # F1 0.889 beats 0.857 at 0.8
    tau_c, _ = cov.calibrate(pairs, conservative=True)
    assert tau_c == 0.8        # lowest tau with no false 'covered'
    with pytest.raises(cov.CoverageError):
        cov.calibrate([])


# ---------------------------------------------------------------------------- promote
def result(status="complete"):
    return {"status": status, "run_id": "suite-9", "label": "baseline"}


def test_promote_writes_the_baseline_and_a_history(tmp_path: Path) -> None:
    src = tmp_path / "r.json"
    src.write_text(json.dumps(result()))
    out = promote(src, "first reviewed baseline", tmp_path / "b")
    assert json.loads(out.read_text())["run_id"] == "suite-9"
    src.write_text(json.dumps({**result(), "run_id": "suite-10"}))
    promote(src, "after drift", tmp_path / "b")
    hist = [json.loads(x) for x in (tmp_path / "b" / "promotions.jsonl").read_text().splitlines()]
    assert [h["replaced_run_id"] for h in hist] == [None, "suite-9"]


def test_promote_refuses_incomplete_results_and_empty_reasons(tmp_path: Path) -> None:
    src = tmp_path / "r.json"
    src.write_text(json.dumps(result("incomplete")))
    with pytest.raises(ValueError):
        promote(src, "x", tmp_path / "b")
    src.write_text(json.dumps(result()))
    assert promote_main(["--result", str(src), "--reason", "  ",
                         "--baselines-dir", str(tmp_path / "b")]) == 2


# ---------------------------------------------------------------------------- candidates
def test_the_committed_candidate_specs_change_exactly_one_thing() -> None:
    from ragops.gate.candidate import main as cmain
    repo = Path(__file__).resolve().parents[2]
    specs = [str(p) for p in sorted((repo / "ragops/config/candidates").glob("cand-*.yaml"))]
    assert len(specs) == 3 and cmain(specs) == 0     # minilm, mxbai, llama1b


def test_a_candidate_that_changes_two_things_is_rejected() -> None:
    from ragops.gate.candidate import validate
    base = {"collection": "rahbar", "embed_model": "a", "chunk_size": 300, "top_k": 5}
    cand = {"name": "x", "release_id": "R9", "change": "embedding_model", "collection": "c",
            "expected": "pass", "embed_model": "b", "chunk_size": 400, "top_k": 5}
    assert any("exactly one" in p for p in validate(cand, base))
    assert any("own collection" in p for p in validate({**cand, "collection": "rahbar",
                                                         "chunk_size": 300}, base))
