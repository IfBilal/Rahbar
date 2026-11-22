"""The vector index the ingestion Job writes, behind a small adapter.

`incremental.py` only talks to this interface, so the in-place update logic can be tested
with an in-memory fake and the Chroma calls live in one place. The adapter implements the
operations docs/a3-ragops/04 section 5 needs: add, delete by document id, flip metadata
without re-embedding, count by document id, and bump the registry revision the API's
semantic cache watches. Task T05 (the Chroma spike) confirms each call against Chroma
1.0.12 on the cluster before the incremental code is relied on.
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import IndexerSettings

WRITE_BATCH = 200


def registry_name(base: str) -> str:
    return f"{base}-registry"


def next_revision(current: str) -> str:
    """r0007 -> r0008. Anything unparseable restarts at r0001."""
    digits = current[1:] if current.startswith("r") else ""
    return f"r{int(digits) + 1:04d}" if digits.isdigit() else "r0001"


class VectorIndex(Protocol):
    name: str

    def count(self) -> int: ...
    def count_where(self, where: dict[str, Any]) -> int: ...
    def ids_where(self, where: dict[str, Any]) -> list[str]: ...
    def all_ids(self) -> list[str]: ...
    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]: ...
    def add(self, ids: list[str], documents: list[str], embeddings: list[list[float]],
            metadatas: list[dict[str, Any]]) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def update_metadata(self, ids: list[str], metadatas: list[dict[str, Any]]) -> None: ...
    def revision(self) -> str: ...
    def bump_revision(self) -> str: ...
    def info(self) -> dict[str, Any]: ...
    def drop(self) -> None: ...


class ChromaIndex:
    """One collection plus its registry collection (`<name>-registry`)."""

    def __init__(self, client: Any, name: str, settings: IndexerSettings,
                 embed_version: str = "") -> None:
        self.client, self.name, self.settings = client, name, settings
        self.embed_version = embed_version
        self._col: Any = None

    # -------------------------------------------------------------- collection plumbing
    def collection(self, dimension: int | None = None) -> Any:
        if self._col is None:
            meta: dict[str, Any] = {"hnsw:space": "cosine",
                                    "embed_model": self.settings.embed_model,
                                    "chunk_size": self.settings.chunk_size,
                                    "chunk_overlap": self.settings.chunk_overlap}
            if dimension:
                meta["dimension"] = dimension
            self._col = self.client.get_or_create_collection(name=self.name, metadata=meta)
        return self._col

    def registry(self) -> Any:
        return self.client.get_or_create_collection(name=registry_name(self.name))

    def exists(self) -> bool:
        names = [c if isinstance(c, str) else c.name for c in self.client.list_collections()]
        return self.name in names

    # -------------------------------------------------------------- reads
    def count(self) -> int:
        return int(self.collection().count()) if self.exists() else 0

    def count_where(self, where: dict[str, Any]) -> int:
        return len(self.ids_where(where))

    def ids_where(self, where: dict[str, Any]) -> list[str]:
        if not self.exists():
            return []
        got = self.collection().get(where=where, include=[])
        return [str(i) for i in got["ids"]]

    def all_ids(self) -> list[str]:
        if not self.exists():
            return []
        return [str(i) for i in self.collection().get(include=[])["ids"]]

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        got = self.collection().get(ids=ids, include=["embeddings"])
        embeddings = got.get("embeddings")
        if embeddings is None:
            return {}
        return {str(i): [float(x) for x in e] for i, e in zip(got["ids"], embeddings)}

    # -------------------------------------------------------------- writes
    def add(self, ids: list[str], documents: list[str], embeddings: list[list[float]],
            metadatas: list[dict[str, Any]]) -> None:
        if not ids:
            return
        col = self.collection(dimension=len(embeddings[0]))
        for s in range(0, len(ids), WRITE_BATCH):
            col.upsert(ids=ids[s:s + WRITE_BATCH], documents=documents[s:s + WRITE_BATCH],
                       embeddings=embeddings[s:s + WRITE_BATCH],
                       metadatas=metadatas[s:s + WRITE_BATCH])

    def delete(self, ids: list[str]) -> None:
        col = self.collection()
        for s in range(0, len(ids), WRITE_BATCH):
            col.delete(ids=ids[s:s + WRITE_BATCH])

    def update_metadata(self, ids: list[str], metadatas: list[dict[str, Any]]) -> None:
        col = self.collection()
        for s in range(0, len(ids), WRITE_BATCH):
            col.update(ids=ids[s:s + WRITE_BATCH], metadatas=metadatas[s:s + WRITE_BATCH])

    # -------------------------------------------------------------- registry (the API's pointer)
    def revision(self) -> str:
        try:
            return str((self.registry().metadata or {}).get("generation", ""))
        except Exception:
            return ""

    def bump_revision(self) -> str:
        """Point the registry at this collection with the next data revision. The API
        reads `generation` from here, so its semantic cache scope changes and old cached
        answers become unreachable (docs/a3-ragops/04 section 5)."""
        reg = self.registry()
        meta = dict(reg.metadata or {})
        new = next_revision(str(meta.get("generation", "")))
        col_meta = self.collection().metadata or {}
        reg.modify(metadata={"active": self.name, "generation": new,
                             "previous": str(meta.get("active", "")),
                             "embed_model": self.settings.embed_model,
                             "embed_version": self.embed_version,
                             "dimension": col_meta.get("dimension", meta.get("dimension", 0))})
        return new

    def info(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count(), "revision": self.revision(),
                "embed_model": self.settings.embed_model, "embed_version": self.embed_version}

    def drop(self) -> None:
        """Delete the collection and its registry (a rejected candidate)."""
        names = [c if isinstance(c, str) else c.name for c in self.client.list_collections()]
        for n in (self.name, registry_name(self.name)):
            if n in names:
                self.client.delete_collection(n)
        self._col = None
