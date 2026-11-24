"""POST /api/retrieve: retrieval only, for the component-level tests (Assignment 03,
docs/a3-ragops/06 section 5, contract 14 section 9).

No generation and no cache, so it is cheap and reproducible. It returns the ranked chunks the
live retriever produced (after filters and exact-term assists) with document and page, which is
what recall, MRR and nDCG are computed from. Enabled only when EVAL_ENDPOINTS_ENABLED=true;
otherwise it is a 404, as if it did not exist.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import trace

router = APIRouter(prefix="/api")


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


@router.post("/retrieve")
def retrieve(body: RetrieveRequest, request: Request, http_response: Response) -> dict:  # type: ignore[type-arg]
    state = request.app.state
    settings = state.settings
    if not settings.eval_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    started = time.perf_counter()
    try:
        passages = state.retriever.retrieve(body.question, k=body.k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"retrieval failed: {type(exc).__name__}")
    ms = round((time.perf_counter() - started) * 1000, 1)
    trace_id = trace.new_trace_id()
    http_response.headers["X-Trace-Id"] = trace_id
    http_response.headers["X-Release-Id"] = settings.release_id
    generation = getattr(state.retriever, "generation", None)
    revision = generation if isinstance(generation, str) else None
    cands = trace.candidates(passages)
    if settings.trace_enabled:
        record = trace.build(settings, trace_id=trace_id, route="/api/retrieve",
                             question=body.question, status="ok", app_version="",
                             eval_controls=None, retriever=state.retriever,
                             ctx={"passages": passages, "retrieve_ms": ms}, total_ms=ms)
        trace.write(settings, record)
    return {"trace_id": trace_id,
            "collection": {"name": getattr(getattr(state.retriever, "settings", None),
                                           "collection", settings.collection),
                           "revision": revision},
            "embedding": {"model": settings.embed_model, "version": settings.embed_version},
            "filters": {"superseded_filter": settings.superseded_filter},
            "candidates": cands, "latency_ms": {"retrieve": ms}}
