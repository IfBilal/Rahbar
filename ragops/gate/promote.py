"""Promote a suite result to be the new baseline (docs/a3-ragops/07 section 9).

    python -m ragops.gate.promote --result RESULT.json --reason "why" \
        [--baselines-dir /results/baselines] [--name live]

An explicit, reviewed step: never run from CI, never automatic. Refuses an incomplete result and
an empty reason, writes `<name>.json` and appends to `promotions.jsonl` so the history of who
promoted what, and why, is kept next to the baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def promote(result: Path, reason: str, baselines_dir: Path, name: str = "live") -> Path:
    body = json.loads(Path(result).read_text(encoding="utf-8"))
    if body.get("status") != "complete":
        raise ValueError(f"{result} is not a complete result (status {body.get('status')!r})")
    if not reason.strip():
        raise ValueError("a reason is required to promote a baseline")
    baselines_dir.mkdir(parents=True, exist_ok=True)
    target = baselines_dir / f"{name}.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    target.write_text(json.dumps(body, indent=2), encoding="utf-8")
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "name": name,
             "from_file": Path(result).name, "run_id": body.get("run_id"),
             "label": body.get("label"), "reason": reason.strip(),
             "replaced_run_id": (previous or {}).get("run_id")}
    with (baselines_dir / "promotions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Promote a result to be the baseline.")
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--baselines-dir", type=Path, default=Path("/results/baselines"))
    ap.add_argument("--name", default="live")
    args = ap.parse_args(argv)
    try:
        path = promote(args.result, args.reason, args.baselines_dir, args.name)
    except (OSError, ValueError) as exc:
        print(f"PROMOTE REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"promoted {args.result.name} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
