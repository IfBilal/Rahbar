"""The suite configuration: loading, hashing, derived seeds (docs/a3-ragops/06 section 2).

Everything that influences a number is in the config file; its hash goes into every result so
two results can be compared only when they were produced the same way.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

LEVELS = ("module", "component", "endpoint")


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read suite config {path}: {exc}") from exc
    for key in ("seed", "api", "top_k", "levels", "typo_noise", "module", "judge", "e2e", "paths"):
        if key not in cfg:
            raise ConfigError(f"suite config is missing {key!r}")
    bad = [lv for lv in cfg["levels"] if lv not in LEVELS]
    if bad:
        raise ConfigError(f"unknown level(s) {bad}; choose from {list(LEVELS)}")
    return cfg


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def config_hash(cfg: dict[str, Any]) -> str:
    """Hash of every knob that changes a number. `api.url` is excluded: the same suite run
    against two addresses of the same system is still the same measurement."""
    knobs = {k: v for k, v in cfg.items() if k not in ("api", "paths")}
    return _digest(knobs)


def profile_hash(cfg: dict[str, Any], profile: str = "full") -> str:
    """The gate compares this: a reduced demo profile never gates against a full baseline."""
    return _digest({"profile": profile, "levels": sorted(cfg["levels"]),
                    "top_k": cfg["top_k"], "e2e": cfg["e2e"], "module": cfg["module"]})


def seeds(cfg: dict[str, Any]) -> dict[str, int]:
    base = int(cfg["seed"])
    return {"typo": base + int(cfg["typo_noise"].get("seed_offset", 1)),
            "judge": int(cfg["judge"].get("seed", 7)), "e2e": int(cfg["e2e"].get("seed", base)),
            "sample": base + 2}
