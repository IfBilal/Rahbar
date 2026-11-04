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


def query_prefix(model: str) -> str:
    return "search_query: " if model.startswith("nomic-embed-text") else ""


def prepare_query(model: str, text: str) -> str:
    """Mirror of indexer/pipeline/embed.py::prepare_document. nomic-embed-text is uncased
    and Ollama does not lowercase for it, so capitalised words collapsed to one unknown
    token ('Rector' == 'Dean'); both sides lowercase, so the pin still holds."""
    if model.startswith("nomic-embed-text"):
        return query_prefix(model) + text.lower()
    return text


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
