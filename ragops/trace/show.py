"""Show one trace and prove what the model was given (docs/a3-ragops/08, contract 14 s.6/11).

    python -m ragops.trace.show TRACE_ID --traces /traces [--lake /data] [--json]

Prints the PDF's D1 fields for the request. Checks that the stored prompt's hash matches its
content (tamper check) and, with --lake, that every chunk in the prompt can be rebuilt from the
immutable chunk snapshot in the data lake (the id carries the first 8 hex of the chunk's SHA).
Exit: 0 found and consistent - 2 usage - 4 not found - 5 prompt store corrupt - 6 a prompt chunk
cannot be rebuilt from the lake.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def find_trace(traces_dir: Path, trace_id: str) -> dict[str, Any] | None:
    for f in sorted(traces_dir.glob("*.jsonl*")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if trace_id in line:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("trace_id") == trace_id:
                    return rec
    return None


def prompt_hash(messages: list[dict[str, str]]) -> str:
    body = json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def verify_prompt(traces_dir: Path, rec: dict[str, Any]) -> tuple[int, list[str], dict[str, Any] | None]:
    prompt = rec.get("prompt")
    if not prompt:
        return 0, ["no prompt (the request did not reach the model)"], None
    path = traces_dir / "prompts" / f"{prompt['sha256']}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 5, [f"prompt file {path.name} is missing or unreadable"], None
    if prompt_hash(body.get("messages", [])) != prompt["sha256"]:
        return 5, [f"prompt file {path.name} does not match its hash: it was altered"], body
    return 0, ["prompt hash verified"], body


def snapshots(lake: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pattern in ("lake/docs/*/*/chunks.jsonl", "archive/*/*/chunks.jsonl"):
        for f in lake.glob(pattern):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    out[row["chunk_id"]] = row
    return out


def rebuild_check(rec: dict[str, Any], body: dict[str, Any] | None, lake: Path) -> tuple[int, list[str]]:
    prompt = rec.get("prompt") or {}
    ids = prompt.get("chunk_ids") or []
    if not ids or body is None:
        return 0, []
    snap = snapshots(lake)
    text = "\n".join(m.get("content", "") for m in body.get("messages", []))
    notes, bad = [], False
    for cid in ids:
        row = snap.get(cid)
        if row is None:
            notes.append(f"{cid}: not found in the lake snapshots")
            bad = True
            continue
        sha8 = cid.rsplit("-", 1)[-1]
        if not hashlib.sha256(row["text"].encode("utf-8")).hexdigest().startswith(sha8) and \
                not hashlib.sha1(row["text"].encode("utf-8")).hexdigest().startswith(sha8):
            notes.append(f"{cid}: snapshot text does not match the id's content hash")
            bad = True
            continue
        probe = row["text"][:60].replace("<", "‹")
        notes.append(f"{cid}: rebuilt from snapshot; " +
                     ("text present in the prompt" if probe in text
                      else "text differs (the injection guard may have rewritten it)"))
    return (6 if bad else 0), notes


def render(rec: dict[str, Any], notes: list[str]) -> str:
    r = rec.get("retrieval") or {}
    resp = rec.get("response") or {}
    lines = [f"TRACE {rec['trace_id']}  {rec['ts']}  route={rec['route']}  status={rec['status']}",
             f"query          : {rec['query']}",
             f"release        : {rec['release_id']}  pod={rec.get('pod')}  app={rec.get('app_version')}",
             f"embedding      : {rec['embedding'].get('model')} {rec['embedding'].get('version')}",
             f"collection     : {rec['collection'].get('name')} @ {rec['collection'].get('revision')}",
             "retrieved      :"]
    for c in r.get("candidates", []):
        lines.append(f"   {c['rank']}. {c['source']} p{c['page']}  {c['chunk_id']}  score={c['score']}"
                     + ("  [superseded]" if c.get("superseded") else ""))
    lines.append(f"guardrails     : {len(rec.get('guardrails') or [])} action(s)")
    for g in rec.get("guardrails") or []:
        lines.append(f"   {g['rail']} {g['action']} {g['target']}: {g.get('excerpt')!r}")
    p = rec.get("prompt")
    lines.append(f"prompt         : {p['sha256'][:12]}... chunks={p['chunk_ids']}" if p else "prompt         : none")
    m = rec.get("model")
    if m:
        lines.append(f"model          : {m['provider']} {m['name']} {m['params']} attempts={m.get('attempts')}")
    if resp:
        lines.append(f"response       : abstained={resp.get('abstained')} confidence={resp.get('confidence')} "
                     f"citations={[(c['source'], c.get('page')) for c in resp.get('citations', [])]}")
        lines.append(f"answer         : {resp.get('answer')}")
    lines.append(f"latency_ms     : {rec.get('latency_ms')}   cache: {rec.get('cache')}")
    lines += [f"check          : {n}" for n in notes]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Show one trace and verify its prompt.")
    ap.add_argument("trace_id")
    ap.add_argument("--traces", type=Path, required=True)
    ap.add_argument("--lake", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.traces.is_dir():
        print(f"traces directory {args.traces} not found", file=sys.stderr)
        return 2
    rec = find_trace(args.traces, args.trace_id)
    if rec is None:
        print(f"trace {args.trace_id} not found", file=sys.stderr)
        return 4
    code, notes, body = verify_prompt(args.traces, rec)
    if code == 0 and args.lake:
        code, more = rebuild_check(rec, body, args.lake)
        notes += more
    print(json.dumps(rec, indent=2) if args.json else render(rec, notes))
    return code


if __name__ == "__main__":
    sys.exit(main())
