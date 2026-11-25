"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import math
import time

import httpx

from .config import IndexerSettings

BATCH = 32
ATTEMPTS = 3


# How text is prepared for each embedding model (docs/a3-ragops/07 section 3.1). The same table is
# kept in the three places that prepare text, because they ship in separate images:
# api/app/retrieval/embedder.py, indexer/pipeline/embed.py and ragops/suite/prep.py.
# tests/test_boundaries.py fails if they differ, so the writer, the reader and the suite cannot drift.
#   doc_prefix / query_prefix: the task instruction the model was trained with
#   lowercase: the model has an uncased vocabulary and Ollama 0.17 does not lowercase for it. Measured
#   (docs/a3-evidence/C/casing-check.txt): true for nomic-embed-text only; mxbai and minilm lowercase themselves.
EMBED_PROFILES: dict[str, dict[str, object]] = {
    "nomic-embed-text": {"doc_prefix": "search_document: ", "query_prefix": "search_query: ",
                         "lowercase": True},
    "mxbai-embed-large": {"doc_prefix": "",
                          "query_prefix": "Represent this sentence for searching relevant passages: ",
                          "lowercase": False},
    "all-minilm": {"doc_prefix": "", "query_prefix": "", "lowercase": False},
}
NO_PROFILE: dict[str, object] = {"doc_prefix": "", "query_prefix": "", "lowercase": False}


def embed_profile(model: str) -> dict[str, object]:
    for name, profile in EMBED_PROFILES.items():
        if model.startswith(name):
            return profile
    return NO_PROFILE


def document_prefix(model: str) -> str:
    """The task prefix for documents, from the model's profile. Queries get theirs from the same
    table (api/app/retrieval/embedder.py), so both sides derive it from the same EMBED_MODEL."""
    return str(embed_profile(model)["doc_prefix"])


def prepare_document(model: str, text: str) -> str:
    """What is actually sent to the model for one chunk.

    nomic-embed-text uses an UNCASED BERT vocabulary, but Ollama 0.17 does not lowercase
    its input, so every capitalised word became the unknown token: 'Rector' and 'Dean',
    'Islamabad' and 'Lahore', 'BS' and 'MS' embedded identically (cosine 1.0000,
    docs/evidence/cache-threshold.txt). Lowercasing is what the reference tokenizer does;
    the API does exactly the same to queries (prepare_query), so the pin still holds."""
    profile = embed_profile(model)
    return document_prefix(model) + (text.lower() if profile["lowercase"] else text)


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
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), BATCH):
            batch = [prepare_document(settings.embed_model, t) for t in texts[start:start + BATCH]]
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
