"""The real retriever (sections 3.2 and 4.4). It only ever reads Chroma.

Which collection: the indexer publishes each index as a new generation and points the
registry collection `<base>-registry` at it (indexer/pipeline/store.py). This class
follows that pointer, re-reading it every few seconds, so a re-index reaches all three
replicas without a restart. Without a registry (the week-1 dummy index) it reads
`<base>` directly.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..schemas import Passage
from .embedder import OllamaEmbedder
from .tables import matches as table_matches
from .tables import quantitative

log = logging.getLogger("rahbar.retrieval")

POINTER_TTL = 5.0       # seconds between registry reads
CHROMA_TIMEOUT = 5.0    # seconds; readiness probes time out at 3, queries should not hang

# The user explicitly asks about an older edition: only then may superseded chunks come back.
_HISTORY = re.compile(r"\b(older|old|previous|earlier|former|superseded|repealed|outdated|"
                      r"prior|used to|before (?:19|20)\d\d)\b", re.I)
# Exact terms that dense embeddings blur: clause numbers ('1.21') and course codes ('CS-1004').
_EXACT = re.compile(r"\b\d{1,2}\.\d{1,2}\b|\b[A-Z]{2,4}-?\d{3,4}\b")


class EmbeddingPinError(RuntimeError):
    """The index was built with a different embedding model or dimension (4.4)."""


@dataclass(frozen=True)
class IndexInfo:
    collection: str
    count: int
    embed_model: str
    dimension: int | None
    generation: str

    @property
    def is_empty(self) -> bool:
        return self.count == 0


def wants_history(question: str) -> bool:
    return bool(_HISTORY.search(question))


def exact_terms(question: str) -> list[str]:
    return list(dict.fromkeys(_EXACT.findall(question)))[:2]


def pin_problem(info: IndexInfo, settings: Settings,
                query_dimension: int | None = None) -> str | None:
    """None when the index and this API agree on the embedding model; otherwise a
    message naming both sides of the conflict."""
    if info.embed_model != settings.embed_model:
        return (f"embedding model mismatch: index {info.collection!r} was built with "
                f"embed_model={info.embed_model!r} (dimension {info.dimension}) but this API "
                f"has EMBED_MODEL={settings.embed_model!r}; re-run the indexer Job or fix "
                f"the ConfigMap")
    if query_dimension is not None and info.dimension and query_dimension != info.dimension:
        return (f"embedding dimension mismatch: index {info.collection!r} has dimension "
                f"{info.dimension} but {settings.embed_model!r} returned {query_dimension}")
    return None


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings, client: Any = None,
                 embedder: OllamaEmbedder | None = None) -> None:
        self.settings = settings
        self._client = client            # created lazily: Chroma may be down at startup
        self.embedder = embedder or OllamaEmbedder(settings.ollama_url, settings.embed_model)
        self._lock = threading.Lock()
        self._cached: tuple[float, Any, IndexInfo] | None = None
        self._table_lock = threading.Lock()
        self._tables: tuple[str, bool, list[tuple[str, str, dict[str, Any]]]] | None = None

    # ------------------------------------------------------------------ connection
    @property
    def client(self) -> Any:
        if self._client is None:
            import chromadb  # the thin client, from chromadb-client in requirements.txt
            from chromadb.config import Settings as ChromaSettings

            # chromadb-client 1.0.12 talks over httpx.Client(timeout=None): against a Service
            # with no ready endpoint (packets dropped by NetworkPolicy) every call would hang
            # forever. Fail fast first, then bound every later call.
            base = f"http://{self.settings.chroma_host}:{self.settings.chroma_port}"
            httpx.get(f"{base}/api/v2/heartbeat", timeout=CHROMA_TIMEOUT).raise_for_status()
            client = chromadb.HttpClient(
                host=self.settings.chroma_host, port=self.settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False))
            client._server._session.timeout = httpx.Timeout(CHROMA_TIMEOUT)  # type: ignore[attr-defined]
            self._client = client
        return self._client

    def _resolve(self, fresh: bool = False) -> tuple[Any, IndexInfo]:
        with self._lock:
            now = time.monotonic()
            if not fresh and self._cached and now - self._cached[0] < POINTER_TTL:
                return self._cached[1], self._cached[2]
        base = self.settings.collection
        client = self.client             # an unreachable Chroma raises here, never falls back
        try:
            pointer = client.get_collection(f"{base}-registry").metadata or {}
            name = str(pointer.get("active") or base)
        except Exception:  # no registry: week-1 dummy index, read the base collection
            name = base
        col = client.get_collection(name)
        meta = col.metadata or {}
        dim = meta.get("dimension")
        info = IndexInfo(collection=name, count=int(col.count()),
                         embed_model=str(meta.get("embed_model", "")),
                         dimension=int(dim) if dim is not None else None,
                         generation=str(meta.get("generation", name)))
        with self._lock:
            self._cached = (time.monotonic(), col, info)
        return col, info

    def index_info(self) -> IndexInfo:
        """Fresh read for /readyz: raises when Chroma or the collection is missing."""
        return self._resolve(fresh=True)[1]

    @property
    def generation(self) -> str:
        return self._resolve()[1].generation

    def embed_query(self, question: str) -> list[float]:
        return self.embedder.embed(question)

    # ------------------------------------------------------------------ query
    def retrieve(self, question: str, k: int) -> list[Passage]:
        col, info = self._resolve()
        vector = self.embed_query(question)
        problem = pin_problem(info, self.settings, len(vector))
        if problem:
            raise EmbeddingPinError(problem)
        current_only = self.settings.superseded_filter and not wants_history(question)
        where = {"superseded": False} if current_only else None
        passages = self._query(col, vector, k, where)
        if self.settings.exact_term_assist:
            for term in exact_terms(question):
                exact = self._query(col, vector, k, where, {"$contains": term})
                passages = exact + [p for p in passages
                                    if p.chunk_id not in {e.chunk_id for e in exact}]
        if self.settings.exact_term_assist and quantitative(question) and not exact_terms(question):
            try:
                table = self._matching_table(col, info, vector, question, current_only)
                if table is not None and table.score >= self.settings.relevance_floor:
                    passages = [table] + [p for p in passages if p.chunk_id != table.chunk_id]
            except Exception as exc:  # dense retrieval remains available on an assist failure
                log.warning("table retrieval unavailable", extra={"error": type(exc).__name__})
        return passages[:k]

    def _matching_table(self, col: Any, info: IndexInfo, vector: list[float],
                        question: str, current_only: bool) -> Passage | None:
        # Read only table-bearing chunks once per generation, not on every question.
        with self._table_lock:
            if self._tables is None or self._tables[:2] != (info.collection, current_only):
                raw = col.get(where={"superseded": False} if current_only else None,
                              where_document={"$contains": "|"},
                              include=["documents", "metadatas"])
                entries = [(str(cid), str(text or ""), meta or {})
                           for cid, text, meta in zip(raw["ids"], raw["documents"], raw["metadatas"])]
                self._tables = (info.collection, current_only, entries)
            entries = self._tables[2]
        candidates = [(cid, text, meta) for cid, text, meta in entries
                      if (not current_only or not meta.get("superseded", False))
                      and table_matches(question, text, str(meta.get("section", "")),
                                        str(meta.get("doc_version", "")), str(meta.get("source", "")))]
        if not candidates:
            return None
        vectors = col.get(ids=[cid for cid, _, _ in candidates], include=["embeddings"])
        embeddings = vectors.get("embeddings")
        if embeddings is None:
            return None
        by_id = {str(cid): emb for cid, emb in zip(vectors["ids"], embeddings)}
        magnitude = math.sqrt(sum(x * x for x in vector))
        best: Passage | None = None
        for cid, text, meta in candidates:
            emb = by_id.get(cid)
            if emb is None or len(emb) != len(vector) or not magnitude:
                continue
            norm = math.sqrt(sum(float(x) ** 2 for x in emb))
            if not norm:
                continue
            score = sum(x * float(y) for x, y in zip(vector, emb)) / (magnitude * norm)
            if not math.isfinite(score) or (best is not None and score <= best.score):
                continue
            page = meta.get("page")
            best = Passage(chunk_id=cid, text=text, source=str(meta.get("source", "?")),
                           section=str(meta.get("section", "?")),
                           page=int(page) if page is not None else None, score=round(score, 4),
                           doc_version=str(meta.get("doc_version", "")) or None,
                           superseded=bool(meta.get("superseded", False)))
        return best

    @staticmethod
    def _query(col: Any, vector: list[float], k: int, where: dict | None,
               where_document: dict | None = None) -> list[Passage]:
        res = col.query(query_embeddings=[vector], n_results=k, where=where,
                        where_document=where_document,
                        include=["documents", "metadatas", "distances"])
        out = []
        for cid, text, meta, dist in zip(res["ids"][0], res["documents"][0],
                                         res["metadatas"][0], res["distances"][0]):
            meta = meta or {}
            page = meta.get("page")
            out.append(Passage(
                chunk_id=cid, text=text or "", source=str(meta.get("source", "?")),
                section=str(meta.get("section", "?")),
                page=int(page) if page is not None else None,
                score=round(1.0 - float(dist), 4),          # cosine distance -> similarity
                doc_version=str(meta.get("doc_version", "")) or None,
                superseded=bool(meta.get("superseded", False))))
        return out
