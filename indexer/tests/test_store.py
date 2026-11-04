"""Stage 5 (store): generations, publish, rollback window, garbage collection."""

from __future__ import annotations

import pytest

from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import collect_garbage, registry_name, store

from .fakes import FakeClient


def _chunks(n: int, tag: str = "a") -> list[Chunk]:
    return [Chunk(id=f"{tag}-{i}", text=f"text {i}", source="r.pdf", section="S", page=1,
                  doc_version="2026", superseded=False) for i in range(n)]


def _vectors(n: int, dim: int = 4) -> list[list[float]]:
    return [[float(i)] * dim for i in range(n)]


def test_store_writes_a_generation_and_publishes_it(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    client, settings = FakeClient(), get_settings()
    assert store(_chunks(5), _vectors(5, 768), settings, client=client) == 5
    registry = client.collections[registry_name("rahbar")].metadata
    active = client.collections[registry["active"]]
    assert active.name.startswith("rahbar-g") and active.count() == 5
    assert active.metadata["embed_model"] == "nomic-embed-text"
    assert active.metadata["dimension"] == 768 == registry["dimension"]
    assert active.metadata["hnsw:space"] == "cosine"
    assert set(active.rows["a-0"][2]) == {"source", "section", "page", "doc_version", "superseded"}


def test_reindex_keeps_previous_and_collects_older(monkeypatch) -> None:
    client, settings = FakeClient(), get_settings()
    ticks = iter(["20260101000000", "20260102000000", "20260103000000"])
    monkeypatch.setattr("pipeline.store.time.strftime", lambda fmt, t=None: next(ticks))
    names = []
    for tag in "abc":
        store(_chunks(3, tag), _vectors(3), settings, client=client)
        names.append(client.collections[registry_name("rahbar")].metadata["active"])
    registry = client.collections[registry_name("rahbar")].metadata
    assert registry["active"] == names[2] and registry["previous"] == names[1]
    assert names[0] not in client.collections            # oldest generation collected
    assert names[1] in client.collections                # kept for rollback


def test_an_empty_index_is_never_published() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="empty"):
        store([], [], get_settings(), client=client)
    assert client.collections == {}


def test_duplicate_ids_are_refused() -> None:
    chunks = _chunks(2)
    chunks[1].id = chunks[0].id
    with pytest.raises(ValueError, match="duplicate"):
        store(chunks, _vectors(2), get_settings(), client=FakeClient())


def test_a_short_write_is_discarded_not_published(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr("tests.fakes.FakeCollection.count", lambda self: 1)
    with pytest.raises(RuntimeError, match="discarded"):
        store(_chunks(3), _vectors(3), get_settings(), client=client)
    assert registry_name("rahbar") not in client.collections
    assert not [n for n in client.collections if n.startswith("rahbar-g")]


def test_garbage_collection_spares_other_collections() -> None:
    client = FakeClient()
    for name in ("rahbar-g1", "rahbar-g2", "rahbar-g3", "rahbar-registry", "other"):
        client.create_collection(name)
    gone = collect_garbage(client, "rahbar", keep={"rahbar-g3", "rahbar-g2"})
    assert gone == ["rahbar-g1"] and "other" in client.collections


def test_dummy_index_unpublishes_a_real_generation() -> None:
    """Week-1 dummy mode must not leave the API reading an older real generation."""
    from pipeline.dummy import write_dummy_index

    client = FakeClient()
    store(_chunks(3), _vectors(3), get_settings(), client=client)
    assert write_dummy_index(get_settings(), client) == 3
    assert registry_name("rahbar") not in client.collections
    assert client.collections["rahbar"].metadata["embed_model"] == "dummy-768"
