# 15 — Hand-off to Taimoor (24 Nov 2026)

Everything that can be built and unit-tested on Bilal's laptop (no cluster, no GPU, no Ollama) is built. This file is the single list of what is **left**, in the order to do it. Read [README](README.md) first (the PDF and the paper are the only sources of truth), then [11](11-IMPLEMENTATION-PLAN.md) §5a and [14](14-INTERFACE-CONTRACTS.md). If a number is not produced by a command you ran on the cluster host, it does not go in the report.

**Branch to start from:** `feat/a3-suite-and-traces` (PR into `docs/a3-ragops-plan`; the plan PR #21 into `main` needs your approval and green CI).

## 0. What exists now (all unit-tested, none run on the cluster)

| Area | Where | State |
|---|---|---|
| Part A pipeline | `indexer/pipeline/*` (ledger, lake, catalog, verify, incremental, ops, report, seed, calibrate, run) | done against fakes; **never run against real Chroma** |
| Batch B fixtures + expectations | `corpus/batch-b/` | done; expectations written before any run |
| Suite (module, component, endpoint, judge, proxy, typos, config, one command) | `ragops/suite/*` | done; smoke-run over HTTP against the real API with stub backends |
| Stochasticity, diff, judge-vs-human agreement | `ragops/suite/{stochasticity,diff,agreement}.py` | done |
| Gate, promote, candidate-spec validator | `ragops/gate/{apply,promote,candidate}.py`, `ragops/config/gate.yaml` | done; **two thresholds deliberately `null`** |
| Coverage + calibration + clustering | `ragops/coverage/coverage.py` | done; **`similarity_threshold: null`** |
| Trace tools | `ragops/trace/{show,summary}.py` | done |
| API: traces, `/api/retrieve`, eval headers, release id | `api/app/{trace,evalctl}.py`, `routes/{ask,retrieve,health}.py` | done; A2 tests unchanged and green (139 pass) |
| Candidates | `ragops/config/candidates/{baseline,cand-mxbai,cand-minilm}.yaml` | specs with expected outcomes written first |
| Data drafts | `eval/golden.draft.jsonl`, `eval/pairs.jsonl`, `eval/live_queries.jsonl` | **drafts**, see §3 |

`make lint` and `make test` are green on Bilal's laptop (api 139, indexer 175, ragops 61, tests 13 + 82 skipped that need kubeconform/kustomize).

## 1. Host rules (do not skip)

* **One machine produces every reported number: your laptop** (GPU, 32 GB). Never compare a result from Bilal's CPU laptop with yours.
* Ollama on the host, `OLLAMA_HOST=0.0.0.0:11434`, models pulled: `llama3.2:3b`, `nomic-embed-text`, `mxbai-embed-large`, `all-minilm`. Record GPU, driver, Ollama version, `OLLAMA_*` env in `docs/a3-evidence/host.md`.
* One heavy run at a time (two jobs on one Ollama distort p95, which the gate checks).
* Save the **raw output** of every command that yields a number or a screenshot under `docs/a3-evidence/<task>/` at the moment you run it.
* Never edit a threshold, a golden label or a candidate's `expected:` after seeing a result. Fix labels only in a separate commit with a reason.
* No `Co-Authored-By` lines in commits; commit as yourself; both of you must have commits.

## 2. Order of work

### Step 1 — prove the host (about 30 min; send the outputs to Bilal)
1. `nvidia-smi`, `ollama ps` (PROCESSOR must say GPU), `ollama run llama3.2:3b "hi"`.
2. `minikube start --cni=calico --memory=8g --cpus=4`, then `kubectl get nodes`.
3. `make test` on this branch.

### Step 2 — **T05 Chroma spike (blocks everything in Part A)**
Run `scripts/ragops/chroma_spike.py` against the cluster's Chroma 1.0.12 (it prints what each call does). Save the output to `docs/a3-evidence/chroma-spike.md`. The adapter `indexer/pipeline/index.py` assumes `upsert`, `delete(ids)`, `update(metadatas)`, `get(where, include)` and registry `modify()`. If any call behaves differently, fix **only** `ChromaIndex` (the rest talks to the `VectorIndex` protocol), re-run `pytest indexer`, and note the fix.

### Step 3 — cluster objects (spec: [10](10-KUBERNETES.md); none of these manifests are written yet)
| Task | File(s) to write | Acceptance |
|---|---|---|
| T47 | `k8s/base/ragops-storage.yaml` (PVCs `ragops-data`, `ragops-traces`, `ragops-results`), `ragops-config.yaml` (`ragops-config`, `ragops-eval-target`), `ragops-gate` ConfigMap from `ragops/config/gate.yaml` | `kubectl get pvc,cm` |
| T48 | edit `k8s/base/api.yaml`: `RELEASE_ID`, `EMBED_VERSION`, `PROMPT_VERSION`, `TRACE_DIR=/traces` mount, `POD_NAME` from the downward API, `EVAL_ENDPOINTS_ENABLED=true`, `EVAL_HEADERS_ENABLED=true` (the code defaults both to false) in the **pod template**; update `tests/test_manifests.py` assertions deliberately | rollout ok; `curl /readyz` shows `release_id` |
| T49 | ingest Job + CronJob (`concurrencyPolicy: Forbid`), `pipeline/job_entry.sh` mapping exit 1 to 0, seed init; retire the A2 `indexer`/`reindex` | Job Complete on a fresh cluster |
| T50 | `k8s/eval-job.yaml` + `ragops/job_entry.sh` per [10](10-KUBERNETES.md) §5 (suite, then `gate.apply`, exit with the gate's code, last line `RESULT=...`); `backoffLimit: 0`; mounts `ragops-data` read-only and `ragops-traces` read-only | Job fails when the gate fails |
| T32 | `k8s/candidate.yaml` (Deployment + Service `api-candidate`, `REDIS_URL` empty) | candidate Ready; trace shows its collection |
| T33 | `scripts/ragops/release.sh <candidate> [--dry-run]` (exit 0 released, 1 refused, 2 rollout failed); refuses without a passing `decision.json` | contract 14 §7.4 |
| T51/T52 | loader pod, `job.sh`, Make targets; NetworkPolicies (eval to API/Ollama only; no eval to Chroma/Redis) and save the `nc`/`wget` matrix | screenshots + matrix file |
| T53 | `kubectl top` measurements while idle and under each Job, then set requests/limits | `docs/a3-evidence/top-*.txt` |
| T58 | clean-cluster rehearsal from `minikube delete` using `k8s/README.md` only (write it, [10](10-KUBERNETES.md) §12) | stopwatch time recorded |

Image for the suite: `ragops/Dockerfile` (build and `minikube image load`). It needs `PYTHONPATH` to include the repo root so `ragops.*` resolves; check the Dockerfile before first use.

### Step 4 — Part A on the cluster (T15/T56): the live state discipline
Live index stays in **corpus state A** through Parts B and C. Batch B goes into the live index **only** at E3.
1. Seed Batch A, run `sync`, then run `sync` again: second run must report `chunks_embedded: 0` (Screenshot A2).
2. Rehearse Batch B on a **scratch** collection (`rahbar-scratch`), compare with `corpus/batch-b/README.md` (expected: 6 quarantined, 6 accepted, 1 archived; B13 later quarantined), delete the scratch collection.
3. Run `python -m pipeline.calibrate corpus/raw --embed` (needs Ollama) and commit `docs/a3-evidence/verify-calibration.md` with the cosine matrix. Set `NEAR_DUP_COSINE` from the gap, justify it.
4. Verification report A1 screenshot on the real Batch B run at E3, and the orphan check `count`.

### Step 5 — golden set, pairs, live queries (with Bilal; humans must do this)
* `eval/golden.draft.jsonl` has 30 questions. **g001-g019** are the A2 human questions with `(doc, page)` taken from the extracted text (the page whose text holds the answer, not from retrieval). **g020-g030** are assistant drafts marked `origin: synthetic` with `review.verdict: pending`; `python -m ragops.suite.golden --validate` rejects them until a member reads the cited page and sets `ok` or `edited` (the PDF needs at least 8 reviewed). Replace any you dislike with your own.
* Verify each gold page once against the ingested document: `python -m ragops.suite.golden --validate eval/golden.draft.jsonl --ledger <ledger.json>` (checks the file exists and the page is in range). Pages for `.md` fixtures are virtual page 1.
* **Freeze:** copy to `eval/golden.jsonl` in a commit named `golden: freeze v1` **before any suite run**. The hash goes into every result.
* B10, B11, B12 (clubs, transport, scholarships) are deliberately **not** in the golden set; they are the Part E gap. Do not add them early.
* `eval/pairs.jsonl` (20 + 20) and `eval/live_queries.jsonl` (28 in-domain + 14 out) are drafts; edit a share in your own words, different authors for different slices (09 §2), then run the validator in `coverage.py`.
* Hand labels: after the first endpoint run, `python -m ragops.suite.agreement sample RESULT.json`, each of you labels at least 8 (aim 12) answers without seeing the judge, write `eval/judge_labels.jsonl`, then `agreement score ... --write`.

### Step 6 — measured runs (one at a time; see [11](11-IMPLEMENTATION-PLAN.md) §4)
1. `run_suite --label baseline --batches A` twice (`--repeat 2`) then `stochasticity run1 run2`. Any non-zero retrieval delta is a finding to investigate first.
2. **Derive and commit** `faithfulness_min` and `p95_latency` in `ragops/config/gate.yaml` with the justification text, **before** any candidate run (`gate.apply` refuses `null`). Promote the baseline: `gate.promote --result ... --reason ...`.
3. Candidates: `python -m ragops.gate.candidate ragops/config/candidates/cand-*.yaml`, build with `pipeline.run build-index`, **calibrate each candidate's `relevance_floor`** (cosine scales differ per model; this is the likeliest reason a "good" candidate fails the abstention rule, a legitimate finding), fill `embed_version`, then suite + gate for `cand-minilm` (expect FAIL) and `cand-mxbai` (hypothesis PASS). The gate decides; write what happened, not what was hoped.
4. Release scenarios S1 (stopped), S2 (released with zero downtime), S3 (bad release then `kubectl rollout undo`, trace shows the previous collection and embedding version).
5. Coverage: calibrate `similarity_threshold` on at least 40 hand-labelled pairs (`coverage pairs` prints the pairs to label; `coverage calibrate`), commit the evidence, set it and `min_share`, run E2 (before), ingest Batch B live (E3) and `run_suite --batches A,B`, `diff --allow-corpus-change`, write at least 6 new questions from the uncovered topics (E4, `added_in: "E4"`), re-run coverage (E2 after) and `run_suite --only-added E4`.
6. D evidence: `ragops.trace.show <trace_id> --traces /traces --lake /data` (D2), `trace.summary` (D3), the B08 parking attack (D4), root-cause note (D5).

### Step 7 — report and submission (T59-T63)
[12](12-REPORT-AND-EVIDENCE.md) and [13](13-DEMO-RUNBOOK.md): report at most 8 pages, screenshots A1 to F6, short answers (a) to (f), README commands per part, AI statement, rehearse the demo twice including the **unseen batch**. Confirm the deadline on Classroom (assumed Fri 27 Nov).

## 3. Known gaps and decisions that are yours to make (written honestly)

1. **Embedding profiles (T03) not done.** `indexer/pipeline/embed.py` and `api/app/retrieval/embedder.py` only add the task prefix and lowercase for `nomic-embed-text`. `mxbai-embed-large` is trained with a query instruction (`Represent this sentence for searching relevant passages: `) and `all-minilm` needs none. If you leave this alone the candidate is judged without its recommended prefix, which is a fairness problem for the comparison. Either add a shared profile table (07 §3.1; `ragops/suite/prep.py` mirrors the API and has a parity test, so extend all three together) or state the limitation in the report.
2. **Trace is partial against contract 14 §6.** Present: ids, route, status, release, query, embedding model/version, collection and revision, ranked candidates with doc/page/score/superseded, guardrail actions (injection neutralised, with excerpt), prompt hash + stored prompt, model params, response, cache, tokens, total/retrieve/generate latency. **Missing:** `dense_order` vs `reranked_order` and `assists`, per-stage embed/rail/prompt/validate timings, `origin_trace_id` for cache hits, the RAIL_EXCLUDE_RATIO exclusion rule (the guard only neutralises; it never excludes a chunk), the `where` filter text, embedding dimension. Add them if D1 or D4 needs them; the PDF's own field list is what matters (08 §2).
3. **The rail is the A2 prompt-level guard** (`services/prompt.py::neutralise`), now recorded in the trace. A true retrieval-stage rail is described in 08 §5; implement it if the report's D4 story needs "excluded", not just "neutralised".
4. **Suite component level uses `(source, page)` from `/api/retrieve`.** `source` is the stored file name. Batch-B markdown/HTML pages are virtual; confirm page numbers on the real ledger (validator `--ledger`).
5. **Judge self-agreement:** the default judge is the same `llama3.2:3b`. If you have a second model pulled, set `judge.model` in `ragops/config/suite.yaml` (it is in the config hash, so change it before the baseline) and record why.
6. **`HttpApi.target_info()`** reads `release_id`, `collection`, `revision`, `embed_model`, `embed_version` from `/readyz` `checks`; `collection` there is a string like `ok: rahbar (532 chunks)`. If you want a clean value in the result file, add a plain `collection_name` check.
7. **Not run anywhere:** the incremental sync against real Chroma, calibrate `--embed`, `build-index` with a real model, the whole suite against a real LLM, every manifest. Treat all of it as untested until you run it.

## 4. What Bilal still does (so nothing is double-booked)
Review and rewrite the drafted data, second-verify gold pages, the hand labels, the report prose, and the sync reviewer role on every PR (swap-review, G-03).

## 5. Quick command reference

```bash
make test lint                                              # everything unit-level
python -m ragops.suite.golden --validate eval/golden.jsonl [--ledger ledger.json]
python -m ragops.suite.run_suite --api http://api:8000 --ollama http://HOST:11434 \
       --label baseline --batches A --ledger /data/ledger/ledger.json --lake /data \
       --traces /traces --out /results [--repeat 2] [--limit 3] [--no-judge]
python -m ragops.suite.stochasticity run1.json run2.json
python -m ragops.gate.apply --baseline BASE.json --candidate CAND.json \
       --config ragops/config/gate.yaml --decision-out decision.json    # exit 0 pass, 1 fail, 2 error
python -m ragops.gate.promote --result RESULT.json --reason "..." --baselines-dir /results/baselines
python -m ragops.coverage.coverage [pairs|calibrate] --golden eval/golden.jsonl --live eval/live_queries.jsonl
python -m ragops.trace.show TRACE_ID --traces /traces --lake /data
python -m ragops.trace.summary --traces /traces
```
