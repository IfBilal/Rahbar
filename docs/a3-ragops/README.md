# Assignment 03 — RAGOps: development harness (start here)

> **What this folder is.** The plan of record for CS4032 Assignment 03 (*RAGOps*, 185 marks, group of 2). It sits next to the Assignment 02 harness in `docs/` and plays the same role: a coding engineer (or coding agent) who reads these files in order knows **what to build, where it goes, how to prove it, and what to screenshot**. It is a *plan*, not evidence. Nothing in here claims a test, number, screenshot or run exists until you have produced it. `MEASURE` marks a value that must come from your own runs.

**Sources of truth, in order of authority**

1. `docs/A3.pdf` — the instructor's assignment (5 pages). Every sentence of it is turned into a numbered requirement in [`01-REQUIREMENTS.md`](01-REQUIREMENTS.md). If anything in this folder disagrees with the PDF, the PDF wins.
2. The reference paper — Xu, Weytjens, Zhang, Lu, Weber, Zhu, *RAGOps: Operating and Managing Retrieval-Augmented Generation Pipelines*, arXiv:2506.03401 (Jun 2025). Digested section by section in [`02-PAPER-DIGEST.md`](02-PAPER-DIGEST.md). The PDF says: *"Sections 3.2, 4.2, Table 1, Table 2, 5.1 and 6.2 matter most. Figure 3 is the map of this assignment."*
3. The working Assignment 02 code in this repository (RAHBAR). Its real state, and where A3 collides with it, is in [`03-GAP-ANALYSIS.md`](03-GAP-ANALYSIS.md).
4. [`14-INTERFACE-CONTRACTS.md`](14-INTERFACE-CONTRACTS.md) — the exact file formats, CLIs, exit codes and paths. When two files in this folder disagree, **14 wins**, then fix the other file.

> **Not in the PDF:** the submission deadline and the per-part mark split. The PDF only says *"Late submissions will receive zero marks"* and *"Marks: 185"*. Read the deadline off Google Classroom today and put it in [`11-IMPLEMENTATION-PLAN.md`](11-IMPLEMENTATION-PLAN.md) §1. Do not guess a split; treat every part as graded.

---

## The assignment in five lines

RAGOps = the **query pipeline** (ordinary DevOps lifecycle) **plus a data-management lifecycle** (ingest → verify → update data lake → update retrieval sources) that is tested against its own evolving data. You add that layer to RAHBAR and run all of it on Kubernetes:

| Part | One-line goal | Paper anchor | Main doc |
|---|---|---|---|
| A | Verify (4 checks) and incrementally update the data; quarantine, archive, restore; Batch B with planted problems | 4.2.1–4.2.4 | [05](05-DATA-MANAGEMENT.md) |
| B | Golden set (≥25) and a three-level offline suite (module, component, end-to-end) with seeds and one command | 4.2.5, Table 1 | [06](06-OFFLINE-TESTING.md) |
| C | Change one thing, compare baseline vs candidate on all three levels, gate it with configurable thresholds | 4.1(d), 4.2.5, 4.2.6 | [07](07-CHANGE-AND-RELEASE.md) |
| D | One JSON trace per query, a trace tool, metrics, guardrail logging, root cause from a trace | 3.2.3, 5.1, Table 2 | [08](08-OBSERVABILITY-TRACING.md) |
| E | Live-query coverage against the golden set, data drift, close the gap, non-zero exit below threshold | 4.2.7 | [09](09-DRIFT-COVERAGE.md) |
| F | Everything on Kubernetes: Jobs, CronJob, PVCs, ConfigMap thresholds, candidate Deployment, rollout and undo | 4.1(e)(f), 5.1 | [10](10-KUBERNETES.md) |
| G | ≤8-page report, two tables, short answers (a)–(f), contribution table, screenshots appendix | — | [12](12-REPORT-AND-EVIDENCE.md) |

**Demo rule that overrides everything:** the pipeline must run on Kubernetes at the demo. Plain `docker run` / Docker Compose = **0 for the demo**. At the demo you will (1) run the evaluation as a Kubernetes Job, (2) open a trace, (3) ingest a small batch of documents you have never seen with your ingestion Job. See [`13-DEMO-RUNBOOK.md`](13-DEMO-RUNBOOK.md).

---

## Reading order

| Reader | Read, in this order |
|---|---|
| **Everyone, first hour** | this file → [01](01-REQUIREMENTS.md) → [02](02-PAPER-DIGEST.md) → [03](03-GAP-ANALYSIS.md) → [04](04-ARCHITECTURE.md) |
| **Developer A (data + evaluation)** | [05](05-DATA-MANAGEMENT.md) → [06](06-OFFLINE-TESTING.md) → [07](07-CHANGE-AND-RELEASE.md) → [09](09-DRIFT-COVERAGE.md) → [14](14-INTERFACE-CONTRACTS.md) |
| **Developer B (cluster + observability)** | [08](08-OBSERVABILITY-TRACING.md) → [10](10-KUBERNETES.md) → [13](13-DEMO-RUNBOOK.md) → [14](14-INTERFACE-CONTRACTS.md) |
| **Both, before every work session** | [11](11-IMPLEMENTATION-PLAN.md) (pick a task) |
| **Both, last two days** | [12](12-REPORT-AND-EVIDENCE.md) and [13](13-DEMO-RUNBOOK.md) |

## File index

| # | File | Purpose |
|---|---|---|
| — | `README.md` | this index and the agent operating manual |
| 01 | [`01-REQUIREMENTS.md`](01-REQUIREMENTS.md) | the PDF as a numbered requirement ledger; evidence and screenshot map; open questions for the instructor |
| 02 | [`02-PAPER-DIGEST.md`](02-PAPER-DIGEST.md) | the paper, end to end, mapped onto the assignment; what the paper has that the assignment does not require |
| 03 | [`03-GAP-ANALYSIS.md`](03-GAP-ANALYSIS.md) | what RAHBAR already does, what A3 needs, and the design collisions between them |
| 04 | [`04-ARCHITECTURE.md`](04-ARCHITECTURE.md) | target architecture, Figure 3 mapping, data-lake layout, ledger, decisions D-01…D-15 |
| 05 | [`05-DATA-MANAGEMENT.md`](05-DATA-MANAGEMENT.md) | Part A in full: verification checks, quarantine, incremental update, archive/restore, Batch B |
| 06 | [`06-OFFLINE-TESTING.md`](06-OFFLINE-TESTING.md) | Part B in full: golden set, three levels, metric formulas, stochasticity, one-command suite |
| 07 | [`07-CHANGE-AND-RELEASE.md`](07-CHANGE-AND-RELEASE.md) | Part C and F3: the change experiment, gate config, release decision, rollback |
| 08 | [`08-OBSERVABILITY-TRACING.md`](08-OBSERVABILITY-TRACING.md) | Part D: trace record, instrumentation points, trace tool, metrics, guardrail logging, root cause |
| 09 | [`09-DRIFT-COVERAGE.md`](09-DRIFT-COVERAGE.md) | Part E: live queries, coverage, drift, closing the gap |
| 10 | [`10-KUBERNETES.md`](10-KUBERNETES.md) | Part F: every manifest, apply order, rollout/undo mechanics, resources, network policy |
| 11 | [`11-IMPLEMENTATION-PLAN.md`](11-IMPLEMENTATION-PLAN.md) | work breakdown T01…T63, owners, dependencies, machine-time plan, schedule, gates, cut list, risks |
| 12 | [`12-REPORT-AND-EVIDENCE.md`](12-REPORT-AND-EVIDENCE.md) | Part G: page budget, table drafts, short-answer guidance, screenshot checklist, README content |
| 13 | [`13-DEMO-RUNBOOK.md`](13-DEMO-RUNBOOK.md) | the demo script, rehearsal, failure modes, viva questions |
| 14 | [`14-INTERFACE-CONTRACTS.md`](14-INTERFACE-CONTRACTS.md) | schemas, CLIs, exit codes, env vars, paths — the single source for formats |

---

## Operating manual for a coding agent

### Non-negotiable rules

1. **Honesty.** *"Every number in your report must come from runs of your own pipeline, and the result files must be committed."* Never invent a metric, a trace, a screenshot, a count or a run. If a step has not been run, write `MEASURE` and say so. This mirrors the A2 rule and the A2 deduction culture.
2. **Kubernetes or nothing.** Every Part-F claim must be demonstrable with `kubectl` on the local cluster. Docker-only = demo 0.
3. **Only the ingestion Job writes the vector store.** The API, the evaluation Job, the trace tools and the coverage tools are read-only against Chroma. `tests/test_boundaries.py` already enforces this for the API; extend it (see [`14`](14-INTERFACE-CONTRACTS.md) §10).
4. **No secret in Git, ever** (A2 deduction: −20 for history). New config goes in ConfigMaps; the LLM key stays a runtime Secret.
5. **Both members commit.** The PDF requires commits from both. Team rule: **no `Co-Authored-By` or other AI-attribution trailers in commit messages or PR descriptions**; disclose AI use only in the report's AI statement and `docs/AI-USAGE.md`.
6. **Do not change the instructor's requirements.** *"There will be no credit if the given requirements are changed."* Where the PDF is ambiguous, pick the reading recorded in [`01`](01-REQUIREMENTS.md) §9 and write it into the report.
7. **Do not weaken A2.** The A2 guarantees (citation whitelist, abstention, superseded filter, embedding pin, single writer, NetworkPolicy, HPA, probes) must still hold. `make test` and `make check` stay green on every merge.
8. **Reproducibility.** Every result file records: UTC timestamp, git SHA, image digests, golden-set hash, corpus-state hash (ledger digest), embed model + version, collection, seeds, config hash. See [`14`](14-INTERFACE-CONTRACTS.md) §5.

### Task loop (same discipline as A2)

1. Pick a task `Txx` from [`11`](11-IMPLEMENTATION-PLAN.md). Confirm its predecessors are really done.
2. Read the doc named in the task, then [`14`](14-INTERFACE-CONTRACTS.md) for the exact contract.
3. Branch off `dev`: `feat/a3-<owner>-Txx-<slug>`. No direct push to `main` (A2 branch protection stays on).
4. Write the test first for anything with a formula or an exit code (metrics, gate, verification checks, coverage). No network, no model in unit tests — use the fakes in `api/tests/fakes.py` and `indexer/tests/fakes.py`.
5. Run `make lint`, `make test`. For cluster tasks, run the acceptance command listed in the task and **keep the real output** under `docs/a3-evidence/` (create it) for the appendix.
6. Open a PR to `dev`: change summary, files, proof commands with real exit codes, rollback note, which requirement IDs it closes (from [`01`](01-REQUIREMENTS.md)). The other member reviews.
7. A task is `DONE` only when its acceptance command passes **and** the consumer task can use its output.

### Ownership (to avoid merge conflicts)

| Owner | Primary paths |
|---|---|
| **A — data and evaluation** | `indexer/pipeline/**` (verify, lake, ledger, incremental, ops), `corpus/batch-b/**`, `eval/**` (golden, pairs, live queries, judge labels, results), `ragops/suite/**`, `ragops/gate/**`, `ragops/coverage/**`, `ragops/config/{suite,gate,coverage,candidates}` |
| **B — cluster and observability** | `k8s/**`, `ragops/trace/**`, `api/app/services/trace.py`, `api/app/services/rails.py`, `api/app/routes/metrics.py`, `api/app/routes/retrieve.py`, `Dockerfile`s, `.github/workflows/**`, `scripts/ragops/**` |
| **Shared (agree the interface first)** | `api/app/schemas.py`, `api/app/config.py`, `api/app/main.py`, `api/app/services/answer.py`, `api/app/retrieval/chroma.py`, `README.md`, `k8s/README.md`, the report |

Both members must be able to explain every part at the demo, so the split is for *building*, not for *knowing*: swap review roles so each of you reads the other's half.

### Definition of done for the whole assignment

The single checklist is [`12-REPORT-AND-EVIDENCE.md`](12-REPORT-AND-EVIDENCE.md) §10. In short: repo with `k8s/`, `eval/`, `traces/`, README (commands for A–F), `k8s/README.md`; committed result files; an 8-page report PDF with the two tables, the results, the short answers, contribution table and AI statement; the screenshot appendix labelled A…F; and a clean-cluster rehearsal that reaches a working pipeline by applying the manifests.
