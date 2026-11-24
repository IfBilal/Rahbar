#!/usr/bin/env python3
"""T05, the Chroma spike (docs/a3-ragops/11): does Chroma 1.0.12 do what the incremental
ingestion code assumes? Run it against the cluster's Chroma, never against the live collection:

    kubectl -n rahbar port-forward svc/chroma 8000:8000 &
    .venv/bin/python scripts/ragops/chroma_spike.py [--host localhost --port 8000]

It creates a throw-away collection `spike-<pid>` and its registry, checks each operation the
adapter in indexer/pipeline/index.py relies on, prints PASS / FAIL / NOTE per check with what it
observed, deletes everything, and exits 1 if any required check failed. Save the output as
docs/a3-evidence/chroma-spike.md. If a required check FAILS, tell the other member before any
more incremental-ingestion code is built (the fallback is written in docs/a3-ragops/03, C-01).
"""

from __future__ import annotations

import argparse
import os
import sys

import chromadb
from chromadb.config import Settings

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", required: bool = True) -> None:
    status = "PASS" if ok else ("FAIL" if required else "NOTE")
    results.append((status, name, detail))
    print(f"{status:<5} {name}" + (f"  -> {detail}" if detail else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    client = chromadb.HttpClient(host=args.host, port=args.port,
                                 settings=Settings(anonymized_telemetry=False))
    name = f"spike-{os.getpid()}"
    created: list[str] = []
    try:
        print(f"chromadb client {chromadb.__version__}; server heartbeat {client.heartbeat()}")
        col = client.get_or_create_collection(name=name, metadata={
            "hnsw:space": "cosine", "embed_model": "spike", "dimension": 3})
        created.append(name)
        meta = {"source": "a.md", "doc_id": "doc-a", "doc_version": "v1", "superseded": False,
                "status": "current", "page": 1}
        col.upsert(ids=["a1", "a2", "b1"], documents=["alpha one", "alpha two", "beta one"],
                   embeddings=[[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0]],
                   metadatas=[dict(meta), {**meta, "page": 2},
                              {**meta, "doc_id": "doc-b", "source": "b.md"}])
        check("upsert adds rows", col.count() == 3, f"count={col.count()}")

        col.upsert(ids=["a1"], documents=["alpha ONE changed"], embeddings=[[1, 0, 0]],
                   metadatas=[{**meta, "page": 9}])
        got = col.get(ids=["a1"], include=["documents", "metadatas"])
        check("upsert of an existing id replaces it", got["documents"][0] == "alpha ONE changed"
              and got["metadatas"][0]["page"] == 9, f"{got['documents'][0]!r}, page={got['metadatas'][0]['page']}")

        by_doc = col.get(where={"doc_id": "doc-a"}, include=[])
        check("get(where={'doc_id': ...}) returns ids", sorted(by_doc["ids"]) == ["a1", "a2"],
              str(sorted(by_doc["ids"])))
        both = col.get(where={"$and": [{"doc_id": "doc-a"}, {"doc_version": "v1"}]}, include=[])
        check("get(where={'$and': [...]}) works", sorted(both["ids"]) == ["a1", "a2"],
              str(sorted(both["ids"])))
        emb = col.get(ids=["a2"], include=["embeddings"])
        check("get(include=['embeddings']) returns vectors", emb.get("embeddings") is not None
              and len(emb["embeddings"][0]) == 3)

        # THE important one: does update() MERGE metadata keys or REPLACE the whole dict?
        col.update(ids=["a2"], metadatas=[{"superseded": True}])
        after = col.get(ids=["a2"], include=["metadatas"])["metadatas"][0]
        merged = after.get("doc_id") == "doc-a" and after.get("superseded") is True
        check("update(metadatas) MERGES keys (else pass the full dict, which the code does)",
              merged, f"after update with only {{'superseded': True}}: {after}", required=False)
        full = {**meta, "superseded": True, "status": "archived"}
        col.update(ids=["a1", "a2"], metadatas=[full, full])
        after = col.get(ids=["a1"], include=["metadatas"])["metadatas"][0]
        check("update(metadatas) with the FULL dict sets every key",
              after["superseded"] is True and after["status"] == "archived" and after["doc_id"] == "doc-a",
              str(after))
        flipped = col.get(where={"superseded": True}, include=[])
        check("a metadata filter sees the update immediately", sorted(flipped["ids"]) == ["a1", "a2"],
              str(sorted(flipped["ids"])))

        res = col.query(query_embeddings=[[1, 0, 0]], n_results=3, where={"superseded": False})
        check("query with where={'superseded': False} excludes updated rows",
              res["ids"][0] == ["b1"], str(res["ids"][0]))

        col.delete(ids=["a1", "a2"])
        check("delete(ids) removes rows", col.count() == 1 and col.get(where={"doc_id": "doc-a"},
              include=[])["ids"] == [], f"count={col.count()}")
        col.delete(where={"doc_id": "doc-b"})
        check("delete(where=...) removes rows (not used by the code, but useful)",
              col.count() == 0, f"count={col.count()}", required=False)

        # registry: modify() of collection metadata (the API's pointer and revision counter)
        reg = client.get_or_create_collection(name=f"{name}-registry")
        created.append(f"{name}-registry")
        reg.modify(metadata={"active": name, "generation": "r0001", "embed_model": "spike"})
        check("registry modify() sets metadata", (reg.metadata or {}).get("generation") == "r0001",
              str(reg.metadata))
        reg.modify(metadata={"active": name, "generation": "r0002", "embed_model": "spike"})
        again = client.get_collection(f"{name}-registry").metadata or {}
        check("registry modify() twice, re-read through a fresh handle: revision bumps",
              again.get("generation") == "r0002", str(again))

        # the collection's own metadata cannot carry the revision (hnsw keys are immutable)
        try:
            col.modify(metadata={"generation": "r0009"})
            now = client.get_collection(name).metadata or {}
            check("collection modify() without hnsw keys", True, f"metadata now {now}", required=False)
        except Exception as exc:
            check("collection modify() (not needed: the revision lives in the registry)", False,
                  f"{type(exc).__name__}: {str(exc)[:120]}", required=False)
        listed = [c if isinstance(c, str) else c.name for c in client.list_collections()]
        check("list_collections sees the throw-away collection", name in listed)
    finally:
        for n in created:
            try:
                client.delete_collection(n)
            except Exception as exc:
                print(f"cleanup of {n} failed: {exc}", file=sys.stderr)
    failed = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results)} checks: {sum(r[0] == 'PASS' for r in results)} pass, {len(failed)} fail, "
          f"{sum(r[0] == 'NOTE' for r in results)} note")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
