"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request

from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_question

router = APIRouter(prefix="/api")
log = logging.getLogger("rahbar.api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    state = request.app.state
    response = answer_question(body.question, state.retriever, state.provider, state.settings,
                               cache=state.cache)
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
