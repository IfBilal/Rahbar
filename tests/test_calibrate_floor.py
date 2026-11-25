"""The relevance-floor arithmetic used to calibrate a candidate (docs/a3-ragops/07 2.3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "calibrate_floor", Path(__file__).resolve().parents[1] / "scripts" / "ragops" / "calibrate_floor.py")
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)


def test_floor_is_the_largest_step_below_the_lowest_gold_score_minus_the_margin() -> None:
    assert cf.suggest_floor(0.650) == 0.60          # the Assignment-02 numbers: lowest 0.650 -> floor 0.60
    assert cf.suggest_floor(0.70) == 0.65
    assert cf.suggest_floor(0.4321) == 0.40
    assert cf.suggest_floor(0.03) == 0.0            # never negative


def test_best_gold_score_matches_document_and_page_case_insensitively() -> None:
    cands = [{"source": "Rules.PDF", "page": 3, "score": 0.7}, {"source": "rules.pdf", "page": 4, "score": 0.9},
             {"source": "rules.pdf", "page": 3, "score": 0.65}]
    assert cf.best_gold_score(cands, [{"doc": "rules.pdf", "page": 3}]) == 0.7
    assert cf.best_gold_score(cands, [{"doc": "other.pdf", "page": 1}]) is None
