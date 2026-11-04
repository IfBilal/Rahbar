> **Status (5 November 2026):** executed on the `dev` branch with pull requests to `main`; history in `git log`. This guide is kept as the plan of record.

# Two-person responsibilities, calendar, Git and handoffs

**Goal:** let each person and their coding agent work at the same time without touching the same unstable files. One developer cannot approve their own changes on protected `main`; use task branches from `dev` and cross-review. Preserve actual commit authorship and show meaningful work by both people.

**Daily sync:** kickoff (10m) → independent A/B implementation → contract checkpoint (15m) → cross-review → joint integration (20–40m). Both people own the final correctness, not just their lane. Templates below are embedded in this file so the documentation count stays at 25.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-13-two-developer-plan-md"></a>

## Two-developer ownership and collaboration contract


### Responsibilities (stable until approved handoff)
| Activity | Developer A — RAG/application lead | Developer B — platform/release lead |
|---|---|---|
| Corpus selection, versions, checksums | **Responsible** | review version/OCR proof |
| Indexing: extract -> store, embeddings | **Responsible** | provide Job image, volume, Chroma service |
| Retrieval, source filtering, generation, cache | **Responsible** | review readiness and secrets interactions |
| API schemas/config and changed imports | propose/spec tests | **joint approval**, B owns runtime wiring |
| FastAPI readiness/probes/metrics route | review interface + instrumentation | **Responsible** |
| nginx UI and Ingress | API contract review | **Responsible** |
| K8s stateful/chroma/redis, network/HPA | review network paths and index read/write | **Responsible** |
| Evaluation/golden/failures | **Responsible** | wire fixture CI and intentional failing PR |
| CI/CD, registry and rolling deployments | review eval gate | **Responsible** |
| Documentation, tests, line refs, final demo | **joint ownership** | **joint ownership** |

### Ownership maps (avoid merge conflicts)
A alone edits: `indexer/pipeline/*.py`, `indexer/tests/*`, `api/app/retrieval/*`, `api/app/providers/llm/*`, `api/app/services/*`, `api/tests/test_rag_*`, `corpus/*`, `eval/*`.
B alone edits: `k8s/**`, `.github/workflows/**`, `api/Dockerfile`, `indexer/Dockerfile`, `ui/Dockerfile`, `ui/**`, `api/app/routes/health.py`, `api/app/routes/metrics.py`, `docs/evidence/platform/**`.
Shared: `api/app/schemas.py`, `api/app/config.py`, `api/app/main.py`, `README.md`, `ARCHITECTURE.md` (this repo uses `ARCHITECTURE.md`; submitters may choose a matching alias if their checker expects it), `ENGINEERING-NOTES-GUIDE.md`, `AI-ASSISTANCE-PLAYBOOK.md`.

### Daily working protocol
1. **Kickoff (10 minutes):** each developer states finished, next task IDs, contract changes, impediments, exact files; set `TWO-DEVELOPER-PLAN.md`.
2. **Independent work:** each opens `feat/a-<task>-slug` or `feat/b-<task>-slug` from current `dev`, commits one task/test set. No direct `main`.
3. **Checkpoint (15 minutes):** A demonstrates API/Job output against fixed contract; B demonstrates cluster/CI output. Exchange env/port names and readiness failure details.
4. **Review:** other developer examines PR, runs at least focused test if feasible, checks security/contract, merges to `dev` only when CI passes.
5. **Evening integration (20–40 minutes):** both pull `dev`, run `make test`, relevant cluster commands, record blocker and next dependencies.

### Integration handoff examples
- **A -> B:** indexed collection with active version and `embed_model`/`dimension`; B confirms `/readyz` and metrics in cluster; sample `kubectl logs job/<name>`.
- **B -> A:** reachable Chroma ClusterIP, ConfigMap fields, Ollama host route, Job pod `/corpus` path; A tests real embedding/indexing with explicit env.
- **A -> B:** `eval/run_eval.py` exits 0/1 correctly and fixture golden identifies relevant `(source,section)` pairs; B wires e2e CI.
- **B -> A:** Ingress URL, 3 endpoint IPs and policy-protected network; A tests grounded answer through route with `Host: rahbar.local`.

### Shared file rule
One developer creates a 1-file contract PR (schemas/config/main) and the other explicitly approves; no parallel uncoordinated edits. If an agent wants to modify shared files, require human consent. Record who owns the handoff and the consumer's acceptance test.

### Branch security
`main` protected: PR required, required CI, >=1 approval, no direct pushes. `dev` is integration branch, and task branches originate from `dev`. Preserve commit ownership and show both members' contributions. One team submits one final repository.

---

<a id="merged-docs-14-daily-schedule-md"></a>

## Time-boxed execution plan — 3–8 November 2026 (PKT)


**Deadline:** Sunday Nov 8 at 23:59 PKT. This plan assumes a start on Tuesday Nov 3; if started later, keep the *gate order* and compress only parallel/peripheral work. Do not imply any gate has already passed. Reserve at least final several hours for clean-clone checks, evidence and submission.

| Date | Developer A track | Developer B track | Mandatory shared checkpoint |
|---|---|---|---|
| Tue 3 Nov | T01/T02 kickoff; verify 6+ documents, revision pair, scanned PDF; start golden set T03/T07 | T01/T02; Dockerfiles T04; prepare registry and branch protection | G0 contracts frozen; URLs and environment blockers surfaced |
| Wed 4 Nov | OCR/extract T08; cleaning/chunking T09, tests | K8s base T05; minikube stub+dummy T06; UI route T20 | G2 stub through Ingress, dummy Job/PVCs verified |
| Thu 5 Nov | pinned embeddings/store T10, retrieval T12; run small real index | probes T11, security/HPA T16, CI static T17 | G4 real index non-empty, correct model metadata |
| Fri 6 Nov | provider T13; orchestrator, cache T14; eval functions T15 | CI fixture e2e T18, CD initial T19, metrics/log proof | G5 grounded answer/abstention and evaluator through Ingress |
| Sat 7 Nov | tune 3 chunk configs and cache threshold; 4 faults T22 | CI blocked/good PR, deploy rollback/HPA/pod-delete tests T23 | G7 quality/regression & operational evidence |
| Sun 8 Nov | assist joint fixes, all notes/corpus/pipeline and AI disclosure | finalize workflows, registry links, clean-clone runbook | T24/T25 G8, final submission before 23:59 PKT |

### Practical daily priorities
Do not spend the whole first days perfecting RAG before the stub stack works; the assignment explicitly asks to ship Kubernetes first. If A blocks on Chroma network, A writes pure extraction/chunking tests and golden labels while B finishes infra. If B blocks on A's eval runner, B completes Docker, manifests, NetworkPolicy, HPA and static CI independently. These are deliberate waiting buffers, not permission to change code in the other person's track.

### Daily gates / stop conditions
- **Tue:** if 2023 version URL unavailable, pick a *verified* policy revision pair or write fallback action; no invented version differences.
- **Wed:** if Ingress fails, diagnose DNS/Calico/hosts/images before reworking API code.
- **Thu:** if real index missing/empty, do not proceed as if version filter/generation are tested.
- **Fri:** if provider JSON fails, handle schema/retry/fallback rather than disabling validation.
- **Sat:** if eval fails, fix real behavior; never update baseline just to make CI green.
- **Sun:** any unverified P0 becomes a reported blocker; stop adding bonuses; test from a clean clone and gather remaining required screenshots/links.

### Workload reality
The WBS focused-hour estimates are risk estimates. With two developers and 6 calendar days, overlapping deadlines are tight; use async task branches, 2 short check-ins/day, and avoid shared-file conflicts. Classify tasks as `blocked`, `in progress`, `ready for review`, `verified`, never `done` without evidence. `CRITICAL-PATH.md` computes a *precedence-only lower bound*, not wall-clock completion.

---

<a id="merged-docs-15-collaboration-and-git-md"></a>

## Collaboration, Git governance and PR lifecycle


### Required branches
- `main`: protected release branch; at least one reviewer approval and required passing CI; **no direct push**.
- `dev`: integration branch; PR work lands here; run static/unit checks on push.
- `feat/a-Txx-meaningful-slug`, `feat/b-Txx-meaningful-slug`, `fix/...`, `docs/...`: short-lived branches from updated `dev`.

### Task branch lifecycle
```bash
git switch dev && git pull --ff-only origin dev
git switch -c feat/a-T08-ocr-extraction
# edit only A-owned paths, write tests, run tools
git add indexer/pipeline/extract.py indexer/tests/
git commit -m 'feat(indexer): support OCR fallback on scanned pages'
git push -u origin feat/a-T08-ocr-extraction
# Open PR targeting dev; request other developer review
```
Then review, merge, delete task branch; rebase new tasks on current dev. Move `dev` -> `main` only through reviewed PR after all required CI jobs and explicit release gate.

### PR description must contain
Task ID + rubric IDs; what/why; files owned/touched; contract changes; exact commands and observed test results; evidence paths; dependency task unblocked; security checklist (secrets, external calls, permissions); rollback effects; any AI assistance and human modifications.

### Merge-blocking conditions
Any changed `AskResponse`, `Chunk.metadata()`, shared ConfigMap key or port without cross-owner approval. Failing coverage, CI status or evaluation gate. `starter TODO` reintroduced in production paths. Real key/secret or downloaded third-party PDF in commit. Unverified claims pasted into documentation. Manifest adds forbidden Service exposure, `:latest`, no resource requests or a default namespace resource.

### Conflict prevention
Agree at G0 on exact key names and Python signatures. A should add new modules in A directories, B should add manifests in B directories, and shared files must be edited by one person at a time. At a conflict, identify contract owner, pair for 15 min, add a regression test, then resolve; never auto-choose one side blindly.

### Evidence in Git
Commit text evidence (`kubectl`, CI logs excerpt) with date, environment and SHA; screenshots can go in `docs/evidence/` with clear filenames if repository size permits. Never commit `.env`, kubeconfig, credentials, or unsanitized logs containing keys. Screenshots of branch rules and blocked merge must be genuine.

---

<a id="merged-docs-developers-developer-a-md"></a>

## Developer A — RAG, corpus, quality owner


### Mission
Build the real evidence path *using starter interfaces*, from verified public documents through `Page -> Document -> Chunk -> embeddings -> Chroma -> Passage -> Answer -> AskResponse`. Own quality evaluation, abstention, cache and prompt-injection safety. B owns infrastructure and deployment; don't edit their manifests without a handoff.

### Chronological tasks
T03 verify sources and manifest; T07 write 15 golden questions from real clauses; T08 OCR extraction; T09 cleaner/chunker and three measured configs; T10 embedding/store and model metadata; T12 Chroma retrieval/version filter; T13 real LLM provider; T14 orchestration, citation guard and cache; T15 evaluation functions; T22 experiment tuning/failure analysis. Read the relevant `PHASES.md` before each.

### First-day commands
```bash
make install
make test
cp corpus/sources.example.yaml corpus/sources.yaml
make fetch
python corpus/fetch.py --verify
```
Record dead URLs, PDF page counts, actual 2023/2026 policy differences. Do not copy `eval/golden.example.yaml` guesses as a finished golden: verify source heading/page labels first.

### Hard coordination
Ask B for Chroma hostname/port, `/corpus` mounting plan, Ollama host route, ConfigMap EMBED_MODEL and Redis URL; deliver B final collection/pin/embedding-dimension contract, probe failure modes, safe reindex protocol and evaluator CLI. Only one person edits `api/app/config.py` at a time. B must confirm readiness checks against *same active collection* A's retriever queries.

### Release acceptance
Actual valid answer/abstain through Ingress; no fake citations; safe reindex invalidation; three measured chunk sets; thresholds chosen from false-hit data; eval JSON real and CI gate; at least four fault experiments, seven notes jointly reviewed. Unit tests never call real hosted service.

---

<a id="merged-docs-developers-developer-b-md"></a>

## Developer B — Kubernetes, DevOps, integration owner


### Mission
Turn the stub app into a real cluster-backed platform without rewriting RAG internals: Dockerfiles, PVC databases, namespace/NetworkPolicy, 3 ready API replicas, UI ingress, Jobs/CronJobs, HPA, probes, CI/CD, deployment/rollback and evidence. B reviews A's collection and cache contracts.

### Chronological tasks
T04 Dockerfiles (api/indexer/ui), T05 kustomize base/dev/prod and stores, T06 local dummy Job/Ingress vertical slice, T11 startup/liveness/readiness and model pin, T16 ServiceAccounts/Calico/HPA, T17 static/unit/scan CI, T18 fixture e2e, T19 SHA CD, T20 UI, T23 resource/deletion/rollback/security evidence. Read `KUBERNETES.md`, `NETWORK-SECURITY.md`, `CI-CD.md`.

### First-day commands
```bash
make install
make cluster
# once Dockerfiles exist:
make images TAG=dev
# once manifests exist:
make apply
kubectl get pods,svc,job,pvc -n rahbar
```
Run dummy index with `EMBED_MODEL=dummy-768` and keep `RETRIEVER=stub`; do not call dummy answers real RAG. Check Chroma/Redis persistence, nginx 8080 read-only root and same-origin `/api/ask`.

### Hard coordination
Deliver A exact `CHROMA_HOST/PORT`, ConfigMap names, PVC/job corpus path and provider network access. Ask A for actual embedding dimension, active collection protocol and fixture test embedding mode before wiring probes and CI. Ensure NetworkPolicy Redis access remains API-only; A's cache invalidation must be compatible. Shared file edits in `api/app/main.py`, `config.py` require A approval.

### Release acceptance
Successful e2e fixture with genuine indexed documents, CI intentional failure and fixed pass, main protection, SHA images, deploy/rollback, 3 endpoints, HPA target resolved, model pin mismatch ready=0/1, no UI->Chroma path, resource measurements and clean clone runbook. No secrets in Git; use Actions Secrets for registry.

---

<a id="merged-docs-developers-handoffs-md"></a>

## Two-developer handoff ledger (live, edit on every integration)


**Status is empty until actual work occurs.** Use task ID rather than vague “backend ready”; include actual consumer acceptance and blockers.

| Date PKT | Producer/task/commit | Deliverable / interface / environment | Consumer test & actual result | Accepted by | Blockers |
|---|---|---|---|---|---|
| TO FILL | A/T03 | chosen source YAML + sha + actual PDF version pair | TO RUN | PENDING | URLs require check |
| TO FILL | B/T06 | minikube Chroma+Redis and ingress stub | TO RUN | PENDING | manifests not yet built |
| TO FILL | A/T10 | populated collection + embed model/dimension | TO RUN | PENDING | depends G2 |
| TO FILL | A/T15 | eval runner + gate | TO RUN | PENDING | depends golden and retrieval |
| TO FILL | B/T18 | fixture e2e CI | TO RUN | PENDING | depends T15 |

### Format for new rows
`DATE | producer task and SHA | exact source path/API schema/env | command run by consumer and observed response | human reviewer | next action and due date`. No accepted handoff until consumer checks it, and no source-branch deletion before dependent task unblocked.

---

<a id="merged-docs-developers-pr-review-checklist-md"></a>

## Pull request / peer review checklist


### PR identity
Task ID: `TO FILL`; owner/branch/base: `TO FILL`; requirement R IDs: `TO FILL`; type feat/fix/ci/docs; proposed ADR change: `none / link`.

### Check before approval
- [ ] Source diff confined to owner paths, or cross-owner approval documented.
- [ ] Starter API/request/answer/metadata contracts preserved; optional changes coordinated.
- [ ] Unit tests cover success and at least one negative path and actually ran (paste command and result).
- [ ] Relevant lint/type, Docker build, kustomize and live smoke ran; NOT RUN list honest.
- [ ] No secret/PDF/prohibited content, unsafe prompt execution or public Chroma/Redis service.
- [ ] Provider validation and cite guard unaffected or tested; no false abstain/cached stale answer.
- [ ] Documentation and traceability updated with actual evidence, not invented output.
- [ ] Consumer knows handoff input and has run acceptance check where relevant.
- [ ] Reviewer understands why design fits assignment and records one meaningful review comment.

### Post-merge
Merge to dev with CI passing, notify dependent task owner, record the SHA and handoff details in the task PR (see the handoff protocol in this file), and refresh branch before next work. Only approved/retested dev -> protected main can trigger CD.

---

<a id="merged-docs-templates-daily-update-md"></a>

## Daily sync — [YYYY-MM-DD] PKT


| | Developer A | Developer B |
|---|---|---|
| DONE with evidence (task IDs, SHAs) | | |
| IN PROGRESS | | |
| BLOCKED on task / contract | | |
| Next independent work | | |
| Handoff needed | | |

### Integration gate update
G0–G8: current gate, commands actually passed, PR links, remaining failures and owner.

### Time-to-deadline response
If key P0 blocked, stop bonuses, pair-debug one reproducible issue and update risk register. Do not alter quality gate to hide regression.

---

<a id="merged-docs-templates-pr-template-md"></a>

## PR — [task ID] [short title]


**Owner:** A/B · **Branch -> target:** feat/... -> dev · **Requirements:** Rxx · **Dependencies verified:** Txx.

### Change
Files, behavior, rationale, ADR/contract impact.

### Verification actually run
| Command/environment | Observed exit and result | Evidence link |
|---|---|---|
| TO FILL | TO FILL | TO FILL |

### Negative test / security
Describe failed scenario and fix, no secrets or prohibited source files, effect on cache/citations/readiness, and how you rolled back locally if needed.

### Handoff
Consumer task and exact expected interface/data/URL. Blocker(s): ... . AI assistance disclosure changes if applicable.

### Review
- [ ] Other developer approved
- [ ] CI passed
- [ ] Traceability evidence reviewed

---

<a id="merged-docs-templates-task-template-md"></a>

## Issue [TASK-ID] — short task


**Owner:** A/B/Both · **Priority:** P0/P1 · **Estimate:** X focused hours · **Hard deps:** IDs · **Rubric:** Rxx.

### Context and contracts
Link actual starter source, spec, phase, provider/consumer interface, allowed paths and forbidden edits.

### Execution checklist
- [ ] baseline inspected, tests identified
- [ ] failing negative test added
- [ ] implementation complete in owner paths
- [ ] lint/type/unit and integration commands executed
- [ ] docs, evidence and handoff updated

### Acceptance and evidence
Exact command, expected behavior, actual output + exit status, commit SHA, consumer acceptance, remaining risks.

---

