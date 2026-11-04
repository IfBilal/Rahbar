"""Liveness and readiness (section 4.3). They answer different questions.

/healthz  is the process alive?           Touches nothing. Liveness and startup probes.
/readyz   can this pod take traffic now?  Chroma reachable, the active collection exists
          and is non-empty, its embedding model matches EMBED_MODEL (4.4), Redis reachable.
          503 names what failed. Readiness removes the pod from the Service; it never
          restarts it, so a slow dependency cannot cause a restart storm.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from ..retrieval.chroma import pin_problem

router = APIRouter()
log = logging.getLogger("rahbar.health")
_last_failures: list[str] = []


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


def readiness_checks(state: object) -> tuple[dict[str, str], list[str]]:
    settings = state.settings  # type: ignore[attr-defined]
    checks: dict[str, str] = {}
    failed: list[str] = []
    retriever = state.retriever  # type: ignore[attr-defined]
    if hasattr(retriever, "index_info"):
        try:
            info = retriever.index_info()
            checks["chroma"] = "ok"
            if info.count > 0:
                checks["collection"] = f"ok: {info.collection} ({info.count} chunks)"
            else:
                checks["collection"] = f"empty: {info.collection} has no chunks"
                failed.append("collection")
            problem = pin_problem(info, settings)
            checks["embedding_pin"] = problem or f"ok: {info.embed_model} ({info.dimension})"
            if problem:
                failed.append("embedding_pin")
        except Exception as exc:
            checks["chroma"] = f"unreachable or no collection: {type(exc).__name__}: {exc}"[:300]
            failed.append("chroma")
    cache = state.cache  # type: ignore[attr-defined]
    if settings.redis_url:
        try:
            cache.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"unreachable: {type(exc).__name__}"
            failed.append("redis")
    return checks, failed


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    global _last_failures
    checks, failed = readiness_checks(request.app.state)
    if failed:
        response.status_code = 503
    if failed != _last_failures:       # log transitions, not every probe
        level = logging.WARNING if failed else logging.INFO
        log.log(level, "readiness changed", extra={"ready": not failed, "failed": failed,
                                                   "checks": checks})
        _last_failures = failed
    return {"status": "not ready" if failed else "ready", "failed": failed, "checks": checks}
