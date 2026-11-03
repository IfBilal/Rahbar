# RAHBAR — coding-agent operating manual

## Package boundary and original files

> **Supplementary documentation only — not a replacement for the starter kit.** This ZIP intentionally contains **25 new standalone Markdown guides, all at ZIP root**. It does **not** contain or overwrite any Markdown supplied with `rahbar-starter.zip` (`README.md`, `STARTER.md`, `docs/CORPUS.md`, `docs/PIPELINE.md`, `docs/FAILURE-ANALYSIS.md`, `docs/ENGINEERING-NOTES.md`, `docs/AI-USAGE.md`, the fixture Markdown, or the ADR template). Keep all of those original files in your project. The instructor requires several **exact submission paths**; implement and update the originals in those paths using these guides as working plans. If names appear similar, this guide is for implementation and the starter file is the deliverable.

**Reading order:** `STARTER.md` (original) → `AGENTS.md` → `PROJECT-GUIDE.md` → `PRD.md` → `INTERFACE-CONTRACTS.md` → `CRITICAL-PATH.md` → `PHASES.md`. **Never delete or overwrite the starter-provided Markdown.** Use the supplementary `CORPUS-PLAN.md`, `PIPELINE-IMPLEMENTATION.md`, `FAILURE-EXPERIMENTS.md`, `ENGINEERING-NOTES-GUIDE.md`, and `AI-ASSISTANCE-PLAYBOOK.md` to complete the original required `docs/*.md` reports.

**Mandatory for every coding agent.** This is the highest-level project execution guide. The attached assignment PDF and actual starter code are authoritative; this document is a *plan*, not evidence that code exists or passes. Read `STARTER.md` in the real starter project first. Every programming session must select a WBS task from `CRITICAL-PATH.md`, its phase from `PHASES.md`, and the acceptance checks from `DEVELOPMENT-FLOW.md`.

### Source-of-truth precedence
1. Instructor's **Assignment 02 — RAHBAR: Grounded RAG on Kubernetes** (20 pages; due **2026-11-08 23:59 PKT**) and `scripts/check_submission.py` for grading constraints.
2. `STARTER.md` and starter code for *currently existing* signatures, source paths and known stubs.
3. `INTERFACE-CONTRACTS.md` and accepted ADRs for approved design.
4. `PRD.md` for required functionality, `CRITICAL-PATH.md` for dependency/task ownership and `PHASES.md` for phased acceptance.
5. Other implementation docs for detailed recipes. If documents disagree, **do not guess**: inspect the source and open a jointly reviewed contract/ADR change.

### Safe editing rules
- **A's primary paths:** `corpus/**`, `indexer/pipeline/**`, `api/app/retrieval/**`, `api/app/providers/**`, `api/app/services/**`, `eval/**`. **B's primary paths:** `k8s/**`, `.github/workflows/**`, `ui/**`, Dockerfiles, `api/app/routes/health.py`, `api/app/routes/metrics.py`.
- **Shared:** `api/app/schemas.py`, `api/app/config.py`, `api/app/main.py`, `README.md`, API-level integration tests and cross-domain docs. Shared edits require an agreed interface and peer review. An agent must not silently modify another developer's path.
- Use a fresh feature branch off `dev` (`feat/a-Txx-slug` or `feat/b-Txx-slug`); no direct push to protected `main`; every PR links the task, its dependencies and tests.
- Keep the starter's `POST /api/ask`, Pydantic `Answer`/`AskResponse`, `Retriever` and `LLMProvider` contracts stable unless both people approve a change; never expose `reasoning` to a user.
- Never place passwords, tokens or real Base64 Secrets in source, manifests or Git history. Use GitHub Secrets and Kubernetes Secrets; never log user keys or full sensitive payloads.

### Irreversible architecture invariants
- API replicas are **readers only**. Only Kubernetes indexer Job/CronJob writes Chroma; no indexing during API startup.
- Both API and indexer use the **same ConfigMap `EMBED_MODEL`**; store actual model name and vector dimension in Chroma, and refuse readiness when incompatible.
- Preserve `source`, `section`, `page`, `doc_version`, `superseded` on every indexed chunk; exclude superseded documents by default.
- Output grounded evidence only, require per-request retrieved citation whitelist, abstain on absent evidence, schema-validate and retry once then safe fallback.
- Redis semantic cache must skip follow-ups, abstentions, invalid/unsupported answers, use a measured threshold and reject old index generations after re-indexing.
- Keep `rahbar` namespace, 3 API replicas, startup/liveness/readiness probes, Chroma StatefulSet/PVC, Redis PVC, NetworkPolicy, HPA 3–8 and explicit image SHA for CD.
- **Do not claim a test, benchmark, screenshot, deployment, CI run or evidence file exists until it has actually been produced.** Never fabricate results or policy version differences.

### Mandatory coding-agent task loop
1. Identify `Txx` (owner, dependencies) and the corresponding `Gx` gate; verify all hard prerequisites are actually complete.
2. Open only needed files; examine starter TODOs and existing tests. State the minimal implementation plan and whether a shared contract must change.
3. Make small, reviewable edits in allowed paths; add positive and negative tests (no network for unit tests).
4. Run focused tests, then `make lint` and `make test`; perform required cluster/evaluation commands when the phase gate demands them. Preserve actual exit codes.
5. Write a concise handoff in PR: change summary; files changed; proof commands/results; security/rollback implications; known open blockers; consumer/next task.
6. Never label `DONE` unless acceptance criteria and the consumer's integration verification are satisfied. If blocked, record the blocker and work on a task that has no unmet predecessors.

### Fast reading routes
- **Agent starting task:** `CRITICAL-PATH.md` → `PHASES.md` → relevant technical doc → `INTERFACE-CONTRACTS.md` → `TESTING-EVALUATION.md`.
- **Developer A:** `CORPUS-PLAN.md`, `PIPELINE-IMPLEMENTATION.md`, `RAG-QUERY.md`, `TESTING-EVALUATION.md`.
- **Developer B:** `KUBERNETES.md`, `SECURITY-OBSERVABILITY.md`, `CI-CD.md`, `DEPLOYMENT-RUNBOOK.md`.
- **Both:** `TWO-DEVELOPER-PLAN.md`, `DEVELOPMENT-FLOW.md`, `SUBMISSION-AND-EVIDENCE.md`, and ADRs.

### Response convention for agents
Each task's final report should contain: `Task / Owner / Dependencies verified / Changed files / Tests run (with actual results) / Contract changes / Evidence location / Remaining risks / Next unblocked task`. Do not substitute a prose claim for an actual tool result.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-agents-md"></a>

## RAHBAR — coding-agent operating instructions


**Read before modifying any file.** This repository is the **provided `rahbar-starter.zip` plus implementation guidance**, not a finished project. The authoritative assignment is **Assignment 02 — RAHBAR: Grounded RAG on Kubernetes**, due **2026-11-08 23:59 PKT**. The grading requirements outrank suggestions in these docs. `STARTER.md` and existing starter interfaces are the source of truth for what is already implemented.

### First five reads (in order)
1. `STARTER.md` and `README.md`.
2. `PRD.md`, `PRD.md`, `ARCHITECTURE.md`.
3. `INTERFACE-CONTRACTS.md` and `AGENTS.md`.
4. `CRITICAL-PATH.md`, `TWO-DEVELOPER-PLAN.md`, and your assigned `PHASES.md`.
5. The **actual source files** referenced in your task before making edits. Treat a doc-to-code disagreement as an issue to resolve, not permission to silently break an interface.

### Mandatory behavior
- **Never index inside the API process.** `indexer` alone writes Chroma; API replicas are read-only.
- Preserve `POST /api/ask` -> `AskResponse` in `api/app/schemas.py`, `GET /healthz`, `/readyz`, `/metrics` and `/api` Ingress routing. Any contract change needs an ADR and explicit approval from both developers.
- Keep `EMBED_MODEL` identical in API and indexer and validate the name and vector dimension in active Chroma collection metadata. For the **dummy** index, use `EMBED_MODEL=dummy-768`; do not confuse fake vectors with live RAG.
- Never log or commit secrets, source PDFs from public websites, fabricated test results, grader evidence, or model `reasoning`. Retain provided fixture files.
- Use the starter's versions and package names unless a tested, recorded migration is necessary: Chroma HTTP client/server `1.0.12`, Python `3.12`, FastAPI, Pydantic, Redis.
- No new dependencies, schemas, ports, service names, or file owners without checking `INTERFACE-CONTRACTS.md` and notifying the other developer.
- Prefer small changes with unit tests and a runnable command. Do not claim passing tests without executing them.
- Implement real behavior, not TODO-shaped examples. All starter `NotImplementedError` and `STARTER-TODO` markers must be resolved before submission.

### Task execution protocol (required for each agentic IDE session)
1. Quote your task ID and owner from `CRITICAL-PATH.md`. Read its blocking dependencies.
2. Identify *exact* files to edit, interfaces consumed/produced, and the other developer's overlapping files. If overlap: stop and arrange a handoff.
3. State a brief implementation plan, then perform the minimum complete change.
4. Run targeted tests, lint/types, and applicable manifest validation; record **actual** command and result.
5. Update the task checklist, references and evidence (or a truthful `NOT YET RUN`), then open a PR following `TWO-DEVELOPER-PLAN.md`.
6. Ask for a human review on security, claims about accuracy, and release evidence.

### Forbidden shortcuts
- Don't replace a graded component with a hard-coded demonstration answer.
- Don't bypass abstention, citation validation, cache invalidation, readiness, or the CI gate to make green checks.
- Don't run live-network/real-LLM unit tests in CI. Use the supplied stubs and fixture corpus.
- Don't merge directly into `main`, publish `latest`, store live credentials in a manifest, or mark acceptance tests complete from inspection alone.

### Communication format
`TASK ID | owner | branch | files touched | contract impact | blockers | tests actually run | next handoff`.
A task is complete only with the `DEVELOPMENT-FLOW.md` checklist satisfied.

---

<a id="merged-docs-19-agent-playbook-md"></a>

## Agentic IDE development playbook


### Task prompt template (copy to agent)
> Implement **[TASK-ID]** from `CRITICAL-PATH.md` under `PHASES.md`. Follow `AGENTS.md`, `STARTER.md`, `INTERFACE-CONTRACTS.md`, target `the corresponding consolidated technical specification`, and the actual starter source. Files allowed: **[explicit paths]**. Dependencies **[IDs]** must be complete. Do not change other-owner files or public schemas. Write unit tests first for normal and failure states, implement, run relevant tests/lint, and report commands/results and remaining blockers. Never mark live cluster/eval evidence as passed without running it. Provide a PR summary and explicit handoff.

### Required agent output
```
TASK: RAG-xx | OWNER: A/B | BRANCH: feat/...
FILES: ...
CONTRACTS: unchanged / proposed change + ADR
IMPLEMENTED: ...
TESTS RUN: command -> PASS/FAIL (copy real output summary)
NOT RUN: cluster/model/eval evidence with reason
BLOCKERS: ...
HANDOFF: consumer, exact interface, smoke invocation
```

### Session boundaries
Keep sessions bounded to one WBS task or one independent directory. An agent should not simultaneously own `api/app/config.py` and `k8s/base/configmap.yaml` unless B/A agreed on env contract first. Stop if a file edit crosses another developer's ownership. Do not accept a green agent assertion instead of executable proof.

### Good implementation sequence
1. Confirm existing types/tests; identify exact TODO comments.
2. Write a failing test using stub components, no network.
3. Implement with small typed functions and isolated network adapter.
4. Test malformed model JSON, no retrieval, superseded, missing cache, timeout, and poisoned prompt; not only success case.
5. Run targeted test and static check, then integration smoke when dependency is available.
6. Update relevant docs and evidence; PR to `dev`; reviewer checks changed files and reproducibility.

### Review red flags
A citation appears without a retrieved passage. API startup calls any indexer method. Readiness uses `LLM_PROVIDER` availability but liveness touches a dependency. Keys in logs, `Secret.data` in Git, `:latest` in a deployment. Fixture CI calls a hosted LLM, uses non-reproducible network, or silently ignores failing golden. `eval/baseline.json` is a fabricated placeholder. Chroma host/client versions differ. Kustomize applies a live Secret placeholder. Those changes must not merge.

### Source-versus-inference convention
Use `Verified from starter`, `Required by assignment`, `Proposed design`, and `Measured on our stack` explicitly in PRs and docs. If you can't support a number with a command/artifact, leave it as `MEASURE` and don't claim it passed.

---

<a id="merged-docs-05-starter-audit-md"></a>

## Instructor starter kit audit — confirmed from supplied ZIP


**Method:** paths and TODO markers inspected inside the uploaded `rahbar-starter.zip`. Status is as of source snapshot, **not evidence of a functioning deployed system**.

| Component | Existing, usable contract | Missing/required implementation | Owner |
|---|---|---|---|
| `api/app/schemas.py` | `AskRequest`, `Passage`, `Citation`, `Answer`, `RetrievedRef`, `AskResponse` | keep stable; add optional `cached` only after agreement | Both |
| `api/app/main.py` | FastAPI lifespan, middleware, JSON request IDs, route mounting | embed pin at startup / dependency wiring | B (A review) |
| `api/app/routes/ask.py` | `POST /api/ask` | keep route and response type | A |
| `api/app/routes/health.py` | `/healthz` process-only | `/readyz` real Chroma/Redis/collection/pin checks | B |
| `api/app/routes/metrics.py` | request count + latency | detailed retrieval/gen/cache/abstain/token metrics | B + A instrumentation |
| `api/app/services/answer.py` | `retriever.retrieve` -> `provider.generate` -> `AskResponse` | cache, floor, abstain, prompt safety, retry, citation guard, fallback | A |
| `api/app/retrieval/{base,stub,chroma}.py` | stable Protocol, stub passages | real Chroma HTTP query and embed, version filter | A |
| `api/app/providers/llm/{base,stub,ollama,hosted}.py` | provider Protocol + reliable stub | real selected provider + structured response handling | A |
| `indexer/pipeline/run.py` | `discover`, front matter, `--dummy`, ordered stages | robust implementation of five stages | A |
| `indexer/pipeline/models.py` | Document/Page/Chunk and required metadata | stable chunk ID policy, optional measured extra fields | A |
| `indexer/pipeline/{extract,clean,chunk,embed,store}.py` | signatures and TODOs | all real behavior, OCR toolchain, metadata/dim | A |
| `indexer/pipeline/dummy.py` | 3 fake vectors, `embed_model=dummy-768`, dim=768 | dev-only; keep testability | A |
| `ui/index.html`, `ui/nginx.conf` | working static chat, same-origin `/api/ask`, nginx port 8080 | Dockerfile and smoke tests | B |
| `corpus/fetch.py`, `sources.example.yaml` | source fetch, SHA manifest, `_index.json` workflow | verify chosen URLs, actual 6+ docs/40 pages, filled CORPUS.md | A |
| `eval/run_eval.py` | CLI/http calls/output writing, gate constants | 4 TODO functions, golden 15+, baseline based on real results | A |
| `eval/fixtures/*` | 3 fictional MD docs + 6-question fixture golden | adapt CI to index fixtures; do not claim full corpus score | Both |
| `k8s/base`, `k8s/overlays/{dev,prod}` | empty directories | every object and kustomizations | B |
| `.github/workflows` | empty | ci.yml and cd.yml | B |
| Dockerfiles | absent | api, indexer, ui + two `.dockerignore` | B |
| `scripts/check_submission.py` | extensive mechanical checker | run and resolve substantive failures | Both |
| `docs/{CORPUS,PIPELINE,FAILURE-ANALYSIS,ENGINEERING-NOTES,AI-USAGE}.md` | prompt templates | truthful results, code line refs and evidence | shared |

### Unmodified public interface — freeze first
- `POST /api/ask` with body `{ "question": "..." }`, length 3–500 -> `AskResponse` (`request_id`, `answer`, `citations`, `answered_from_context`, `confidence`, `retrieved`, `provider`).
- `Answer` provider contract additionally includes `reasoning`; **strip it before response**.
- `Passage.score` is **cosine similarity**; the Chroma client returns **distance**, so convert `score = 1 - distance`.
- `Retriever.retrieve(question, k) -> list[Passage]` and `LLMProvider.generate(question, passages) -> Answer` are synchronous in supplied code.
- Chroma HTTP client `chromadb-client==1.0.12`; server should match image `chromadb/chroma:1.0.12`.
- `indexer/pipeline.run` discovers `_index.json` or Markdown front matter; dummy index stores `dummy-768`, not `nomic-embed-text`.
- Eval fixture golden file has 6 questions, real golden must contain **at least 15**, from actual confirmed corpus.

### Important trap: starter test and documentation are not completion
`/readyz` currently always returns 200; `eval/run_eval.py` has `NotImplementedError`; `ChromaRetriever.retrieve`, provider(s), the five stages and live cluster are missing. No project outcome should be marked passed solely because the stub UI gives a response. Check with `grep -R 'STARTER-TODO\|NotImplementedError' api indexer eval` before final release.

### Recommendations that are *not* supplied requirements
Versioned immutable Chroma collections + Chroma registry active pointer (safe-reindex design (consolidated in ADR 0003)), lexical exact-term assist (optional hybrid design (consolidated in ADR 0002)), and branch-per-task coordination are recommended designs. They require implementation and peer approval; don't claim them as features in current starter.

---

