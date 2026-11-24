"""Module level: the embedding model on its own (docs/a3-ragops/06 section 4).

Paraphrase pairs should be close, unrelated pairs far; the gap between the two means is the
headline, reported again for easy and hard negatives because easy negatives flatter a model.
Also: embedding time, vector size and determinism (embed twice, compare).
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Sequence
from typing import Any

from .clients import Embedder
from .metrics import mean, percentile
from .prep import prepare_query


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _pair_cos(embedder: Embedder, pairs: list[dict[str, Any]]) -> list[float]:
    texts = [prepare_query(embedder.model, p[side]) for p in pairs for side in ("a", "b")]
    vecs = embedder.embed(texts)
    return [cosine(vecs[2 * i], vecs[2 * i + 1]) for i in range(len(pairs))]


def pair_accuracy(para: Sequence[float], unrel: Sequence[float]) -> float | None:
    """Share of (paraphrase, unrelated) combinations where the paraphrase scores higher."""
    if not para or not unrel:
        return None
    wins = sum(1.0 if p > u else 0.5 if p == u else 0.0 for p in para for u in unrel)
    return wins / (len(para) * len(unrel))


def determinism(embedder: Embedder, texts: list[str]) -> tuple[float, float]:
    """(largest absolute per-component difference, smallest pair cosine) over texts embedded
    twice in separate requests."""
    worst, low = 0.0, 1.0
    for t in texts:
        a = embedder.embed([t])[0]
        b = embedder.embed([t])[0]
        worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
        low = min(low, cosine(a, b))
    return worst, low


def run(embedder: Embedder, pairs: list[dict[str, Any]], chunk_texts: list[str],
        cfg: dict[str, Any], seed: int, notes: list[str]) -> dict[str, Any]:
    para = [p for p in pairs if p["kind"] == "paraphrase"]
    unrel = [p for p in pairs if p["kind"] == "unrelated"]
    cp, cu = _pair_cos(embedder, para), _pair_cos(embedder, unrel)
    by_diff: dict[str, float | None] = {}
    for d in ("easy", "hard"):
        sel = [c for c, p in zip(cu, unrel) if p.get("difficulty") == d]
        by_diff[d] = None if not sel else round(sum(sel) / len(sel), 4)
    mp, mu = mean(cp), mean(cu)

    sample_n = int(cfg["module"]["embed_sample_chunks"])
    pool = chunk_texts
    if not pool:
        pool = [p[s] for p in pairs for s in ("a", "b")]
        notes.append("module: no chunk snapshots available; embedding time measured on pair texts")
    rng = random.Random(seed)
    sample = rng.sample(pool, min(sample_n, len(pool)))
    for _ in range(int(cfg["module"]["warmup_calls"])):
        embedder.embed([sample[0]])
    ms: list[float] = []
    dim = 0
    for t in sample:
        t0 = time.perf_counter()
        v = embedder.embed([t])[0]
        ms.append((time.perf_counter() - t0) * 1000)
        dim = len(v)
    det_texts = rng.sample(pool, min(int(cfg["module"]["determinism_texts"]), len(pool)))
    worst, low = determinism(embedder, det_texts)
    return {"paraphrase_mean_cos": _r(mp), "unrelated_mean_cos": _r(mu),
            "gap": _r(None if mp is None or mu is None else mp - mu),
            "pair_accuracy": _r(pair_accuracy(cp, cu)),
            "unrelated_by_difficulty": by_diff,
            "embed_ms_mean": _r(mean(ms)), "embed_ms_p95": _r(percentile(ms, 95)),
            "vector_bytes": dim * 4, "determinism_max_abs_diff": worst,
            "determinism_min_cos": _r(low), "n_paraphrase": len(para), "n_unrelated": len(unrel)}


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)
