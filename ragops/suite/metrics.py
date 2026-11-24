"""Retrieval and agreement metrics (docs/a3-ragops/06 sections 5.3 and 6.3).

Everything here is a pure function over small lists, so the formulas can be tested against
hand-computed numbers. Relevance is judged at (document, page): a retrieved chunk is a hit
when its document and page match a gold pair that no earlier chunk already matched, so two
chunks of the same page earn the gain once and nDCG can never exceed 1.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

Pair = tuple[str, int]


def norm_doc(name: str | None) -> str:
    """Compare document names the way a reader would: case and spacing ignored."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _pair(p: Pair) -> Pair:
    return norm_doc(p[0]), int(p[1])


def hits(gold: Sequence[Pair], ranked: Sequence[Pair]) -> list[bool]:
    """For each ranked chunk: True if it matches a gold pair not matched by an earlier one."""
    remaining = {_pair(g) for g in gold}
    out: list[bool] = []
    for r in ranked:
        key = _pair(r)
        if key in remaining:
            remaining.discard(key)
            out.append(True)
        else:
            out.append(False)
    return out


def recall_at_k(gold: Sequence[Pair], ranked: Sequence[Pair], k: int) -> float | None:
    """Distinct gold pairs found in the top k / all gold pairs. None when there is no gold
    (unanswerable questions): recall is undefined there, never 1.0."""
    distinct = {_pair(g) for g in gold}
    if not distinct:
        return None
    return sum(hits(gold, ranked[:k])) / len(distinct)


def reciprocal_rank(gold: Sequence[Pair], ranked: Sequence[Pair], k: int = 5) -> float | None:
    if not gold:
        return None
    for i, hit in enumerate(hits(gold, ranked[:k]), start=1):
        if hit:
            return 1.0 / i
    return 0.0


def ndcg_at_k(gold: Sequence[Pair], ranked: Sequence[Pair], k: int = 5) -> float | None:
    """Binary-gain nDCG. IDCG places min(|G|, k) hits at ranks 1..min(|G|, k)."""
    distinct = {_pair(g) for g in gold}
    if not distinct:
        return None
    dcg = sum(1.0 / math.log2(i + 1) for i, hit in enumerate(hits(gold, ranked[:k]), start=1) if hit)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(distinct), k) + 1))
    return dcg / ideal


def precision_at_k(gold: Sequence[Pair], ranked: Sequence[Pair], k: int = 5) -> float | None:
    if not gold:
        return None
    return sum(hits(gold, ranked[:k])) / k


def mean(values: Sequence[float | None]) -> float | None:
    """Macro-average over the questions that have a value (None entries are excluded)."""
    real = [v for v in values if v is not None]
    return sum(real) / len(real) if real else None


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least p% of the data at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def agreement(a: Sequence[str], b: Sequence[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Cohen's kappa for two raters over the same items. None when undefined (no items, or
    both raters used one single label so chance agreement is 1)."""
    if not a or len(a) != len(b):
        return None
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    labels = set(a) | set(b)
    chance = sum((list(a).count(lab) / n) * (list(b).count(lab) / n) for lab in labels)
    if math.isclose(chance, 1.0):
        return None
    return (observed - chance) / (1.0 - chance)
