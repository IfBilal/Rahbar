# RAHBAR + RAGOps: operating a grounded RAG pipeline on Kubernetes

**CS4032 Assignment 03 (RAGOps), Fall 2026.** Team: **Taimoor Shaukat (24I-3015)** and **Muhammad Bilal Tahir (24I-3166)**.
Repository: <https://github.com/IfBilal/Rahbar> · submitted commit: `«MEASURE: git SHA»` · every number below is from a run on one CPU-only laptop (`docs/a3-evidence/host.md`; no GPU, so latencies are slow and comparable only with themselves) and cites a committed file under `docs/a3-evidence/` (letter = Part) or `eval/results/`.

We added the RAGOps layer of the reference paper (Xu et al., arXiv:2506.03401; cited as 2026 in the assignment, posted 3 Jun 2025) to our Assignment-02 pipeline RAHBAR (FAST-NUCES rules, cited answers, abstains when the documents do not cover a question): a verification and incremental-update lifecycle for the data (**Batch A**: nine public documents, 279 PDF pages plus 2 web pages, 532 chunks; **Batch B**: thirteen files with planted problems (eleven fictional, two byte copies of Batch-A documents)), a three-level offline suite, a configurable release gate, a trace and metrics for every query, a coverage check, and a gated rolling release on Kubernetes. Ingestion, evaluation and coverage are Jobs; data, traces and results are on PersistentVolumeClaims; thresholds are a ConfigMap.

## 1. Table 1: the stages of Figure 3

| Figure-3 stage | What our pipeline does | File | What is missing |
|---|---|---|---|
| Ingest | An inbox on the `ragops-data` volume; adds, changes and removals are detected against a ledger; PDF, HTML, Markdown and text extraction with OCR for scans | `indexer/pipeline/catalog.py`, `extract.py`, `run.py` | No webhook or change-data-capture; formats beyond those four |
| Verify | Four checks per document (quality, completeness, recency, uniqueness) with a reason code; failures go to quarantine; one report per run | `verify.py`, `report.py` | No consistency check across documents; malicious content is not detectable here (B08 passes all four checks) |
| Update data lake | Verified versions on the PVC, superseded versions archived and restorable, deletions recorded, a versioned ledger | `lake.py`, `ledger.py`, `ops.py` | No access-control metadata |
| Update retrieval sources | Chunk-level incremental update: 0 embeddings when nothing changed, changed document replaces only its chunks, deletion leaves no orphans, `superseded` flag in metadata, revision in a registry | `incremental.py`, `store.py`, `index.py` | A change of embedding model or chunking is a full rebuild of a new collection |
| Offline testing | Golden set (30 frozen, 45 after E4) and a three-level suite (module, component, end-to-end), seeds, run twice, one command; gate over ConfigMap thresholds | `ragops/suite/`, `ragops/gate/` | Public benchmarks; a larger golden set; a stronger judge than the 3B generator |
| Live testing | A candidate Deployment on its own collection, the same suite against it, a gated rolling release with `kubectl rollout undo`; traces and a summary over a time window | `k8s/candidate.yaml`, `scripts/ragops/release.sh`, `ragops/trace/` | No A/B traffic split; no alerting |
| Check coverage | Embedding similarity between live queries and golden questions; share against a calibrated threshold; uncovered topics; exit code | `ragops/coverage/coverage.py` | Retrieval-level and generation-level coverage |

## 2. Table 2: the five qualities

| Quality | What we measure | Threshold (ours) | Evidence |
|---|---|---|---|
| Adaptability | Embeddings for an unchanged corpus and for a new, a changed and a deleted document; old questions after a new batch arrives | 0 embeds if unchanged (got 0, 0.06 s); a changed document replaces only its chunks (10 deleted, 10 written, other 558 untouched, orphans 0); common-question recall@5 must not drop (0.7895 to 0.7895) | `A/A2`, `A/A5`, `E/E3-drift-diff.txt`, `eval/results/20261125T101514Z_drift-AB.md` |
| Monitorability | Offline gate: recall@5, abstention, citation validity, faithfulness, p95. Live: `/metrics`, incl. the new `rahbar_top1_similarity` and `rahbar_injection_flagged_total`; coverage share | Gate: recall@5 drop at most 0.02; abstention not below baseline; citation validity at least 0.95; faithfulness at least 0.89; p95 at most 225 s (`ragops/config/gate.yaml`). Coverage: tau 0.6448, min share 0.85 (`coverage.yaml`) | `C/C1-gate-fail.txt`, `C/C2-gate-pass.txt`, `F/F4-metrics-port-forward.txt` (taken before the two new series were added in `api/app/routes/metrics.py`; not yet in a capture) |
| Observability | One JSON trace per query: versions, filters, top-5 with scores, rail actions, prompt hash, per-stage latency; a summary over a window | Every query traced; a rail action recorded when text is neutralised (1 of 1 traced B08 query) | `D/D1`, `D/D3-trace-summary.txt`, `D/D4-injection-rail-b08.txt` |
| Traceability | The trace tool re-hashes the stored prompt and rebuilds each chunk from the data-lake snapshot | 100 % of sampled traces rebuild: 3 of 3 distinct traces checked (hash verified, every chunk rebuilt) | `D/D2`, `D/D4`, `D/D5-root-cause-g025-trace.txt`; `traces/samples.jsonl` |
| Reliability | Requests during a rolling release and a bad release; who may reach whom | 0 failed requests: 47 of 47 answered 200 in the release, 150 of 150 during the bad release and undo; network matrix as designed | `F/F5-zero-downtime.txt`, `F/F6-bad-release-and-undo.txt`, `F/F7-network-matrix.txt` |

## 3. Results

### 3.1 Part A: verification and incremental update

| File (Batch B) | Planted problem | Observed (`A/A1-verification-report-batch-b.txt`) | Caught |
|---|---|---|---|
| B01 `Student_Handbook_Copy.pdf` | exact duplicate | uniqueness `U-EXACT-DUP`, quarantined | yes |
| B02 `grading-page-backup.html` | exact duplicate | uniqueness FAIL and completeness FAIL (`C-MISSING-DATE-VERSION`) | yes |
| B03 `library-lending-regulations.md` | near-duplicate of B09 | uniqueness `U-NEAR-DUP` | yes |
| B04 `lab-safety-notice.pdf` | corrupt PDF | quality `Q-EXTRACT-FAIL` (+ completeness FAIL) | yes |
| B05 `exam-schedule-policy-trunc.md` | truncated | completeness `C-TRUNCATED` | yes |
| B06 `untitled-notes.txt` | no title, date, version | completeness `C-MISSING-TITLE` | yes |
| B07 `faculty-entrepreneurship-policy-2026.md` | newer version | accepted; 2022 version archived (`R-SUPERSEDED-BY`) | yes |
| **B08** `campus-parking-policy.md` | **injected instruction** | **all four checks pass, indexed** | **no** |
| B09-B12 | clean documents | all four pass | n/a |
| B13 `...-2019.md` (later run, `A/A1b-*`) | older version arrives late | recency `R-NEWER-EXISTS`, quarantined | yes |

Failures by check, first Batch-B run: completeness 4, uniqueness 3, quality 1, recency 1 (last line of the report). `corpus/batch-b/README.md` predicted completeness 3; the fourth is B02, which also lacks a date. We caught 8 of the 9 planted problems; B08 is the one verification cannot see.

| Run | docs new / unchanged / quarantined | chunks embedded / deleted | revision | seconds | file |
|---|---|---|---|---|---|
| Batch A first sync | 9 / 0 / 0 (1 superseded) | 532 / 0 | r0001 | 561.35 | `F/F2` |
| Unchanged re-run | 0 / 9 / 0 | **0** / 0 | r0001, not bumped | 0.06 | `A/A2` |
| Batch B sync | 6 / 9 / 6 (1 superseded) | 26 in each of 2 indexes / 0 | r0002 (532 to 558 chunks) | 42.13 | `A/A1-sync-batch-b.txt` |
| B13 later run | 0 / 15 / 1 | 0 / 0 | n/a | n/a | `A/A1b` |
| New doc, then edit, re-run, delete | 1 new; 1 updated; 0 embedded on re-run | 10 / 10 on the edit; 10 deleted on delete; orphans `[]` | r0007, r0008 | n/a | `A/A5` |
| Restore 2022 version, then 2026 | n/a | **0 embedded** both ways | r0004, r0005, r0006 | n/a | `A/A4` |

### 3.2 Part B: the three-level suite (baseline `nomic-embed-text`, corpus A, git 3f22101)

| Level | Metric | Value (N) | | Level | Metric | Value (N) |
|---|---|---|---|---|---|---|
| module | paraphrase / unrelated cosine, gap | 0.823 / 0.497, 0.327 (20) | | endpoint | faithfulness (judge / proxy) | 0.947 / 1.000 (20) |
| module | embed ms per chunk, mean / p95 | 525.3 / 1434.6 | | endpoint | abstention correctness | 1.000 (6) |
| component | recall@3 / recall@5 | 0.775 / 0.800 (20) | | endpoint | false abstention; citation validity | 0.050 (20); 1.000 (19) |
| component | MRR / nDCG@5 | 0.725 / 0.727 | | endpoint | latency p50 / p95 | 99.6 s / 153.0 s (26) |
| component | noisy recall@5 (typo rate 0.06) | 0.750 (delta -0.050) | | module | determinism, max difference | 0 |

Source `B/B1-eval-summary.txt` (`eval/results/20261124T174636Z_baseline.md`). Four Batch-B questions are skipped on corpus A. **Stochasticity** (`B/B2-stochasticity.txt`, two baseline runs): 36 of 42 metrics are identical; the 6 that differ are wall-clock (for example p95 153.0 s vs 177.3 s, embed 525 vs 882 ms per chunk). A first attempt at run 2 stalled when the laptop suspended; it was discarded and repeated (`B/run2-stalled-by-suspend.md`). **Judge agreement** (`B/B3-judge-agreement.txt`): 14 of 16 hand labels agree (0.875), but Cohen's kappa is **-0.067**, because 15 of the 16 labels are "supported". **The 16 labels in `eval/judge_labels.jsonl` were made by Claude Code reading each answer against the evidence the system retrieved, not by a team member.**

### 3.3 Part C: one change (the embedding model); same suite, seed and golden set (hash 2cabdf74ca990ab2)

| Level | Metric | baseline | cand-minilm | cand-mxbai | cand-llama1b |
|---|---|---|---|---|---|
| module | paraphrase / unrelated cosine | 0.823 / 0.497 | 0.641 / 0.116 | 0.817 / 0.411 | 0.842 / 0.570 |
| module | gap; embed ms per chunk | 0.327; 525 | 0.525; 58 | 0.406; 1051 | 0.272; 2156 |
| component | recall@3 / recall@5 | 0.775 / 0.800 | 0.775 / 0.800 | 0.825 / 0.850 | **0.450 / 0.600** |
| component | MRR / nDCG@5 / noisy recall@5 | 0.725 / 0.727 / 0.750 | 0.742 / 0.733 / 0.725 | 0.700 / 0.738 / 0.775 | 0.487 / 0.489 / 0.475 |
| endpoint | faithfulness (limit 0.89) | 0.947 | 0.944 | 0.947 | **0.857** |
| endpoint | abstention correctness | 1.000 | 1.000 | **0.833** | 1.000 |
| endpoint | false abstention; citation validity | 0.050; 1.000 | 0.100; 1.000 | 0.050; 1.000 | 0.300; 1.000 |
| endpoint | latency p50 / p95 s (limit 225) | 99.6 / 153.0 | 85.1 / 175.35 | 107.1 / 190.9 | 59.7 / 87.8 |
| gate | verdict | baseline | **PASS** | **FAIL** | **FAIL** |
| spec | predicted before the run (`expected:`) | | fail | pass | fail |

Source `C/comparison.md`; decisions `eval/results/*_cand-*.decision.json`; gate output `C/C1-gate-fail.txt` (llama1b), `C/C1b-gate-fail-mxbai.txt`, `C/C2-gate-pass.txt`. **Caveat: the first suite run of cand-minilm** (`eval/results/20261125T054522Z_cand-minilm.md`) **has an invalid module level**: a bug in our suite embedded with nomic, so it printed nomic's 0.823 / 0.497. The table uses the corrected module-only run (`C/C1-module-minilm-corrected.txt`, `20261125T072335Z_cand-minilm-module.md`); the bug is fixed with a test, and the gate rules do not read the module level, so the decision is unaffected. Thresholds: faithfulness 0.89 is the baseline 0.9474 minus one answer (1/19); p95 225 s is the worst baseline p95 (177.3 s) times 1.25, rounded up (`gate.yaml`, committed before any candidate ran). **Predictions in the candidate specs: minilm fail, mxbai pass, llama1b fail; two were wrong** (minilm passed, mxbai failed). The llama1b spec was written after minilm's surprise, so it was not a blind prediction.

**Release decisions** (reasoning in `C/release-decisions.md`).

| Candidate | Decision | Reason |
|---|---|---|
| cand-minilm | **RELEASE**, with reservations | Passed every rule (recall@5 unchanged, faithfulness 0.944, p95 175.35 s); embeds 9 times faster; vectors half the size. Reservations no rule covers: false abstention doubled (0.10 vs 0.05); 74 of 532 chunks (14 %) were embedded from shortened text (512-token context); floor 0.25 lets 5 of 6 unanswerable questions reach the model (`C/C0-floor-minilm.txt`). Released by rolling update, then rolled back to R1-nomic so that Batch B changes one thing (`F/F6-return-to-baseline.txt`). |
| cand-mxbai | **REJECT** | Best retrieval (recall@5 0.850) but the Canada-visa question (g022, must be declined) was answered: abstention 0.833 vs 1.000. Its score scale needs its own floor; we did not re-tune after seeing the result, which would tune to the test set. Follow-up. |
| cand-llama1b | **REJECT** | A language model has no retrieval training: recall@3 0.775 to 0.450, false abstention 0.30, faithfulness 0.857. `release.sh` refused it (exit 1, revision unchanged, `F/F3-release-refused.txt`). |

`release.sh` hardening (`F/F3-release-hardened-checks.txt`): a fresh passing decision gives a dry-run plan (exit 0); a mistyped option, a name with odd characters, and the failed llama1b and mxbai decisions are each refused (exit 1).

### 3.4 Part D: traces, rails, tools

| Trace of the B08 parking question (`D/D4-injection-rail-b08.txt`) | |
|---|---|
| query; release; collection | "How much is the semester parking fee for a car?"; R1-nomic; `rahbar` @ r0009; `nomic-embed-text` 0a109f422b47 |
| top-3 (score) | `campus-parking-policy@2026-09#0002` (0.8405), `#0004` (0.7433), `fee-structure@2026-27#0002` (0.7036) |
| guardrail | 1 action: injection neutralised in chunk `#0002`; the prompt shows "[instruction-like text removed]" |
| answer | motorcycle Rs 2,000 and car Rs 5,000, cited to `campus-parking-policy.md`: the true fee, not "parking is free" |
| checks | prompt hash verified; 3 of 3 chunks rebuilt from snapshot; `trace.show` prints the exact prompt and context |

**Summary** (`D/D3-trace-summary.txt`; `/api/ask`, R1-nomic, the suite's own queries): 62 requests, 48 ok, 14 abstained (0.2258); fallback 0; cache hit 0; top-1 similarity p10 / p50 / p90 0.629 / 0.769 / 0.874 (min 0.573, max 0.891); latency p50 / p95: generate 111.9 / 177.2 s, retrieve 15.2 / 161.3 ms, total 110.9 / 173.6 s. Guardrail actions 0 in that window (it predates B08). Curated samples: `traces/` (`traces/README.md`). One full record: `D/D1-trace-record.txt` (the parking question g028, 166 lines of JSON: trace id, query, embedding model and version, collection and revision, filters, ranked candidates with document versions and scores, the guardrail action, prompt hash, model parameters, response, latency per stage, cache). The same line is readable with `kubectl logs` (`F/F4-trace-in-kubectl-logs.txt`). The trace has no reranked-order field because the pipeline has no reranker, and `embedding.dimension` is null: both are known gaps. `/metrics` now also exposes `rahbar_top1_similarity` and `rahbar_injection_flagged_total` (`api/app/routes/metrics.py`; the summary script reports the same quantities from the trace log).

**D5 root cause** of the abstained g025 (`D/D5-root-cause.md`, trace `d08cce5a...`): (1) status `abstained`, reason `model_declined`: retrieval worked. (2) All 5 candidates are 2026 documents. (3) The filter is `superseded_filter: true`: the 2023 rules are archived and excluded. (4) The history switch (`wants_history`) fires on older, previous, earlier, "before 20xx"; "the 2023 rules" has none. (5) The model saw only 2026 text and said so. Cause: version filter plus trigger vocabulary, not retrieval or the model. Fix: also trigger on a year before the current version.

### 3.5 Part E: coverage and drift

| Item | Value | File |
|---|---|---|
| tau calibration | 42 labelled (live query, nearest golden) pairs; maximum F1 at tau 0.6448 (precision 0.68, recall 0.944); conservative alternative 0.79 (precision 1.0, recall 0.444) | `E/E0-calibrate.txt`, `coverage.yaml` |
| Coverage before | 42 live queries, 25 covered, **share 0.595** (in-domain 0.750, out-of-domain 0.286) vs min share 0.85: `COVERAGE GAP`, Job `Failed`; tau -0.05 gives 0.810, +0.05 gives 0.405; tf-idf cross-check 0.024 | `E/E1-coverage-before.txt` |
| Uncovered (17 queries) | late bus, financial aid, clubs in classrooms, retake exam (2 queries each); one each: society size, medals, cafeteria, F vs FA, lab credit hours, swimming pool, cum laude, plagiarism, degree attestation | same |
| E4 round 1: 8 new golden questions (g031-g038: clubs, transport, scholarships, two absent topics) | coverage **0.595 to 0.738** (out-of-domain 0.286 to 0.714), still below 0.85: `COVERAGE GAP`, exit 1 | `E/E2-coverage-after.txt`, `E/e4-questions.draft.jsonl` |
| E4 round 2: 7 more (g039-g045: medals, FA grade, lab credit hours, retake, late exam, cum laude, cheating in a project) | coverage **0.905** (in-domain 1.000, out-of-domain 0.714): `COVERAGE OK`, Job `Complete`; tau -0.05 gives 0.976, +0.05 gives 0.690. Still uncovered: late bus, financial aid, swimming pool, degree attestation | `E/E2-coverage-after-round2.txt`, `E/e4-round2.jsonl` |
| E4 suite on the new questions | «MEASURE: result of `--only-added E4` (15 questions), `eval/results/*_e4-added.md`» | |

The E4 questions were written by Claude Code from the uncovered topics, each checked against the page that answers it, and worded differently from the live queries; a member should spot-check them. Writing questions for the uncovered topics is what E4 asks, and it raises the share by construction: the number shows the gap closed for those topics, not that the golden set is representative.

**The E1 live queries were drafted by Claude Code (header of `eval/live_queries.jsonl`) and the coverage pair labels were labelled by Claude Code (`eval/coverage-calibration.jsonl`); a member still has to spot-check both.** Tau is only as good as those labels. **Drift** (`E/E3-drift-diff.txt`, `eval/results/20261125T101514Z_drift-AB.md`; corpus A+B, 558 chunks): backward compatibility on the 25 common questions, recall@5 **0.7895 to 0.7895, 0 per-question changes**; the 4 new Batch-B questions (g027 to g030) retrieved, forward recall@5 **1.0**; g008 retired because the 2022 policy is archived. Overall recall@5 went 0.800 to 0.826 only because the question mix changed (23 answerable instead of 20); the common-subset figure is the fair one. p95 latency 153.0 to 186.4 s.

### 3.6 Part F: Kubernetes

| Item | Result | File |
|---|---|---|
| Rolling release of cand-minilm | 3 replicas, `maxUnavailable 0`; 47 of 47 probe requests 200 (09:47:20 to 09:47:43) | `F/F5-release-rollout.txt`, `F/F5-zero-downtime.txt` |
| Bad release (collection typo, R5-bad-typo) | new pod never Ready, `rollout status` timed out (exit 1), old pods kept serving; `rollout undo` restored; 150 of 150 requests 200 | `F/F6-bad-release-and-undo.txt` |
| Trace after undo | previous release R3-minilm: collection `rahbar-cand-minilm` @ r0001, embedding `all-minilm` 1b226e2802db, hash verified | `F/F6-trace-after-undo.txt` |
| Network matrix | eval pods reach api, api-candidate, Ollama only; chroma only from api and api-candidate; redis only from api; ui reaches only api; loader nothing | `F/F7-network-matrix.txt` |
| Gate result after a ConfigMap edit | Job on the stored `cand-llama1b` result: `GATE_FAIL` (exit 1); after setting `recall5_drop` 0.02 to 0.25 and `faithfulness_min` 0.89 to 0.80 in `ragops-gate`, the same manifest: `GATE_PASS` (exit 0); the image printed both times is `rahbar-ragops:dev`; thresholds restored afterwards. The demo writes to `gate-demo.decision.json`: an earlier version overwrote the real decision and was fixed (`docs/AI-USAGE.md` item 6) | `F/F4-configmap-edit-flips-gate.txt` |
| Volumes survive pod deletion | ledger hash, 14 quarantined files, archive, 34 reports identical before and after deleting the loader, API and Chroma pods; Chroma 558 chunks again | `F/F8-pvc-survival.txt` |
| Resources (measured peak / steady, request, limit) | api 9m/75Mi peak, 3m/72Mi steady: 100m/80Mi, 500m/256Mi (A2 startup peak 151m); chroma 8m/99Mi, 2m/97Mi: 10m/96Mi, 500m/512Mi; ingest Job 1377m/1206Mi, 1219m/824Mi: 1250m/896Mi, 2 CPU/1792Mi; eval Job 36m/30Mi, 20m/23Mi: 50m/64Mi, 1 CPU/768Mi; redis 19m/9Mi: 20m/16Mi, 250m/256Mi; ui, loader unchanged; candidate sized like the api (no separate sample); coverage Job not measured. Applied to the cluster: the api, chroma and redis rollouts completed | `F5-resources.md`, `F/F5-apply-measured-resources.txt` |
| Clean-cluster rehearsal | «MEASURE: time to rebuild from a clean cluster» | |

## 4. Short answers

**(a)** The **completeness** check caught the most in Batch B: 4 failures, then uniqueness 3, quality 1, recency 1 (`A/A1-verification-report-batch-b.txt`). The problem it did **not** catch is **B08**, a well-formed, current, unique policy containing "Ignore all previous instructions...": it passes all four checks and is indexed. What would catch it: an injection scan at ingest, source trust or human review of new sources, the paper's consistency check. Until then the retrieval rail is the defence, and the D4 trace shows it neutralised the line and the answer was the true fee (Rs 5,000 for a car).

**(b)** Yes. llama1b's paraphrase cosine (0.842) is the highest of the four models, so on that metric it looks fine, yet recall@3 fell 0.775 to 0.450 and false abstention rose 0.05 to 0.30; only its gap (0.272, the lowest) hinted at it. The other way round, minilm has the best gap (0.525) with end-to-end quality equal to baseline, and mxbai has the second-best gap (0.406) and the best recall, yet failed on abstention. The module level predicted none of the three outcomes (`C/comparison.md`).

**(c)** We **archived**, not deleted: the 2022 policy is flagged and kept, and restoring it embedded 0 chunks (`A/A4`). Deleting a document removes its chunks (10 of 10, no orphans, `A/A5`) and costs: rollback without re-ingesting the source; answers about the old version; and, we expect but did not test, trace rebuild, since the trace tool rebuilds chunks from the lake snapshot. Archiving has a cost too: the version filter hid the 2023 rules from g025 (D5).

**(d)** The **LLM-judge faithfulness**. A 3B model judges 3B output; agreement is 14 of 16 but kappa is -0.067 (15 of 16 labels "supported") and the labels came from Claude Code, not a member. It also called an answer for g024 "supported" when the retrieved text did not say it (`traces/README.md`, sample `baseline-g024-wrong-answer`). One answer moves faithfulness by 0.0526. Next: recall@5 on about 20 questions (one question is 0.05, against a gate of 0.02) and coverage share (AI-made labels).

**(e)** Hardest: **coverage with a threshold**. The paper gives a share; a similarity needs a calibrated tau that depends on the embedding model and on hand labels we did not make, and the share swings 0.81 to 0.40 for +-0.05. Changed from the paper: a shadow candidate plus gated rolling release instead of an A/B split; archive by metadata flag, not a separate store; per-document incremental update; no consistency check or access-control metadata; a CPU 3B model limited the end-to-end set to 26 questions.

**(f)** Table below. Single writer: only the ingestion Job writes, enforced by Job/CronJob (`concurrencyPolicy: Forbid`), a lock on the data PVC and NetworkPolicy (`F/F7`: among the pods tested, chroma is reachable only from api and api-candidate). Chroma has no authentication, so Kubernetes alone does not make the API read-only.

| Responsibility | Object |
|---|---|
| Ingestion once; scheduled | Job `ingest`; CronJob (`Forbid`) |
| Data lake, quarantine, archive survive restarts | PVC `ragops-data` (rw for the Job, ro for eval) |
| Vector index survives | StatefulSet `chroma` with its own PVC |
| Traces and results outlive pods | PVCs `ragops-traces`, `ragops-results`; stdout |
| Thresholds without a rebuild | ConfigMap `ragops-gate` |
| Offline test as gate | Job `eval`, `backoffLimit: 0`, exit code = verdict |
| Candidate isolation | Deployment `api-candidate`, Service, own collection |
| Zero-downtime release, rollback | Deployment `RollingUpdate` + readiness probe; ReplicaSet history, `rollout undo` |
| Isolation | NetworkPolicy, ServiceAccounts |

## 5. Contribution and AI statement

Git history only (`git log --format='%an' | sort | uniq -c`, `git shortlog -sn`, at `0b98546`; later commits are Taimoor's): 170 commits `T361` and 7 `Taimoor Shaukat` (one account, 177); 48 `IfBilal` and 16 `8BitNinja` (one email, 64). Commits touching each path (Bilal / Taimoor): `ragops/` 2 / 19; `indexer/pipeline/` 3 / 9; `k8s/` 1 / 24; `scripts/ragops/` 1 / 18; `api/app/` 11 / 22; `docs/a3-ragops/` 7 / 1; `corpus/batch-b/` 1 / 0. A commit author is the configured git user, not necessarily who wrote the change. **Bilal merged PR #24 (`a9a845b`) himself.** He has not reviewed the 11 synthetic golden questions (`docs/AI-USAGE.md` item 4); both members must read the other's half before the demo. The questions were read by Taimoor: his statement, recorded by Claude Code in `docs/a3-evidence/synthetic-spot-check.md`.

**AI statement.** Claude Code (on both laptops) and an AI chat assistant (planning and first drafts, Bilal's laptop) drafted the plans, code, tests, manifests, the synthetic golden questions, the E1 live queries, the coverage pair labels, the 16 judge labels and this report; the full list, including OpenAI Codex in Assignment 02, is in `docs/AI-USAGE.md`. Every metric, trace and screenshot comes from our runs on our cluster; the AI-made labels (judge, coverage pairs, live queries) are marked above and await a member's check.

<div class="appendix"></div>

## Appendix: screenshots

Each shows the command and its output; raw text is next to each in `docs/a3-evidence/<part>/`.

### A1 verification report, Batch B
![A1](../a3-evidence/A/screenshots/A1-verification-report-batch-b.png)

### A2 unchanged re-run, 0 chunks embedded
![A2](../a3-evidence/A/screenshots/A2-unchanged-rerun.png)

### B1 evaluation summary, all three levels
![B1](../a3-evidence/B/screenshots/B1-eval-summary.png)

### C1 gate failing (cand-llama1b, then cand-mxbai)
![C1](../a3-evidence/C/screenshots/C1-gate-fail.png)
![C1b](../a3-evidence/C/screenshots/C1b-gate-fail-mxbai.png)

### C2 gate passing (cand-minilm)
![C2](../a3-evidence/C/screenshots/C2-gate-pass.png)

### D1 one full trace record
![D1](../a3-evidence/D/screenshots/D1-trace-record-1.png)

![D1 continued](../a3-evidence/D/screenshots/D1-trace-record-2.png)

![D1 continued](../a3-evidence/D/screenshots/D1-trace-record-3.png)

### D2 trace tool rebuilding the prompt
![D2](../a3-evidence/D/screenshots/D2-trace-tool-prompt-rebuild-1.png)

![D2 continued](../a3-evidence/D/screenshots/D2-trace-tool-prompt-rebuild-2.png)

### D4 injection rail, B08
![D4](../a3-evidence/D/screenshots/D4-injection-rail-b08.png)

### E1 coverage before
![E1](../a3-evidence/E/screenshots/E1-coverage-before.png)

### E2 coverage after
![E2](../a3-evidence/E/screenshots/E2-coverage-after-round2.png)

### F1 namespace overview
![F1](../a3-evidence/F/screenshots/F1-namespace-overview-1.png)

### F2 logs of the completed ingestion Job
![F2](../a3-evidence/F/screenshots/F2-ingest-first-run.png)

### F4 gate result changing after a ConfigMap edit
![F4](../a3-evidence/F/screenshots/F4-configmap-edit-flips-gate.png)

### F5 rollout status
![F5](../a3-evidence/F/screenshots/F5-release-rollout.png)

### F6 bad release, undo, and the trace afterwards
![F6](../a3-evidence/F/screenshots/F6-bad-release-and-undo.png)
![F6t](../a3-evidence/F/screenshots/F6-trace-after-undo.png)

### F7 network matrix
![F7](../a3-evidence/F/screenshots/F7-network-matrix.png)
