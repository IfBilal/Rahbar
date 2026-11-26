"""Summarise traces over a window (docs/a3-ragops/08, D3).

    python -m ragops.trace.summary --traces /traces [--since 2026-11-26T00:00:00Z] [--route /api/ask]
                                   [--release R1-nomic]

Counts by status and route, abstention and cache-hit rates, the distribution of the top-1 retrieval
similarity, latency p50/p95 (total and per stage), the release and collection mix, and every
guardrail action (injection attempts flagged). Exit 0 ok, 2 usage, 3 no traces.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ragops.suite.metrics import percentile


def load(traces_dir: Path, since: str | None, route: str | None,
         release: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for f in sorted(traces_dir.glob("*.jsonl*")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "trace":
                continue
            if since and rec.get("ts", "") < since:
                continue
            if until and rec.get("ts", "") >= until:
                continue
            if route and rec.get("route") != route:
                continue
            if release and rec.get("release_id") != release:
                continue
            rows.append(rec)
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    status = Counter(r["status"] for r in rows)
    stages: dict[str, list[float]] = {}
    for r in rows:
        for k, v in (r.get("latency_ms") or {}).items():
            if isinstance(v, (int, float)):
                stages.setdefault(k, []).append(float(v))

    def p(vals: list[float], q: float) -> float | None:
        x = percentile(vals, q)
        return None if x is None else round(x, 1)
    top1 = [float(c[0]["score"]) for r in rows
            for c in [((r.get("retrieval") or {}).get("candidates") or [])] if c]

    def q4(vals: list[float], q: float) -> float | None:
        x = percentile(vals, q)
        return None if x is None else round(x, 4)          # similarities need 4 decimals, latencies 1

    def dist(vals: list[float]) -> dict[str, float | int | None]:
        return {"n": len(vals), "min": q4(vals, 0), "p10": q4(vals, 10), "p50": q4(vals, 50),
                "p90": q4(vals, 90), "max": q4(vals, 100)} if vals else {"n": 0}
    rails = Counter(f"{g['rail']}:{g['action']}" for r in rows for g in (r.get("guardrails") or []))
    return {"requests": n, "by_route": dict(Counter(r["route"] for r in rows)),
            "by_status": dict(status),
            "abstention_rate": round(status.get("abstained", 0) / n, 4) if n else None,
            "fallback_rate": round(status.get("fallback", 0) / n, 4) if n else None,
            "cache_hit_rate": round(sum(1 for r in rows if (r.get("cache") or {}).get("hit")) / n, 4)
            if n else None,
            "top1_similarity": dist(top1),
            "latency_ms": {k: {"p50": p(v, 50), "p95": p(v, 95)} for k, v in sorted(stages.items())},
            "releases": dict(Counter(r.get("release_id") for r in rows)),
            "collections": dict(Counter((r.get("collection") or {}).get("name") for r in rows)),
            "guardrail_actions": dict(rails),
            "requests_with_guardrail_action": sum(1 for r in rows if r.get("guardrails")),
            "eval_runs": dict(Counter((r.get("eval") or {}).get("run_id") for r in rows
                                      if r.get("eval")))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarise traces.")
    ap.add_argument("--traces", type=Path, required=True)
    ap.add_argument("--since")
    ap.add_argument("--until", help="exclusive upper bound on ts (ISO 8601)")
    ap.add_argument("--route")
    ap.add_argument("--release", help="only traces of this release id, e.g. R1-nomic")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.traces.is_dir():
        print(f"traces directory {args.traces} not found", file=sys.stderr)
        return 2
    rows = load(args.traces, args.since, args.route, args.release, args.until)
    if not rows:
        print("no traces in the window", file=sys.stderr)
        return 3
    out = summarise(rows)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{out['requests']} requests  routes={out['by_route']}  status={out['by_status']}")
    print(f"abstention {out['abstention_rate']}  fallback {out['fallback_rate']}  "
          f"cache hit {out['cache_hit_rate']}")
    t1 = out["top1_similarity"]
    if t1.get("n"):
        print(f"top-1 retrieval similarity (n={t1['n']}): min {t1['min']}  p10 {t1['p10']}  "
              f"p50 {t1['p50']}  p90 {t1['p90']}  max {t1['max']}")
    print(f"releases={out['releases']}  collections={out['collections']}")
    print("latency ms (p50 / p95):")
    for k, v in out["latency_ms"].items():
        print(f"  {k:<10} {v['p50']} / {v['p95']}")
    print(f"guardrail actions: {out['guardrail_actions']} "
          f"({out['requests_with_guardrail_action']} request(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
