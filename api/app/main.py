"""The API process. It reads the index; it never builds it (section 4.2).

Run locally with stubs:   make dev     (then open http://localhost:8000)
Run in the container:     uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .logjson import configure_logging, request_id_var
from .providers.llm import get_provider
from .retrieval import get_retriever
from .retrieval.chroma import pin_problem
from .routes import ask, health, metrics
from .services.cache import SemanticCache

log = logging.getLogger("rahbar.api")
APP_VERSION = os.environ.get("APP_VERSION", "dev")   # baked in at build time (Dockerfile ARG)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.retriever = get_retriever(settings)
    app.state.provider = get_provider(settings)
    app.state.cache = (SemanticCache.from_url(settings.redis_url, settings.cache_threshold,
                                              settings.cache_max_entries,
                                              settings.cache_ttl_seconds)
                       if settings.redis_url else None)
    # The embedding pin (4.4): compare the index's recorded model with ours now, and log the
    # conflict loudly. /readyz repeats the check on every probe and stays 503 while they
    # disagree, so a mismatched pod never joins the Service. This process only READS the
    # index; the indexer Job writes it (4.2).
    # In a thread: startup must never wait on a dependency, or a slow Chroma turns into a
    # startup-probe restart loop. Readiness enforces the pin on every probe anyway.
    threading.Thread(target=_check_pin_at_startup, args=(app,), daemon=True).start()
    log.info(
        "api started",
        extra={"retriever": settings.retriever, "llm_provider": settings.llm_provider,
               "embed_model": settings.embed_model, "top_k": settings.top_k},
    )
    yield


def _check_pin_at_startup(app: FastAPI) -> None:
    retriever = app.state.retriever
    if not hasattr(retriever, "index_info"):
        return
    try:
        problem = pin_problem(retriever.index_info(), app.state.settings)
    except Exception as exc:   # Chroma not up yet, or no index yet: readiness will say so
        log.warning("index not readable at startup",
                    extra={"error": f"{type(exc).__name__}: {exc}"[:300]})
        return
    if problem:
        log.error("embedding model mismatch: refusing readiness", extra={"conflict": problem})


app = FastAPI(title="RAHBAR API", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        response.headers["X-Rahbar-Version"] = APP_VERSION   # which image answered (4.6)
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")   # route template, not the raw URL
        elapsed = time.perf_counter() - start
        metrics.REQUESTS.labels(path=path, status=str(status)).inc()
        metrics.LATENCY.labels(path=path).observe(elapsed)
        if path not in ("/healthz", "/readyz", "/metrics"):
            log.info("request", extra={"path": path, "status": status,
                                       "ms": round(elapsed * 1000, 1)})
        request_id_var.reset(token)


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(ask.router)

# Development only: `make dev` serves the chat UI from this process, so you can try it
# without a cluster. On Kubernetes the ui Deployment serves it and this stays unset.
_ui_dir = os.environ.get("SERVE_UI_DIR")
if _ui_dir:
    app.mount("/", StaticFiles(directory=_ui_dir, html=True), name="ui")
