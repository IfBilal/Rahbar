# 03 — Gap analysis: RAHBAR today vs what A3 needs

Read from the code in this repository (branch `main`, 157 commits). File references are to the real files; function names are real. **Nothing here is speculation about code you have not read** — but re-check a reference before you edit around it, the files move.

---

## 1. What RAHBAR already gives you (reuse, do not rebuild)

| Capability | Where | Why it matters for A3 |
|---|---|---|
| 3-stage ingest: extract (PDF text, tables, OCR; HTML; MD; TXT) → clean → structure-aware chunk | `indexer/pipeline/extract.py`, `clean.py`, `chunk.py` | Part A inserts *verify* between extract and chunk; extraction already reports per-page OCR flags |
| Chunk metadata `source, section, page, doc_version, superseded` and stable id `chunk_id(source, doc_version, ordinal, text)` with an 8-hex text digest | `indexer/pipeline/models.py`, `chunk.py:182` | Superseded flag is the retrieval-side hook for A2-04; the digest enables chunk-level reuse |
| Embed with a pinned model, batched, retried, vectors validated | `indexer/pipeline/embed.py` | Reused for near-duplicate embeddings and the candidate-model build |
| Store with **generation collections + registry pointer** `<base>-registry` | `indexer/pipeline/store.py` | The registry idea is reused (see §3 C-01); the *rebuild-every-run* behaviour is not |
| The embedding **pin** (`EMBED_MODEL` recorded in collection metadata; API refuses readiness on mismatch) | `store.py`, `api/app/retrieval/chroma.py::pin_problem`, `routes/health.py` | Protects the release: a candidate with another embed model cannot silently serve the live collection |
| Chroma retriever that follows the registry, superseded filter, exact-term assist, table assist | `api/app/retrieval/chroma.py` | The component under test in Part B; returns scores `1 − cosine distance` |
| 8-step query pipeline, relevance floor, schema-validated `Answer`, citation guard, retry-once, fallbacks | `api/app/services/answer.py`, `guard.py` | End-to-end metrics (abstention, citation validity) read off its output |
| Prompt delimiting and **injection neutralisation** `neutralise()` | `api/app/services/prompt.py` | The A2 injection defence that D4 must log |
| Semantic cache in Redis, scope keyed by generation/model/provider/knobs | `api/app/services/cache.py`, `answer.py::cache_scope` | Must be **bypassed** by the suite; collides with the candidate (§3 C-08) |
| JSON logs to stdout with request id; Prometheus metrics (retrieval/generation latency, cache, abstentions, fallbacks, tokens) | `api/app/logjson.py`, `routes/metrics.py` | Starting point of Part D; **not** a trace |
| `AskResponse.retrieved` lists every retrieved chunk with score | `api/app/schemas.py` | Component metrics can be computed from it; but see §3 C-07 (speed) |
| Golden-set runner with gate and baseline (YAML, 19 questions; recall@3/5, citation validity, abstention) | `eval/run_eval.py`, `eval/golden.yaml`, `eval/baseline.json` | Source of ~19 human-written questions; the *gate idea* — but hard-coded constants, YAML, section-level labels |
| K8s: namespace `rahbar`, API Deployment ×3 + HPA, Chroma StatefulSet (+PVC), Redis (+PVC), indexer Job + weekly CronJob `reindex`, 4 Services, Ingress, default-deny NetworkPolicy, ServiceAccounts, probes | `k8s/base/*` | Part F is "extend", not "create" |
| Images: `api`, `indexer`, `ui`; overlays dev/prod/ci/incluster; CI + CD workflows | `*/Dockerfile`, `k8s/overlays/*`, `.github/workflows` | A3 adds one image (the RAGOps/eval image) |
| Boundary tests: the API never writes Chroma; API startup does no indexing | `tests/test_boundaries.py` | Single-writer proof for F2-03 — extend it |
| Evidence habit: `docs/evidence/*`, `scripts/*-experiment*.sh` | repo | Same habit for `docs/a3-evidence/` |

---

## 2. What A3 needs that does not exist yet

| Need (requirement IDs) | Exists? | Size |
|---|---|---|
| Verification stage with four checks and a per-run report (A1-*) | no | M |
| Quarantine folder, archive, restore, ledger, durable data lake on a PVC (A1-07, A2-*, F1-04) | no — corpus lives in an `emptyDir` fetched at Job start | L |
| **Incremental** update: zero re-embeds on unchanged corpus; doc-scoped replace/delete (A2-01…03) | no — `store()` builds a whole new generation every run | L |
| Batch B (≥ 10 planted-problem documents) (A-B-*) | no | M |
| Golden set in JSONL with `(doc,page)` truth, origins, reviews, validator (B-G-*) | partly (19 YAML questions, `(source,section)` labels) | M |
| Module-level embedding tests (B-M-*) | no | S |
| Component-level metrics incl. **MRR and nDCG@5**, noise test (B-C-*) | recall only | M |
| Faithfulness + LLM judge + hand-label agreement; latency p50/p95 (B-E-*) | no (citation validity and abstention exist) | M |
| Seeds, run-twice, diff (B-S-01); one-command suite with timestamped result and summary table (B-1C-01) | no | M |
| Gate from a config file, exit 0/1, comparing two result files (C2-*) | partly — thresholds are constants in `run_eval.py` | S |
| Candidate pipeline + second Deployment/Service/collection (F3-*) | no | M |
| Trace record (≈ 20 fields), trace tool, summary script, rail logging (D1-*…D5) | no — only request logs and Prometheus | L |
| Coverage tool, live-query log, drift run, exit code (E-*) | no | M |
| Evaluation Job, ingestion Job on a PVC, gate ConfigMap, CronJob, PVCs, network rules (F2-*, F4-*, F5-*) | partly | M |
| Report, README per part, `k8s/README.md`, screenshots | no | L |

---

## 3. Collisions — where A3 contradicts a design decision made in A2

Each collision names the problem, the consequence if ignored, and the resolution adopted (see decision IDs in [04](04-ARCHITECTURE.md) §10). These are the places where a naive "add a feature" approach breaks something that worked.

### C-01 · Rebuild-per-run generations vs *incremental* updates  *(decision D-03)*
* **A2:** `store()` creates `<base>-g<generation>`, writes **every** chunk, publishes by moving the registry pointer, deletes older generations (`store.py`). `run_pipeline` re-extracts, re-chunks and **re-embeds the entire corpus on every run**. Brilliant for atomic swaps; useless for A2-01 ("unchanged corpus must embed zero chunks").
* **If ignored:** the second ingestion run re-embeds ~532 chunks — a direct fail of A2-01 and a 4–13-minute run on CPU.
* **Resolution:** the live collection is updated **in place** (upsert/delete by `doc_id`), driven by the ledger. The registry stays (API follows it), but its `generation` becomes a **data revision counter** bumped on every committed change so the API's cache scope still invalidates. The full-rebuild path survives, used only to build a *candidate* collection from the lake (an embedding or chunking change legitimately re-embeds everything). Spike first: confirm Chroma 1.0.12 behaviour for `upsert`, `delete(where=…)`, `update(metadatas=…)` and registry `modify()` — task T05.

### C-02 · Corpus lives in an `emptyDir` fetched at Job start  *(D-02)*
* **A2:** the indexer Job's init container downloads the public corpus into `/work` (an `emptyDir`) and diffs against `corpus/MANIFEST.md`. Nothing survives the pod.
* **If ignored:** no data lake, no quarantine, no archive, no ledger across runs → F1-04 fails, incremental detection impossible.
* **Resolution:** a PVC `ragops-data` holds `inbox/`, `lake/`, `archive/`, `quarantine/`, `ledger/`, `reports/`. The init container becomes a **seed step** that only runs when the inbox is empty (A2's fetch + manifest diff stays as the way to *populate* the inbox the first time). New documents arrive by dropping files into the inbox ([10](10-KUBERNETES.md) §8).

### C-03 · Metadata comes from a hand-written index  *(D-06)*
* **A2:** `discover()` reads `corpus/raw/_index.json` (written by `fetch.py`) or Markdown front matter. Metadata is **trusted input**.
* **If ignored:** (1) completeness (A1-04) is meaningless — the catalog is always complete; (2) the demo's **unseen** batch has no catalog row and the Job either crashes or indexes garbage.
* **Resolution:** a resolution order *catalog > embedded (PDF info, front matter, HTML meta) > derived (first heading, date regex in text)*; completeness fails only when a required field cannot be resolved by any route. Page count is always computed from the extraction, never declared.

### C-04 · Test labels are `(source, section)`; A3 wants `(document, page)`
* **A2:** `eval/run_eval.py::_matches` compares source and a *section substring*; the golden YAML has no page numbers.
* **If ignored:** B-G-02 ("ground-truth document and page") unmet; MRR/nDCG definitions ambiguous.
* **Resolution:** new `golden.jsonl` with `gold:[{doc,page}]`; the 19 A2 questions are migrated by looking up the page of the chunk that holds the answer (human step, committed as such). Chunk-to-gold match = same `doc_id`/source and `page ∈ gold.pages`. The A2 YAML stays for the A2 CI gate until the migration is complete.

### C-05 · One end-to-end call is a minutes-long LLM call  *(D-07)*
* **A2:** every eval question goes through `POST /api/ask` → Ollama (`llama3.2:3b` on CPU; the Deployment has `terminationGracePeriodSeconds: 240` precisely because answers take up to ~190 s).
* **If ignored:** component-level metrics (retrieval-only) cost the same as end-to-end; noise test (+typos) and the run-twice requirement multiply it: 30 questions × 2 pipelines × 2 runs × (clean + noisy) ≈ hundreds of LLM calls — **hours**, per experiment.
* **Resolution:** a **retrieval-only endpoint** `POST /api/retrieve` (no generation) for module/component tests and the noise test; the LLM is called only for the end-to-end level, and only on the questions that need it (answerable + unanswerable; the noisy variant skips generation). Estimate and budget in [06](06-OFFLINE-TESTING.md) §12.

### C-06 · Determinism knobs do not exist
* **A2:** temperature comes from the ConfigMap (0.2); there is no seed; the cache can answer without calling the model.
* **If ignored:** "fix random seeds" (B-S-01) cannot be met; run 2 may be served from run 1's cache (A2 hit exactly this: `docs/evidence/eval-run2-cache-hits.json`).
* **Resolution:** request headers honoured only when `EVAL_HEADERS_ENABLED=true`: `X-Eval-Bypass-Cache`, `X-Eval-Seed`, `X-Eval-Temperature`, `X-Eval-Run`. They are recorded in the trace so a seeded run is provably seeded.

### C-07 · The release identity lives in a shared ConfigMap  *(D-11)*
* **A2:** API and indexer read `EMBED_MODEL` and `CHROMA_COLLECTION` from the **one** ConfigMap `rahbar-config`; `tests/test_manifests.py` asserts that the API's `envFrom` references it and that the Deployment has **no** `EMBED_MODEL` in `env`.
* **If ignored:** `kubectl rollout undo` restores only the Deployment's *pod template*. If the release changes a ConfigMap value, undo reverts the template but **not** the config → the "previous" pods read the *new* collection and embedding. F3-05 ("after the undo, a new trace must show the previous collection and embedding version") would be false, and you would not notice until the demo.
* **Resolution:** the release-scoped values (`CHROMA_COLLECTION`, `EMBED_MODEL`, `EMBED_VERSION`, `RELEASE_ID`, `TOP_K`, prompt version) are explicit `env:` entries **in the Deployment pod template** (they override `envFrom`). A release = `kubectl set env`/`apply` on the Deployment → a new ReplicaSet → `rollout undo` restores the previous values exactly. The A2 manifest test must be updated deliberately and its rationale recorded (the pin is still enforced at runtime by readiness, so the safety property is unchanged).

### C-08 · The semantic cache thrashes when two API versions share Redis
* **A2:** `SemanticCache.observe(scope)` deletes **every** `rahbar:cache:*:entries` key whose scope differs from *this* pod's scope.
* **If ignored:** live (scope X) and candidate (scope Y) delete each other's entries on every request; the candidate also pollutes the live cache namespace.
* **Resolution:** the candidate runs with `REDIS_URL` empty (cache off — the suite bypasses the cache anyway). At release time the live scope changes (new generation/embed model) and A2's own invalidation purges stale entries. Add a test.

### C-09 · The API cannot write traces to a durable place
* **A2:** the API pods have a read-only root filesystem and only a `/tmp` `emptyDir`; logs go to stdout only (deliberately: "a pod's filesystem is ephemeral").
* **If ignored:** F4-02 ("also written to a volume") unmet; report scripts have nothing to read after a pod restart.
* **Resolution:** mount the PVC `ragops-traces` read-write at `/traces` in every API/candidate pod; each pod appends to its own file `/traces/<pod-name>.jsonl` (no cross-pod interleaving, no locking). Same-node assumption for `ReadWriteOnce` on minikube is documented ([10](10-KUBERNETES.md) §3).

### C-10 · A2 logging policy forbids the user's question; A3's trace requires it
* **A2:** `_log_turn` never logs the question text, passage text or reasoning (`answer.py`).
* **A3:** D1 requires "user query … response … prompt".
* **Resolution:** a **separate, access-limited trace stream** (stdout line tagged `"type":"trace"` + PVC file) carries the query; the ordinary request log keeps its A2 policy. Document the reversal and the mitigation (retention limit, no credentials, queries are the group's own test queries, not real users) in [08](08-OBSERVABILITY-TRACING.md) §10.

### C-11 · NetworkPolicy has no place for the new pods
* **A2:** default-deny plus per-app allow rules selecting `app: api|ui|chroma|redis|indexer`.
* **If ignored:** the evaluation Job cannot reach the API or Ollama; the candidate Deployment cannot reach Chroma; the new PVC loader pod would be denied even DNS.
* **Resolution:** new labels `app: ragops-eval`, `app: api-candidate`, `app: ragops-loader`; extra policies listed in [10](10-KUBERNETES.md) §7. The UI→Chroma denial and Redis API-only remain.

### C-12 · `retrieved` lists the top-k, but the answer used fewer
* **A2:** `MAX_CONTEXT_PASSAGES=3` of `TOP_K=5` are sent to the model. The trace must distinguish *retrieved* (5) from *in the prompt* (≤ 3) — `reranked_order` and `prompt.chunk_ids`.
* **Resolution:** trace schema carries both ([14](14-INTERFACE-CONTRACTS.md) §6).

### C-13 · CI cannot run the new Jobs against real documents
* **A2:** `ci.yml`'s `e2e-eval` uses a 3-document fixture corpus and a deterministic embedder.
* **Resolution:** A3's heavy runs (full suite, Batch B, model comparison) are **local-cluster** activities (Ollama is on the laptop). CI gets only unit tests for the new code, a `kustomize | kubeconform` pass on the new manifests, and optionally a fixture-sized ingest check. Do not try to run the full suite in GitHub Actions.

### C-14 · Chroma has no authentication
* A read-only client cannot be enforced by Chroma itself. "Only the Job writes" is therefore enforced by **code boundary tests, a single-writer lock, `concurrencyPolicy: Forbid`, and network reachability limited to the three known clients** — not by Chroma permissions. Say this plainly in short answer (f); do not claim Kubernetes makes the vector store read-only.

---

## 4. Contracts you may touch, and contracts you may not

| Contract | A2 status | A3 change |
|---|---|---|
| `POST /api/ask` request/response (`AskRequest`, `AskResponse`) | frozen (the UI and `run_eval.py` rely on it) | **Additive only:** optional response fields (e.g., `trace_id`, `release_id`) are allowed; do not rename or remove. |
| `Answer` schema | frozen | unchanged |
| `Retriever.retrieve(question, k)` | shared interface | add optional richer return via a *new* method `retrieve_detailed()`; keep `retrieve()` |
| `Passage` / `RetrievedRef` | shared | add optional `doc_id`, `doc_version`, `revision` fields (defaults keep the stub valid) |
| Chunk metadata keys `source, section, page, doc_version, superseded` | required by the A2 rubric | keep all five; **add** `doc_id`, `status`, `content_sha`, `ingest_run` |
| `eval/results.json` / `baseline.json` (A2) | committed, used by the A2 CI gate | leave untouched; A3 writes to `eval/results/` |

---

## 5. Risks that come specifically from the A2 baseline

| Risk | Likelihood | Mitigation |
|---|---|---|
| Chroma 1.0.12 in-place `modify()` of the registry metadata or `update(metadatas)` behaves differently than assumed | medium | spike task T05 before building on it ([11](11-IMPLEMENTATION-PLAN.md)) |
| CPU LLM makes full end-to-end runs too slow to repeat | high | `/api/retrieve`; run end-to-end only where needed; budget table in [06](06-OFFLINE-TESTING.md) §12; keep generation `num_predict` bounded |
| Changing `test_manifests.py` assertions silently weakens an A2 guarantee | medium | change the *assertion*, not delete it; keep the runtime pin test; record in the PR |
| API pods multiply trace files (HPA up to 8) | low | per-pod file names; the summary tool globs `/traces/*.jsonl` |
| Ollama on the host is the only embedding service; a candidate embedding model must be pulled | certain | `ollama pull <model>` is a documented prerequisite; the NetworkPolicy already allows the host IP on 11434 |
| Documents arriving at the demo are PDFs the extractor handles badly | medium | rehearse with 3 unfamiliar documents; verification must fail *gracefully* (quarantine with a reason), never crash the Job |
