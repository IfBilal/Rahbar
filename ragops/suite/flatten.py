"""Flatten a result file into `level.metric -> value` (shared by stochasticity and diff)."""

from __future__ import annotations

from typing import Any


def flatten(result: dict[str, Any]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for level, block in (result.get("levels") or {}).items():
        if level == "component":
            for section in ("clean", "noisy", "delta_noisy"):
                for k, v in (block.get(section) or {}).items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out[f"component.{section}.{k}"] = float(v)
        else:
            for k, v in block.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[f"{level}.{k}"] = float(v)
    return out
