"""Query coverage: does the test set still represent live usage? (docs/a3-ragops/09 section 3)

    python -m ragops.coverage.coverage --golden eval/golden.jsonl --live eval/live_queries.jsonl \
        --config ragops/config/coverage.yaml --ollama http://localhost:11434 [--out eval/results/]
    python -m ragops.coverage.coverage calibrate --pairs eval/coverage-calibration.jsonl

Exit codes: 0 share >= min_share (equal passes) - 1 share < min_share - 2 usage, config or model
mismatch, or an uncalibrated threshold - 3 the embedding service is unavailable.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

import yaml  # type: ignore[import-untyped]

from ragops.suite.clients import InfrastructureError, OllamaEmbedder
from ragops.suite.golden import golden_hash, load_golden
from ragops.suite.module_level import cosine
from ragops.suite.prep import prepare_query


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class CoverageError(ValueError):
    """Usage, config or model-mismatch problem (exit 2)."""


def load_config(path: Path, live_model: str | None) -> dict[str, Any]:
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CoverageError(f"cannot read {path}: {exc}") from exc
    if cfg.get("similarity_threshold") is None:
        raise CoverageError("similarity_threshold is not calibrated yet (09 section 3.2): run "
                            "`coverage calibrate` on hand-labelled pairs, commit the evidence, "
                            "then set it")
    if live_model and cfg.get("embed_model") != live_model:
        raise CoverageError(f"the threshold was calibrated for {cfg.get('embed_model')!r} but the "
                            f"live model is {live_model!r}; cosine scales differ - recalibrate")
    return cfg


# ----------------------------------------------------------------------- validation of E1
def validate_live(live: list[dict[str, Any]], golden_questions: set[str]) -> list[str]:
    """Rules of 09 section 2. Hard problems are errors; the 28/12 split is a warning."""
    bad, seen = [], set()
    for row in live:
        qid = row.get("id", "?")
        text = " ".join(str(row.get("query", "")).lower().split())
        if row.get("domain") not in ("in", "out"):
            bad.append(f"{qid}: domain must be 'in' or 'out'")
        if text in seen:
            bad.append(f"{qid}: duplicate query")
        seen.add(text)
        if text in golden_questions:
            bad.append(f"{qid}: identical to a golden question")
    return bad


def split_warnings(live: list[dict[str, Any]]) -> list[str]:
    n_in = sum(1 for r in live if r.get("domain") == "in")
    n_out = sum(1 for r in live if r.get("domain") == "out")
    warn = []
    if len(live) < 40:
        warn.append(f"only {len(live)} live queries; the PDF asks for at least 40")
    if n_out < 12:
        warn.append(f"only {n_out} out-of-coverage queries; the PDF asks for at least 12")
    if n_in < 28:
        warn.append(f"{n_in} in-domain queries; the plan targets about 28")
    return warn


# ----------------------------------------------------------------------- the computation
def best_matches(embedder: Embedder, golden: list[dict[str, Any]],
                 live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    g_vecs = embedder.embed([prepare_query(embedder.model, g["question"]) for g in golden])
    l_vecs = embedder.embed([prepare_query(embedder.model, q["query"]) for q in live])
    out = []
    for q, lv in zip(live, l_vecs):
        sims = sorted(((cosine(lv, gv), g["id"]) for gv, g in zip(g_vecs, golden)),
                      key=lambda t: (-t[0], t[1]))  # ties: lowest golden id first
        best_sim, best_id = sims[0]
        out.append({"id": q["id"], "query": q["query"], "domain": q.get("domain"),
                    "best_golden_id": best_id, "best_similarity": round(best_sim, 4)})
    return out


def tfidf_best(golden: list[dict[str, Any]], live: list[dict[str, Any]]) -> list[float]:
    """The paper's cheap cross-check: TF-IDF cosine over the question text."""
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())  # noqa: E731
    docs = [tok(g["question"]) for g in golden]
    df = Counter(w for d in docs for w in set(d))
    n = len(docs)
    idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}

    def vec(words: list[str]) -> dict[str, float]:
        tf = Counter(words)
        return {w: c * idf.get(w, math.log(1 + n) + 1) for w, c in tf.items()}

    def cos(a: dict[str, float], b: dict[str, float]) -> float:
        dot = sum(v * b.get(w, 0.0) for w, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0
    gv = [vec(d) for d in docs]
    return [max(cos(vec(tok(q["query"])), g) for g in gv) for q in live]


def share(rows: list[dict[str, Any]], tau: float, domain: str | None = None) -> float | None:
    sel = [r for r in rows if domain is None or r["domain"] == domain]
    if not sel:
        return None
    return round(sum(1 for r in sel if r["best_similarity"] >= tau) / len(sel), 4)


def cluster_uncovered(embedder: Embedder, uncovered: list[dict[str, Any]],
                      threshold: float) -> list[list[dict[str, Any]]]:
    """Average-linkage agglomerative clustering on cosine similarity, deterministic."""
    if not uncovered:
        return []
    vecs = embedder.embed([prepare_query(embedder.model, u["query"]) for u in uncovered])
    clusters: list[list[int]] = [[i] for i in range(len(uncovered))]

    def sim(a: list[int], b: list[int]) -> float:
        return sum(cosine(vecs[i], vecs[j]) for i in a for j in b) / (len(a) * len(b))
    while len(clusters) > 1:
        best, pair = -1.0, (0, 1)
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                s = sim(clusters[i], clusters[j])
                if s > best:
                    best, pair = s, (i, j)
        if best < threshold:
            break
        i, j = pair
        clusters[i] = sorted(clusters[i] + clusters[j])
        del clusters[j]
    return [[uncovered[i] for i in c] for c in sorted(clusters, key=lambda c: (-len(c), c[0]))]


def top_terms(queries: list[str], k: int = 3) -> list[str]:
    stop = {"the", "a", "an", "is", "are", "do", "does", "can", "i", "how", "what", "when",
            "where", "to", "for", "of", "in", "on", "and", "my", "me", "it", "at", "there"}
    c = Counter(w for q in queries for w in re.findall(r"[a-z]{3,}", q.lower()) if w not in stop)
    return [w for w, _ in c.most_common(k)]


def run(embedder: Embedder, golden: list[dict[str, Any]], live: list[dict[str, Any]],
        cfg: dict[str, Any], golden_file_hash: str, live_hash: str) -> dict[str, Any]:
    tau, min_share = float(cfg["similarity_threshold"]), float(cfg["min_share"])
    rows = best_matches(embedder, golden, live)
    tf = tfidf_best(golden, live)
    covered = [r for r in rows if r["best_similarity"] >= tau]
    s = share(rows, tau)
    assert s is not None
    uncovered = sorted((r for r in rows if r["best_similarity"] < tau),
                       key=lambda r: r["best_similarity"])
    groups = cluster_uncovered(embedder, uncovered, float(cfg.get("cluster_similarity", 0.70)))
    return {"schema": 1, "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "golden_hash": golden_file_hash, "live_hash": live_hash, "embed_model": embedder.model,
            "similarity_threshold": tau, "min_share": min_share, "n_live": len(rows),
            "covered": len(covered), "share": s, "share_in_domain": share(rows, tau, "in"),
            "share_out_of_domain": share(rows, tau, "out"),
            "verdict": "OK" if s >= min_share else "GAP",       # equal passes (09 section 3.3)
            "sensitivity": {f"{t:+.2f}": share(rows, tau + t) for t in (-0.05, 0.05)},
            "tfidf_cross_check": {"share": round(sum(1 for x in tf if x >= tau) / len(tf), 4)},
            "uncovered": [{k: r[k] for k in ("id", "query", "best_golden_id", "best_similarity",
                                              "domain")} for r in uncovered],
            "topics": [{"name": " / ".join(top_terms([m["query"] for m in g])) or "misc",
                        "queries": [m["id"] for m in g], "single": len(g) == 1,
                        "in_corpus": None, "document": None} for g in groups]}


def render(rep: dict[str, Any]) -> str:
    f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    out = [f"COVERAGE  model={rep['embed_model']}  tau={rep['similarity_threshold']}  "
           f"min_share={rep['min_share']}",
           f"live queries {rep['n_live']}  covered {rep['covered']}  share {f(rep['share'])}  "
           f"(in-domain {f(rep['share_in_domain'])}, out-of-domain {f(rep['share_out_of_domain'])})",
           f"sensitivity {rep['sensitivity']}  tf-idf cross-check share {f(rep['tfidf_cross_check']['share'])}",
           "COVERAGE OK" if rep["verdict"] == "OK" else "COVERAGE GAP", "",
           "UNCOVERED (lowest similarity first):"]
    for u in rep["uncovered"]:
        out.append(f"  {u['id']:<6} {u['best_similarity']:.3f}  best={u['best_golden_id']:<6} {u['query']}")
    if rep["topics"]:
        out += ["", "TOPICS:"]
        out += [f"  {t['name']:<30} {len(t['queries'])} quer{'y' if len(t['queries']) == 1 else 'ies'}"
                f"{'  (single - check by hand)' if t['single'] else ''}" for t in rep["topics"]]
    return "\n".join(out)


# ----------------------------------------------------------------------- calibration of tau
def calibrate(pairs: list[dict[str, Any]], conservative: bool = False
              ) -> tuple[float, list[dict[str, Any]]]:
    """Choose tau from hand-labelled pairs. Default: maximise F1 of 'covered'. Conservative:
    the lowest tau with NO false 'covered'. Returns (tau, a table of candidates)."""
    cands = sorted({round(p["similarity"], 4) for p in pairs})
    table = []
    for t in cands:
        tp = sum(1 for p in pairs if p["similarity"] >= t and p["human"] == "covered")
        fp = sum(1 for p in pairs if p["similarity"] >= t and p["human"] != "covered")
        fn = sum(1 for p in pairs if p["similarity"] < t and p["human"] == "covered")
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        table.append({"tau": t, "precision": round(prec, 3), "recall": round(rec, 3),
                      "f1": round(f1, 3), "false_covered": fp})
    if not table:
        raise CoverageError("no labelled pairs")
    if conservative:
        ok = [r for r in table if r["false_covered"] == 0]
        chosen = min(ok, key=lambda r: r["tau"]) if ok else max(table, key=lambda r: r["tau"])
    else:
        chosen = max(table, key=lambda r: (r["f1"], -r["tau"]))
    return float(chosen["tau"]), table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Query coverage check.")
    ap.add_argument("command", nargs="?", choices=["check", "calibrate", "pairs"], default="check")
    ap.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    ap.add_argument("--live", type=Path, default=Path("eval/live_queries.jsonl"))
    ap.add_argument("--config", type=Path, default=Path("ragops/config/coverage.yaml"))
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pairs", type=Path, default=Path("eval/coverage-calibration.jsonl"))
    ap.add_argument("--conservative", action="store_true")
    args = ap.parse_args(argv)
    embedder = OllamaEmbedder(args.ollama, args.model)
    try:
        golden = load_golden(args.golden)
        live = [json.loads(x) for x in args.live.read_text(encoding="utf-8").splitlines()
                if x.strip() and not x.lstrip().startswith("#")]
        if args.command == "pairs":      # produce the (live, nearest golden) pairs to label by hand
            rows = best_matches(embedder, golden, live)
            for r in rows:
                print(json.dumps({"live_id": r["id"], "golden_id": r["best_golden_id"],
                                  "similarity": r["best_similarity"], "human": ""}))
            return 0
        if args.command == "calibrate":
            labelled = [json.loads(x) for x in args.pairs.read_text(encoding="utf-8").splitlines()
                        if x.strip()]
            labelled = [p for p in labelled if p.get("human") in ("covered", "not_covered")]
            tau, table = calibrate(labelled, args.conservative)
            for r in table:
                print(r)
            print(f"chosen tau = {tau}  (n={len(labelled)} labelled pairs)")
            return 0
        problems = validate_live(live, {" ".join(g["question"].lower().split()) for g in golden})
        if problems:
            print("live query set invalid:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        for w in split_warnings(live):
            print(f"warning: {w}", file=sys.stderr)
        cfg = load_config(args.config, args.model)
        rep = run(embedder, golden, live, cfg, golden_hash(args.golden), golden_hash(args.live))
    except (CoverageError, OSError, ValueError) as exc:
        print(f"usage/config error: {exc}", file=sys.stderr)
        return 2
    except InfrastructureError as exc:
        print(f"embedding service unavailable: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(rep, indent=2) if args.json else render(rep))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        stamp = rep["run_at"].replace("-", "").replace(":", "")
        (args.out / f"{stamp}_coverage.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        (args.out / f"{stamp}_coverage.md").write_text("```\n" + render(rep) + "\n```\n",
                                                       encoding="utf-8")
    return 0 if rep["verdict"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
