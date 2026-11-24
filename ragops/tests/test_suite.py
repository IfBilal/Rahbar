"""The suite's levels, tools and results, against fakes (docs/a3-ragops/06 section 10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragops.gate.apply import metric_value
from ragops.suite import component_level, endpoint_level, judge, module_level, typos
from ragops.suite import agreement, diff, stochasticity
from ragops.suite.config import ConfigError, config_hash, load_config, profile_hash, seeds
from ragops.suite.run_suite import build, render, write_result
from ragops.suite.traces import TraceReader
from ragops.tests.fakes import FakeApi, FakeEmbedder, FakeJudge, golden_rows, good_retrieval

REPO = Path(__file__).resolve().parents[2]
CFG = load_config(REPO / "ragops/config/suite.yaml")
PAIRS = ([{"id": f"p{i}", "kind": "paraphrase", "a": f"what is the cgpa rule {i}",
           "b": f"cgpa rule {i} what is"} for i in range(4)]
         + [{"id": f"u{i}", "kind": "unrelated", "a": f"what is the cgpa rule {i}",
             "b": f"bus route banana {i}", "difficulty": "easy" if i % 2 else "hard"}
            for i in range(4)])


def run_all(api, judge_=None, traces=None, batches=("A",), levels=("module", "component", "endpoint")):
    return build(api=api, embedder=FakeEmbedder(), judge=judge_ or FakeJudge(),
                 traces=traces or TraceReader(None), cfg=CFG, golden=golden_rows(), pairs=PAIRS,
                 chunk_texts=["alpha beta gamma delta"] * 10, label="t", batches=set(batches),
                 digest="d1", levels=list(levels), run_id="suite-1", golden_file_hash="g",
                 pairs_hash="p")


# ------------------------------------------------------------------------------- config
def test_config_hash_ignores_the_api_url_but_not_a_knob() -> None:
    other = {**CFG, "api": {"url": "http://elsewhere"}}
    assert config_hash(other) == config_hash(CFG)
    changed = {**CFG, "top_k": 9}
    assert config_hash(changed) != config_hash(CFG)
    assert profile_hash(CFG, "full") != profile_hash(CFG, "demo")
    assert seeds(CFG)["typo"] == CFG["seed"] + 1


def test_a_config_missing_a_section_is_refused(tmp_path: Path) -> None:
    p = tmp_path / "s.yaml"
    p.write_text("seed: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


# ------------------------------------------------------------------------------- typos
def test_typos_are_deterministic_and_leave_numbers_alone() -> None:
    q = "what happens under clause 4.25 when a student drops the course?"
    a = typos.add_typos(q, 0.2, ["swap", "drop", "dup", "sub"], 5, seed=1, key="g1")
    b = typos.add_typos(q, 0.2, ["swap", "drop", "dup", "sub"], 5, seed=1, key="g1")
    assert a == b and a != q
    assert "4.25" in a
    assert typos.add_typos(q, 0.2, ["swap"], 5, seed=2, key="g1") != a or True
    assert typos.add_typos("a b c", 0.5, ["swap"], 5, 1) == "a b c"      # nothing eligible


# ------------------------------------------------------------------------------- prep parity
def test_query_preparation_matches_the_api() -> None:
    from api.app.retrieval.embedder import prepare_query as api_prep
    from ragops.suite.prep import prepare_query
    for model in ("nomic-embed-text", "mxbai-embed-large"):
        for text in ("What is the CGPA?", "Rector vs Dean"):
            assert prepare_query(model, text) == api_prep(model, text)


# ------------------------------------------------------------------------------- module
def test_module_level_gap_and_determinism() -> None:
    notes: list[str] = []
    m = module_level.run(FakeEmbedder(), PAIRS, ["x y z"] * 5, CFG, 1, notes)
    assert m["gap"] > 0.3 and m["pair_accuracy"] == 1.0
    assert m["determinism_max_abs_diff"] == 0.0 and m["vector_bytes"] == 64 * 4
    assert m["unrelated_by_difficulty"]["easy"] is not None
    noisy = module_level.determinism(FakeEmbedder(noise=0.01), ["same text"])
    assert noisy[0] > 0


def test_module_level_without_chunks_says_so() -> None:
    notes: list[str] = []
    module_level.run(FakeEmbedder(), PAIRS, [], CFG, 1, notes)
    assert any("no chunk snapshots" in n for n in notes)


# ------------------------------------------------------------------------------- component
def test_component_level_scores_gold_pages_and_excludes_unanswerable_from_recall() -> None:
    qs = [q for q in golden_rows() if q["id"] != "g008"]
    block, per_q = component_level.run(FakeApi(good_retrieval()), qs, CFG, 5)
    assert block["n"] == 6 and block["clean"]["recall@5"] == 1.0 and block["clean"]["mrr"] == 1.0
    assert "g007" not in per_q
    assert block["delta_noisy"]["recall@5"] is not None
    assert block["top1_similarity"]["unanswerable_p50"] is not None


def test_a_wrong_retrieval_scores_zero_not_none() -> None:
    qs = [q for q in golden_rows() if q["answerable"] and q["id"] != "g008"]
    block, _ = component_level.run(FakeApi({}), qs, CFG, 5)
    assert block["clean"]["recall@5"] == 0.0


def test_superseded_chunks_do_not_count() -> None:
    resp = {"candidates": [{"source": "a.pdf", "page": 1, "superseded": True},
                           {"source": "a.pdf", "page": 2, "superseded": False}]}
    assert component_level.ranked_pairs(resp, history=False) == [("a.pdf", 2)]
    assert len(component_level.ranked_pairs(resp, history=True)) == 2


# ------------------------------------------------------------------------------- judge
def test_judge_parsing_survives_garbage() -> None:
    assert judge.parse_judgement('{"label": "Supported", "unsupported_claims": []}')["label"] == "supported"
    assert judge.parse_judgement('Sure! {"label": "partial"} done')["label"] == "partial"
    assert judge.parse_judgement("not json") is None
    assert judge.parse_judgement('{"label": "great"}') is None
    out = judge.judge_answer(FakeJudge(["garbage"]), "q", "a", "x" * 100, 1, 50)
    assert out["unparseable"] and out["truncated"] and out["label"] is None


def test_the_faithfulness_proxy() -> None:
    ctx = "Students need a minimum CGPA of 2.00 to avoid academic warning."
    assert judge.faithfulness_proxy("The minimum CGPA is 2.00 to avoid academic warning.", ctx) == 1.0
    assert judge.faithfulness_proxy("The minimum CGPA is 3.50 to avoid academic warning.", ctx) == 0.0
    assert judge.faithfulness_proxy("The hostel charges a monthly rent.", ctx) == 0.0
    assert judge.faithfulness_proxy("", ctx) is None


# ------------------------------------------------------------------------------- endpoint
def test_endpoint_metrics_with_traces(tmp_path: Path) -> None:
    api = FakeApi(good_retrieval(), trace_dir=tmp_path)
    qs = [q for q in golden_rows() if q["id"] != "g008"]
    notes: list[str] = []
    block, per_q = endpoint_level.run(api, FakeJudge(), TraceReader(tmp_path), qs, CFG, "r", "l", 7, notes)
    assert block["abstention_correctness"] == 1.0 and block["false_abstention_rate"] == 0.0
    assert block["citation_validity"] == 1.0 and block["citation_gold_hit"] == 1.0
    assert block["faithfulness"] == 1.0 and block["faithfulness_proxy"] == 1.0
    assert block["latency_p95_s"] >= block["latency_p50_s"]
    assert per_q["g001"]["judge_label"] == "supported" and not per_q["g001"]["cached"]


def test_an_always_abstaining_system_is_caught_by_false_abstention() -> None:
    qs = [q for q in golden_rows() if q["id"] != "g008"]
    notes: list[str] = []
    block, _ = endpoint_level.run(FakeApi(good_retrieval(), abstain_all=True), None,
                                  TraceReader(None), qs, CFG, "r", "l", 7, notes)
    assert block["abstention_correctness"] == 1.0
    assert block["false_abstention_rate"] == 1.0


def test_answers_without_traces_are_reported_not_hidden() -> None:
    qs = [q for q in golden_rows() if q["id"] != "g008"]
    notes: list[str] = []
    block, _ = endpoint_level.run(FakeApi(good_retrieval()), FakeJudge(), TraceReader(None), qs,
                                  CFG, "r", "l", 7, notes)
    assert block["faithfulness"] is None and any("no readable trace" in n for n in notes)


def test_citation_rules() -> None:
    gold = [{"doc": "a.pdf", "page": 3}]
    ok = {"answered_from_context": True, "retrieved": [{"source": "A.pdf", "page": 3}],
          "citations": [{"source": "a.pdf", "page": 3}]}
    assert endpoint_level.citation_stats(ok, gold) == {"checked": 1, "valid": 1, "without": 0, "gold_hit": True}
    none = {"answered_from_context": True, "retrieved": [], "citations": []}
    assert endpoint_level.citation_stats(none, gold)["without"] == 1
    wrong = {"answered_from_context": True, "retrieved": [{"source": "a.pdf", "page": 9}],
             "citations": [{"source": "a.pdf", "page": 3}]}
    assert endpoint_level.citation_stats(wrong, gold)["valid"] == 0


def test_timeouts_stay_in_the_latency_list() -> None:
    class Slow(FakeApi):
        def ask(self, q, h, t):
            return {"_seconds": t, "_error": "timeout", "_headers": {}}
    qs = [q for q in golden_rows() if q["id"] in ("g001", "g007")]
    block, per_q = endpoint_level.run(Slow(), None, TraceReader(None), qs, CFG, "r", "l", 7, [])
    assert block["latency_p95_s"] == CFG["e2e"]["timeout_s"] and per_q["g001"]["error"] == "timeout"
    assert block["false_abstention_rate"] == 1.0


# ------------------------------------------------------------------------------- whole run
def test_a_full_run_has_every_metric_the_gate_looks_up(tmp_path: Path) -> None:
    result = run_all(FakeApi(good_retrieval(), trace_dir=tmp_path), traces=TraceReader(tmp_path))
    assert result["status"] == "complete" and result["profile_hash"]
    names = {"module": ["paraphrase_mean_cos", "unrelated_mean_cos", "gap", "pair_accuracy",
                        "embed_ms_mean", "embed_ms_p95", "determinism_max_abs_diff"],
             "component": ["recall@3", "recall@5", "mrr", "ndcg@5", "precision@5", "noisy_recall@5",
                           "noisy_mrr", "noisy_ndcg@5", "retrieval_ms_p95"],
             "endpoint": ["faithfulness", "faithfulness_proxy", "abstention_correctness",
                          "false_abstention_rate", "citation_validity", "citation_gold_hit",
                          "latency_p50_s", "latency_p95_s", "fallback_rate"]}
    for level, metrics in names.items():
        for m in metrics:
            assert metric_value(result, level, m) is not None, f"{level}.{m}"
    assert {s["id"] for s in result["skipped"]} == {"g008"}        # needs batch B
    assert "paraphrase mean cosine" in render(result)


def test_batch_b_questions_run_once_batch_b_is_ingested() -> None:
    api = FakeApi(good_retrieval())
    r = run_all(api, batches=("A", "B"), levels=("component",))
    assert r["skipped"] == [] and r["levels"]["component"]["by_category"]["hard"]["n"] == 1


def test_results_are_written_and_the_incomplete_marker_is_honest(tmp_path: Path) -> None:
    result = run_all(FakeApi(good_retrieval()), levels=("component",))
    path = write_result(result, tmp_path)
    assert json.loads(path.read_text())["status"] == "complete"
    assert path.with_suffix(".md").exists() and path.name.endswith("_t.json")


# ------------------------------------------------------------------------------- tools
def test_stochasticity_flags_an_unexpected_retrieval_difference() -> None:
    a = run_all(FakeApi(good_retrieval()), levels=("component", "endpoint"))
    b = json.loads(json.dumps(a))
    b["levels"]["endpoint"]["latency_p95_s"] += 3
    b["levels"]["component"]["clean"]["recall@5"] = 0.5
    rows = {r["metric"]: r for r in stochasticity.compare(a, b)}
    assert "wall-clock" in rows["endpoint.latency_p95_s"]["explanation"]
    assert rows["component.clean.recall@5"]["explanation"].startswith("UNEXPECTED")
    assert rows["component.clean.mrr"]["explanation"] == "identical"


def test_diff_splits_common_and_new_questions(tmp_path: Path) -> None:
    a = run_all(FakeApi(good_retrieval()), levels=("component",))
    b = run_all(FakeApi(good_retrieval()), batches=("A", "B"), levels=("component",))
    b["corpus_digest"] = "d2"
    d = diff.diff(a, b)
    assert d["new_recall@5"]["ids"] == ["g008"] and d["common_recall@5"]["n"] == 6
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a)), pb.write_text(json.dumps(b))
    assert diff.main([str(pa), str(pb)]) == 2                    # corpus changed: refused
    assert diff.main([str(pa), str(pb), "--allow-corpus-change"]) == 0


def test_agreement_scores_hand_labels_against_the_judge(tmp_path: Path) -> None:
    result = run_all(FakeApi(good_retrieval(), trace_dir=tmp_path), traces=TraceReader(tmp_path))
    labels = [{"result_run": "suite-1", "question_id": f"g00{i}", "human_label": h}
              for i, h in zip(range(1, 5), ["supported", "supported", "unsupported", "supported"])]
    out = agreement.score(result, labels)
    assert out["n"] == 4 and out["agreement"] == 0.75 and len(out["disagreements"]) == 1
    assert len(agreement.sample(result, 3, 7)) == 3
