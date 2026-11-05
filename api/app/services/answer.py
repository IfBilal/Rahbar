"""Turns a question into an AskResponse: the eight-step query pipeline of section 3.2.

  1. validate      AskRequest (3..500 chars) in routes/ask.py, before this runs
  2. cache check   semantic cache, skipped for follow-ups            services/cache.py
  3. embed         same model as the indexer                         retrieval/embedder.py
  4. retrieve      top_k, superseded filtered out unless asked for    retrieval/chroma.py
     floor         nothing at or above RELEVANCE_FLOOR -> honest abstention, no model call
  5. augment       instructions, numbered evidence, question         services/prompt.py
  6. generate      schema-constrained, low temperature               providers/llm/*
  7. validate      Pydantic + citation guard, retry once, then fall back   services/guard.py
  8. store         one JSON log line for the turn; cache it only when safe
A user never sees a 500 because a model misbehaved: every failure ends in a canned answer.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from pydantic import ValidationError

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider, usage_var
from ..retrieval.base import Retriever
from ..routes import metrics as m
from ..schemas import Answer, AskResponse, Passage, RetrievedRef
from .cache import SemanticCache
from .guard import GuardError, check_answer, is_follow_up
from .prompt import REMINDER, SYSTEM

# A prompt change changes answers, so it must start a fresh cache scope (found when run 2
# of the evaluation was served run 1's answers after the evidence ids changed).
PROMPT_VERSION = hashlib.sha256((SYSTEM + REMINDER).encode()).hexdigest()[:8]

log = logging.getLogger("rahbar.answer")

ABSTAIN_TEXT = ("The documents I have do not cover this question, so I cannot answer it "
                "from them. Please check with the relevant university office.")
FALLBACK_TEXT = ("I could not produce a reliable, properly cited answer from the documents "
                 "for this question. Please try rephrasing it.")


def _refs(passages: list[Passage]) -> list[RetrievedRef]:
    return [RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page,
                         score=p.score) for p in passages]


def _declined(text: str, passages: list[Passage], provider: str) -> AskResponse:
    return AskResponse(request_id=request_id_var.get(), answer=text, citations=[],
                       answered_from_context=False, confidence="low",
                       retrieved=_refs(passages), provider=provider)


def cache_scope(generation: str, provider: str, settings: Settings) -> str:
    """Everything that shapes an answer is in the key, so an answer is only reused under
    the exact rules that produced it: a new index generation, model, provider, floor,
    top_k, passage count or temperature starts a fresh, empty scope."""
    knobs = (f"{PROMPT_VERSION}|{provider}|{settings.llm_model}|{settings.temperature}|"
             f"{settings.relevance_floor}|"
             f"{settings.top_k}|{settings.max_context_passages}|{settings.exact_term_assist}|"
             f"{settings.superseded_filter}|retrieval-order-v1|table-assist-v1")
    digest = hashlib.sha256(knobs.encode()).hexdigest()[:10]
    return f"{generation}:{settings.embed_model}:{digest}"


RETRIES = 1   # 3.4: retry once on a rejected reply, then fall back


def generate_checked(question: str, passages: list[Passage],
                     provider: LLMProvider) -> tuple[Answer | None, str | None, int]:
    """Steps 6-7: generate, validate, retry once. Returns (answer, failure reason, attempts)."""
    reason: str | None = None
    for attempt in range(1, RETRIES + 2):
        try:
            raw = provider.generate(question, passages, retry_reason=reason)
            return check_answer(raw, passages), None, attempt
        except (ValidationError, GuardError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        except Exception as exc:  # timeout, connection refused, HTTP 5xx from the model host
            reason = f"provider error {type(exc).__name__}: {str(exc)[:200]}"
        log.warning("generation rejected", extra={"attempt": attempt, "reason": reason})
    return None, reason, RETRIES + 1


def answer_question(question: str, retriever: Retriever, provider: LLMProvider,
                    settings: Settings, cache: SemanticCache | None = None) -> AskResponse:
    turn: dict[str, Any] = {"retriever": retriever.name, "provider": provider.name,
                            "top_k": settings.top_k}
    follow_up = is_follow_up(question)
    usage_var.set((0, 0))

    # 2. semantic cache (only when there is a cache and a retriever that embeds)
    scope = vector = None
    embed = getattr(retriever, "embed_query", None)
    if cache is not None and embed is not None and not follow_up:
        try:
            scope = cache_scope(retriever.generation, provider.name, settings)  # type: ignore[attr-defined]
            cache.observe(scope)
            vector = embed(question)
            hit, similarity = cache.lookup(scope, vector)
            m.record_cache(hit is not None)
            turn["cache_similarity"] = round(similarity, 4)
            if hit is not None:
                response = AskResponse(**{**hit, "request_id": request_id_var.get(),
                                          "cached": True})
                _log_turn(turn, response, cached=True, follow_up=follow_up)
                return response
        except Exception as exc:   # a cache problem must never fail the question
            log.warning("cache unavailable", extra={"error": f"{type(exc).__name__}: {exc}"})
            scope = None

    # 3-4. embed + retrieve
    started = time.perf_counter()
    try:
        passages = retriever.retrieve(question, k=settings.top_k)
    except Exception as exc:
        m.RETRIEVAL.observe(time.perf_counter() - started)
        m.FALLBACKS.labels(reason="retrieval_error").inc()
        log.error("retrieval failed", extra={"error": f"{type(exc).__name__}: {exc}"})
        response = _declined(FALLBACK_TEXT, [], provider.name)
        _log_turn(turn, response, fallback="retrieval_error")
        return response
    turn["retrieval_ms"] = round((time.perf_counter() - started) * 1000, 1)
    m.RETRIEVAL.observe(time.perf_counter() - started)

    # relevance floor: nothing relevant enough means an honest abstention, no model call
    relevant = [p for p in passages if p.score >= settings.relevance_floor]
    # Keep the retriever ranking: exact-term matches may intentionally precede
    # higher-scoring semantic matches. The floor still applies to every passage.
    relevant = relevant[:settings.max_context_passages]
    if not relevant:
        m.ABSTENTIONS.labels(reason="below_relevance_floor").inc()
        response = _declined(ABSTAIN_TEXT, passages, provider.name)
        _log_turn(turn, response, abstained="below_relevance_floor")
        return response

    # 5-7. augment, generate, validate (retry once), fall back
    started = time.perf_counter()
    answer, failure, attempts = generate_checked(question, relevant, provider)
    m.GENERATION.observe(time.perf_counter() - started)
    turn["generation_ms"] = round((time.perf_counter() - started) * 1000, 1)
    turn["attempts"] = attempts
    tokens_in, tokens_out = usage_var.get()
    m.record_tokens(tokens_in, tokens_out)
    turn.update(tokens_in=tokens_in, tokens_out=tokens_out)
    if answer is None:
        m.FALLBACKS.labels(reason="invalid_output").inc()
        response = _declined(FALLBACK_TEXT, passages, provider.name)
        _log_turn(turn, response, fallback=failure)
        return response

    response = AskResponse(request_id=request_id_var.get(), answer=answer.answer,
                           citations=answer.citations,
                           answered_from_context=answer.answered_from_context,
                           confidence=answer.confidence, retrieved=_refs(passages),
                           provider=provider.name)
    if not response.answered_from_context:
        m.ABSTENTIONS.labels(reason="model_declined").inc()

    # 8. store: cache only a grounded, validated, standalone answer. Fallbacks and
    # abstentions below the floor returned earlier and never reach this point.
    never_cache = follow_up or not response.answered_from_context or not response.citations
    cacheable = scope is not None and vector is not None and not never_cache
    if cacheable and cache is not None and scope is not None and vector is not None:
        try:
            cache.store(scope, question, vector,
                        response.model_dump(exclude={"request_id", "cached"}))
        except Exception as exc:
            log.warning("cache store failed", extra={"error": f"{type(exc).__name__}: {exc}"})
    _log_turn(turn, response, cached_now=cacheable, follow_up=follow_up)
    return response


def _log_turn(turn: dict[str, Any], response: AskResponse,
              **extra: Any) -> None:
    """One line per request (4.8): top_k, chunk ids, scores, abstention. Never the
    question text, the passage text or the model's reasoning."""
    refs = response.retrieved
    log.info("answered", extra={
        **turn, **extra,
        "chunk_ids": [r.chunk_id for r in refs],
        "scores": [round(r.score, 4) for r in refs],
        "answered_from_context": response.answered_from_context,
        "abstained": not response.answered_from_context,
        "citations": len(response.citations),
        "cached": response.cached,
    })
