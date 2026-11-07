"""Prometheus metrics at /metrics (section 4.8).

Request count and latency per route, plus the RAG signals: retrieval and generation
latency, cache lookups/hits (ratio = hits / lookups, also exported as a gauge),
abstentions, fallbacks by reason, and tokens in and out per request.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL = Histogram("rahbar_retrieval_seconds", "Embed + vector search latency",
                      buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5))
GENERATION = Histogram("rahbar_generation_seconds", "LLM generation latency (all attempts)",
                       buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120))
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache lookups")
CACHE_HITS = Counter("rahbar_cache_hits_total", "Semantic cache hits")
CACHE_HIT_RATIO = Gauge("rahbar_cache_hit_ratio", "Cache hits / lookups since this pod started")
ABSTENTIONS = Counter("rahbar_abstentions_total", "Answers with answered_from_context=false",
                      ["reason"])
FALLBACKS = Counter("rahbar_fallbacks_total", "Safe canned responses served", ["reason"])
TOKENS = Counter("rahbar_tokens_total", "LLM tokens", ["direction"])
TOKENS_PER_REQUEST = Histogram("rahbar_tokens_per_request", "LLM tokens per request",
                               ["direction"], buckets=(50, 100, 250, 500, 1000, 2000, 4000, 8000))
# Labelled series only appear after their first use; create them at 0 so a fresh pod's
# /metrics already lists abstentions, fallbacks and tokens (4.8).
for _reason in ("below_relevance_floor", "model_declined"):
    ABSTENTIONS.labels(reason=_reason)
for _reason in ("retrieval_error", "invalid_output"):
    FALLBACKS.labels(reason=_reason)
for _direction in ("in", "out"):
    TOKENS.labels(direction=_direction)


def record_cache(hit: bool) -> None:
    CACHE_LOOKUPS.inc()
    if hit:
        CACHE_HITS.inc()
    lookups = CACHE_LOOKUPS._value.get()
    CACHE_HIT_RATIO.set(CACHE_HITS._value.get() / lookups if lookups else 0.0)


def record_tokens(tokens_in: int, tokens_out: int) -> None:
    for direction, n in (("in", tokens_in), ("out", tokens_out)):
        TOKENS.labels(direction=direction).inc(n)
        TOKENS_PER_REQUEST.labels(direction=direction).observe(n)


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
