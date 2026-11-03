# Frozen HTTP, Python, metadata and environment contracts

**Hard gate G0:** both humans sign off on these contracts before independent coding. `api/app/schemas.py` is the actual schema source; do not silently add `session_id`, change JSON fields or invent provider modes. All examples of scores and answers illustrate schema **only**, not evaluation results.

**Two cross-cutting caveats:** the starter has no user/session history, so follow-up detection must conservatively disable cache for ambiguous turns; its dummy Chroma index writes only stub data and is **not** proof that production indexing works. Contract additions must be reflected in both app config classes, K8s ConfigMap, tests, and the downstream consuming service.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-08-interface-contracts-md"></a>

## Frozen interface contracts and integration map (G0)


**Source:** examined starter files; additions noted as proposals, not preexisting behavior. Contract changes must be reviewed by both developers and documented in an ADR.

### HTTP API
`POST /api/ask`, `Content-Type: application/json`, `{"question":"..."}`; 3–500 characters, otherwise HTTP 422 (Pydantic). Response model `api/app/schemas.py::AskResponse`:
```json
{
  "request_id": "r-123",
  "answer": "Evidence-grounded answer or abstention",
  "citations": [{"source":"doc.pdf","section":"5.4","page":12}],
  "answered_from_context": true,
  "confidence": "medium",
  "retrieved": [{"chunk_id":"doc-5-4-001","source":"doc.pdf","section":"5.4","page":12,"score":0.87}],
  "provider": "ollama"
}
```
Values above are **shape examples, not real answer/evaluation evidence**. `reasoning` belongs only in internal `Answer` and is NEVER returned. Citation key `(source,section,page)` must identify one of the response's retrieved records for that question; if not, reject it and retry/fallback. `X-Request-ID` optionally supplied; echoed and logged.

Other endpoints: `GET /healthz` process-only -> HTTP 200; `GET /readyz` -> 200 if Chroma reachable, **non-empty active collection**, pinned model/dim agree and Redis reachable, otherwise HTTP 503 with non-secret diagnostics; `GET /metrics` Prometheus text.

### Python interfaces
| Producer -> consumer | Frozen signature | Responsibilities |
|---|---|---|
| Retriever -> answer service | `retrieve(question: str, k: int) -> list[Passage]` | sorted highest similarity first, `score=1-distance`, old-version filter |
| LLM -> answer service | `generate(question: str, passages: list[Passage]) -> Answer` | JSON-schema enforcement + Pydantic validation; return `Answer` |
| Indexer extractor -> cleaner | `extract(path, doc_version, superseded) -> Document` | Page list with source, 1-based page, OCR flag |
| Cleaner -> chunker | `clean(doc: Document) -> Document` | preserve section/page alignment |
| Chunker -> embedder | `chunk(doc, size, overlap) -> list[Chunk]` | stable IDs and metadata fields |
| Embedder -> store | `embed(texts, settings) -> list[list[float]]` | one vector per chunk, matching pinned model |
| Store -> runner | `store(chunks, vectors, settings) -> int` | only writer, metadata + dimension recorded |
| Eval -> API | `POST /api/ask` returning `AskResponse` | live quality scoring |

### Required data metadata
`Chunk`: `id`, `text`, `source`, `section`, `page`, `doc_version`, `superseded`. `.metadata()` includes at least the five required keys; Chroma collection metadata includes `embed_model` and vector `dimension`. Chroma supports only primitive metadata values. Preserve 1-based `page` and source filenames unchanged across manifest, vectors, golden labels and citations. Where a section spans pages, choose the page containing the start of the cited evidence and document that rule.

### Runtime configuration
| Key | Owner / expected source | Semantic contract |
|---|---|---|
| `EMBED_MODEL` | shared ConfigMap; API + Job | MUST be identical and checked against collection |
| `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION` | shared ConfigMap | Chroma cluster endpoint and base name |
| `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_URL`, `TEMPERATURE` | ConfigMap | selected provider, generation settings |
| `LLM_API_KEY` | Secret **only** | hosted mode credential |
| `RETRIEVER`, `TOP_K` | ConfigMap | stub/chroma, top count |
| `CHUNK_SIZE`, `CHUNK_OVERLAP`, `CORPUS_DIR` | ConfigMap / Job | measured chunk settings + accessible files |
| `RELEVANCE_FLOOR`, `CACHE_THRESHOLD`, `REDIS_URL` | **new proposed keys** | implement in `api/app/config.py`, manifests and tests |
| `CHROMA_REGISTRY_COLLECTION` | **safe-reindex design (consolidated in ADR 0003) proposal** | Chroma control collection stores active pointer; API reads it; Redis cache is generation-scoped |

### Provider and score contracts
The current Protocol is synchronous. Network SDK timeouts and errors must return predictable application fallbacks; never leak model JSON errors as HTTP 500. The actual returned `provider` string comes from provider.name (`ollama` for both local Ollama modes in starter); don't invent an incompatible enum. Normalize cosine distance `1 - d` consistently, including relevance and cache cosine scores; document threshold direction (higher means more relevant).

### Cache and follow-ups
Cache key must include Chroma active generation, pinned model, selected provider and relevant question context to prevent cross-version answers. The API does not currently have session IDs; conservatively **do not cache follow-up-like requests** rather than manufacturing session state. Never cache abstentions, out-of-scope answers, malformed outputs or citation-validation failures.

### Frozen file ownership until G3
A owns `indexer/pipeline/*`, `api/app/services/*`, `api/app/retrieval/*`, `api/app/providers/*`, `eval/*`, `corpus/*`.
B owns `k8s/*`, `.github/workflows/*`, Dockerfiles, `ui/*`, and `api/app/routes/health.py`, `api/app/routes/metrics.py`, with coordination for metrics instrumentation.
Shared: `api/app/schemas.py`, `api/app/config.py`, `api/app/main.py`, `README.md`, `docs/*`, tests crossing directories. See `INTERFACE-CONTRACTS.md`.

---

<a id="merged-docs-developers-contract-freeze-md"></a>

## G0 contract-freeze sheet


**Freeze before parallel branch work.** Verify from actual source: `POST /api/ask` with `AskRequest(question 3..500)` -> `AskResponse`; no `reasoning` exposed, retrieved score higher-is-better; `Retriever.retrieve(question,k)`, `LLMProvider.generate(question,passages)`, indexer five stage signatures from STARTER.md; namespace `rahbar`, four internal service names and ports; same ConfigMap `EMBED_MODEL` for API+Job. Confirm optional extension fields before changing tests.

| Area | Initial authoritative source | Proposed addition | A approves | B approves |
|---|---|---|---|---|
| HTTP schema | `api/app/schemas.py` | optional `cached` only with explicit compatibility check | PENDING | PENDING |
| Env config | `api/app/config.py`, `indexer/pipeline/config.py` | relevance floor, Redis URL, threshold and active index pointer behavior | PENDING | PENDING |
| Index metadata | `indexer/pipeline/models.py` | generation and vector dimension at collection level | PENDING | PENDING |
| Readiness | `api/app/routes/health.py` | active collection/Redis and pin checks | PENDING | PENDING |
| Corpus delivery | `corpus/fetch.py`, `run.py::discover` | mount/init fetch strategy | PENDING | PENDING |
| CI fixtures | fixture docs & golden | deterministic query/index embedding in fixture mode | PENDING | PENDING |

### Change protocol
Author proposes one PR with contract diff and adapter tests, recipient signs off, then both update their code. Do not break compiler/lint to temporarily unblock an agent. Sync actual env key names to Kubernetes ConfigMap and docs.

---

<a id="merged-docs-specs-api-ui-md"></a>

## Implementation spec — Api Ui


**Owner:** B. **WBS:** T11,T20. **Primary paths:** `api/app/main.py; api/app/routes/*; ui/index.html; ui/nginx.conf; ui/Dockerfile`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Existing UI
`ui/index.html` is already a chat client. `ui/nginx.conf` listens on 8080 and serves static content. Ingress sends `/` to UI and `/api` to FastAPI unchanged. Do not create another API proxy inside nginx or rewrite `/api/ask` path; use same host. `make dev` can serve the UI through FastAPI in stub mode, but Kubernetes uses the separate UI Deployment.

### Health contracts
`/healthz`: always process-only 200 if app alive, no Redis/Chroma/LLM calls. `/readyz`: 200 only when Chroma reachable, active collection exists and nonempty, Redis reachable, and metadata embed_model+dimension match configured embedding implementation. Return 503 and dependency-specific diagnostics otherwise; readiness removes pod from endpoints, should not kill/restart it.

### API output
Request 3–500 characters; maintain `AskResponse`, X-Request-ID header, JSON structured log. UI renders citations from returned fields, absence state when `answered_from_context=false`, error and loading states. `cached` is optional proposed extension; if added, coordinate contract and tests before deployment.

### Tests
Browser: ask answerable and absent question, citations and loading, intentionally malformed input; curl through Host header; 3-API endpoint count; health at dependency fail; UI pod read-only root uses tmpfs/emptyDir; accessibility basic keyboard and small screen check, no unnecessary redesign.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

