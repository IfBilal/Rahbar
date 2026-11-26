"""Per-request traces (Assignment 03 Part D, docs/a3-ragops/08, contract 14 section 6).

One JSON line per request in `<TRACE_DIR>/<POD_NAME>.jsonl` (and the same line on stdout, so
`kubectl logs` shows it), plus a content-addressed prompt store `<TRACE_DIR>/prompts/<sha>.json`
holding the exact messages sent to the model. Writing a trace can never fail a request: every
error is swallowed and counted in the log. Never stored: the model's `reasoning`, credentials.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .evalctl import EvalControls
from .services.prompt import REMINDER, SYSTEM

log = logging.getLogger("rahbar.trace")
_lock = threading.Lock()

# Filled by answer_question for the request that is running, read by the route afterwards.
ctx_var: ContextVar[dict[str, Any] | None] = ContextVar("trace_ctx", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def note(**values: Any) -> None:
    """Record facts about the current request, if a trace is being collected."""
    ctx = ctx_var.get()
    if ctx is not None:
        ctx.update(values)


def template_version(settings: Settings) -> str:
    """PROMPT_VERSION if set, else a short hash of the fixed prompt text, so it changes when the prompt does."""
    return settings.prompt_version or "t-" + hashlib.sha256((SYSTEM + REMINDER).encode()).hexdigest()[:12]


def prompt_hash(messages: list[dict[str, str]]) -> str:
    body = json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def store_prompt(directory: Path, messages: list[dict[str, str]], template_version: str) -> str:
    sha = prompt_hash(messages)
    path = directory / "prompts" / f"{sha}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sha256": sha, "template_version": template_version,
                                   "messages": messages}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    return sha


def _rotate(path: Path, max_bytes: int) -> None:
    if path.exists() and path.stat().st_size >= max_bytes:
        for n in range(3, 0, -1):
            older = path.with_name(f"{path.name}.{n}")
            if older.exists():
                older.replace(path.with_name(f"{path.name}.{n + 1}")) if n < 3 else older.unlink()
        path.replace(path.with_name(path.name + ".1"))


def write(settings: Settings, record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    log.info(line)                         # stdout: visible in `kubectl logs`
    if not settings.trace_dir:
        return
    try:
        directory = Path(settings.trace_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{settings.pod_name}.jsonl"
        with _lock:
            _rotate(path, settings.trace_max_bytes)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as exc:               # a full or read-only volume must not break answers
        log.warning("trace not written", extra={"error": f"{type(exc).__name__}: {exc}"[:200]})


def _doc_id(chunk_id: str) -> str | None:
    return chunk_id.split("@", 1)[0] if "@" in chunk_id else None


def candidates(passages: list[Any]) -> list[dict[str, Any]]:
    return [{"rank": i + 1, "chunk_id": p.chunk_id, "doc_id": _doc_id(p.chunk_id),
             "doc_version": p.doc_version, "source": p.source, "section": p.section,
             "page": p.page, "score": round(p.score, 4), "superseded": p.superseded}
            for i, p in enumerate(passages)]


def build(settings: Settings, *, trace_id: str, route: str, question: str, status: str,
          app_version: str, eval_controls: EvalControls | None, retriever: Any,
          ctx: dict[str, Any], total_ms: float, response: Any = None) -> dict[str, Any]:
    """Assemble the record of contract 14 section 6 from what the request noted."""
    passages = ctx.get("passages")
    generation = getattr(retriever, "generation", None)
    revision = generation if isinstance(generation, str) else None
    collection = getattr(getattr(retriever, "settings", None), "collection", settings.collection)
    rails = ctx.get("rails") or []
    messages = ctx.get("prompt")
    prompt: dict[str, Any] | None = None
    if messages and settings.trace_dir and settings.trace_enabled:
        try:
            sha = store_prompt(Path(settings.trace_dir), messages, template_version(settings))
            prompt = {"sha256": sha, "template_version": template_version(settings),
                      "chunk_ids": [p.chunk_id for p in (ctx.get("relevant") or [])],
                      "stored": True, "from_cache": False}
        except Exception as exc:
            log.warning("prompt not stored", extra={"error": f"{type(exc).__name__}"})
    elif messages:
        prompt = {"sha256": prompt_hash(messages), "template_version": template_version(settings),
                  "chunk_ids": [p.chunk_id for p in (ctx.get("relevant") or [])],
                  "stored": False, "from_cache": False}
    cache = ctx.get("cache") or {"enabled": False, "hit": False, "similarity": None, "scope": None}
    resp = None
    if response is not None:
        resp = {"answer": response.answer[:2000], "confidence": response.confidence,
                "answered_from_context": response.answered_from_context,
                "abstained": not response.answered_from_context,
                "abstain_reason": ctx.get("abstained"), "fallback_reason": ctx.get("fallback"),
                "citations": [c.model_dump() for c in response.citations],
                "citation_check": {"valid": ctx.get("fallback") is None, "rewritten": []}}
    tokens = ctx.get("tokens") or (0, 0)
    return {
        "type": "trace", "schema": 1, "trace_id": trace_id,
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "route": route, "status": status, "pod": settings.pod_name, "app_version": app_version,
        "release_id": settings.release_id, "query": question[:500],
        "query_truncated": len(question) > 500, "rewritten_query": None,
        "embedding": {"model": settings.embed_model, "version": settings.embed_version,
                      "dimension": ctx.get("dimension")},
        "collection": {"name": collection, "revision": revision, "generation": revision},
        "retrieval": None if passages is None else {
            "top_k": settings.top_k,
            "filters": {"superseded_filter": settings.superseded_filter},
            "candidates": candidates(passages),
            # no reranker: the retriever order (incl. exact-term/table assists) is the final order
            "reranker": "none", "reranked_order": [p.chunk_id for p in passages],
            "from_cache": bool(cache.get("hit")),
            "origin_trace_id": None},
        "guardrails": rails,
        "prompt": prompt,
        "model": None if prompt is None else {
            "provider": settings.llm_provider, "name": settings.llm_model,
            "params": {"temperature": (eval_controls.temperature if eval_controls
                                       and eval_controls.temperature is not None
                                       else settings.temperature),
                       "seed": eval_controls.seed if eval_controls else None,
                       "timeout_s": settings.llm_timeout},
            "attempts": ctx.get("attempts")},
        "response": resp,
        "latency_ms": {"total": round(total_ms, 1), "retrieve": ctx.get("retrieve_ms"),
                       "generate": ctx.get("generation_ms")},
        "cache": cache, "tokens": {"in": tokens[0], "out": tokens[1]},
        "eval": None if not eval_controls or not eval_controls.active else {
            "run_id": eval_controls.run, "label": eval_controls.label,
            "seed": eval_controls.seed, "bypass_cache": eval_controls.bypass_cache},
    }
