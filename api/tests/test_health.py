"""/healthz touches nothing; /readyz names every failed dependency with a 503."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.retrieval.chroma import IndexInfo
from app.services.cache import SemanticCache

from .fakes import FakeRedis


@dataclass
class Retriever:
    info: IndexInfo | None = None
    error: Exception | None = None
    name: str = "chroma"

    def index_info(self) -> IndexInfo:
        if self.error:
            raise self.error
        assert self.info
        return self.info


GOOD = IndexInfo(collection="rahbar-gx", count=480, embed_model="nomic-embed-text",
                 dimension=768, generation="x")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    from app.main import app

    with TestClient(app) as c:
        yield c, app


def _wire(app, retriever, redis_down=False):
    redis = FakeRedis()
    redis.down = redis_down
    app.state.retriever = retriever
    app.state.cache = SemanticCache(redis, 0.95)
    app.state.settings = app.state.settings.__class__(
        **{**app.state.settings.__dict__, "redis_url": "redis://redis:6379/0"})


def test_ready_when_everything_is_fine(client) -> None:
    c, app = client
    _wire(app, Retriever(GOOD))
    r = c.get("/readyz")
    assert r.status_code == 200 and r.json()["failed"] == []
    assert "480 chunks" in r.json()["checks"]["collection"]


@pytest.mark.parametrize("retriever,redis_down,failed", [
    (Retriever(error=ConnectionError("refused")), False, ["chroma"]),
    (Retriever(IndexInfo("rahbar", 0, "nomic-embed-text", 768, "x")), False, ["collection"]),
    (Retriever(IndexInfo("rahbar", 3, "dummy-768", 768, "x")), False, ["embedding_pin"]),
    (Retriever(GOOD), True, ["redis"]),
])
def test_not_ready_names_the_dependency(client, retriever, redis_down, failed) -> None:
    c, app = client
    _wire(app, retriever, redis_down)
    r = c.get("/readyz")
    assert r.status_code == 503 and r.json()["failed"] == failed


def test_pin_mismatch_message_names_both_models(client) -> None:
    c, app = client
    _wire(app, Retriever(IndexInfo("rahbar", 3, "dummy-768", 768, "x")))
    msg = c.get("/readyz").json()["checks"]["embedding_pin"]
    assert "dummy-768" in msg and "nomic-embed-text" in msg and "mismatch" in msg


def test_liveness_never_touches_dependencies(client) -> None:
    c, app = client
    _wire(app, Retriever(error=AssertionError("liveness must not call Chroma")), redis_down=True)
    assert c.get("/healthz").json() == {"status": "alive"}


def test_stub_mode_is_ready_without_dependencies(client) -> None:
    c, _ = client
    assert c.get("/readyz").status_code == 200
