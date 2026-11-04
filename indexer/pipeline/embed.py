"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import math
import time

import httpx

from .config import IndexerSettings

BATCH = 32
ATTEMPTS = 3


def document_prefix(model: str) -> str:
    """nomic-embed-text is trained with task prefixes: documents get 'search_document: ',
    queries 'search_query: ' (api/app/retrieval/embedder.py). Part of the pin: both sides
    derive the prefix from the same EMBED_MODEL, so they cannot disagree."""
    return "search_document: " if model.startswith("nomic-embed-text") else ""


def embed(texts: list[str], settings: IndexerSettings,
          client: httpx.Client | None = None) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    POST {ollama_url}/api/embed with {"model": ..., "input": [texts]} returns
    {"embeddings": [[...], ...]}. Batched, retried, and every vector is checked: one per
    text, finite, and all of the same dimension.
    """
    if not texts:
        return []
    own = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
    prefix = document_prefix(settings.embed_model)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), BATCH):
            batch = [prefix + t for t in texts[start:start + BATCH]]
            vectors.extend(_embed_batch(http, settings, batch))
    finally:
        if own:
            http.close()
    check_vectors(vectors, len(texts))
    return vectors


def _embed_batch(http: httpx.Client, settings: IndexerSettings,
                 batch: list[str]) -> list[list[float]]:
    url = f"{settings.ollama_url.rstrip('/')}/api/embed"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = http.post(url, json={"model": settings.embed_model, "input": batch})
            r.raise_for_status()
            got = r.json().get("embeddings") or []
            if len(got) != len(batch):
                raise ValueError(f"asked for {len(batch)} embeddings, got {len(got)}")
            return [list(map(float, v)) for v in got]
        except (httpx.HTTPError, ValueError):
            if attempt == ATTEMPTS:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def check_vectors(vectors: list[list[float]], expected: int) -> int:
    """Return the common dimension, or raise: a bad vector must fail the Job, not
    reach the index."""
    if len(vectors) != expected:
        raise ValueError(f"{expected} chunks but {len(vectors)} vectors")
    dims = {len(v) for v in vectors}
    if len(dims) != 1:
        raise ValueError(f"vectors have mixed dimensions {sorted(dims)}")
    if any(not math.isfinite(x) for v in vectors for x in v):
        raise ValueError("a vector contains NaN or infinity")
    return dims.pop()
