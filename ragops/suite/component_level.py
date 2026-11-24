"""Component level: retrieval (docs/a3-ragops/06 section 5).

Calls /api/retrieve for every answerable question, clean and with typo noise, and scores the
ranked chunks against the gold (document, page) pairs. Unanswerable questions are excluded
from recall (0/0 is not 1.0); only their top-1 score is recorded.
"""

from __future__ import annotations

from typing import Any

from .clients import Api
from .metrics import mean, ndcg_at_k, percentile, precision_at_k, recall_at_k, reciprocal_rank
from .typos import add_typos


def ranked_pairs(resp: dict[str, Any], history: bool) -> list[tuple[str, int]]:
    out = []
    for c in resp.get("candidates") or []:
        if c.get("superseded") and not history:
            continue
        if c.get("page") is None:
            continue
        out.append((str(c.get("source", "")), int(c["page"])))
    return out


def score(gold: list[tuple[str, int]], ranked: list[tuple[str, int]]) -> dict[str, float | None]:
    return {"recall@3": recall_at_k(gold, ranked, 3), "recall@5": recall_at_k(gold, ranked, 5),
            "mrr": reciprocal_rank(gold, ranked, 5), "ndcg@5": ndcg_at_k(gold, ranked, 5),
            "precision@5": precision_at_k(gold, ranked, 5)}


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    v = mean([r[key] for r in rows])
    return None if v is None else round(v, 4)


def run(api: Api, questions: list[dict[str, Any]], cfg: dict[str, Any], seed: int
        ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    k = int(cfg["top_k"])
    noise = cfg["typo_noise"]
    answerable = [q for q in questions if q.get("answerable")]
    clean_rows: list[dict[str, Any]] = []
    noisy_rows: list[dict[str, Any]] = []
    per_q: dict[str, dict[str, Any]] = {}
    lat: list[float] = []
    for q in answerable:
        gold = [(g["doc"], int(g["page"])) for g in q["gold"]]
        history = "history" in (q.get("type_tags") or [])
        resp = api.retrieve(q["question"], k)
        lat.append(float(resp.get("_seconds", 0.0)) * 1000)
        ranked = ranked_pairs(resp, history)
        row = {**score(gold, ranked), "id": q["id"], "category": q["category"],
               "hard_kind": q.get("hard_kind")}
        clean_rows.append(row)
        noisy_q = add_typos(q["question"], float(noise["rate"]), list(noise["kinds"]),
                            int(noise["min_word_len"]), seed, q["id"])
        nresp = api.retrieve(noisy_q, k)
        nrow = {**score(gold, ranked_pairs(nresp, history)), "id": q["id"]}
        noisy_rows.append(nrow)
        per_q[q["id"]] = {
            "retrieved": [{"rank": i + 1, "doc": c.get("source"), "page": c.get("page"),
                           "score": c.get("score"),
                           "hit": (c.get("source"), c.get("page")) in {tuple(g) for g in gold}}
                          for i, c in enumerate(resp.get("candidates") or [])],
            "recall@3": row["recall@3"], "recall@5": row["recall@5"], "rr": row["mrr"],
            "ndcg@5": row["ndcg@5"], "noisy_query": noisy_q, "noisy_recall@5": nrow["recall@5"],
            "trace_id": resp.get("trace_id")}
    tops, unans_tops = [], []
    for q in questions:
        if q.get("answerable"):
            continue
        resp = api.retrieve(q["question"], 1)
        cands = resp.get("candidates") or []
        if cands:
            unans_tops.append(float(cands[0].get("score", 0.0)))
    for r in per_q.values():
        if r["retrieved"] and r["retrieved"][0].get("score") is not None:
            tops.append(float(r["retrieved"][0]["score"]))
    keys = ("recall@3", "recall@5", "mrr", "ndcg@5", "precision@5")
    clean = {k_: _avg(clean_rows, k_) for k_ in keys}
    clean["retrieval_ms_mean"] = None if not lat else round(sum(lat) / len(lat), 4)
    p95 = percentile(lat, 95)
    clean["retrieval_ms_p95"] = None if p95 is None else round(p95, 4)
    noisy = {k_: _avg(noisy_rows, k_) for k_ in ("recall@3", "recall@5", "mrr", "ndcg@5")}
    noisy["typo_rate"] = float(noise["rate"])
    delta: dict[str, float | None] = {}
    for k_ in ("recall@5", "mrr", "ndcg@5"):
        c_, n_ = clean[k_], noisy[k_]
        delta[k_] = None if c_ is None or n_ is None else round(float(n_) - float(c_), 4)
    by_cat: dict[str, Any] = {}
    for cat in ("answerable", "hard"):
        rows = [r for r in clean_rows if r["category"] == cat]
        by_cat[cat] = {"n": len(rows), "recall@5": _avg(rows, "recall@5")}
    hk: dict[str, Any] = {}
    for kind in sorted({r["hard_kind"] for r in clean_rows if r["hard_kind"]}):
        rows = [r for r in clean_rows if r["hard_kind"] == kind]
        hk[kind] = {"n": len(rows), "recall@5": _avg(rows, "recall@5")}
    by_cat["hard"]["by_kind"] = hk
    dist = {}
    if tops:
        s = sorted(tops)
        dist = {"min": s[0], "p10": percentile(s, 10), "p50": percentile(s, 50),
                "p90": percentile(s, 90), "max": s[-1],
                "unanswerable_p50": percentile(sorted(unans_tops), 50) if unans_tops else None}
    return ({"n": len(answerable), "clean": clean, "noisy": noisy, "delta_noisy": delta,
             "by_category": by_cat, "top1_similarity": dist}, per_q)
