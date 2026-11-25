"""The one command (docs/a3-ragops/06 section 8, contract 14 section 5.2).

    python -m ragops.suite.run_suite --api http://api:8000 --ollama http://ollama:11434 \
        --label baseline --batches A --config ragops/config/suite.yaml --out eval/results/

Runs the module, component and endpoint levels, writes `<UTC>_<label>.json` and `.md`, and
prints the summary table. Exit 0 = finished (quality is the gate's job), 2 = usage/config/
golden invalid, 3 = infrastructure failure (a result with status "incomplete" is written).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import component_level, endpoint_level, module_level
from .clients import Api, Embedder, HttpApi, InfrastructureError, Judge, OllamaEmbedder, OllamaJudge
from .config import ConfigError, config_hash, load_config, profile_hash, seeds
from .golden import golden_hash, ledger_pages, load_golden, select, validate
from .traces import TraceReader

SCHEMA = 1


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def git_sha() -> str:
    if os.environ.get("GIT_SHA"):
        return os.environ["GIT_SHA"]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def target_embed_model(api: Any) -> str:
    """The embedding model of the system under test, from its /readyz. The module level must embed with
    THAT model: reading EMBED_MODEL from the Job's environment measured nomic-embed-text for the
    all-minilm candidate (found on the first candidate run: identical cosines). The environment is
    only a fallback when the target does not say."""
    try:
        model = api.target_info().get("embed_model")
    except InfrastructureError:
        model = None
    return str(model or os.environ.get("EMBED_MODEL", "nomic-embed-text"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            rows.append(json.loads(line))
    return rows


def chunk_texts_from_lake(lake: Path | None, limit: int = 2000) -> list[str]:
    texts: list[str] = []
    if lake and lake.is_dir():
        for f in sorted(lake.glob("lake/docs/*/*/chunks.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    texts.append(json.loads(line).get("text", ""))
                if len(texts) >= limit:
                    return texts
    return texts


def corpus_state(ledger_path: Path | None) -> tuple[str, list[str], dict[str, int] | None]:
    if not ledger_path or not Path(ledger_path).is_file():
        return "", [], None
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    return str(ledger.get("digest", "")), [str(b) for b in ledger.get("batches", [])], \
        ledger_pages(ledger)


def build(*, api: Api, embedder: Embedder | None, judge: Judge | None, traces: TraceReader,
          cfg: dict[str, Any], golden: list[dict[str, Any]], pairs: list[dict[str, Any]],
          chunk_texts: list[str], label: str, batches: set[str], digest: str,
          levels: list[str], run_id: str, golden_file_hash: str, pairs_hash: str,
          profile: str = "full", limit: int | None = None,
          only_added: str | None = None) -> dict[str, Any]:
    """Assemble one result (contract 14 section 5.2). Pure of file I/O so tests can drive it."""
    sd = seeds(cfg)
    notes: list[str] = []
    started = utc_now()
    questions, skipped = select(golden, batches)
    if only_added:
        questions = [q for q in questions if q.get("added_in") == only_added]
    if limit:
        questions = questions[:limit]
    result: dict[str, Any] = {
        "schema": SCHEMA, "status": "incomplete", "run_id": run_id, "label": label,
        "started_at": started, "finished_at": None, "git_sha": git_sha(),
        "images": {"api": os.environ.get("API_IMAGE", ""), "ragops": os.environ.get("RAGOPS_IMAGE", "")},
        "config_hash": config_hash(cfg), "golden_hash": golden_file_hash, "pairs_hash": pairs_hash,
        "corpus_digest": digest, "batches": sorted(batches), "seed": cfg["seed"], "seeds": sd,
        "profile": profile, "profile_hash": profile_hash(cfg, profile),
        "target": api.target_info(), "levels": {}, "per_question": [], "skipped": skipped,
        "notes": ""}
    per_q: dict[str, dict[str, Any]] = {}
    if "module" in levels:
        if embedder is None:
            raise InfrastructureError("module level needs an embedding service (--ollama)")
        result["levels"]["module"] = module_level.run(embedder, pairs, chunk_texts, cfg,
                                                      sd["sample"], notes)
    if "component" in levels:
        block, rows = component_level.run(api, questions, cfg, sd["typo"])
        result["levels"]["component"] = block
        for qid, r in rows.items():
            per_q.setdefault(qid, {}).update(r)
    if "endpoint" in levels:
        block, rows = endpoint_level.run(api, judge, traces, questions, cfg, run_id, label,
                                         sd["judge"], notes)
        result["levels"]["endpoint"] = block
        for qid, r in rows.items():
            per_q.setdefault(qid, {}).update(r)
    result["per_question"] = [{"id": qid, **row} for qid, row in sorted(per_q.items())]
    result["status"] = "complete"
    result["finished_at"] = utc_now()
    result["notes"] = "; ".join(dict.fromkeys(notes))
    return result


def fmt(x: Any, nd: int = 3) -> str:
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def render(result: dict[str, Any]) -> str:
    t, lv = result["target"], result["levels"]
    out = [f"RAGOps suite  label={result['label']}  {result['started_at']}  "
           f"git={result['git_sha']}  embed={t.get('embed_model')}  collection={t.get('collection')}  "
           f"corpus={','.join(result['batches']) or '?'} (ledger {result['corpus_digest'][:6]}...)",
           f"{'LEVEL':<10} {'METRIC':<32} {'VALUE':<18} N"]
    m = lv.get("module")
    if m:
        out += [f"{'module':<10} {'paraphrase mean cosine':<32} {fmt(m['paraphrase_mean_cos']):<18} {m['n_paraphrase']}",
                f"{'module':<10} {'unrelated mean cosine':<32} {fmt(m['unrelated_mean_cos']):<18} {m['n_unrelated']}",
                f"{'module':<10} {'gap':<32} {fmt(m['gap'])}",
                f"{'module':<10} {'embed ms/chunk (mean / p95)':<32} {fmt(m['embed_ms_mean'], 1)} / {fmt(m['embed_ms_p95'], 1)}",
                f"{'module':<10} {'determinism max |d|':<32} {m['determinism_max_abs_diff']:.1e}"]
    c = lv.get("component")
    if c:
        cl, no, d = c["clean"], c["noisy"], c["delta_noisy"]
        out += [f"{'component':<10} {'recall@3 / recall@5':<32} {fmt(cl['recall@3'])} / {fmt(cl['recall@5']):<9} {c['n']}",
                f"{'component':<10} {'MRR / nDCG@5':<32} {fmt(cl['mrr'])} / {fmt(cl['ndcg@5']):<9} {c['n']}",
                f"{'component':<10} {'noisy recall@5 (delta)':<32} {fmt(no['recall@5'])} ({fmt(d['recall@5'])}) {c['n']}"]
    e = lv.get("endpoint")
    if e:
        out += [f"{'endpoint':<10} {'faithfulness (judge / proxy)':<32} {fmt(e['faithfulness'])} / {fmt(e['faithfulness_proxy']):<9} {e['n_answerable']}",
                f"{'endpoint':<10} {'abstention correctness':<32} {fmt(e['abstention_correctness']):<18} {e['n_unanswerable']}",
                f"{'endpoint':<10} {'false abstention rate':<32} {fmt(e['false_abstention_rate']):<18} {e['n_answerable']}",
                f"{'endpoint':<10} {'citation validity':<32} {fmt(e['citation_validity']):<18} {e['citations_checked']}",
                f"{'endpoint':<10} {'latency p50 / p95 (s)':<32} {fmt(e['latency_p50_s'], 1)} / {fmt(e['latency_p95_s'], 1):<9} {e['n']}"]
    if result.get("skipped"):
        out.append(f"skipped {len(result['skipped'])} question(s): "
                   + ", ".join(f"{s['id']} ({s['reason']})" for s in result["skipped"][:6]))
    if result.get("notes"):
        out.append(f"notes: {result['notes']}")
    return "\n".join(out)


def write_result(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = result["started_at"].replace("-", "").replace(":", "")
    path = out_dir / f"{stamp}_{result['label']}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    path.with_suffix(".md").write_text("```\n" + render(result) + "\n```\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the three-level offline test suite.")
    ap.add_argument("--api", help="RAHBAR API base URL (default from the config)")
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--label", required=True)
    ap.add_argument("--batches", help="comma list, e.g. A or A,B (default: from the ledger)")
    ap.add_argument("--config", type=Path, default=Path("ragops/config/suite.yaml"))
    ap.add_argument("--out", type=Path, default=Path("eval/results"))
    ap.add_argument("--levels", help="comma list of module,component,endpoint")
    ap.add_argument("--ledger", type=Path, help="ledger.json (corpus digest, batches, pages)")
    ap.add_argument("--lake", type=Path, help="data-lake root for chunk snapshots (module timing)")
    ap.add_argument("--traces", type=Path, help="traces volume (to read prompt contexts)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only-added", help="run only questions with this added_in tag (E4)")
    ap.add_argument("--profile", default="full")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        golden = load_golden(Path(cfg["paths"]["golden"]))
        pairs = load_jsonl(Path(cfg["paths"]["pairs"]))
        digest, ledger_batches, docs = corpus_state(args.ledger)
        batches = {b.strip().upper() for b in (args.batches or ",".join(ledger_batches) or "A").split(",")}
        problems, _ = validate(golden, docs, batches)
        if problems:
            print("golden set invalid:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        levels = [lv.strip() for lv in (args.levels or ",".join(cfg["levels"])).split(",")]
        if args.profile != "full":
            print("note: reduced profile; the gate will not compare it with a full baseline",
                  file=sys.stderr)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"usage/config error: {exc}", file=sys.stderr)
        return 2
    api = HttpApi(args.api or cfg["api"]["url"], timeout=float(cfg["e2e"]["timeout_s"]))
    embedder = OllamaEmbedder(args.ollama, target_embed_model(api))
    judge = None if args.no_judge else OllamaJudge(args.ollama, cfg["judge"]["model"],
                                                   float(cfg["judge"]["temperature"]))
    traces = TraceReader(args.traces)
    chunks = chunk_texts_from_lake(args.lake)
    rc = 0
    for i in range(max(1, args.repeat)):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        run_id = f"suite-{stamp}-{i + 1}"
        try:
            result = build(api=api, embedder=embedder, judge=judge, traces=traces, cfg=cfg,
                           golden=golden, pairs=pairs, chunk_texts=chunks, label=args.label,
                           batches=batches, digest=digest, levels=levels, run_id=run_id,
                           golden_file_hash=golden_hash(Path(cfg["paths"]["golden"])),
                           pairs_hash=golden_hash(Path(cfg["paths"]["pairs"])),
                           profile=args.profile, limit=args.limit, only_added=args.only_added)
        except InfrastructureError as exc:
            print(f"INFRASTRUCTURE FAILURE: {exc}", file=sys.stderr)
            stub = {"schema": SCHEMA, "status": "incomplete", "run_id": run_id,
                    "label": args.label, "started_at": utc_now(), "error": str(exc),
                    "git_sha": git_sha(), "levels": {}, "target": {}, "batches": sorted(batches),
                    "corpus_digest": digest, "per_question": [], "skipped": [], "notes": str(exc)}
            write_result(stub, args.out)
            return 3
        path = write_result(result, args.out)
        print(render(result))
        print(f"RESULT={path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
