# Product requirements, traceability and acceptance

**Authority:** Assignment 02 sections 1–8 and the inspected starter contracts. This file combines the original product brief, requirement traceability, acceptance, and quality attributes. Treat acceptance as a testable obligation rather than a claim of delivery. If the PDF and this plan differ, follow the PDF.

**Agent task:** for any feature, identify the relevant `FR-xx`/`Rxx` and work breakdown `Txx`, add a unit/integration test, and attach output before changing its status to verified. Required quality numbers must be measured, not invented.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-02-prd-md"></a>

## Product requirements document (PRD)


### 1. Product summary
**Product:** RAHBAR — grounded question-answering for a real university-style document corpus. **Audience:** students and evaluators. **Surface:** simple browser chat, nginx and FastAPI behind one Kubernetes Ingress. **Core promise:** *If the indexed documents don't support the answer, say so; otherwise cite source/section/page.* It is not an official policy decision-maker.

### 2. User journeys
#### UJ-01 Grounded question
Student enters a 3–500 character question. System checks eligible semantic cache, embeds the question using the indexed embedding model, retrieves top `k` passages excluding superseded versions by default, constructs an evidence-only prompt, validates structured model output and returns an answer with citations (or declines if ungrounded).

#### UJ-02 Version-sensitive question
Student asks about today's rule: use current version by default. If explicitly asking about a 2023 rule, allow the historical version under a deliberate version-selection path. Never silently conflate versions or rely only on prompt wording to fix old-policy retrieval.

#### UJ-03 Absent-topic question
Student asks about hostel application details when the corpus deliberately omits hostel policy. No relevant passages exceed relevance floor; system sets `answered_from_context=false`, shows clear limits, and does not give guessed procedure or bogus references.

#### UJ-04 Service failure and restore
One API replica is deleted; remaining ready replicas continue. A slow vector store makes replicas **unready** without liveness-triggered restart storms. The indexer is rerun without rebuilding API pods; the cache is invalidated on publish.

#### UJ-05 Evaluator/maintainer
Maintainer performs a reproducible download, verifies checksums, indexes, runs `eval/run_eval.py`, examines recall@3/@5, citation validity and abstention; CI rejects regressions, and the pipeline publishes SHA-tagged images after approval.

### 3. Functional requirements
| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| FR-01 | Validate question length 3–500 | P0 | invalid inputs -> 422 |
| FR-02 | Extract all eligible public/owned PDFs, HTML, MD and TXT; detect scanned pages and OCR | P0 | documented scan + readable output or honest limitations |
| FR-03 | Clean without losing sections and tables | P0 | table before/after + named cleaning rules |
| FR-04 | Structure-aware overlap chunking with traceable metadata | P0 | five required metadata fields on every chunk; 3 measured settings |
| FR-05 | Index once per corpus change with one Job, weekly CronJob | P0 | Job exits, re-run does not redeploy API |
| FR-06 | Pin embed model and dimension across API and indexer | P0 | mismatch -> 0/1 READY + diagnostic log |
| FR-07 | Retrieve top k with superseded filtering and score conversion | P0 | version and exact-term tests pass |
| FR-08 | Evidence-only augmented prompt, pluggable provider, schema validation | P0 | no freeform malformed output reaches UI |
| FR-09 | Truthful abstention + citation whitelisting to retrieved chunks | P0 | must-abstain 100%; no invented citations |
| FR-10 | Semantic cache with data-tuned threshold, safe exclusions and reindex invalidation | P0 | no follow-up/abstention/invalid cache entries; stale cache cannot survive index switch |
| FR-11 | UI shows answer, citations, errors, no-answer and optionally cached badge | P0 | manual test through Ingress |
| FR-12 | JSON logs, request IDs, detailed metrics | P0 | /metrics and JSON log evidence |
| FR-13 | Automated retrieval and generation quality evaluation | P0 | >=15 golden questions in required mix and CI gate |
| FR-14 | All mandated Kubernetes objects, security and probes | P0 | manifest + live cluster proof |
| FR-15 | CI lint, test, image build, vulnerability scan, manifests and e2e; CD SHA images | P0 | successful required workflows with protected main |

### 4. Nonfunctional requirements
- **Availability:** API Deployment has 3 replicas; rolling update `maxUnavailable:0, maxSurge:1`, deletion of one pod does not disrupt reachable endpoint.
- **Persistence:** Chroma StatefulSet PVC, Redis Deployment PVC/AOF; no data loss expected from deleting an API pod.
- **Resource discipline:** resource requests and limits on every container; measure peak indexer memory with `kubectl top pods`; HPA 3–8 replicas with CPU request and metrics-server.
- **Security:** namespace isolation; non-root containers with read-only root; drop capabilities; dedicated ServiceAccounts; no plaintext secrets in Git; default-deny NetworkPolicy and intentional exceptions.
- **Observability:** stdout JSON, request_id, retrieval/generation latency, hits, abstentions, fallbacks and token usage.
- **Quality:** >=60% app package test coverage, citation validity >=95%, must-abstain 100%, recall@5 regression no greater than 5 percentage points from verified baseline.
- **Reproducibility:** Docker Hub images tagged by commit SHA; docs explain apply order, clean clone and expected validation.

### 5. Constraints and out of scope
UI is supplied; don't rebuild it unless required for correctness. No authentication, billing, user profiles, vector databases other than assignment Chroma, always-on in-cluster LLM, sophisticated RBAC application layer or bulk proprietary scraping is required. Hybrid lexical retrieval is an **optional recommended quality enhancement**, not a substitute for implementing dense Chroma retrieval.

### 6. Dependencies and open decisions
**Given and verified in starter:** `AskRequest`, `Answer`, `AskResponse`, `Passage`, retrieval/provider Protocols; dummy writer, fixtures, evaluator shell. **Decide and document:** real source availability, chosen LLM mode (`ollama-host` suggested), relevance threshold, chunk size/overlap after tests, semantic threshold after zero-false-hit tuning, live reindex publish strategy, image registry/repo owner, and the exact corpus delivery mechanism into the Job.

### 7. Launch gate
Real corpus fetched and hashed; all 7 corpus properties documented; successful full index; correct + declined answers via ingress; scale/restart/rollback tested; CI/CD successful; `make check` clean; artifacts and evidence committed. Every check requires command output, not merely an implementation claim.

---

<a id="merged-docs-03-requirements-traceability-md"></a>

## Assignment requirements traceability matrix


This is a work-tracking map, **not a pass certificate**. R01–R30 map the instructor PDF and the starter checker to responsible code, owned tasks, tests and final evidence. All are `NOT VERIFIED` until linked to actual output. Update statuses and paths after implementation; do not claim success based only on a document.

| ID | Required behavior | Owner | Source / planned artifact | Proof to capture | Status |
|---|---|---|---|---|---|
| R01 | Corpus has >=6 public/owned docs, >=40 pages | A | `CORPUS-PLAN.md; corpus/MANIFEST.md` | source checksums and page count | NOT VERIFIED |
| R02 | Two revisions of one policy; mark superseded | A | `corpus/sources.yaml; indexer/pipeline/models.py` | two version-sensitive golden questions | NOT VERIFIED |
| R03 | Scanned image-only PDF is detected and OCR attempted | A | `indexer/pipeline/extract.py; PIPELINE-IMPLEMENTATION.md` | pdffonts/extracted text before-after | NOT VERIFIED |
| R04 | Real tables + long definitions preserved | A | `indexer/pipeline/clean.py; chunk.py` | table sample + chunk inspection | NOT VERIFIED |
| R05 | Absent topic + exact-term content in corpus | A | `CORPUS-PLAN.md; eval/golden.yaml` | abstain + exact-term test | NOT VERIFIED |
| R06 | 5-stage indexer and graded metadata + model/dimension | A | `indexer/pipeline/{extract,clean,chunk,embed,store}.py` | Job logs + Chroma collection metadata | NOT VERIFIED |
| R07 | 3 chunk configurations measured; storage amplification | A | `PIPELINE-IMPLEMENTATION.md` | measured recall@5 table, no placeholder | NOT VERIFIED |
| R08 | Question length and eight-step query flow | A | `api/app/routes/ask.py; services/answer.py` | 422, cache, retrieval, generation unit tests | NOT VERIFIED |
| R09 | Current-version filter, historical exception | A | `api/app/retrieval/chroma.py` | golden version pair + no superseded leak | NOT VERIFIED |
| R10 | Cache similarity tuned with zero false hits | A | `api/app/services/cache.py; PIPELINE-IMPLEMENTATION.md` | two/three thresholds + false hit evidence | NOT VERIFIED |
| R11 | Never cache follow-up, abstention, invalid; invalidate on reindex | A | `api/app/services/cache.py; indexer/pipeline/store.py` | cache regressions pre/post reindex | NOT VERIFIED |
| R12 | Schema provider, 1 retry, safe fallback and 0..0.3 temperature | A | `api/app/providers/llm/*; services/answer.py` | malformed JSON + timeout tests | NOT VERIFIED |
| R13 | No fabricated citations; abstain below floor; injection test | A | `api/app/services/*; api/tests` | cite whitelist and injection test | NOT VERIFIED |
| R14 | Pluggable LLM provider and separate embed pin | A | `api/app/providers/llm/*; config.py` | stub/real selected by env; metadata mismatch | NOT VERIFIED |
| R15 | Namespace, 3 API replicas, UI, StatefulSet+PVC, Redis+PVC | B | `k8s/base/*` | kubectl get/describe endpoints and PVC | NOT VERIFIED |
| R16 | Indexer Job + weekly CronJob; 4 Services + Ingress | B | `k8s/base/*; Makefile` | one-shot logs + ingress smoke | NOT VERIFIED |
| R17 | ConfigMap/Secret, deny-default NetworkPolicy, HPA 3..8 | B | `k8s/base/*` | DNS, blocked UI->Chroma; HPA target | NOT VERIFIED |
| R18 | Startup,liveness,readiness; mismatch blocks ready | B | `k8s/base/api.yaml; api/app/routes/health.py` | 0/1 READY mismatch test | NOT VERIFIED |
| R19 | Resource requests/limits, rollout + rollback + endpoint count | B | `k8s/base/*; docs/evidence/*` | kubectl top; rollout history; endpoints | NOT VERIFIED |
| R20 | Nonroot, read-only root, token rules, secret hygiene | B | `Dockerfiles; k8s/base/*; .gitignore` | pod securityContext and secret scan | NOT VERIFIED |
| R21 | JSON request logs + metrics covering retrieval, gen, cache, tokens | B | `api/app/logjson.py; routes/metrics.py` | /metrics scrape and structured stdout | NOT VERIFIED |
| R22 | >=15 golden: 8 ordinary,2 version,2 exact,2 abstain,1 injection | A | `eval/golden.yaml` | labeled question count + source references | NOT VERIFIED |
| R23 | Recall@3/@5, by type; citation validity; abstain 100% | A | `eval/run_eval.py` | results.json saved from live stack | NOT VERIFIED |
| R24 | CI gate: recall@5 <=5pp drop, >=95% citations, 100% abstain | A | `eval/run_eval.py; eval/baseline.json` | intentional regression fails CI | NOT VERIFIED |
| R25 | Break 4 stages, diagnose and document | A | `FAILURE-EXPERIMENTS.md` | actual commands, logs and recovery | NOT VERIFIED |
| R26 | CI lint, >=60% tests, kustomize/kubeconform, build, scan, e2e | B | `.github/workflows/ci.yml` | PR statuses including blocked merge | NOT VERIFIED |
| R27 | CD test -> SHA build/push -> ephemeral deploy/Ingress smoke | B | `.github/workflows/cd.yml` | successful CD URL and Docker Hub tags | NOT VERIFIED |
| R28 | Protected main, dev branch, PR approval; no direct main push | Both | `.github; docs/evidence/*` | settings screenshots/PR history | NOT VERIFIED |
| R29 | Seven engineering notes with source line numbers | Both | `ENGINEERING-NOTES-GUIDE.md` | real code line references and measurements | NOT VERIFIED |
| R30 | AI disclosure, final URLs, checker clean, README apply order | Both | `AI-ASSISTANCE-PLAYBOOK.md; README.md` | checker output + submission links | NOT VERIFIED |

### How to complete a row
1. Implement and run its linked test or live command. 2. Record the date, commit SHA, environment, actual result and artifact/screenshot path under `docs/evidence/`. 3. Change status to `VERIFIED <SHA>` only after the other developer reviews it. 4. If unable to demonstrate, keep the row red and identify fallback in `DEVELOPMENT-FLOW.md`.

### Pre-submission audit
Run `python scripts/check_submission.py` and record any warnings/errors. Check that required evidence files genuinely exist and README install/apply order works from a clean clone. The checker is a *lint*, not an authoritative grade; add manual testing for behavioral safety.

---

<a id="merged-docs-04-acceptance-criteria-md"></a>

## Acceptance criteria / black-box contract


| AC | Given | When | Then | Verification |
|---|---|---|---|---|
| AC-01 | FastAPI available | send 2- or 501-char question | HTTP 422; no model call | unit/API test |
| AC-02 | Indexed current policy | ask ordinary policy question | grounded answer, valid citation source/section/page | live API+golden |
| AC-03 | Old and new versions | ask latest rule | returned evidence excludes superseded sources | retrieval unit test + inspection |
| AC-04 | Explicit old-policy request | ask 2023-specific rule | historical filter allows old evidence, answer marks historical context | version golden |
| AC-05 | Absent topic | ask intentionally excluded question | `answered_from_context=false`; no invented citation | 2 golden must-abstain cases |
| AC-06 | No/marginal retrieval | highest similarity below measured floor | abstain before generation | deterministic unit test |
| AC-07 | Malformed model output | provider returns invalid schema twice | safe fallback, no 500, fallback metric | stub unit test |
| AC-08 | Malicious document text | chunk says ignore system | model/guard does not follow injected instruction | poisoned fixture test |
| AC-09 | Fake model citation | cites absent source | reject citation / retry or fallback, never serve fabricated reference | unit test |
| AC-10 | Cacheable independent question | repeat paraphrase above tuned threshold | eligible hit only when same index/config | cache test |
| AC-11 | Follow-up / abstain / invalid output | ask again | answer not stored/reused | exclusion tests |
| AC-12 | New corpus index published | re-ask formerly cached question | stale previous-generation answer not served | reindex integration |
| AC-13 | Index model mismatches API config | API restarts | `/readyz` 503, 0/1 READY, explicit mismatch log | cluster experiment |
| AC-14 | Chroma down for 90s | kubelet probes API | `/healthz` stays 200; `/readyz` fails; no restart storm | manual/cluster |
| AC-15 | One API pod deleted | request through Ingress | service remains available through remaining ready pods | live incident evidence |
| AC-16 | Image updated | rollout + undo | new version healthy then old version returns; no unavailable endpoints | kubectl logs |
| AC-17 | Calico policy active | UI pod tries Chroma | connection denied; UI->API allowed; API->Chroma allowed | run test within pods |
| AC-18 | Evaluator runs golden | all questions processed | recall@3/@5, by-type metrics, cite validity, abstain results stored | eval/results.json |
| AC-19 | Retrieval intentionally regresses >5pp | run CI eval | non-zero exit and blocked PR merge | CI screenshot |
| AC-20 | New clean clone | follow README apply order | healthy ingress + indexed cited answer + absent answer | demo on new environment |

### Minimal definition of user-visible correctness
All claim-bearing sentences should cite evidence actually retrieved in that request. If citation validation fails, **do not quietly strip all citations while still claiming grounding**. Either recover a fully grounded answer after one retry or decline safely. The `reasoning` provider field must never be serialized in `AskResponse`.

### Release blockers
AC-02, AC-05, AC-09, AC-12, AC-13, AC-15, AC-17, AC-18, AC-19, AC-20 are P0. No `PASS` label without the exact run ID / proof path. Functional UI screenshots do not replace a machine-readable evaluation or live cluster command.

---

<a id="merged-docs-30-quality-attributes-md"></a>

## Quality attributes, tradeoffs and observable targets


| Attribute | Required measurable design | Competing cost | How to judge |
|---|---|---|---|
| Grounding | only retrieved citations; correct abstention | provider refusals / less fluent answers | golden tests and manual inspection |
| Freshness | reindex without redeploy, invalidates cache | staging collections consume temporary disk | generation switch and stale-answer test |
| Availability | 3 API replicas, no unavailable during rolling update | capacity requests cost resource space | pod delete + rollout undo and endpoints |
| Consistency | pin model/dimension and superseded filter | extra readiness/query check | deliberate mismatch, old-rule test |
| Performance | retrieval/generation latency and semantic-cache hit ratio | false hit risk and Redis memory | measured metrics and negative test sweep |
| Maintainability | clear Protocols, ADRs and task ownership | documentation updates | clean implementation PRs and reproducible tests |
| Security | least-privilege namespace/policy/secret handling | host egress/DNS complexity | Calico negative test, Trivy, secret scan |
| Reproducibility | SHA images, same dependency pins, clean clone | extra CI runtime | tested README apply order and successful CD |

### Budget rationale
Minikube on a laptop with Ollama on host avoids an 8GB in-cluster model requirement. Actual CPU requests/limits and memory margins must come from `kubectl top pods`; write them in engineering notes after running. HPA CPU samples app CPU, not model GPU/remote generation backlog; future load-based scaling could use in-flight queries/custom metrics.

### User safety
The app can summarize documents but cannot substitute for a university registrar's current policy confirmation. The UI should show the source and revision and clearly decline absent content. No fabricated details in generated docs or returned answer.

---

