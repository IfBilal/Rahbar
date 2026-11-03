# Nine implementation phases: developer A/B parallel playbook

Each of the nine phases below includes the original concrete tasks, parallel work and definition-of-done requirements. To avoid dependency confusion, **phase numbers describe a coarse working sequence, not a requirement that every phase completes before the next begins**. Use the task DAG in `CRITICAL-PATH.md` to decide what can run concurrently. Some tasks overlap phases on purpose.

| Phase | Work and gate | A | B |
|---|---|---|---|
| 00 | Repo/bootstrap/contracts — G0 | inspect schemas + golden plan | git protection + baseline |
| 01 | Corpus and container foundations — G1 | sources, version pair, golden | Dockerfiles |
| 02 | Stub-backed Kubernetes slice — G2 | prepare extraction tests | full dummy Job / UI / Ingress |
| 03 | OCR + readiness + platform hardening — G3 | extract/clean/chunk | probes, routes, security |
| 04 | Real Chroma indexing and retrieval — G4 | embed/store/filter | CI skeleton and K8s path |
| 05 | Generation, caching and evaluation — G5 | provider, citations, Redis, eval | e2e harness prep |
| 06 | CI/CD — G6 | fixture test contract | CI e2e, SHA-publishing CD |
| 07 | Failure and operational validation — G7 | tuning, four fault tests | scaling, pod delete, rollback |
| 08 | Final release — G8 | notes and evidence | final workflows and checker |

**Time:** target November 3–8, 2026 (PKT); the deadline is absolute, not an excuse to falsify an unrun check.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-phases-readme-md"></a>

## Development phases — action sequence and gates


Read these **in order**. Each phase has task IDs, owners, hard dependencies, exact target paths, acceptance tests and an evidence checklist. Tasks inside one phase may run in parallel where the WBS allows; don't block independent A and B work unnecessarily. A phase is complete only after its gate is truly verified.

| Phase | Gate | Objective | Detailed guide |
|---|---|---|---|
| 00 | G0 | Starter audit and contract freeze | [Phase 00 — Bootstrap and contracts](#merged-docs-phases-00-bootstrap-and-contracts-md) |
| 01 | G1 | Verified corpus and Docker foundation | [Phase 01 — Corpus and Docker foundation](#merged-docs-phases-01-corpus-selection-and-container-foundation-md) |
| 02 | G2 | Stub UI/API and dummy indexed cluster | [Phase 02 — Stub Kubernetes deployment](#merged-docs-phases-02-stub-kubernetes-vertical-slice-md) |
| 03 | G3 | Extraction and readiness/security | [Phase 03 — OCR and platform hardening](#merged-docs-phases-03-ocr-and-platform-hardening-md) |
| 04 | G4 | Live Chroma collection and versioned retrieval | [Phase 04 — Real indexing and retrieval](#merged-docs-phases-04-real-indexing-and-retrieval-md) |
| 05 | G5 | Grounded output, safe cache, evaluator | [Phase 05 — Generation, caching and evaluation](#merged-docs-phases-05-generation-cache-and-evaluation-md) |
| 06 | G6 | Full CI/CD and deliberate failing PR | [Phase 06 — CI/CD integration](#merged-docs-phases-06-ci-cd-integration-md) |
| 07 | G7 | Retrieval tuning and Kubernetes proof | [Phase 07 — Verification and fault experiments](#merged-docs-phases-07-verification-and-failure-experiments-md) |
| 08 | G8 | Clean clone, checker, final links | [Phase 08 — Release and submission](#merged-docs-phases-08-release-and-submission-md) |

### Rules
- Follow `CRITICAL-PATH.md` for finish-to-start dependencies and `TWO-DEVELOPER-PLAN.md` for non-overlapping owners.
- `G2` proves a stub deployment, **not** real RAG; `G4` is the first real indexed retrieval gate.
- A may write unit code while B provisions minikube; call a task integrated only after producer-consumer verification.
- Do not record model scores, cluster tests, CI status or PDF accessibility as true until actually run.

---

<a id="merged-docs-phases-00-bootstrap-and-contracts-md"></a>

## Phase 00 — Bootstrap and contracts


**Gate:** G0: starter tests run and source contracts agreed; repo branch policy recorded. **Prerequisites:** None; supplied starter ZIP and assignment PDF. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T01 — Unpack starter, run baseline, initialize repo and dev branch

- **Owner / estimate:** Both / 2 focused h.
- **Blocking dependencies:** none; do not claim integrated before these gates pass.
- **Allowed output paths:** `README.md; AGENTS.md`.
- **Execution goal:** Unzip instructor starter, capture `git status`, `make test` and `make lint` output before edits; initialize git history, ensure `.gitignore` excludes downloaded PDFs and secrets, establish `dev` and main protection.
- **Task-specific exit criterion:** Both can reproduce a clean baseline, know the stub limitations, and show commit hash + failed/passed output as observed.
- **Minimum acceptance:** make install; make test; make lint. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** baseline command log; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T02 — Freeze public contracts, roles, ADR conventions

- **Owner / estimate:** Both / 2 focused h.
- **Blocking dependencies:** T01; do not claim integrated before these gates pass.
- **Allowed output paths:** `INTERFACE-CONTRACTS.md; TWO-DEVELOPER-PLAN.md`.
- **Execution goal:** Inspect `AskRequest`, `Answer`, `AskResponse`, `Passage`, `Retriever`/`LLMProvider` Protocols, `Chunk` data model, both config classes and Makefile. Freeze request/response keys, service ports, collection semantics and new env keys with two approvals.
- **Task-specific exit criterion:** No ambiguous API shape or shared-file ownership; contract fixtures and signed review comment exist.
- **Minimum acceptance:** review schemas and source paths. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** approved G0 contract; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   make install
   make test
   make lint
   git switch -c dev  # only if not created by initial setup
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Do not claim starter unit tests validate real RAG; they cover stubs. Protect main before direct writes.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G0: starter tests run and source contracts agreed; repo branch policy recorded
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-01-corpus-selection-and-container-foundation-md"></a>

## Phase 01 — Corpus selection and container foundation


**Gate:** G1: corpus evidence/labels approved; all three Docker images build. **Prerequisites:** G0 contracts and owner paths frozen. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T03 — Verify corpus URLs, versions, scans, manifest

- **Owner / estimate:** A / 4 focused h.
- **Blocking dependencies:** T02; do not claim integrated before these gates pass.
- **Allowed output paths:** `corpus/sources.yaml; corpus/MANIFEST.md; CORPUS-PLAN.md`.
- **Execution goal:** Select and independently download public/owned 6+ PDFs totalling 40+ pages; verify real revision pair, image-only scan, table, definitions, absent topic and exact terms. Run provided `corpus/fetch.py`, verify manifest hashes and page counts; mark superseded versions in `_index.json`.
- **Task-specific exit criterion:** `corpus/MANIFEST.md` is reproducible, documents verified not assumed, `CORPUS-PLAN.md` maps all seven properties.
- **Minimum acceptance:** fetch --verify; pdffonts; page counts. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** approved documents and source metadata; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T04 — Build minimal API/UI/indexer Dockerfiles

- **Owner / estimate:** B / 4 focused h.
- **Blocking dependencies:** T02; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/Dockerfile; indexer/Dockerfile; ui/Dockerfile`.
- **Execution goal:** Create `api/Dockerfile`, `indexer/Dockerfile`, `ui/Dockerfile` and `.dockerignore` files with pinned runtime dependencies, non-root users, read-only writable paths, minimal layers, correct commands and ports. Build all three locally and smoke with stubs.
- **Task-specific exit criterion:** Docker builds succeed; API serves 8000, UI 8080, indexer runs as CLI; no runtime root requirement.
- **Minimum acceptance:** docker build x3; nonroot inspect. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** images with pinned tags; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T07 — Create true 15-question golden set before tuning

- **Owner / estimate:** A / 4 focused h.
- **Blocking dependencies:** T03; do not claim integrated before these gates pass.
- **Allowed output paths:** `eval/golden.yaml; CORPUS-PLAN.md`.
- **Execution goal:** Before querying or tuning, read source clauses and author ≥15 golden questions: 8 ordinary, 2 version-sensitive, 2 exact, 2 must-abstain, 1 injection, with independently verified `(source,section)` labels and expected facts. Preserve a separate fixture golden set.
- **Task-specific exit criterion:** Golden labels are pre-registered, reviewers can find actual source sections, absent question lacks corresponding policy.
- **Minimum acceptance:** validate counts, sources and sections. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** frozen labels to evaluator; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   cp corpus/sources.example.yaml corpus/sources.yaml
   make fetch
   python corpus/fetch.py --verify
   docker build -t rahbar-api:dev api
   docker build -t rahbar-indexer:dev indexer
   docker build -t rahbar-ui:dev ui
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Source URL may fail; a guessed policy revision pair invalidates the core corpus requirement. Do not commit downloaded PDFs.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G1: corpus evidence/labels approved; all three Docker images build
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-02-stub-kubernetes-vertical-slice-md"></a>

## Phase 02 — Stub Kubernetes vertical slice


**Gate:** G2: dummy index Job succeeds; stub UI/API reachable through Ingress; PVCs bound. **Prerequisites:** Docker images build, base ConfigMap, Chroma/Redis persistence and minikube network prerequisites. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T05 — K8s namespace, services, config, Chroma/Redis PVCs, Jobs

- **Owner / estimate:** B / 6 focused h.
- **Blocking dependencies:** T04; do not claim integrated before these gates pass.
- **Allowed output paths:** `k8s/base/*; overlays/dev/*`.
- **Execution goal:** Create namespace, ConfigMap, four ClusterIP Services, API/UI Deployments, Chroma StatefulSet with `volumeClaimTemplates`, Redis Deployment+PVC, one-shot Job, weekly CronJob, Ingress and Kustomize base/dev overlay. Set restart policy, replicas, rolling policy, probes, resources and `imagePullPolicy` correctly.
- **Task-specific exit criterion:** `kustomize build` renders, schema validation passes, persistent workloads remain ClusterIP-only and namespace is `rahbar`.
- **Minimum acceptance:** kustomize build; kubeconform. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** manifests baseline; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T06 — Boot minikube + dummy index + stub ingress

- **Owner / estimate:** B / 4 focused h.
- **Blocking dependencies:** T05; do not claim integrated before these gates pass.
- **Allowed output paths:** `k8s/overlays/dev/*; docs/evidence/*`.
- **Execution goal:** Start Calico minikube with ingress and metrics-server, load local images, apply overlays in dependency order, run `python -m pipeline.run --dummy` via Job while pinning `EMBED_MODEL=dummy-768`, and test `/api/ask` through Ingress.
- **Task-specific exit criterion:** Dummy Job reaches Complete, Chroma/PVC persist, three API pods have ready endpoints, UI route calls stub JSON.
- **Minimum acceptance:** kubectl logs job; ingress curl. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G2 cluster URL and logs; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   make cluster
   make images
   make apply
   kubectl get pods,svc,pvc,job -n rahbar
   kubectl logs job/indexer -n rahbar  # replace name from kubectl get jobs
   make ask Q='Is RAHBAR connected?'
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Initially `/readyz` is a lie in starter; implement true readiness. In dummy mode pin must be `dummy-768`, not the production embed model.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G2: dummy index Job succeeds; stub UI/API reachable through Ingress; PVCs bound
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-03-ocr-and-platform-hardening-md"></a>

## Phase 03 — OCR and platform hardening


**Gate:** G3: extracted sample pages and chunks inspectable; health/readiness/security UI paths verified. **Prerequisites:** G2 reachable stub cluster for platform tests; independently A can run document unit tests. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T08 — Implement extraction incl OCR and table samples

- **Owner / estimate:** A / 5 focused h.
- **Blocking dependencies:** T03; do not claim integrated before these gates pass.
- **Allowed output paths:** `indexer/pipeline/extract.py; indexer/tests/*`.
- **Execution goal:** Implement `extract.py` handling PDF/MD/HTML/TXT, one-based pages and per-page OCR detection; use Tesseract or a justified alternative for scanned PDF and log irrecoverable pages. Preserve tables/section markers and record a real pre/post extraction sample.
- **Task-specific exit criterion:** Unit tests cover normal PDF, textless scan, corrupt PDF and table; OCR gains actual text without changing source identity.
- **Minimum acceptance:** unit scanned pdf + html + md. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** pages with OCR flags; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T09 — Implement cleaning, structure-aware chunking

- **Owner / estimate:** A / 5 focused h.
- **Blocking dependencies:** T08; do not claim integrated before these gates pass.
- **Allowed output paths:** `indexer/pipeline/clean.py; chunk.py`.
- **Execution goal:** Implement cleaning while keeping headings/numbers/tables, then deterministic structure-aware chunking by section→paragraph→sentence with overlap and stable IDs/metadata. Validate size units, boundary cases and storage amplification; expose configuration for three experiments.
- **Task-specific exit criterion:** Chunks contain all five mandated metadata keys, overlap works within section, empty page and long clause are handled.
- **Minimum acceptance:** test section/page/overlap, 3 trials. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** stable chunks to store; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T11 — Implement API readiness and embedding pin

- **Owner / estimate:** B / 4 focused h.
- **Blocking dependencies:** T06; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/app/routes/health.py; main.py; k8s/base/*`.
- **Execution goal:** Implement `/readyz` checks for Chroma reachability, nonempty active collection, matching `EMBED_MODEL` and observed dimension, and Redis ping. Keep `/healthz` dependency-free; wire correct startup/liveness/readiness HTTP probes.
- **Task-specific exit criterion:** Initial empty collection -> 503; pin mismatch -> 503 and named logs; process liveness stays 200 during Chroma/Redis outage.
- **Minimum acceptance:** empty/index mismatch + redis-down. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** probe contract validated; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T20 — UI through ingress, read-only nginx, route verification

- **Owner / estimate:** B / 3 focused h.
- **Blocking dependencies:** T06; do not claim integrated before these gates pass.
- **Allowed output paths:** `ui/Dockerfile; ui/nginx.conf; k8s/base/ingress*`.
- **Execution goal:** Use given `ui/index.html` and `nginx.conf` with non-root Dockerfile, read-only root and `/tmp` emptyDir. Route `/api` to FastAPI and `/` to UI on same Ingress without nginx proxy duplication.
- **Task-specific exit criterion:** Browser via Ingress displays citations, abstentions and invalid input feedback; network policies do not break UI→API.
- **Minimum acceptance:** browser UI, curl /api/ask. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** UI smoke for integration; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   cd indexer && ../.venv/bin/pytest -q
   kubectl get deployments -n rahbar
   kubectl get pods -n rahbar -o wide
   kubectl get --raw /healthz  # use port-forward/curl instead if necessary
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
OCR system packages must exist in container; network policies must allow DNS and host model; no liveness dependency calls.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G3: extracted sample pages and chunks inspectable; health/readiness/security UI paths verified
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-04-real-indexing-and-retrieval-md"></a>

## Phase 04 — Real indexing and retrieval


**Gate:** G4: a real index is non-empty; Chroma model+dimension metadata; filtered retrieval works. **Prerequisites:** G2 Chroma cluster plus extracted/cleaned chunks and frozen golden labels. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T10 — Implement pinned batched embedding and safe Chroma store

- **Owner / estimate:** A / 6 focused h.
- **Blocking dependencies:** T09, T06; do not claim integrated before these gates pass.
- **Allowed output paths:** `indexer/pipeline/embed.py; store.py; run.py`.
- **Execution goal:** Implement pinned Ollama batched embedding with timeout/retries, length and dimension checks, finite vectors and Chroma storage as the sole writer. Make Job corpus delivery real; stage index separately from active collection and verify before publishing; collection metadata includes `embed_model` and dimension.
- **Task-specific exit criterion:** Real Job exits 0, Chroma count >0, repeat indexing is safe, model-mismatch and interrupted-build tests pass.
- **Minimum acceptance:** real index Job + metadata/count. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G4 indexed collection; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T12 — Implement Chroma retrieval, version filtering, floor

- **Owner / estimate:** A / 5 focused h.
- **Blocking dependencies:** T10, T07; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/app/retrieval/chroma.py; api/app/config.py`.
- **Execution goal:** Implement `ChromaRetriever.retrieve` using the pinned query embedder, cosine-indexed collection, `1-distance` similarity, top-k, `superseded:false` default filtering and explicit historical-version handling, preserving citation fields. Add relevance floor before generation.
- **Task-specific exit criterion:** Tests show correct sorting, old policy exclusion, explicit historical access, exact-term behavior, empty index and Chroma error handling.
- **Minimum acceptance:** topk, scores, old-version tests. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** Passage[] to answer service; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T16 — Implement deny-default NetworkPolicy, service accounts, HPA

- **Owner / estimate:** B / 5 focused h.
- **Blocking dependencies:** T06; do not claim integrated before these gates pass.
- **Allowed output paths:** `k8s/base/*`.
- **Execution goal:** Implement separate minimal ServiceAccounts, no token automount, non-root/read-only/dropped-capability pod policies, Calico default-deny plus exactly documented ingress, API→Chroma/Redis/Ollama, indexer→Chroma/Ollama and DNS paths. Add HPA min 3 max 8 with CPU requests.
- **Task-specific exit criterion:** UI→Chroma blocked, API and indexer required paths work, `kubectl get hpa` resolves percent and resource limits present.
- **Minimum acceptance:** DNS+forbidden flows+HPA. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** secure cluster proof; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T17 — CI lint/test/build/kubeconform/Trivy skeleton

- **Owner / estimate:** B / 5 focused h.
- **Blocking dependencies:** T04; do not claim integrated before these gates pass.
- **Allowed output paths:** `.github/workflows/ci.yml`.
- **Execution goal:** Create workflow lint Ruff/Mypy, pytest coverage ≥60%, UI checks if needed, `kustomize build` piped to kubeconform, three-image build and Trivy fixed HIGH/CRITICAL scan. Avoid network/model calls in unit tests; pin action/tool versions.
- **Task-specific exit criterion:** A PR on `dev`/`main` triggers each check; a deliberate faulty manifest or unit test blocks merge.
- **Minimum acceptance:** open PR and observe CI jobs. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** CI reusable jobs; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   kubectl get job,cronjob -n rahbar
   kubectl logs -l job-name=indexer -n rahbar  # adjust actual job label
   kubectl get pods -n rahbar
   make ask Q='What does clause 1.21 say?'
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Never replace the active live Chroma collection destructively; collection metadata and query embed model must align.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G4: a real index is non-empty; Chroma model+dimension metadata; filtered retrieval works
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-05-generation-cache-and-evaluation-md"></a>

## Phase 05 — Generation, cache and evaluation


**Gate:** G5: correct cited answer and abstention; safe cache; eval reports actual metrics. **Prerequisites:** G4 real indexed Chroma collection with verified metadata and retrieval. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T13 — Implement selected real LLM provider and safe prompt

- **Owner / estimate:** A / 5 focused h.
- **Blocking dependencies:** T12; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/app/providers/llm/ollama.py; services/*`.
- **Execution goal:** Implement real Ollama host (or chosen hosted) adapter behind the given Protocol, a numbered untrusted-evidence prompt, explicit temperature 0–0.3 and provider-enforced JSON schema. Parse with Pydantic and ensure `reasoning` never reaches the client.
- **Task-specific exit criterion:** Answerable fixture yields schema-valid answer; malformed/prose JSON, prompt injection and provider timeout safely recover.
- **Minimum acceptance:** malformed output, injection, retry. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** Answer contract validated; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T14 — Implement orchestration, citation guard and Redis cache

- **Owner / estimate:** A / 6 focused h.
- **Blocking dependencies:** T13; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/app/services/answer.py; services/cache.py`.
- **Execution goal:** Orchestrate cache→retrieve→floor→prompt→generate→validate→citation whitelist→return; retry once and deterministic fallback. Implement Redis vector semantic lookup with measured threshold and exclusion rules, cache generation prefix, TTL and safe reindex invalidation.
- **Task-specific exit criterion:** No invalid citations; must-abstain returns false; follow-ups/malformed/old-generation items skip cache; two API replicas share Redis.
- **Minimum acceptance:** cache exclusions, citations, abstain. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G5 grounded API behavior; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T15 — Implement eval functions, by-type metrics, gate

- **Owner / estimate:** A / 5 focused h.
- **Blocking dependencies:** T07, T12; do not claim integrated before these gates pass.
- **Allowed output paths:** `eval/run_eval.py; eval/tests/*`.
- **Execution goal:** Implement `eval/run_eval.py::{recall_at_k,citation_validity,summarise,gate}` and unit tests for denominators, null/no relevant, grouping and absolute 0.05 recall regression. Evaluate real golden and fixture golden without confusing their baselines.
- **Task-specific exit criterion:** Evaluator writes real JSON, returns exit 1 on gate failure, calculates recall@3/@5 and by-type metrics, enforces 95% citations/100% abstention.
- **Minimum acceptance:** unit gate + fixture live tests. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** runner CLI for CI; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   cd api && ../.venv/bin/pytest -q
   python eval/run_eval.py --api http://<INGRESS_IP> --host rahbar.local
   curl -i -H "Host: rahbar.local" http://<INGRESS_IP>/readyz
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Never accept valid JSON as proof of truth; cite matching retrieval, abstain, validate, retry once, and tune cache with negatives.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G5: correct cited answer and abstention; safe cache; eval reports actual metrics
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-06-ci-cd-integration-md"></a>

## Phase 06 — CI/CD integration


**Gate:** G6: complete PR CI e2e and SHA-tagged CD smoke tested. **Prerequisites:** A evaluator is implemented; CI unit/static jobs green; cluster image contracts exist. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T18 — CI fixture e2e cluster index + evaluation gate

- **Owner / estimate:** B / 6 focused h.
- **Blocking dependencies:** T15, T17, T06; do not claim integrated before these gates pass.
- **Allowed output paths:** `.github/workflows/ci.yml; k8s/overlays/*`.
- **Execution goal:** Add CI kind/k3d fixture deployment with Chroma/Redis, Job indexing real fixture corpus (not dummy-only), deterministic matched embedding mode or test model, live API/Ingress wait, `eval/run_eval.py` and baseline gate. Fail workflow on evaluator non-zero.
- **Task-specific exit criterion:** CI artifacts prove fixture documents indexed and evaluator gate executed; injected must-abstain violation produces red check.
- **Minimum acceptance:** live CI PR run; intentional fail. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G6 blocked and green PR; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T19 — CD SHA-tag image build/push + ephemeral deploy

- **Owner / estimate:** B / 5 focused h.
- **Blocking dependencies:** T17, T05; do not claim integrated before these gates pass.
- **Allowed output paths:** `.github/workflows/cd.yml`.
- **Execution goal:** Implement CD test dependency, Docker Hub build-push for api/ui/indexer tagged `github.sha`, then ephemeral deploy with those exact tags, wait for rollout and Ingress smoke. Use `needs:` and GitHub Secrets; do not deploy from a failing build.
- **Task-specific exit criterion:** A real main-merge run shows test→publish→deploy dependency and running image tags matching commit SHA.
- **Minimum acceptance:** push to main after approval; smoke. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** CD run, registry links; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   kubectl kustomize k8s/overlays/prod
   python scripts/check_submission.py
   git log --oneline --max-count=5
   inspect CI and CD run URLs in GitHub
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
The CI fixture must actually index documents and query them; `eval.run_eval` with static stub passages is not an e2e RAG test.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G6: complete PR CI e2e and SHA-tagged CD smoke tested
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-07-verification-and-failure-experiments-md"></a>

## Phase 07 — Verification and failure experiments


**Gate:** G7: measured evaluation, four fault experiments, rollout and policy evidence recorded. **Prerequisites:** G5 real grounded application and G6 CI e2e successfully integrated. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T21 — Pair end-to-end integration and defect resolution

- **Owner / estimate:** Both / 5 focused h.
- **Blocking dependencies:** T14, T15, T16, T11, T18, T20; do not claim integrated before these gates pass.
- **Allowed output paths:** `api/*; indexer/*; k8s/*`.
- **Execution goal:** Pair-run real corpus indexing, question through Ingress, versions, empty/absent question, citation whitelist and metrics, then run full evaluation. Confirm A/B integration contracts, three ready API endpoints and cache reindex invalidation.
- **Task-specific exit criterion:** Joint signed G7 smoke log with actual payloads and outputs, no unresolved P0 cross-service defects.
- **Minimum acceptance:** answer + abstain via Ingress. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G7 green integrated service; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T22 — Measure chunk configs/cache threshold; 4 failure experiments

- **Owner / estimate:** A / 6 focused h.
- **Blocking dependencies:** T21; do not claim integrated before these gates pass.
- **Allowed output paths:** `PIPELINE-IMPLEMENTATION.md; FAILURE-ANALYSIS.md`.
- **Execution goal:** With frozen golden set, run ≥3 chunk size/overlap configs, compute recall@5 and storage amplification, choose one; sweep cache thresholds to find lowest zero-false-hit setting. Cause ≥4 fault stages A–F individually in disposable collection and restore.
- **Task-specific exit criterion:** `PIPELINE-IMPLEMENTATION.md` and `FAILURE-EXPERIMENTS.md` contain observed tables, before/after evidence and rationale.
- **Minimum acceptance:** actual recall + false-hit table. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** verified quality evidence; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T23 — Pod deletion, rollback, HPA, resource and security evidence

- **Owner / estimate:** B / 5 focused h.
- **Blocking dependencies:** T21; do not claim integrated before these gates pass.
- **Allowed output paths:** `docs/evidence/*; ENGINEERING-NOTES.md`.
- **Execution goal:** Delete one API pod and verify continued service; inspect `kubectl get endpoints`, CPU HPA with metrics-server, peak `kubectl top pods`, requests/limits margin, rolling `kubectl set image` + undo, policy-blocked connections, and embedding mismatch 0/1 readiness.
- **Task-specific exit criterion:** Real platform evidence includes pod/events/logs/images SHA, no downtime claim without observed requests, all workload resources checked.
- **Minimum acceptance:** kubectl top; rollout undo; HPA. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** verified operations evidence; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   python eval/run_eval.py --api http://<INGRESS_IP> --host rahbar.local
   kubectl top pods -n rahbar
   kubectl get endpoints,hpa -n rahbar
   kubectl rollout status deployment/api -n rahbar
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
Experiments must alter one stage at a time and be restored; values in PIPELINE and engineering notes must be actually measured.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G7: measured evaluation, four fault experiments, rollout and policy evidence recorded
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

<a id="merged-docs-phases-08-release-and-submission-md"></a>

## Phase 08 — Release and submission


**Gate:** G8: clean clone success; all required grader files and submission links verified. **Prerequisites:** G7 fault/rollout evidence collected, CD images available, and all core capabilities functioning. **Status:** unverified until commands are run. Tasks here are from `CRITICAL-PATH.md`; the owner listed controls the edit set.

### Implementation tasks
#### T24 — Final joint regression; resolve checker failures

- **Owner / estimate:** Both / 4 focused h.
- **Blocking dependencies:** T22, T23, T19; do not claim integrated before these gates pass.
- **Allowed output paths:** `tests; docs; scripts/check_submission.py`.
- **Execution goal:** From a clean clone, follow exact README apply order; build/run/index/query/evaluate using pinned images; run lint/test/schema/security/eval and the starter `scripts/check_submission.py`. Resolve missing files, secrets, docs and CI gates.
- **Task-specific exit criterion:** No checker findings, actual CI/CD proof, two reviewers approve the final change set.
- **Minimum acceptance:** make test lint check + eval. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** G8 release candidate; inform consumer in `TWO-DEVELOPER-PLAN.md`.

#### T25 — Freeze README, 7 notes, AI usage, submission URLs

- **Owner / estimate:** Both / 3 focused h.
- **Blocking dependencies:** T24; do not claim integrated before these gates pass.
- **Allowed output paths:** `README.md; docs/*; eval/results.json`.
- **Execution goal:** Replace `MEASURE` placeholders and sample values with observed data; answer seven notes with `file:line` and actual incident; complete AI disclosure, corpus/manifest, evidence index, final demo and four submission links.
- **Task-specific exit criterion:** GitHub URL, successful CD run, Docker Hub SHA links, actual eval baseline/results committed; submit once before deadline.
- **Minimum acceptance:** clean clone; checklist; links. Record command, actual exit code, output/URL and commit SHA. Include one failure-path check.
- **Handoff:** submitted deliverables; inform consumer in `TWO-DEVELOPER-PLAN.md`.


### Phase verification commands (examples; substitute real pod/job names)
```bash
   make test
   make lint
   make check
   python scripts/check_submission.py
   git grep -n STARTER-TODO
   confirm final submission links, Docker Hub SHA tags, actual results.json and baseline.json
```

### Concurrency and blocking
Two developers may work in parallel **only on their assigned files and once dependencies are satisfied**. A testable module may be written before an upstream cluster exists, but cannot be labeled fully integrated. Read `CRITICAL-PATH.md` for hard blockers; reserve shared files for explicit handoffs.

### Risks and stop condition
No submission on a partly green checker; guard against leak in entire Git history and make sure clean clone README works.

### Exit criteria — both developers sign
- [ ] All phase tasks satisfy `DEVELOPMENT-FLOW.md`; no false evidence.
- [ ] G8: clean clone success; all required grader files and submission links verified
- [ ] Capture commands/commit in `docs/evidence/` with true timestamps.
- [ ] Next-phase owner confirms the expected input/connection/contract before dependent task starts.

---

