"""Metrics against hand-computed numbers (docs/a3-ragops/06 section 5.3 worked example)."""

from __future__ import annotations

import math

from ragops.suite.metrics import (
    agreement, cohen_kappa, hits, mean, ndcg_at_k, percentile, precision_at_k, recall_at_k,
    reciprocal_rank,
)

GOLD = [("A.pdf", 3), ("B.pdf", 7)]
RANKED = [("C.pdf", 1), ("A.pdf", 3), ("A.pdf", 3), ("B.pdf", 7), ("D.pdf", 2)]


def test_the_worked_example_from_the_plan() -> None:
    assert hits(GOLD, RANKED) == [False, True, False, True, False]     # the repeat earns no gain
    assert recall_at_k(GOLD, RANKED, 3) == 0.5
    assert recall_at_k(GOLD, RANKED, 5) == 1.0
    assert reciprocal_rank(GOLD, RANKED) == 0.5
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert math.isclose(ndcg_at_k(GOLD, RANKED, 5), dcg / idcg)
    assert round(ndcg_at_k(GOLD, RANKED, 5), 3) == 0.651
    assert precision_at_k(GOLD, RANKED, 5) == 2 / 5


def test_no_gold_means_undefined_not_one() -> None:
    for fn in (recall_at_k, ):
        assert fn([], RANKED, 5) is None
    assert reciprocal_rank([], RANKED) is None and ndcg_at_k([], RANKED) is None
    assert mean([None, None]) is None and mean([1.0, None, 0.0]) == 0.5


def test_no_hit_is_zero_and_a_perfect_ranking_is_one() -> None:
    assert recall_at_k(GOLD, [("X.pdf", 1)], 5) == 0.0
    assert reciprocal_rank(GOLD, [("X.pdf", 1)]) == 0.0 and ndcg_at_k(GOLD, [("X.pdf", 1)]) == 0.0
    perfect = [("A.pdf", 3), ("B.pdf", 7)]
    assert ndcg_at_k(GOLD, perfect, 5) == 1.0 and reciprocal_rank(GOLD, perfect) == 1.0


def test_more_gold_pairs_than_k_cannot_push_ndcg_above_one() -> None:
    gold = [(f"D{i}.pdf", 1) for i in range(8)]
    ranked = [(f"D{i}.pdf", 1) for i in range(5)]
    assert recall_at_k(gold, ranked, 5) == 5 / 8
    assert ndcg_at_k(gold, ranked, 5) == 1.0


def test_document_names_and_pages_are_compared_loosely_but_pages_exactly() -> None:
    assert recall_at_k([("Rules.PDF", 3)], [("  rules.pdf ", 3)], 1) == 1.0
    assert recall_at_k([("rules.pdf", 3)], [("rules.pdf", 4)], 1) == 0.0


def test_nearest_rank_percentile() -> None:
    values = list(range(1, 21))                       # 1..20
    assert percentile(values, 50) == 10 and percentile(values, 95) == 19
    assert percentile([5.0], 95) == 5.0 and percentile([], 50) is None


def test_agreement_and_kappa() -> None:
    a = ["s", "s", "n", "n", "s", "n", "s", "s"]
    b = ["s", "s", "n", "s", "s", "n", "s", "n"]
    assert agreement(a, b) == 6 / 8
    assert math.isclose(cohen_kappa(a, b), (0.75 - 34 / 64) / (1 - 34 / 64))   # chance = 25/64 + 9/64
    assert cohen_kappa(["s", "s"], ["s", "s"]) is None and cohen_kappa([], []) is None
    assert agreement(["s"], []) is None
