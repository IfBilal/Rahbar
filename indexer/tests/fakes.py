"""In-memory stand-ins for the Chroma HTTP client (no server needed)."""

from __future__ import annotations

from typing import Any


class FakeCollection:
    def __init__(self, name: str, metadata: dict | None) -> None:
        self.name, self.metadata, self.rows = name, dict(metadata or {}), {}

    def add(self, ids, documents, embeddings, metadatas) -> None:
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def count(self) -> int:
        return len(self.rows)

    def modify(self, metadata: dict | None = None, name: str | None = None) -> None:
        self.metadata = dict(metadata or {})


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def create_collection(self, name: str, metadata: dict | None = None) -> FakeCollection:
        if name in self.collections:
            raise ValueError(f"collection {name} already exists")
        self.collections[name] = FakeCollection(name, metadata)
        return self.collections[name]

    def get_or_create_collection(self, name: str, metadata: Any = None) -> FakeCollection:
        return self.collections.get(name) or self.create_collection(name, metadata)

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        del self.collections[name]

    def list_collections(self) -> list[FakeCollection]:
        return list(self.collections.values())
