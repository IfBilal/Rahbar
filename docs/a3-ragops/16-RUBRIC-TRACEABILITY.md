# Assignment 03 rubric traceability

Every requirement in `docs/A3.pdf` (read in full with `pdftotext`) mapped to the implementation, the command that proves
it, the committed evidence, and an honest status. Not to be confused with `docs/TRACEABILITY.md` (Assignment 02).
Evidence paths are under `docs/a3-evidence/` (`X/` = Part letter); report sections are in `docs/a3-report/report.md`
(appendix = `Appendix: screenshots`, PNGs in `docs/a3-evidence/<part>/screenshots/`). Result files: `eval/results/`.

Test commands are per package (that is how `make test` runs them, never one `pytest` over everything):
`cd api && ../.venv/bin/pytest -q`, `cd indexer && ../.venv/bin/pytest -q`, `cd eval && ../.venv/bin/pytest -q tests`,
`cd ragops && ../.venv/bin/pytest -q`, `.venv/bin/pytest -q tests --ignore=tests/system`. "Cluster" means a run on the
minikube cluster with the evidence file named.

Status: **Done** = implemented, tested, evidenced. **Done-with-caveat** = done, with a limit stated in the last column.
**Needs-human** = only a member can finish it.

## 1. Matrix

### Instructions and demo constraints

| ID | Requirement (PDF) | Implementation | Test / command | Evidence, report section, appendix | Status | Caveat or residual risk |
|---|---|---|---|---|---|---|
| I1 | "Every number in your report must come from runs of your own pipeline, and the result files must be committed" | `eval/results/`, `docs/a3-evidence/` | `grep` each report number against the cited file; `git ls-files eval/results` | whole report; `eval/results/*.json` | Done-with-caveat | A few numbers come from a cluster that was later rebuilt; their re-captures are listed in the report (D1, D3, F4). Batch B per-run verification reports from the first cluster no longer exist (only the two current runs are committed, `A/verification-reports/`). |
| I2 | "must be deployed on Kubernetes during the demo ... Docker only gives 0" | `k8s/` (kustomize base, overlays), `Makefile` `cluster`, `images`, `apply` | `kubectl get all,pvc,configmap,cronjob,job -n rahbar`; `tests/test_manifests.py` | `F/F1-namespace-overview.txt`, `F/F10-clean-cluster-rehearsal.txt`; appendix F1 | Done | The demo needs the laptop cluster running (see section 2). |
| I3 | "Commits must come from both members" | git history | `git shortlog -sn` | report section 5 | Done-with-caveat | Bilal's commits are mostly Assignment 02 and the first Part A to E drafts; in Part F he has 1 commit in `k8s/` and 1 in `scripts/ragops/`. The report says so. |
| I4 | "Both members must be able to explain every part" / demo: run eval Job, open a trace, ingest an unseen batch | `docs/a3-ragops/13-DEMO-RUNBOOK.md` | rehearsal `scripts/ragops/rehearsal.sh` | `F/F10-clean-cluster-rehearsal.txt` | Needs-human | See section 2: demo prep. |

### Part A: data management

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| A1 | Verification step after ingestion, before chunking; pass or fail with reason for quality, completeness, recency, uniqueness (exact hash, near-duplicate by embedding) | `indexer/pipeline/verify.py`, `report.py`, `run.py` | `cd indexer && pytest -q tests/test_verify.py tests/test_run.py`; cluster: `scripts/ragops/job.sh sync` | `A/A1-verification-report-batch-b.txt`, `A/A1-sync-batch-b.txt`, `A/verification-reports/`; report 3.1; appendix A1 | Done | Near-duplicate threshold calibrated on our corpus (`docs/a3-evidence/verify-calibration.md`); a real near-duplicate with a different layout could slip through (short answer (a)). |
| A1q | Failing documents moved to a quarantine folder, not indexed; verification report file per run | `indexer/pipeline/lake.py`, `report.py` | `tests/test_ledger_lake.py`, `tests/test_run.py`; `kubectl exec ragops-loader -- ls /data/quarantine /data/reports/verification` | `A/A1-*`, `F/F8-pvc-survival.txt` (14 quarantined files survive pod deletion) | Done | Per-run reports for the first Batch B runs are gone with the old cluster. |
| A2a | Re-run on unchanged corpus embeds zero chunks (show counts) | `indexer/pipeline/incremental.py`, `ledger.py` | `tests/test_incremental.py`; cluster: second `job.sh sync` | `A/A2-unchanged-rerun.txt`; report 3.1; appendix A2 | Done | None known. |
| A2b | Changed document replaces only its own chunks | `incremental.py`, `ops.py` | `tests/test_incremental.py`; `scripts/ragops/a5-changed-deleted-document.sh` | `A/A5-changed-and-deleted-document.txt`; report 3.1 | Done-with-caveat | Shows 10 chunks for a 5-chunk fixture because two collections were written (report notes it). The script was recovered from the session transcript, not authored as a script. |
| A2c | Deleted document leaves no orphan chunks (count by document id) | `ops.py` (`delete`, `count`) | `tests/test_ops_cli.py`; `job.sh count -- count` | `A/A3-count-before-batch-b.txt`, `A/A5-...txt` (orphans `[]`) | Done | None known. |
| A2d | Superseded version archived, excluded by metadata, restorable (rollback demo) | `incremental.py`, `ops.py` (`restore`), `api/app/retrieval` version filter | `tests/test_ops_cli.py`; `scripts/ragops/a4-restore-rollback.sh` | `A/A4-restore-rollback-demo.txt`; report 3.1, short answer (c) | Done-with-caveat | Archiving hid the 2023 rules from g025 (D5): a cost, reported. Script recovered from the session transcript. |
| AB | Batch B: >= 10 documents; >= 2 exact duplicates, 1 near-duplicate, 1 truncated/corrupt, 1 missing metadata, 1 newer version, 1 injected instruction; run through A1 and A2 | `corpus/batch-b/` (+ `build.py`) | `cd indexer && pytest -q tests/test_batch_b.py`; `A/A0-deliver-batch-b.txt` | `A/A0`, `A/A1`, `A/A1b-*`; report 3.1 (6 quarantined, 6 accepted, 1 archived) | Done | The batch was planted by us, so detection rates are on known problems. The late-arriving file (b13) needed a second sync (`A1b`). |

### Part B: offline testing

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| BG | Golden set >= 25 q; >= 15 answerable with doc+page; >= 5 unanswerable; >= 5 hard; >= 8 by hand; labelled human or synthetic; >= 8 synthetic reviewed by hand | `eval/golden.jsonl` (45 questions: 19 human, 26 synthetic), `ragops/suite/golden.py` | `cd ragops && pytest -q tests/test_golden.py` | report 3.2; `docs/a3-evidence/synthetic-spot-check.md` | Done-with-caveat | The >= 8 hand-reviewed synthetic questions: Taimoor's statement covers the 11 v1 questions, recorded by Claude Code; the sheet has no initials. The 15 E4 questions were checked by Claude Code only. See section 2. |
| BM | Module level: >= 15 paraphrase and >= 15 unrelated pairs, gap, embed time per chunk, determinism | `ragops/suite/module_level.py`, `eval/pairs.jsonl` (20 + 20) | `cd ragops && pytest -q tests/test_suite.py`; `make eval-suite LABEL=baseline` | `B/B1-eval-summary.txt`; report 3.2; appendix B1 | Done | None known. |
| BC | Component level: recall@3, recall@5, MRR, nDCG@5; noise test (typos or >= 3 irrelevant docs) | `ragops/suite/component_level.py`, `metrics.py`, `typos.py` | `cd ragops && pytest -q tests/test_metrics.py` | `B/B1`, `eval/results/20261125T034256Z_baseline.json`; report 3.2 (all four metrics under typo rate 0.06) | Done | N = 20 answerable: one question moves recall by 0.05. |
| BE | End-to-end: faithfulness, abstention correctness, citation validity, latency p50 and p95; LLM judge needs >= 8 hand labels and agreement | `ragops/suite/endpoint_level.py`, `judge.py`, `agreement.py`, `eval/judge_labels.jsonl` (16) | `pytest -q tests/test_suite.py`; `python -m ragops.suite.agreement` | `B/B3-judge-agreement.txt`; report 3.2 | Done-with-caveat | The 16 labels were made by Claude Code, not a member; kappa -0.067 (15 of 16 "supported"). The PDF says "label at least 8 answers by hand": this is not yet met by a person. See section 2. |
| BS | Fix seeds, run twice, report the difference per metric, explain variation | `ragops/suite/stochasticity.py`, `ragops/config/suite.yaml` | `python -m ragops.suite.stochasticity a.json b.json` | `B/B2-stochasticity.txt`, `B/run2-stalled-by-suspend.md`; report 3.2 | Done-with-caveat | The two runs were at different commits (3f22101 and 26c05d9); 36 of 42 metrics identical, the 6 that differ are wall-clock. |
| B1 | One command runs the whole suite, writes a timestamped result file with a summary table | `scripts/ragops/eval.sh`, `ragops/suite/run_suite.py`, `k8s/eval-job.yaml`, `make eval-suite` | `make eval-suite LABEL=baseline` | `eval/results/20261124T174636Z_baseline.{json,md}` | Done | None known. |

### Part C: change and release gate

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| C1 | One change; baseline vs candidate on all three levels | `ragops/config/candidates/*.yaml`, `ragops/gate/candidate.py`, `scripts/ragops/candidate.sh` | `pytest -q ragops/tests/test_gate.py`; `make eval-gate LABEL=cand-minilm` | `C/comparison.md`, `eval/results/*_cand-*.json`; report 3.3, Figure 1 | Done-with-caveat | Three candidates were run for the one change (embedding model); the first cand-minilm run had an invalid module level (a suite bug, fixed with a test; the corrected module-only run is used). Each candidate carries its own relevance floor, which the validator ties to `embed_model`. |
| C2 | Thresholds in a config file; a script applies the gate and exits pass/fail; one failing and one passing candidate | `ragops/config/gate.yaml`, `ragops/gate/apply.py` | `pytest -q ragops/tests/test_gate.py`; `scripts/ragops/gate-demo.sh` | `C/C1-gate-fail.txt`, `C/C1b-gate-fail-mxbai.txt`, `C/C2-gate-pass.txt`, `eval/results/*.decision.json`; appendix C1, C2 | Done | Thresholds derived from the two baseline runs (faithfulness 0.89, p95 225 s), committed before any candidate ran. |
| C3 | Candidate released and, if needed, rolled back (see F3) | `scripts/ragops/release.sh`, `ragops/gate/promote.py` | see F3 | `C/release-decisions.md`, `F/F5-release-rollout.txt`, `F/F6-*`; report 3.3 release decision | Done-with-caveat | The decision for cand-minilm is "release as a trial, with reservations" (false abstention doubled; 14 % of chunks embedded from shortened text). |

### Part D: observability

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| D1 | One JSON line per query with trace id, timestamp, query, rewritten query, embedding model+version, collection, chunk ids/doc ids/versions/scores, filters, reranked order, prompt hash, model+params, response, citations, guardrail actions, latency per stage, cache | `api/app/trace.py`, `api/app/routes/ask.py` | `cd api && pytest -q tests/test_trace.py` | `D/D1-trace-record.txt` (trace `dd8f4789...`); `traces/samples.jsonl`; report 3.4; appendix D1 | Done-with-caveat | There is no reranker, so `retrieval.reranked_order` is the retriever order and `reranker` is `"none"`. The D1 record was re-captured on the rebuilt cluster. |
| D2 | Command takes a trace id, prints exact context and prompt | `ragops/trace/show.py` | `cd ragops && pytest -q tests/test_trace_tools.py`; `python -m ragops.trace.show <id> --traces traces` | `D/D2-trace-tool-prompt-rebuild.txt`; appendix D2 | Done | None known. |
| D3 | Metrics: top-1 similarity distribution, abstention rate, cache hit rate, p95 per stage, injection attempts flagged; script summarises the log over a time window | `api/app/routes/metrics.py`, `ragops/trace/summary.py` (`--since`, `--until`) | `pytest -q ragops/tests/test_trace_tools.py`; `kubectl port-forward deploy/api 8000:8000; curl :8000/metrics` | `D/D3-trace-summary.txt`, `F/F4-metrics-port-forward.txt` (has `rahbar_top1_similarity`, `rahbar_injection_flagged_total`); report 3.4 | Done-with-caveat | Cache hit rate is 0 in every window (the suite never repeats a query). `/metrics` is per pod. The 62-request window predates the guardrail series; D3 was re-run for a 3-request window. |
| D4 | Guardrail writes its action into the trace; test with the injected Batch B document | `api/app/services` guard, `api/tests/test_guard.py`, `test_injection.py` | `cd api && pytest -q tests/test_guard.py tests/test_injection.py` | `D/D4-injection-rail-b08.txt`, `traces/samples.jsonl` (`b08-injection-neutralised`, `rebuilt-cluster-parking-injection-neutralised`); appendix D4 | Done | One planted injection; no claim about other attack forms. |
| D5 | Root cause of one wrong or abstained answer from its trace only; 5 lines | none (analysis) | `python -m ragops.trace.show d08cce5a76644beeab76f8b4eaa149b6 --traces traces` | `D/D5-root-cause.md`, `D/D5-root-cause-g025-trace.txt`; report 3.4 | Done | Cause: version filter hid the 2023 rules (archived 2022 policy). |

### Part E: drift and coverage

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| E1 | >= 40 live queries (about 28 in domain, >= 12 out of domain) | `eval/live_queries.jsonl` (42) | `cd ragops && pytest -q tests/test_coverage_promote.py` | `E/E1-coverage-before.txt`; report 3.5 | Done-with-caveat | Drafted by Claude Code (header of the file), not collected from users; a member must spot-check. |
| E2 | Coverage share above a justified threshold; uncovered queries grouped into topics | `ragops/coverage/coverage.py`, `ragops/config/coverage.yaml` (tau 0.6448, min share 0.85), `eval/coverage-calibration.jsonl` | `python -m ragops.coverage.coverage`; `kubectl apply -f k8s/coverage-job.yaml` | `E/E0-calibrate.txt`, `E/E1`, `eval/results/coverage/`; report 3.5 | Done-with-caveat | Tau depends on pair labels made by Claude Code; the share swings 0.81 to 0.40 for +-0.05 of tau. See section 2. |
| E3 | Ingest Batch B, re-run Part B, report what changed and why | `ragops/suite/diff.py` | `python -m ragops.suite.diff` | `E/E3-drift-diff.txt`, `eval/results/20261125T101514Z_drift-AB.md`; report 3.5 | Done | Common-question recall@5 0.7895 to 0.7895; overall recall changed only because the question mix changed. |
| E4 | >= 6 new golden questions from uncovered topics; coverage rises; script exits non-zero below threshold | `eval/golden.jsonl` (+15), `ragops/coverage/coverage.py` exit code, `k8s/coverage-job.yaml` | coverage Job exit code; `pytest -q ragops/tests/test_coverage_promote.py` | `E/E2-coverage-after.txt`, `E/E2-coverage-after-round2.txt`, `E/e4-*.jsonl`; coverage 0.595 to 0.738 to 0.905; appendix E1, E2 | Done-with-caveat | Questions written by Claude Code, not hand-checked by a member. Two misses reported (g032, g041). |

### Part F: Kubernetes

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| F1 | API Deployment, vector store StatefulSet, Service; data lake, quarantine, archive on a PVC | `k8s/base/api.yaml`, `chroma-statefulset.yaml`, `services.yaml`, `ragops-storage.yaml` | `tests/test_manifests.py`; `kubectl get all,pvc,configmap,cronjob,job -n rahbar` | `F/F1-namespace-overview.txt`, `F/F8-pvc-survival.txt`; appendix F1 | Done | Single-node minikube: `ReadWriteOnce` means one node. |
| F2a | Ingestion Job and a CronJob; only writer to the vector store is the Job | `k8s/base/ingest-job.yaml`, `ingest-cronjob.yaml`, `networkpolicy.yaml` | `tests/test_boundaries.py`, `tests/test_manifests.py`; `F/F7-network-matrix.txt` | `F/F2-ingest-first-run.txt`, `F/F2-ingest-job-full-log.txt`; appendix F2 | Done-with-caveat | NetworkPolicy lets api, indexer and api-candidate reach Chroma; the API does not write by code (`tests/test_boundaries.py`), not by Kubernetes. The matrix did not test the indexer pod. Chroma has no authentication. |
| F2b | Suite as a Job (`kubectl apply -f k8s/eval-job.yaml`), result file on a volume, fails when the gate fails | `k8s/eval-job.yaml`, `ragops/job_entry.sh` | `make eval-suite`, `make eval-gate`; `kubectl wait --for=condition=complete job/eval` | `F/F3-eval-job-log.txt`, `eval/results/20261125T155648Z_demo.{json,md}`; appendix F3 | Done-with-caveat | F3 log is cut with `cut -c1-200` and could not be re-shot: the eval Job no longer exists on the rebuilt cluster. The full output is the committed result file. A full run takes about 40 min on CPU. |
| F2c | Gate thresholds in a ConfigMap; changing one changes the outcome with no rebuild | `k8s/base/ragops-gate.yaml` | `scripts/ragops/eval.sh gate-rerun`; `make eval-gate-rerun` | `F/F4-configmap-edit-flips-gate.txt`; appendix F4 | Done | None known. |
| F3a | Candidate as a second Deployment, Service, own collection; Part B Job against it | `k8s/candidate.yaml`, `scripts/ragops/candidate.sh` | `scripts/ragops/candidate.sh cand-minilm --dry-run` | `C/C0-build-index-*.txt`, `F/F5-release-rollout.txt` | Done-with-caveat | The rebuilt cluster has no candidate collections: build-index first (runbook). |
| F3b | Gate-passing candidate released by rolling update (`maxUnavailable: 0`), watched with `rollout status` | `scripts/ragops/release.sh`, `k8s/base/api.yaml` | `scripts/ragops/rollout-probe.sh`; `tests/test_manifests.py` | `F/F5-release-rollout.txt`, `F/F5-zero-downtime.txt` (47 of 47 requests 200); appendix F5 | Done | One probe window; not a load test. |
| F3c | A candidate stopped by the gate, never rolled out | `release.sh` refusal | `scripts/ragops/release.sh cand-llama1b` (exit 1) | `F/F3-release-refused.txt`, `F/F3-release-hardened-checks.txt`, `F/F3-release-dry-run.txt` | Done | `release.sh` is the guard; Kubernetes itself does not know the gate. |
| F3d | Bad release reversed with `rollout undo`; new trace shows the previous collection and embedding version | `scripts/ragops/s3-bad-release-undo.sh` (recovered), release-scoped env in the pod template | `kubectl rollout undo deployment/api -n rahbar` | `F/F6-bad-release-and-undo.txt`, `F/F6-trace-after-undo.txt`, `traces/samples.jsonl` (`after-undo-R3-minilm`); appendix F6 | Done-with-caveat | Script recovered from the session transcript; the evidence file still shows `bash /tmp/s3.sh`. 150 of 150 requests 200 during the bad release. |
| F4 | Traces to stdout and to a volume; metrics via port-forward | `api/app/trace.py`, `k8s/base/ragops-storage.yaml` (`ragops-traces`) | `kubectl logs deploy/api`; `kubectl port-forward ... ; curl /metrics` | `F/F4-trace-in-kubectl-logs.txt`, `F/F4-metrics-port-forward.txt` | Done | `/metrics` is per pod. |
| F5 | Requests and limits for API, vector store and Jobs from measurements | `k8s/base/*.yaml`, `scripts/ragops/top_summary.py` | `python -m pytest -q tests/test_top_summary.py` | `F5-resources.md`, `F/F5-apply-measured-resources.txt`, `F/F5-resample-top.txt`; report 3.6 | Done-with-caveat | The ingest and eval Job peaks are from single runs; the coverage Job is one sample of a 20 s run; throttling not measured. |
| FK | Every manifest under `k8s/`; a fresh cluster reaches a working pipeline; extra commands in `k8s/README.md` | `k8s/`, `k8s/README.md`, `scripts/ragops/rehearsal.sh` | `make manifests`; `tests/test_manifests.py` | `F/F10-clean-cluster-rehearsal.txt` (ingest 1,031.67 s); appendix F1 | Done | The rehearsal ran on one laptop; it is not a second machine. |

### Part G: report, submission lists, README

| ID | Requirement | Implementation | Test / command | Evidence, report, appendix | Status | Caveat |
|---|---|---|---|---|---|---|
| G1 | Table mapping each Figure 3 stage to what the pipeline does, the file, and what is missing | report section 1 | `docs/a3-report/build.sh` | report section 1 | Done | None known. |
| G2 | Table for the five qualities: what you measure, threshold, evidence | report section 2 (Table 2) | same | report section 2 | Done | None known. |
| G3 | Results tables and figures A to F; release decision for Part C | report section 3, Figures 1 and 2 (`docs/a3-report/fig-*.png`, `scripts/ragops/charts.py`) | same | report 3.1 to 3.6, `C/release-decisions.md` | Done | None known. |
| G4 | Short answers (a) to (f) | report section 4 | same | report section 4 | Done-with-caveat | (d) names the judge as the least trusted metric; its labels are not human. |
| G5 | Contribution table and 2-to-3-line AI statement | report section 5, `docs/AI-USAGE.md` | `git shortlog -sn --no-merges` | report section 5 | Done-with-caveat | Counts are at `0b98546`, merges excluded. Bilal's Part F share is review, not authorship; the report says so. |
| G6 | One PDF, at most 8 pages body, names and roll numbers on page 1, screenshots appendix | `docs/a3-report/report.md`, `report.css`, `build.sh` | `docs/a3-report/build.sh` prints `body pages: 8 (limit 8)` | `docs/a3-report/report.pdf` | Done-with-caveat | Exactly at the limit: any text added to the body may push it to 9 (the build fails then). Rebuild and commit the PDF after the last body edit. |
| S1 | Screenshots: command and output, nothing cropped, labelled by part and item | `scripts/ragops/capture.sh`, `shot.py` | open each PNG | appendix A1, A2, B1, C1, C2, D1, D2, F1 to F7 | Done-with-caveat | Rendered from the captured transcripts, not OS screenshots (the report says so). Cut or truncated commands remain in C1 (`tail`) and F3 (`cut`); F2 was re-shot with the full log. D1 is 166 lines and is split across pages. |
| S2 | Required screenshots: A (Batch B report; 0-embedded rerun), B (summary), C (fail, pass), D (full trace; prompt rebuild), E (before, after), F (get all; ingest log; eval log; ConfigMap edit; rollout status + undo + trace) | `docs/a3-evidence/*/screenshots/` | `ls docs/a3-evidence/*/screenshots` | appendix, in the order of the PDF | Done-with-caveat | As S1. |
| R1 | Repository: code, `k8s/`, `eval/` (golden set, results), `traces/`, config files | repo root | `git ls-files k8s eval traces ragops/config` | `eval/results/`, `traces/samples.jsonl` (6 records), `traces/README.md` | Done-with-caveat | `traces/` is a curated sample; the full set lived on the cluster volume. |
| R2 | README with the exact command to run each part (A to F) | `README.md` section "Assignment 03: RAGOps" | follow the table on a clean cluster | `F/F10-clean-cluster-rehearsal.txt` | Done | The rehearsal followed these commands. |
| R3 | `k8s/README.md` with the extra commands for a fresh cluster | `k8s/README.md` | same | same | Done | Chroma access text corrected to match `networkpolicy.yaml`. |

## 2. Needs a member (cannot be done by AI)

| # | What | Why it cannot be done by AI | Where to record it |
|---|---|---|---|
| 1 | Hand-label at least 8 judge answers (include the unsupported ones, g024 and g041), then re-run `ragops.suite.agreement` on your labels | The PDF asks for hand labels; the current 16 are Claude Code's. We must not claim a person made them. | `eval/judge_labels.jsonl`, `B/B3-judge-agreement.txt`, report 3.2 and (d) |
| 2 | Initial the synthetic spot-check sheet, in your own commit, for the rows you have read (at least 8) | Initials are a human attestation | `docs/a3-evidence/synthetic-spot-check.md` |
| 3 | Spot-check the coverage pair labels and the E4 questions; if a label is wrong, note it, do not edit a frozen file after a run | AI-made labels fix tau; a member must own them | `eval/coverage-calibration.jsonl`, `E/e4-*.jsonl` |
| 4 | Bilal reviews and merges the final PR on GitHub | Approval is his | GitHub review record |
| 5 | Submit on Classroom: repository URL and the report PDF (rebuild with `docs/a3-report/build.sh` after the last edit; check `body pages: 8`) | Only a member can submit | Classroom |
| 6 | Demo prep: both members read the other's half; run the runbook (`13-DEMO-RUNBOOK.md`) on the laptop; build the candidate index before showing a release; have Ollama on the host and the cluster warm | The demo is live and personal | `docs/a3-ragops/13-DEMO-RUNBOOK.md` |

## 3. Mark risk

The PDF states a total of 185 marks and gives **no per-part weights**, so no per-part mark can be stated here. An independent
audit of the repository estimated **about 172 / 185, with a range of 163 to 176**. That is an estimate by a reviewer, not a
grade. The risk is concentrated in:

| Risk | Why it may cost marks | What would reduce it |
|---|---|---|
| Human work is AI-made (judge labels, coverage pair labels, E1 live queries, E4 questions, spot-check sheet) | The PDF asks for hand labels and hand-reviewed questions; a marker may not accept AI labels | Section 2, items 1 to 3 |
| Judge agreement kappa -0.067 | The metric is weak: 15 of 16 labels are "supported" | More hand labels with unsupported answers (g024, g041) |
| Screenshots "with nothing cropped" | C1 uses `tail` and F3 uses `cut`; images are renderings of transcripts | Re-run C1 and the eval Job with full output (an eval Job takes about 40 min) |
| Demo | Needs a live cluster, a warm model and both members able to explain every part; generation takes 100 s or more per question on CPU | Rehearse (section 2, item 6) |
| 8-page limit | The body is exactly 8 pages | Do not add body text without removing some |
| Small N | 20 answerable questions: one question moves recall by 0.05 against a gate of 0.02 | Reported in (d); more questions are future work |
