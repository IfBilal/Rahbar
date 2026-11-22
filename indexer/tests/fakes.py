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

    # --- the subset of the real collection API the Assignment 03 adapter uses
    @staticmethod
    def _match(meta: dict, where: dict | None) -> bool:
        if not where:
            return True
        if "$and" in where:
            return all(FakeCollection._match(meta, w) for w in where["$and"])
        return all(meta.get(k) == v for k, v in where.items())

    def upsert(self, ids, documents, embeddings, metadatas) -> None:
        self.add(ids, documents, embeddings, metadatas)

    def get(self, ids=None, where=None, include=None) -> dict:
        keep = [i for i, (_, _, m) in self.rows.items()
                if (ids is None or i in ids) and self._match(m, where)]
        out: dict = {"ids": keep}
        if include and "embeddings" in include:
            out["embeddings"] = [self.rows[i][1] for i in keep]
        return out

    def delete(self, ids) -> None:
        for i in ids:
            self.rows.pop(i, None)

    def update(self, ids, metadatas) -> None:
        for i, m in zip(ids, metadatas):
            d, e, _ = self.rows[i]
            self.rows[i] = (d, e, dict(m))


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


# ---------------------------------------------------------------- Assignment 03 (incremental ingestion)
class FakeIndex:
    """In-memory VectorIndex (pipeline/index.py): supports the `where` shapes the ingestion
    code uses (`{"k": v}` and `{"$and": [...]}`) and records every write."""

    def __init__(self, name: str = "rahbar") -> None:
        self.name = name
        self.rows: dict[str, tuple[str, list[float], dict]] = {}
        self._revision = ""
        self.writes: list[tuple[str, int]] = []

    @staticmethod
    def _match(meta: dict, where: dict) -> bool:
        if "$and" in where:
            return all(FakeIndex._match(meta, w) for w in where["$and"])
        return all(meta.get(k) == v for k, v in where.items())

    def count(self) -> int:
        return len(self.rows)

    def count_where(self, where: dict) -> int:
        return len(self.ids_where(where))

    def ids_where(self, where: dict) -> list[str]:
        return [i for i, (_, _, m) in self.rows.items() if self._match(m, where)]

    def all_ids(self) -> list[str]:
        return list(self.rows)

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        return {i: self.rows[i][1] for i in ids if i in self.rows}

    def add(self, ids, documents, embeddings, metadatas) -> None:
        self.writes.append(("add", len(ids)))
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, list(e), dict(m))

    def delete(self, ids: list[str]) -> None:
        self.writes.append(("delete", len(ids)))
        for i in ids:
            self.rows.pop(i, None)

    def update_metadata(self, ids, metadatas) -> None:
        self.writes.append(("update", len(ids)))
        for i, m in zip(ids, metadatas):
            d, e, _ = self.rows[i]
            self.rows[i] = (d, e, dict(m))

    def revision(self) -> str:
        return self._revision

    def bump_revision(self) -> str:
        from pipeline.index import next_revision
        self._revision = next_revision(self._revision)
        return self._revision

    def info(self) -> dict:
        return {"name": self.name, "count": self.count(), "revision": self._revision}

    def drop(self) -> None:
        self.rows.clear()
        self.dropped = True


class CountingEmbed:
    """Deterministic 32-d bag-of-words embedder that remembers what it was asked."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        out = []
        for t in texts:
            v = [0.0] * 32
            for w in t.lower().split():
                v[sum(w.encode()) % 32] += 1.0
            out.append(v)
        return out

    @property
    def texts_embedded(self) -> int:
        return sum(len(c) for c in self.calls)
