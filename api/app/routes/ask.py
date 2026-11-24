"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays.

Assignment 03 additions (additive): every request gets a trace id (response header
`X-Trace-Id` and `trace_id` field) and one trace record; `X-Eval-*` request headers, honoured
only when EVAL_HEADERS_ENABLED, let the offline suite bypass the cache and fix the seed.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request, Response

from .. import trace
from ..evalctl import eval_var, parse
from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_question
from ..services.prompt import prompt_var, rail_var

router = APIRouter(prefix="/api")
log = logging.getLogger("rahbar.api")


def _status(response: AskResponse, ctx: dict) -> str:  # type: ignore[type-arg]
    if ctx.get("fallback"):
        return "fallback"
    return "ok" if response.answered_from_context else "abstained"


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, http_response: Response) -> AskResponse:
    state = request.app.state
    settings = state.settings
    controls = parse(request, settings)
    trace_id = trace.new_trace_id()
    ctx: dict = {}  # type: ignore[type-arg]
    t_ctx = trace.ctx_var.set(ctx)
    t_eval = eval_var.set(controls if controls.active else None)
    t_prompt = prompt_var.set([])
    t_rails = rail_var.set([])
    started = time.perf_counter()
    try:
        cache = None if controls.bypass_cache else state.cache
        response = answer_question(body.question, state.retriever, state.provider, settings,
                                   cache=cache)
        ctx["prompt"] = prompt_var.get() or None
        ctx["rails"] = rail_var.get() or []
    finally:
        trace.ctx_var.reset(t_ctx)
        eval_var.reset(t_eval)
        prompt_var.reset(t_prompt)
        rail_var.reset(t_rails)
    response.trace_id, response.release_id = trace_id, settings.release_id
    http_response.headers["X-Trace-Id"] = trace_id
    http_response.headers["X-Release-Id"] = settings.release_id
    if settings.trace_enabled:
        try:
            trace.write(settings, trace.build(
                settings, trace_id=trace_id, route="/api/ask", question=body.question,
                status=_status(response, ctx), app_version=_app_version(), eval_controls=controls, retriever=state.retriever,
                ctx=ctx, total_ms=(time.perf_counter() - started) * 1000, response=response))
        except Exception as exc:      # tracing must never fail an answer
            log.warning("trace failed", extra={"error": f"{type(exc).__name__}: {exc}"[:200]})
    if state.cache is not None:
        try:    # 3.2 step 8: store the turn; a Redis problem must never fail the answer
            state.cache.record_turn({
                "request_id": response.request_id, "ts": int(time.time()),
                "question": body.question, "answer": response.answer,
                "answered_from_context": response.answered_from_context,
                "citations": [c.model_dump() for c in response.citations],
                "chunk_ids": [p.chunk_id for p in response.retrieved],
                "cached": response.cached, "provider": response.provider,
            })
        except Exception as exc:
            log.warning("turn not stored", extra={"error": f"{type(exc).__name__}: {exc}"})
    return response


def _app_version() -> str:
    import os
    return os.environ.get("APP_VERSION", "dev")
