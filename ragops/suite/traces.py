"""Read the trace of a request from the traces volume (docs/a3-ragops/08, 14 section 6).

The suite uses it to learn the exact context the model was given, which is the text the
judge and the proxy compare the answer against. If the volume is not mounted the suite still
runs; those rows simply have no judged faithfulness and the result says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TraceReader:
    def __init__(self, directory: Path | None) -> None:
        self.dir = Path(directory) if directory else None
        self._index: dict[str, dict[str, Any]] | None = None

    @property
    def available(self) -> bool:
        return bool(self.dir and self.dir.is_dir())

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._index is None:
            self._index = {}
            if self.available:
                assert self.dir is not None
                for f in sorted(self.dir.glob("*.jsonl*")):
                    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        if rec.get("type") == "trace" and rec.get("trace_id"):
                            self._index[rec["trace_id"]] = rec
        return self._index

    def refresh(self) -> None:
        self._index = None

    def get(self, trace_id: str | None) -> dict[str, Any] | None:
        if not trace_id:
            return None
        rec = self._load().get(trace_id)
        if rec is None:  # the line may have been written after the index was built
            self.refresh()
            rec = self._load().get(trace_id)
        return rec

    def context(self, trace_id: str | None) -> str | None:
        """The passages the model saw, or None if the trace or the prompt file is missing."""
        rec = self.get(trace_id)
        sha = ((rec or {}).get("prompt") or {}).get("sha256")
        if not sha or not self.dir:
            return None
        path = self.dir / "prompts" / f"{sha}.json"
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return "\n\n".join(str(m.get("content", "")) for m in body.get("messages", [])
                           if m.get("role") != "system")
