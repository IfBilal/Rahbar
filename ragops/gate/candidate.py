"""Validate a candidate spec: it may differ from the baseline in exactly ONE dimension
(docs/a3-ragops/07 section 2.2, decision D-09).

    python -m ragops.gate.candidate ragops/config/candidates/cand-mxbai.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

BASELINE = Path(__file__).resolve().parents[1] / "config" / "candidates" / "baseline.yaml"
DIMENSIONS = {"embed_model": "embedding_model", "chunk_size": "chunk", "chunk_overlap": "chunk",
              "top_k": "top_k", "relevance_floor": "relevance_floor", "prompt_version": "prompt_version", "reranker": "reranker"}
IDENTITY = {"name", "release_id", "change", "collection", "embed_version", "cache_threshold",
            "expected", "calibrates_floor_for"}


def changed_dimensions(base: dict[str, Any], cand: dict[str, Any]) -> set[str]:
    out = set()
    for key, dim in DIMENSIONS.items():
        if base.get(key) != cand.get(key) and not (key not in cand and key not in base):
            out.add(dim)
    return out


def validate(cand: dict[str, Any], base: dict[str, Any] | None = None) -> list[str]:
    base = base if base is not None else yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    problems = []
    for key in ("name", "release_id", "change", "collection", "expected"):
        if not cand.get(key):
            problems.append(f"missing {key}")
    if cand.get("collection") == base.get("collection"):
        problems.append("a candidate needs its own collection, not the live one")
    if cand.get("expected") not in ("pass", "fail"):
        problems.append("expected must be 'pass' or 'fail', written before the run")
    dims = changed_dimensions(base, cand)
    if "relevance_floor" in dims:
        # The floor is a per-model score-scale calibration: it may only move WITH the embedding model,
        # and the spec must say so explicitly. It is part of that one change, not a second change.
        if "embedding_model" not in dims:
            problems.append("relevance_floor changed without an embed_model change")
        elif cand.get("calibrates_floor_for") != "embed_model":
            problems.append("relevance_floor moves with embed_model only if `calibrates_floor_for: embed_model` is set")
        dims = dims - {"relevance_floor"}
    if len(dims) != 1:
        problems.append(f"exactly one dimension may change, found {sorted(dims) or 'none'}")
    elif cand.get("change") not in dims:
        problems.append(f"`change: {cand.get('change')}` does not match what differs ({sorted(dims)})")
    return problems


def main(argv: list[str] | None = None) -> int:
    paths = (argv if argv is not None else sys.argv[1:]) or []
    if not paths:
        print("usage: python -m ragops.gate.candidate SPEC.yaml [...]", file=sys.stderr)
        return 2
    rc = 0
    for p in paths:
        problems = validate(yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {})
        print(f"{p}: " + ("OK" if not problems else "; ".join(problems)))
        rc = rc or (1 if problems else 0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
