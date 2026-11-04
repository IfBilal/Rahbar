"""Stage 5: Store. The only code in the whole system that writes to Chroma.

Re-indexing never touches the collection the API is serving (ADR 0001):
  1. build a new, uniquely named generation collection  <base>-g<generation>
  2. check it holds every chunk
  3. publish: point the registry collection <base>-registry at it (one metadata write,
     so the 3 API replicas switch from the old index to the new one at once)
  4. delete generations older than the previous one (kept for rollback)
A Job that dies half-way leaves an unpublished generation behind; the API never reads it
and the next successful run garbage-collects it. The API sees the new generation id and
expires its semantic cache (case study 3.3), so the indexer never needs Redis access.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .config import IndexerSettings
from .embed import check_vectors
from .models import Chunk

WRITE_BATCH = 200


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def registry_name(base: str) -> str:
    return f"{base}-registry"


def new_generation(chunks: list[Chunk], settings: IndexerSettings) -> str:
    digest = hashlib.sha256(json.dumps(
        [settings.embed_model, settings.chunk_size, settings.chunk_overlap,
         [c.id for c in chunks]]).encode()).hexdigest()[:8]
    return f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{digest}"


def _names(client: Any) -> list[str]:
    return [c if isinstance(c, str) else c.name for c in client.list_collections()]


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings,
          client: Any = None) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    if not chunks:
        raise ValueError("refusing to publish an empty index")
    dimension = check_vectors(vectors, len(chunks))
    if len({c.id for c in chunks}) != len(chunks):
        raise ValueError("duplicate chunk ids")
    client = client or get_client(settings)
    generation = new_generation(chunks, settings)
    name = f"{settings.collection}-g{generation}"
    col = client.create_collection(name=name, metadata={
        "hnsw:space": "cosine", "embed_model": settings.embed_model,
        "dimension": dimension, "generation": generation, "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap})
    for start in range(0, len(chunks), WRITE_BATCH):
        part = chunks[start:start + WRITE_BATCH]
        col.add(ids=[c.id for c in part], documents=[c.text for c in part],
                embeddings=vectors[start:start + WRITE_BATCH],
                metadatas=[c.metadata() for c in part])
    count = int(col.count())
    if count != len(chunks):
        client.delete_collection(name)
        raise RuntimeError(f"wrote {count} of {len(chunks)} chunks; generation discarded")
    previous = publish(client, settings, name, generation, dimension)
    collect_garbage(client, settings.collection, keep={name, previous})
    return count


def publish(client: Any, settings: IndexerSettings, name: str, generation: str,
            dimension: int) -> str:
    """Point the registry at the new generation. Returns the generation it replaced."""
    registry = client.get_or_create_collection(name=registry_name(settings.collection))
    previous = str((registry.metadata or {}).get("active", ""))
    registry.modify(metadata={"active": name, "generation": generation,
                              "previous": previous, "embed_model": settings.embed_model,
                              "dimension": dimension})
    return previous


def collect_garbage(client: Any, base: str, keep: set[str]) -> list[str]:
    """Delete generation collections that are neither active nor the previous one."""
    gone = [n for n in _names(client) if n.startswith(f"{base}-g") and n not in keep]
    for n in gone:
        client.delete_collection(n)
    return gone
