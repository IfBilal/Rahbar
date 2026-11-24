# T05 Chroma spike

Run 24 Nov 2026 on the host: `kubectl -n rahbar port-forward svc/chroma 8000:8000` then `.venv/bin/python scripts/ragops/chroma_spike.py` against the cluster's `chromadb/chroma:1.0.12` (client 1.0.12). Raw output, unedited:

```
chromadb client 1.0.12; server heartbeat 1795539019989175381
PASS  upsert adds rows  -> count=3
PASS  upsert of an existing id replaces it  -> 'alpha ONE changed', page=9
PASS  get(where={'doc_id': ...}) returns ids  -> ['a1', 'a2']
PASS  get(where={'$and': [...]}) works  -> ['a1', 'a2']
PASS  get(include=['embeddings']) returns vectors
PASS  update(metadatas) MERGES keys (else pass the full dict, which the code does)  -> after update with only {'superseded': True}: {'doc_id': 'doc-a', 'source': 'a.md', 'superseded': True, 'doc_version': 'v1', 'page': 2, 'status': 'current'}
PASS  update(metadatas) with the FULL dict sets every key  -> {'superseded': True, 'doc_id': 'doc-a', 'doc_version': 'v1', 'source': 'a.md', 'page': 1, 'status': 'archived'}
PASS  a metadata filter sees the update immediately  -> ['a1', 'a2']
PASS  query with where={'superseded': False} excludes updated rows  -> ['b1']
PASS  delete(ids) removes rows  -> count=1
PASS  delete(where=...) removes rows (not used by the code, but useful)  -> count=0
PASS  registry modify() sets metadata  -> {'active': 'spike-84075', 'generation': 'r0001', 'embed_model': 'spike'}
PASS  registry modify() twice, re-read through a fresh handle: revision bumps  -> {'active': 'spike-84075', 'generation': 'r0002', 'embed_model': 'spike'}
PASS  collection modify() without hnsw keys  -> metadata now {'generation': 'r0009'}
PASS  list_collections sees the throw-away collection

15 checks: 15 pass, 0 fail, 0 note
```

Result: every call the adapter in `indexer/pipeline/index.py` relies on behaves as assumed. No change to `ChromaIndex` was needed.
