"""ChromaRetriever against a fake Chroma: pointer, pin, filter, scores, exact terms."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.retrieval import chroma as ch
from app.retrieval.chroma import ChromaRetriever, EmbeddingPinError, exact_terms, wants_history
from app.retrieval.embedder import OllamaEmbedder, query_prefix


class FakeCollection:
    def __init__(self, name, metadata, rows) -> None:
        self.name, self.metadata, self.rows = name, metadata, rows
        self.queries: list[dict] = []

    def count(self) -> int:
        return len(self.rows)

    def query(self, query_embeddings, n_results, where, where_document, include):
        self.queries.append({"where": where, "where_document": where_document, "n": n_results})
        rows = [r for r in self.rows
                if (where is None or r["meta"]["superseded"] == where["superseded"])
                and (where_document is None or where_document["$contains"] in r["text"])]
        rows = sorted(rows, key=lambda r: r["dist"])[:n_results]
        return {"ids": [[r["id"] for r in rows]], "documents": [[r["text"] for r in rows]],
                "metadatas": [[r["meta"] for r in rows]], "distances": [[r["dist"] for r in rows]]}


class FakeClient:
    def __init__(self, collections) -> None:
        self.collections = {c.name: c for c in collections}

    def get_collection(self, name):
        if name not in self.collections:
            raise ValueError(f"Collection {name} does not exist.")
        return self.collections[name]


class FixedEmbedder:
    def __init__(self, dim: int = 3) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        return [0.1] * self.dim


def _row(i, dist, superseded=False, text=None, section=None):
    return {"id": f"c{i}", "dist": dist, "text": text or f"chunk {i}",
            "meta": {"source": "rules.pdf", "section": section or f"S{i}", "page": i,
                     "doc_version": "2023-08" if superseded else "2026-06",
                     "superseded": superseded}}


ROWS = [_row(1, 0.10), _row(2, 0.20, superseded=True), _row(3, 0.30, text="1.21 Students"),
        _row(4, 0.40)]
META = {"embed_model": "nomic-embed-text", "dimension": 3, "generation": "g7"}


def _retriever(meta=None, registry=True, dim=3, **kw) -> ChromaRetriever:
    cols = [FakeCollection("rahbar-gg7", dict(meta or META), ROWS)]
    if registry:
        cols.append(FakeCollection("rahbar-registry", {"active": "rahbar-gg7"}, []))
    settings = Settings(retriever="chroma", embed_model="nomic-embed-text", **kw)
    return ChromaRetriever(settings, client=FakeClient(cols), embedder=FixedEmbedder(dim))


def test_follows_the_registry_and_converts_distance_to_similarity() -> None:
    r = _retriever()
    got = r.retrieve("What is the rule?", 2)
    assert [p.chunk_id for p in got] == ["c1", "c3"]            # c2 is superseded
    assert got[0].score == 0.9 and got[0].doc_version == "2026-06"
    assert r.generation == "g7" and r.index_info().count == 4


def test_without_a_registry_it_reads_the_base_collection() -> None:
    col = FakeCollection("rahbar", {"embed_model": "dummy-768", "dimension": 3}, ROWS[:1])
    r = ChromaRetriever(Settings(retriever="chroma", embed_model="dummy-768"),
                        client=FakeClient([col]), embedder=FixedEmbedder())
    assert r.index_info().collection == "rahbar" and r.retrieve("q", 5)[0].chunk_id == "c1"


def test_superseded_chunks_only_come_back_when_asked_for() -> None:
    r = _retriever()
    assert "c2" not in [p.chunk_id for p in r.retrieve("What is the withdrawal deadline?", 5)]
    old = r.retrieve("Under the older 2023 rules, what was the withdrawal deadline?", 5)
    assert "c2" in [p.chunk_id for p in old] and next(p for p in old if p.chunk_id == "c2").superseded


@pytest.mark.parametrize("question,expected", [
    ("Under the older 2023 academic rules, what was the deadline?", True),
    ("What did the previous handbook say?", True),
    ("What was the rule before 2026?", True),
    ("How many faculty members according to the 2023-24 annual report?", False),
    ("What is the deadline to withdraw from a course?", False),
])
def test_history_intent(question: str, expected: bool) -> None:
    assert wants_history(question) is expected


def test_exact_terms_are_pulled_to_the_front() -> None:
    assert exact_terms("What does clause 1.21 require for CS-1004?") == ["1.21", "CS-1004"]
    got = _retriever().retrieve("What does clause 1.21 require?", 2)
    assert got[0].chunk_id == "c3"                            # dense rank 2, exact match first
    plain = _retriever(exact_term_assist=False).retrieve("What does clause 1.21 require?", 2)
    assert plain[0].chunk_id == "c1"


def test_a_different_embedding_model_is_refused() -> None:
    r = _retriever(meta={**META, "embed_model": "mxbai-embed-large"})
    with pytest.raises(EmbeddingPinError, match="mxbai-embed-large.*nomic-embed-text"):
        r.retrieve("q", 3)


def test_a_different_dimension_is_refused() -> None:
    with pytest.raises(EmbeddingPinError, match="dimension"):
        _retriever(dim=768).retrieve("q", 3)


def test_pointer_is_reread_after_the_ttl(monkeypatch) -> None:
    r = _retriever()
    r.retrieve("q", 1)
    r._client.collections["rahbar-gg8"] = FakeCollection("rahbar-gg8", {**META, "generation": "g8"}, ROWS)
    r._client.collections["rahbar-registry"].metadata = {"active": "rahbar-gg8"}
    assert r.generation == "g7"                                # still inside the TTL
    monkeypatch.setattr(ch, "POINTER_TTL", 0.0)
    assert r.generation == "g8"


def test_query_embedder_uses_the_pin_prefix_and_reuses_vectors() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[0.5, 0.5]]})

    e = OllamaEmbedder("http://ollama:11434/", "nomic-embed-text",
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert e.embed("Hello") == e.embed("Hello") == [0.5, 0.5]
    assert len(calls) == 1 and calls[0] == {"model": "nomic-embed-text",
                                             "input": ["search_query: hello"]}
    assert query_prefix("all-minilm") == ""


def test_query_embedder_rejects_an_empty_reply() -> None:
    e = OllamaEmbedder("http://o", "m", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"embeddings": []}))))
    with pytest.raises(ValueError):
        e.embed("x")


def test_an_unreachable_chroma_fails_fast_instead_of_hanging(monkeypatch) -> None:
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        raise httpx.ConnectTimeout("dropped by policy")

    monkeypatch.setattr(ch.httpx, "get", fake_get)
    r = ChromaRetriever(Settings(retriever="chroma", chroma_host="chroma", chroma_port=8000),
                        embedder=FixedEmbedder())
    with pytest.raises(httpx.ConnectTimeout):
        r.index_info()
    assert calls == [("http://chroma:8000/api/v2/heartbeat", ch.CHROMA_TIMEOUT)]
