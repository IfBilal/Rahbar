> **Status (5 November 2026):** implemented; see `README.md` (clean-clone path) and `docs/TRACEABILITY.md`. This guide is kept as the plan of record.

# RAHBAR — 25-file Agent Development Documentation

> **Supplementary documentation only — not a replacement for the starter kit.** This ZIP intentionally contains **25 new standalone Markdown guides, all at ZIP root**. It does **not** contain or overwrite any Markdown supplied with `rahbar-starter.zip` (`README.md`, `STARTER.md`, `docs/CORPUS.md`, `docs/PIPELINE.md`, `docs/FAILURE-ANALYSIS.md`, `docs/ENGINEERING-NOTES.md`, `docs/AI-USAGE.md`, the fixture Markdown, or the ADR template). Keep all of those original files in your project. The instructor requires several **exact submission paths**; implement and update the originals in those paths using these guides as working plans. If names appear similar, this guide is for implementation and the starter file is the deliverable.

## How to use these flat files

1. Extract this archive into the **root of the original starter repository**. It will add only 25 new `.md` documents, without replacing the instructor's original Markdown.
2. Read `STARTER.md` (original), then `AGENTS.md`, `PROJECT-GUIDE.md`, `PRD.md`, `INTERFACE-CONTRACTS.md`, `CRITICAL-PATH.md`, and `TWO-DEVELOPER-PLAN.md`.
3. Each developer picks unblocked tasks in `CRITICAL-PATH.md`, follows `PHASES.md` and the relevant implementation guides, and checks `DEVELOPMENT-FLOW.md` for acceptance criteria.
4. Keep the instructor's required project documentation updated **in its required original location** (examples below), using the corresponding *new planning file* as guidance.

| Original required starter file (keep/update) | New supplementary guide in this ZIP |
|---|---|
| `README.md` | `PROJECT-GUIDE.md`, `DEPLOYMENT-RUNBOOK.md`, `SUBMISSION-AND-EVIDENCE.md` |
| `STARTER.md` | `AGENTS.md`, `INTERFACE-CONTRACTS.md` |
| `docs/CORPUS.md` | `CORPUS-PLAN.md` |
| `docs/PIPELINE.md` | `PIPELINE-IMPLEMENTATION.md` |
| `docs/FAILURE-ANALYSIS.md` | `FAILURE-EXPERIMENTS.md` |
| `docs/ENGINEERING-NOTES.md` | `ENGINEERING-NOTES-GUIDE.md` |
| `docs/AI-USAGE.md` | `AI-ASSISTANCE-PLAYBOOK.md` |
| `docs/adr/0000-template.md` | Four `ADR-000x-*.md` planning decisions; **the assignment also expects ADR outputs under `docs/adr/`** |
| `eval/fixtures/*.md` | `TESTING-EVALUATION.md` (use the original fixtures unchanged unless an approved test requires updates) |

**Important:** All 25 docs are intentionally at ZIP root, so their Markdown links point to filenames in the same directory. The real project directories (`api/`, `indexer/`, `k8s/`, `eval/`, etc.) remain as originally supplied.

## All 25 documentation files

1. [`AGENTS.md`](AGENTS.md)
2. [`PROJECT-GUIDE.md`](PROJECT-GUIDE.md)
3. [`AI-ASSISTANCE-PLAYBOOK.md`](AI-ASSISTANCE-PLAYBOOK.md)
4. [`ARCHITECTURE.md`](ARCHITECTURE.md)
5. [`CI-CD.md`](CI-CD.md)
6. [`CORPUS-PLAN.md`](CORPUS-PLAN.md)
7. [`CRITICAL-PATH.md`](CRITICAL-PATH.md)
8. [`DEPLOYMENT-RUNBOOK.md`](DEPLOYMENT-RUNBOOK.md)
9. [`DEVELOPMENT-FLOW.md`](DEVELOPMENT-FLOW.md)
10. [`ENGINEERING-NOTES-GUIDE.md`](ENGINEERING-NOTES-GUIDE.md)
11. [`FAILURE-EXPERIMENTS.md`](FAILURE-EXPERIMENTS.md)
12. [`INTERFACE-CONTRACTS.md`](INTERFACE-CONTRACTS.md)
13. [`KUBERNETES.md`](KUBERNETES.md)
14. [`PHASES.md`](PHASES.md)
15. [`PIPELINE-IMPLEMENTATION.md`](PIPELINE-IMPLEMENTATION.md)
16. [`PRD.md`](PRD.md)
17. [`RAG-QUERY.md`](RAG-QUERY.md)
18. [`SECURITY-OBSERVABILITY.md`](SECURITY-OBSERVABILITY.md)
19. [`SUBMISSION-AND-EVIDENCE.md`](SUBMISSION-AND-EVIDENCE.md)
20. [`TESTING-EVALUATION.md`](TESTING-EVALUATION.md)
21. [`TWO-DEVELOPER-PLAN.md`](TWO-DEVELOPER-PLAN.md)
22. [`ADR-0001-indexer-as-job.md`](adr/0001-indexer-as-job.md)
23. [`ADR-0002-structure-aware-chunking.md`](adr/0002-structure-aware-chunking.md)
24. [`ADR-0003-semantic-cache-store.md`](adr/0003-semantic-cache-store.md)
25. [`ADR-0004-llm-provider-and-data-governance.md`](adr/0004-llm-provider-and-data-governance.md)

---


# RAHBAR — 25-file documentation index and project setup

> **Documentation-only package.** This archive contains exactly 25 Markdown files and **no source code, manifests, secrets or measurement artifacts**. Unzip into the root of the provided `rahbar-starter` project, retaining the starter's existing `STARTER.md`, `Makefile`, `api/`, `indexer/`, `ui/`, `eval/`, `corpus/` and `scripts/`. When the docs say to create a manifest, source file or screenshot, they are describing future work, not claiming it is already implemented.

**Project:** RAHBAR — evidence-grounded RAG over public/owned FAST-NUCES-style documents on Kubernetes. **Team:** exactly two developers. **Deadline:** Sunday, 8 November 2026 at 23:59 PKT. **Execution order:** Kubernetes stub deployment first, real RAG next, measured quality and CI/CD last. The assignment PDF and `STARTER.md` are the final authority.

### Where each developer and agent should start
1. Both: read [AGENTS.md](AGENTS.md), [PRD](PRD.md), [contracts](INTERFACE-CONTRACTS.md), and [critical path](CRITICAL-PATH.md); assign A/B ownership.
2. A: [Corpus](CORPUS-PLAN.md) → [Index pipeline](PIPELINE-IMPLEMENTATION.md) → [Query, model and cache](RAG-QUERY.md) → [Evaluation](TESTING-EVALUATION.md).
3. B: [Kubernetes](KUBERNETES.md) → [Security/observability](SECURITY-OBSERVABILITY.md) → [CI/CD](CI-CD.md) → [Runbook](DEPLOYMENT-RUNBOOK.md).
4. Both: follow [Nine implementation phases](PHASES.md), [pair plan](TWO-DEVELOPER-PLAN.md), [integration gates](DEVELOPMENT-FLOW.md), and [submission](SUBMISSION-AND-EVIDENCE.md).

### All 25 files
| File | Contents |
|---|---|
| `AGENTS.md` | Agent rules, invariants, code ownership and task loop |
| `README.md` | This index and setup |
| `PRD.md` | Requirements, acceptance, traceability, nonfunctionals |
| `ARCHITECTURE.md` | Topology, boundaries, data model, sequences |
| `INTERFACE-CONTRACTS.md` | Existing Python/HTTP/metadata/config contracts |
| `CRITICAL-PATH.md` | 25-task WBS, DAG, CPM, blocking/parallel windows |
| `TWO-DEVELOPER-PLAN.md` | A/B lanes, calendar, Git, review, handoffs |
| `DEVELOPMENT-FLOW.md` | Integration gates G0–G8, risk register, DoD |
| `PHASES.md` | Nine phase playbooks with implementation and exit checks |
| `CORPUS-PLAN.md` | Seven corpus properties, sources, version checks, hashes |
| `PIPELINE-IMPLEMENTATION.md` | Extract/clean/chunk/embed/store, OCR and tuning |
| `RAG-QUERY.md` | Retrieval, provider, citations, abstention, Redis cache |
| `KUBERNETES.md` | Kubernetes objects, manifests, resources, scaling |
| `SECURITY-OBSERVABILITY.md` | Threat model, policies, JSON logs and metrics |
| `TESTING-EVALUATION.md` | Unit/integration/fixture tests, golden and CI gate |
| `CI-CD.md` | Two GitHub workflows with SHA and gated publishing |
| `DEPLOYMENT-RUNBOOK.md` | Local cluster, rollout, re-index and recovery |
| `FAILURE-EXPERIMENTS.md` | Four controlled RAG failure experiments |
| `ENGINEERING-NOTES-GUIDE.md` | Seven required implementation-grounded questions |
| `SUBMISSION-AND-EVIDENCE.md` | Deliverables, checker, screenshots, demos |
| `AI-ASSISTANCE-PLAYBOOK.md` | Honest AI-tool attribution |
| `ADR-0001-indexer-as-job.md` | Indexer Job and reader-only API |
| `ADR-0002-structure-aware-chunking.md` | Measured chunking and optional exact-term enhancement |
| `ADR-0003-semantic-cache-store.md` | Redis cache and safe re-index publication |
| `ADR-0004-llm-provider-and-data-governance.md` | LLM, data safety and readiness guardrail |

### Verify starter before implementation
```bash
make install
make test
make lint
make dev
```
These are starter targets (Python 3.12, `make`, WSL2 on Windows recommended). In a separate terminal open `http://localhost:8000` for the stub UI. **The starter lacks real Dockerfiles, Kubernetes manifests, pipelines and GitHub workflows**. An agent must not assume they already exist.

### Scope and decision discipline
The preferred base is host Ollama `llama3.2:3b` + `nomic-embed-text`, Chroma server/client `1.0.12`, Redis semantic cache, Calico minikube and SHA-tagged Docker Hub images. Those are project planning defaults; verify installed software, available model endpoints, actual corpus availability and resource numbers. The nine-phase runbooks and 25 tasks are estimates; they do not imply the work has been executed. Report every unresolved measurement as `MEASURE`, never guessed evidence.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-readme-md"></a>

## RAHBAR — Grounded RAG on Kubernetes


**Status: implementation pending.** This repo starts from the instructor-provided `rahbar-starter.zip`. The documentation is a **development blueprint**, not evidence that the system is deployed or that its evaluation passes.

RAHBAR is a citation-grounded question-answering service over a public/owned document corpus. A one-shot indexer transforms documents into Chroma vectors; multiple FastAPI replicas retrieve evidence and return validated, cited answers or safely decline unsupported questions. Kubernetes hosts nginx UI, API, persistent Chroma and Redis, and scheduled re-indexing.

### Quick navigation
- **Start:** [Documentation index](PROJECT-GUIDE.md), [starter instructions](../STARTER.md), [requirements](PRD.md).
- **Build:** [architecture](ARCHITECTURE.md), [API/data contracts](INTERFACE-CONTRACTS.md), [critical path](CRITICAL-PATH.md), [two-person plan](TWO-DEVELOPER-PLAN.md), [phase guides](PHASES.md).
- **Quality:** [tests](TESTING-EVALUATION.md), [evaluation](TESTING-EVALUATION.md), [grader traceability](PRD.md).
- **Operate and submit:** [deployment](DEPLOYMENT-RUNBOOK.md), [submission](SUBMISSION-AND-EVIDENCE.md), [evidence](SUBMISSION-AND-EVIDENCE.md).

### What the starter already contains
FastAPI request/response contracts and routes, stub retriever/provider, basic metrics and request IDs, a provided static chat page, indexer runner and dummy index, corpus downloader, fixture documents, skeleton eval runner, Makefile and submission checker. **It does not yet contain working PDF/HTML extraction, embeddings, Chroma retrieval, real model calls, caching, the required Kubernetes manifests, Dockerfiles, or CI/CD workflows.** Read [the audited inventory](AGENTS.md).

### Local stub run (without Kubernetes)
```bash
make install
make test
make lint
make dev
# In another terminal:
curl -s localhost:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"What is RAHBAR?"}'
```
Use Python 3.12, Linux or WSL2, bash, make and git. `make dev` intentionally returns stub answers; **do not represent this as real corpus-grounded RAG**.

### Intended cluster path (execute only after implementation)
```bash
make cluster
make images
make apply
kubectl get pods -n rahbar
make index
make ask Q='What does the academic warning policy say?'
make check
```
The runbook specifies installation order, secrets, dependency checks, CI and proof to capture. The commands above are **not guaranteed to succeed until the missing implementation and manifests are completed**.

### Team workflow
Two contributors use feature branches off `dev`; `main` is protected and only receives reviewed, passing PRs. Developer A owns the corpus/RAG/evaluation path; Developer B owns deployment/CI/security/UI operations; shared contracts and releases need both approvals. See [ownership](TWO-DEVELOPER-PLAN.md), [PR rules](TWO-DEVELOPER-PLAN.md) and [integration gates](DEVELOPMENT-FLOW.md).

### Corpus and confidentiality
Use only public FAST-NUCES documents or owned documents. Commit `corpus/sources.yaml`, `corpus/MANIFEST.md` (URLs + verified SHA-256), and the fetch script, **not downloaded third-party PDFs**. Confirm website availability before finalizing the golden set. Use `CORPUS-PLAN.md` to show all seven corpus properties.

### Reproducibility and evidence
Do not copy example metrics or invented screenshots into submission docs. Create `eval/golden.yaml` **before tuning**, then commit actual `eval/results.json` and `eval/baseline.json`; collect proof in `docs/evidence/`. Run `python scripts/check_submission.py` from the root. Final submission includes repo URL, successful CD run, Docker Hub SHA-tagged images, and evaluation results.

### Submission timing
**Sunday 2026-11-08, 23:59 Asia/Karachi**. Use the relative schedule in the [daily plan](TWO-DEVELOPER-PLAN.md) and adapt if starting later; no claim is made that earlier milestones have already happened.

### AI disclosure
AI assistance is permitted with attribution. See [AI-ASSISTANCE-PLAYBOOK.md](AI-ASSISTANCE-PLAYBOOK.md) and record tools, generated work, and meaningful human corrections accurately.

---

<a id="merged-docs-00-start-here-md"></a>

## Documentation map — read this first


This package is a **build-ready specification and task system** adapted to the uploaded instructor starter kit and 20-page assignment. It **does not contain completed project code, real measured numbers, or real screenshots**. Any `TBD/MEASURE` fields are mandatory evidence to replace after implementing and testing. The deadline is 2026-11-08 23:59 PKT.

### Who reads what
| Reader / moment | Read first | Then use |
|---|---|---|
| Both developers, before code | `STARTER.md`, `AGENTS.md`, `PRD.md` | `INTERFACE-CONTRACTS.md`, `TWO-DEVELOPER-PLAN.md` |
| Developer A | `TWO-DEVELOPER-PLAN.md` | specs CORPUS, EXTRACTION, CHUNKING, EMBEDDING-STORAGE, RETRIEVAL, GENERATION, CACHE, EVALUATION |
| Developer B | `TWO-DEVELOPER-PLAN.md` | specs K8S, NETWORK-SECURITY, CI-CD, API-UI, deployment and operations |
| Coding agent | `AGENTS.md` | Assigned phase file, target spec and owning source files |
| Reviewer | `PRD.md` | phase gates, tests, actual evidence in `evidence/` |
| Last-day submitter | `SUBMISSION-AND-EVIDENCE.md` | `SUBMISSION-AND-EVIDENCE.md`, `ENGINEERING-NOTES.md` |

### Navigating by concern
- **Product / requirements:** `README.md`, `PRD.md`, `PRD.md`, `PRD.md`.
- **Design:** `README.md`, `ARCHITECTURE.md`, `INTERFACE-CONTRACTS.md`, `ARCHITECTURE.md`, `ARCHITECTURE.md`, `ADR-0001-indexer-as-job.md` through `ADR-0004-llm-provider-and-data-governance.md`.
- **Planning:** `CRITICAL-PATH.md`, `CRITICAL-PATH.md`, `TWO-DEVELOPER-PLAN.md`, `TWO-DEVELOPER-PLAN.md`, `DEVELOPMENT-FLOW.md`, `PHASES.md`.
- **Collaboration:** `TWO-DEVELOPER-PLAN.md`, `DEVELOPMENT-FLOW.md`, `DEVELOPMENT-FLOW.md`, `AGENTS.md`, `TWO-DEVELOPER-PLAN.md`, `TWO-DEVELOPER-PLAN.md`.
- **Verification:** `TESTING-EVALUATION.md`, `TESTING-EVALUATION.md`, `CORPUS.md`, `PIPELINE.md`, `FAILURE-ANALYSIS.md`, `ENGINEERING-NOTES.md`, `AI-USAGE.md`.
- **Delivery:** `DEPLOYMENT-RUNBOOK.md` through `DEPLOYMENT-RUNBOOK.md`, `SUBMISSION-AND-EVIDENCE.md`.

### Source-of-truth precedence
1. Instructor assignment PDF and explicit rubric.
2. Instructor-provided `STARTER.md` and existing source/fixture/checker contracts.
3. Actual running behavior confirmed by reproducible tests.
4. Approved ADRs and frozen contracts (`INTERFACE-CONTRACTS.md`).
5. Remaining plan documents (implementation recommendations, not grading facts).

If a proposed implementation conflicts with #1 or #2, file an issue and change the plan before writing incompatible code. Never silently 'fix' grading requirements. Docs can evolve through reviewed PRs.

### Symbols and gates
`P0` = submission-blocker; `P1` = important but can follow first runnable stack; `P2` = optional/bonus. `G0..G8` = integration checkpoints. A gate may only be checked off with execution output. An unchecked gate means its successor tasks may not claim integration complete.

### First 30 minutes
- [ ] Extract starter into the **existing repo root** with paths unchanged.
- [ ] Run `make install && make test && make lint` and record environment; these are **expected commands**, not pre-certified results.
- [ ] Create `dev`; protect `main`; choose two GitHub identities, exact initials and branch prefixes.
- [ ] Read `AGENTS.md`; confirm owning directories; create task tickets from WBS.
- [ ] Confirm FAST-NUCES source URLs and scanned/version pair; freeze initial `/api/ask` contract.
- [ ] Take first parallel tasks: **A: corpus & golden set**; **B: Docker/Kubernetes stub baseline**.

### Non-negotiable final-state checks
`3` API replicas; `1` Chroma StatefulSet; `1+` nginx UI; Redis PVC; Job and weekly CronJob; services ×4; ingress; network policies and HPA; three probes; cross-service embedding pin; factual citations and abstention; `>=15` golden questions; `>=60%` app tests; passing quality gate; CI/CD to SHA images; seven engineering notes with actual line numbers; safe deploy and reproducible documentation.

---

<a id="merged-docs-01-project-charter-md"></a>

## Project charter


### Problem statement
University rules can be old, contradictory, scanned or difficult to find. General chatbots may confidently invent answers. RAHBAR must **answer only from verifiable, indexed documents**, indicate its evidence, and decline absent answers, while surviving realistic Kubernetes failures.

### Primary outcome
From a clean clone, an evaluator provisions the stack in namespace `rahbar`, indexes an approved corpus via an isolated Job, asks an answerable question through the Ingress, receives valid evidence citations, asks an absent-topic question and sees an abstention, deletes an API pod, and observes continued service.

### Stakeholders
| Stakeholder | Needs | Proof |
|---|---|---|
| Course assessor | rubric adherence, design explanations | manifests, docs, checker, CI run, evidence |
| End user | honest, understandable answers | rendered answer, citations, no-answer state |
| Developer A | reliable app/index contracts | unit tests and real index/query integration |
| Developer B | deployable images/manifests | readiness, ingress, jobs, rollbacks, CI evidence |

### Constraints
Two developers; due Sunday 2026-11-08 23:59 PKT; local minikube with Calico; Python 3.12 starter; public/owned corpus only; no committed secrets; internet potentially required to fetch documents and invoke Ollama or a hosted provider; fixed evaluation rubric. No SSO/auth, production multi-tenant scaling, live university advisory guarantees, or mobile-native client is required.

### Decision boundaries
- **Must implement**: every Section 2–8 rubric and checker path.
- **May choose**: exact corpus documents, OCR tooling, measured chunking parameters, cache store (document in ADR), hosting provider and reindex cutover strategy.
- **Don't invent**: fee amounts, academic clauses, baseline scores, memory usage, screenshot evidence, GitHub status.

### Project-level success tests
1. A reader can trace each rubric item to owning code, test, evidence, and a responsible person.
2. Stubs run first; real RAG replaces them without changing public API contract.
3. All golden must-abstain questions decline; citation validity >=95%; recall@5 does not regress >5 percentage points from committed verified baseline.
4. A new reader follows README and obtains a working Ingress answer; a pod deletion and rollout do not interrupt availability.
5. Both members can demonstrate their own code and explain cross-component design choices.

### Definition of failure
Any secret in Git history, indexing in API startup, fabricated citations, missing model pin, absent evaluation, no clean-clone apply order or direct pushes to protected `main` threaten rubric compliance. Prioritize these over polish.

---

<a id="merged-docs-06-scope-and-decisions-md"></a>

## Scope, assumptions, and open decisions


### P0 implementation boundaries
Build the assignment rubric and starter `NotImplementedError` TODOs first. The critical path runs from local stub -> Docker/K8s stub -> real index -> real retrieval/generation -> abstention/evaluation -> integrated CI/CD -> evidence. Avoid building unrelated features.

### Architectural choices proposed for team approval
| Decision | Default proposal | Why | Freeze time |
|---|---|---|---|
| Corpus | public FAST-NUCES files in provided sources list | real, local domain, version pairs/tables | G0 after URL validation |
| Generation | `ollama-host` using `llama3.2:3b` | local model, avoids embedding+LLM resources inside minikube | G1; hosted provider is backup |
| Embedding | `nomic-embed-text`, same ConfigMap key in both workloads | starter default + pin guardrail | G0 |
| Chroma | single StatefulSet with 1 PVC, versioned logical collections and Chroma control registry | isolate writes from readers | G2; if simplifying, update safe-reindex design (consolidated in ADR 0003) |
| Cache | Redis with vector-aware matching and versioned key namespace | Redis already required with persistent PVC | G2 |
| Query scoring | similarity = 1 − Chroma cosine distance | starter Passage semantics | G0 |
| Split of work | A=RAG/eval, B=K8s/CI/UI | minimize source-file conflicts | immediately |
| Chunk parameters | experiment candidates, not final | rubric requires 3 measured configs | after first real corpus index |
| Relevance/cache thresholds | select by observed false-hit / abstention tests | cannot assume correct cutoff | after golden set |
| Registry | Docker Hub with `${{ github.sha }}` tag | assignment-required CD | before CD |

### Explicitly unresolved until confirmed
- Which 2023 policy URL actually downloads and proves the same policy was revised?
- Which item is truly image-only? Confirm `pdffonts` and PDF text extraction; if not, choose a replacement scanned document.
- How will the indexer pod receive real `corpus/raw/` documents? Recommended: an explicit init/download path from manifest into writable ephemeral storage, or a staged shared volume. **Never depend on PDFs committed to Git.**
- Does the chosen local host/OS expose `host.minikube.internal:11434` and which host CIDR needs NetworkPolicy egress?
- Does the CI e2e environment have a deterministic no-external-model fixture embedding mode that uses the **same vectors for indexer and query**? Implement and test it rather than silently using real Ollama in CI.
- Which actual values satisfy CPU/memory limits, top-k, relevance floor, cache threshold? Only measurements settle these.

### Change control
For contract, security, persistence or evaluation changes: create ADR, update requirements traceability, notify other developer and add a regression test. Bonus features may never block P0 completion.

---

