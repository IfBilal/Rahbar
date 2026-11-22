"""The release gate: every rule type, the boundary, missing metrics and incomparable runs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from ragops.gate.apply import GateInputError, config_hash, decide, load_config, main, metric_value

REPO = Path(__file__).resolve().parents[2]


def result(recall5=0.90, abstain=1.0, faith=0.85, cite=1.0, p95=40.0, label="x", **over) -> dict:
    r = {"schema": 1, "status": "complete", "label": label, "golden_hash": "g", "corpus_digest": "c",
         "seed": 1, "profile_hash": "p", "target": {"release_id": "R1"},
         "levels": {"module": {"gap": 0.4},
                    "component": {"clean": {"recall@5": recall5, "mrr": 0.8}, "noisy": {"recall@5": 0.7}},
                    "endpoint": {"abstention_correctness": abstain, "faithfulness": faith,
                                 "citation_validity": cite, "latency_p95_s": p95}}}
    r.update(over)
    return r


def cfg(**values) -> dict:
    base = {"recall5_drop": 0.02, "abstention": 0.0, "citation_validity": 0.95,
            "faithfulness_min": 0.80, "p95_latency": 60.0}
    base.update(values)
    c = yaml.safe_load((REPO / "ragops" / "config" / "gate.yaml").read_text())
    for rule in c["rules"]:
        rule["value"] = base[rule["id"]]
    return c


def verdicts(baseline: dict, candidate: dict, config: dict) -> dict[str, str]:
    return {r.id: r.status for r in decide(baseline, candidate, config).rules}


def test_a_matching_candidate_passes_every_rule() -> None:
    d = decide(result(), result(), cfg())
    assert d.passed and all(r.status == "pass" for r in d.rules)


def test_recall_drop_exactly_at_the_limit_passes_and_a_hair_beyond_fails() -> None:
    assert verdicts(result(0.90), result(0.88), cfg())["recall5_drop"] == "pass"       # exactly 0.02
    assert verdicts(result(0.90), result(0.8799), cfg())["recall5_drop"] == "fail"     # 0.0201
    assert verdicts(result(0.90), result(0.95), cfg())["recall5_drop"] == "pass"       # improvement


def test_abstention_must_not_be_lower_than_baseline() -> None:
    assert verdicts(result(abstain=1.0), result(abstain=0.8333), cfg())["abstention"] == "fail"
    assert verdicts(result(abstain=0.8333), result(abstain=1.0), cfg())["abstention"] == "pass"


def test_min_and_max_rules_include_their_limit() -> None:
    assert verdicts(result(), result(faith=0.80), cfg())["faithfulness_min"] == "pass"
    assert verdicts(result(), result(faith=0.7999), cfg())["faithfulness_min"] == "fail"
    assert verdicts(result(), result(p95=60.0), cfg())["p95_latency"] == "pass"
    assert verdicts(result(), result(p95=60.01), cfg())["p95_latency"] == "fail"
    assert verdicts(result(), result(cite=0.9499), cfg())["citation_validity"] == "fail"


def test_a_missing_metric_fails_it_never_passes() -> None:
    cand = result()
    del cand["levels"]["endpoint"]["faithfulness"]
    d = decide(result(), cand, cfg())
    rule = next(r for r in d.rules if r.id == "faithfulness_min")
    assert rule.status == "fail" and "missing" in rule.message and not d.passed
    cand2 = result()
    cand2["levels"]["endpoint"]["abstention_correctness"] = None
    assert verdicts(result(), cand2, cfg())["abstention"] == "fail"
    base2 = result()
    del base2["levels"]["component"]["clean"]["recall@5"]
    assert verdicts(base2, result(), cfg())["recall5_drop"] == "fail"


def test_incomparable_runs_are_refused_not_compared() -> None:
    for key in ("golden_hash", "corpus_digest", "seed", "profile_hash"):
        with pytest.raises(GateInputError, match="incomparable"):
            decide(result(), result(**{key: "other"}), cfg())
    with pytest.raises(GateInputError, match="not complete"):
        decide(result(), result(status="incomplete"), cfg())


def test_the_shipped_config_refuses_to_run_until_the_two_thresholds_are_derived() -> None:
    with pytest.raises(GateInputError, match="not set"):
        load_config(REPO / "ragops" / "config" / "gate.yaml")


def test_config_errors(tmp_path: Path) -> None:
    def write(obj) -> Path:
        p = tmp_path / "g.yaml"
        p.write_text(yaml.safe_dump(obj))
        return p
    good = cfg()
    with pytest.raises(GateInputError, match="unknown type"):
        c = copy.deepcopy(good)
        c["rules"][0]["type"] = "nope"
        load_config(write(c))
    with pytest.raises(GateInputError, match="on_missing_metric"):
        c = copy.deepcopy(good)
        c["on_missing_metric"] = "pass"
        load_config(write(c))
    with pytest.raises(GateInputError, match="no rules"):
        load_config(write({"rules": []}))
    with pytest.raises(GateInputError, match="duplicated"):
        c = copy.deepcopy(good)
        c["rules"].append(dict(c["rules"][0]))
        load_config(write(c))


def test_metric_lookup_resolves_clean_and_noisy_component_metrics() -> None:
    r = result()
    assert metric_value(r, "component", "recall@5") == 0.90
    assert metric_value(r, "component", "noisy_recall@5") == 0.7
    assert metric_value(r, "module", "gap") == 0.4 and metric_value(r, "endpoint", "nope") is None
    assert metric_value({}, "module", "gap") is None


def test_changing_a_threshold_changes_the_outcome_with_the_same_result_files() -> None:
    base, cand = result(), result(0.80)
    assert not decide(base, cand, cfg()).passed                          # 0.10 drop vs limit 0.02
    assert decide(base, cand, cfg(recall5_drop=0.10)).passed             # the ConfigMap edit
    assert config_hash(cfg()) != config_hash(cfg(recall5_drop=0.10))


def test_cli_exit_codes_and_decision_file(tmp_path: Path, capsys) -> None:
    files = {}
    for name, res in (("base", result()), ("good", result()), ("bad", result(0.5, faith=0.1))):
        files[name] = tmp_path / f"{name}.json"
        files[name].write_text(json.dumps(res))
    config = tmp_path / "gate.yaml"
    config.write_text(yaml.safe_dump(cfg()))
    out = tmp_path / "decision.json"
    assert main(["--baseline", str(files["base"]), "--candidate", str(files["good"]),
                 "--config", str(config), "--decision-out", str(out)]) == 0
    assert "GATE PASSED" in capsys.readouterr().out and json.loads(out.read_text())["overall"] == "pass"
    assert main(["--baseline", str(files["base"]), "--candidate", str(files["bad"]),
                 "--config", str(config), "--decision-out", str(out)]) == 1
    text = capsys.readouterr().out
    assert "GATE FAILED" in text and "recall5_drop" in text
    dec = json.loads(out.read_text())
    assert dec["overall"] == "fail" and any(r["status"] == "fail" for r in dec["rules"])
    assert main(["--baseline", str(tmp_path / "missing.json"), "--candidate", str(files["good"]),
                 "--config", str(config)]) == 2
    assert main(["--baseline", str(files["base"]), "--candidate", str(files["good"]),
                 "--config", str(REPO / "ragops" / "config" / "gate.yaml")]) == 2
