"""Query embeddings, from the pinned model only (3.2 step 3, 4.4).

The indexer embeds chunks with the same EMBED_MODEL (indexer/pipeline/embed.py). For
nomic-embed-text both sides add the model's task prefix ('search_document: ' there,
'search_query: ' here) and lowercase the text (the model is uncased), both derived from
the model name, so they cannot drift apart.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import httpx


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


def query_prefix(model: str) -> str:
    return str(embed_profile(model)["query_prefix"])


def prepare_query(model: str, text: str) -> str:
    """Mirror of indexer/pipeline/embed.py::prepare_document. nomic-embed-text is uncased
    and Ollama does not lowercase for it, so capitalised words collapsed to one unknown
    token ('Rector' == 'Dean'); both sides lowercase, so the pin still holds."""
    profile = embed_profile(model)
    return str(profile["query_prefix"]) + (text.lower() if profile["lowercase"] else text)


class OllamaEmbedder:
    """POST {ollama_url}/api/embed. Keeps the last few vectors, because the semantic
    cache and the retriever embed the same question in one request."""

    def __init__(self, url: str, model: str, timeout: float = 30.0,
                 client: httpx.Client | None = None, keep: int = 256) -> None:
        self.url = url.rstrip("/") + "/api/embed"
        self.model = model
        self.http = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))
        self._recent: OrderedDict[str, list[float]] = OrderedDict()
        self._keep = keep
        self._lock = threading.Lock()

    def embed(self, text: str) -> list[float]:
        with self._lock:
            if text in self._recent:
                self._recent.move_to_end(text)
                return self._recent[text]
        r = self.http.post(self.url, json={"model": self.model,
                                           "input": [prepare_query(self.model, text)]})
        r.raise_for_status()
        vectors = r.json().get("embeddings") or []
        if len(vectors) != 1 or not vectors[0]:
            raise ValueError(f"embedding service returned {len(vectors)} vectors for 1 input")
        vector = [float(x) for x in vectors[0]]
        with self._lock:
            self._recent[text] = vector
            if len(self._recent) > self._keep:
                self._recent.popitem(last=False)
        return vector
