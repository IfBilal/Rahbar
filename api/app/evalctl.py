"""Evaluation controls (Assignment 03, docs/a3-ragops/14 section 9).

The offline suite must be able to run the live system reproducibly: bypass the semantic cache,
fix the seed, pin the temperature, and label the run in the trace. Honoured ONLY when
EVAL_HEADERS_ENABLED=true, so ordinary traffic can never switch the cache off.
"""

from __future__ import annotations

import hmac
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request

from .config import Settings


@dataclass(frozen=True)
class EvalControls:
    bypass_cache: bool = False
    seed: int | None = None
    temperature: float | None = None
    run: str | None = None
    label: str | None = None

    @property
    def active(self) -> bool:
        return any((self.bypass_cache, self.seed is not None, self.temperature is not None,
                    self.run, self.label))


eval_var: ContextVar[EvalControls | None] = ContextVar("eval_controls", default=None)
TEMPERATURE_MAX = 0.3


def authorised(request: Request, settings: Settings) -> bool:
    """True when no token is configured, or the request carries the matching X-Eval-Token."""
    if not settings.eval_token:
        return True
    # bytes, not str: compare_digest raises TypeError for non-ASCII str, and a header can be any latin-1 text,
    # so a public client could otherwise turn a wrong token into a 500
    return hmac.compare_digest(request.headers.get("X-Eval-Token", "").encode("utf-8", "replace"),
                               settings.eval_token.encode("utf-8"))


def parse(request: Request, settings: Settings) -> EvalControls:
    if not settings.eval_headers_enabled or not authorised(request, settings):
        return EvalControls()
    h = request.headers

    def num(name: str, cast: type) -> float | int | None:
        try:
            return cast(h[name]) if name in h else None   # type: ignore[no-any-return]
        except ValueError:
            return None
    temp = num("X-Eval-Temperature", float)
    return EvalControls(
        bypass_cache=h.get("X-Eval-Bypass-Cache", "").lower() == "true",
        seed=num("X-Eval-Seed", int),            # type: ignore[arg-type]
        temperature=None if temp is None else min(max(float(temp), 0.0), TEMPERATURE_MAX),
        run=_short(h.get("X-Eval-Run")), label=_short(h.get("X-Eval-Label")))


def _short(value: str | None) -> str | None:
    """Run ids and labels only end up in traces: cap them so a header cannot bloat a record."""
    return value[:64] if value else value
