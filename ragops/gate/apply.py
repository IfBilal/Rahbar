"""The release gate (docs/a3-ragops/07 section 5, schema in 14 section 7).

    python -m ragops.gate.apply --baseline BASE.json --candidate CAND.json \
        --config ragops/config/gate.yaml [--decision-out decision.json]

Compares two suite result files against thresholds read from a config file (in the cluster:
a ConfigMap mounted into the evaluation Job, so a threshold can change without rebuilding the
image). Exit 0 = pass, 1 = fail, 2 = usage, unreadable input, unset threshold or incomparable
runs. A metric that is missing counts as a FAILURE, never as a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

EPS = 1e-9
RULE_TYPES = {"max_drop_abs", "max_increase_abs", "min_value", "max_value",
              "not_lower_than_baseline"}
LEVELS = {"module", "component", "endpoint"}
COMPARABLE_KEYS = {"golden_hash": "golden_hash", "corpus_digest": "corpus_digest",
                   "suite_schema": "schema", "seed": "seed", "profile_hash": "profile_hash"}


class GateInputError(ValueError):
    """Bad config, unreadable result, unset threshold or incomparable runs (exit 2)."""


def metric_value(result: dict[str, Any], level: str, metric: str) -> float | None:
    """Look a metric up in a suite result file (14 section 5.2). `noisy_*` component metrics
    live under `component.noisy`, the rest of the component metrics under `component.clean`."""
    block = (result.get("levels") or {}).get(level)
    if not isinstance(block, dict):
        return None
    if level == "component":
        section = block.get("noisy") if metric.startswith("noisy_") else block.get("clean")
        name = metric[len("noisy_"):] if metric.startswith("noisy_") else metric
        value = (section or {}).get(name)
    else:
        value = block.get(metric)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


@dataclass
class RuleResult:
    id: str
    metric: str
    type: str
    limit: float
    baseline: float | None
    candidate: float | None
    delta: float | None
    status: str
    message: str


@dataclass
class Decision:
    overall: str
    rules: list[RuleResult] = field(default_factory=list)
    incomparable: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall == "pass"


def load_config(path: Path) -> dict[str, Any]:
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise GateInputError(f"cannot read gate config {path}: {exc}") from exc
    rules = cfg.get("rules")
    if not isinstance(rules, list) or not rules:
        raise GateInputError("gate config has no rules")
    seen: set[str] = set()
    for r in rules:
        rid = str(r.get("id", ""))
        if not rid or rid in seen:
            raise GateInputError(f"rule id missing or duplicated: {rid!r}")
        seen.add(rid)
        if r.get("type") not in RULE_TYPES:
            raise GateInputError(f"rule {rid}: unknown type {r.get('type')!r}")
        if r.get("level") not in LEVELS or not r.get("metric"):
            raise GateInputError(f"rule {rid}: needs level (module|component|endpoint) and metric")
        if r.get("value") is None:
            raise GateInputError(
                f"rule {rid}: threshold is not set. Derive it, justify it in the config and "
                "commit it BEFORE running candidates (docs/a3-ragops/07 section 5.2)")
        if not isinstance(r["value"], (int, float)) or isinstance(r["value"], bool):
            raise GateInputError(f"rule {rid}: value must be a number")
    cfg.setdefault("require_same", [])
    cfg.setdefault("on_missing_metric", "fail")
    if cfg["on_missing_metric"] != "fail":
        raise GateInputError("on_missing_metric must be 'fail': a missing metric never passes")
    return cfg


def config_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


def check_comparable(baseline: dict[str, Any], candidate: dict[str, Any],
                     require_same: list[str]) -> list[str]:
    problems = []
    for key in require_same:
        field_name = COMPARABLE_KEYS.get(key)
        if field_name is None:
            raise GateInputError(f"require_same: unknown key {key!r}")
        if baseline.get(field_name) != candidate.get(field_name):
            problems.append(f"{key} differs (baseline {baseline.get(field_name)!r}, "
                            f"candidate {candidate.get(field_name)!r})")
    for name, res in (("baseline", baseline), ("candidate", candidate)):
        if res.get("status") != "complete":
            problems.append(f"{name} result is not complete (status {res.get('status')!r})")
    return problems


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def evaluate_rule(rule: dict[str, Any], baseline: dict[str, Any],
                  candidate: dict[str, Any]) -> RuleResult:
    level, metric, kind = rule["level"], rule["metric"], rule["type"]
    limit = float(rule["value"])
    base = _r(metric_value(baseline, level, metric))
    cand = _r(metric_value(candidate, level, metric))
    full = f"{level}.{metric}"
    if cand is None or (kind in ("max_drop_abs", "max_increase_abs", "not_lower_than_baseline")
                        and base is None):
        which = "candidate" if cand is None else "baseline"
        return RuleResult(rule["id"], full, kind, limit, base, cand, None, "fail",
                          f"{full} is missing from the {which} result: a missing metric fails")
    delta = None if base is None else round(cand - base, 4)
    ok: bool
    if kind == "max_drop_abs":
        assert base is not None and delta is not None
        ok = (base - cand) <= limit + EPS
        msg = f"{full} {cand} is {max(base - cand, 0):.4f} below baseline {base} (limit {limit})"
    elif kind == "max_increase_abs":
        assert base is not None and delta is not None
        ok = (cand - base) <= limit + EPS
        msg = f"{full} {cand} is {max(cand - base, 0):.4f} above baseline {base} (limit {limit})"
    elif kind == "not_lower_than_baseline":
        assert base is not None
        ok = cand >= base - limit - EPS
        msg = f"{full} {cand} vs baseline {base} (tolerance {limit})"
    elif kind == "min_value":
        ok = cand >= limit - EPS
        msg = f"{full} {cand} vs minimum {limit}"
    else:
        ok = cand <= limit + EPS
        msg = f"{full} {cand} vs maximum {limit}"
    return RuleResult(rule["id"], full, kind, limit, base, cand, delta,
                      "pass" if ok else "fail", msg)


def decide(baseline: dict[str, Any], candidate: dict[str, Any], cfg: dict[str, Any]) -> Decision:
    problems = check_comparable(baseline, candidate, cfg["require_same"])
    if problems:
        raise GateInputError("incomparable runs: " + "; ".join(problems))
    results = [evaluate_rule(r, baseline, candidate) for r in cfg["rules"]]
    overall = "pass" if all(r.status == "pass" for r in results) else "fail"
    return Decision(overall=overall, rules=results)


def decision_json(decision: Decision, cfg: dict[str, Any], baseline_file: str,
                  candidate_file: str, baseline: dict[str, Any], candidate: dict[str, Any],
                  git_sha: str = "") -> dict[str, Any]:
    def ident(path: str, res: dict[str, Any]) -> dict[str, Any]:
        target = res.get("target") or {}
        return {"file": Path(path).name, "label": res.get("label"),
                "release_id": target.get("release_id")}
    return {"schema": 1, "overall": decision.overall,
            "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_sha": git_sha, "config_hash": config_hash(cfg),
            "gate_config_version": cfg.get("version"),
            "baseline": ident(baseline_file, baseline), "candidate": ident(candidate_file, candidate),
            "rules": [r.__dict__ for r in decision.rules], "incomparable": decision.incomparable}


def render(decision: Decision) -> str:
    width = max(len(r.id) for r in decision.rules)
    lines = [f"{'RULE':<{width}}  {'BASELINE':>9}  {'CANDIDATE':>9}  VERDICT  DETAIL"]
    for r in decision.rules:
        b = "-" if r.baseline is None else f"{r.baseline:.4f}"
        c = "-" if r.candidate is None else f"{r.candidate:.4f}"
        lines.append(f"{r.id:<{width}}  {b:>9}  {c:>9}  {r.status.upper():<7}  {r.message}")
    lines.append("")
    lines.append("GATE PASSED" if decision.passed else "GATE FAILED")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply the release gate to two suite results.")
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--decision-out", type=Path)
    ap.add_argument("--git-sha", default="")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GateInputError(f"cannot read a result file: {exc}") from exc
        decision = decide(baseline, candidate, cfg)
    except GateInputError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return 2
    print(render(decision))
    if args.decision_out:
        body = decision_json(decision, cfg, str(args.baseline), str(args.candidate), baseline,
                             candidate, args.git_sha)
        args.decision_out.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return 0 if decision.passed else 1


if __name__ == "__main__":
    sys.exit(main())
