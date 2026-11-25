# 13 — Demo runbook (rewritten after the measured runs)

The PDF (`docs/A3.pdf`): both members attend with a laptop running the pipeline on the local Kubernetes cluster. Live, we
(1) run the evaluation as a Kubernetes Job, (2) open a trace, (3) ingest a small batch we have not seen with the ingestion
Job. Both members must explain every part.

How to read this file. Every command below exists in the repo. "Evidence" names the file under `docs/a3-evidence/` (or
`eval/results/`) where that command, or the nearest one that was run, has real output with real timing. A command or a
combination marked **(not rehearsed)** has not been run on the cluster as written; run it once before the demo and write the
real timing on the cue card. Timings are from this CPU-only laptop (no GPU, `docs/a3-evidence/host.md`).

Speed facts we plan around (all measured): one model answer takes 90-130 s (p50 99.6 s, `B/B1-eval-summary.txt`; 87 s
in `D/D4-injection-rail-b08.txt`; 94 s in `F/F6-trace-after-undo.txt`); a full suite is 26-30 questions, 65-85 minutes, so it
**cannot** be run live; ingesting Batch B took 42.13 s (`A/A1-sync-batch-b.txt`); an unchanged re-sync 0.06 s
(`A/A2-unchanged-rerun.txt`); a rolling release about 25 s (`F/F5-zero-downtime.txt`: 09:47:20 to 09:47:43).

Rules: everything live is `kubectl` (or a script that only wraps it). Ollama is the only heavy process: **never run two things
that call the model at once** (eval and a live question) or both slow down and the eval can time out. One member drives, the
other narrates; swap at each part.

---

## 1. Pre-flight (do it 30 minutes before; not part of the demo time)

| # | Check | Command | Expect | Evidence |
|---|---|---|---|---|
| P1 | laptop on AC, sleep blocked | `systemd-inhibit --what=sleep:idle:handle-lid-switch --why=demo sleep 7200 &` | process stays up; notifications off | the suspend stall: `B/run2-stalled-by-suspend.md` |
| P2 | cluster up | `kubectl config current-context; kubectl get nodes` | minikube context, Ready | `F/F1-namespace-overview.txt` (cluster) |
| P3 | Ollama on the gateway address | `ss -ltn \| grep 11434` shows `192.168.49.1:11434`; if not, `make ollama-host` in its own terminal; then `ollama list` shows `nomic-embed-text`, `llama3.2:3b` | listening on 192.168.49.1 | `F/F7-network-matrix.txt` (pods reach 192.168.49.1:11434) |
| P4 | everything Ready | `kubectl get all,pvc,configmap,cronjob,job -n rahbar` | api x3, api-candidate, chroma-0, redis, ui Running; PVCs Bound | `F/F1-namespace-overview.txt` |
| P5 | eval-token Secret | `kubectl get secret ragops-eval-token -n rahbar`; if missing `scripts/ragops/eval-token.sh` (idempotent) | secret exists | script only (not rehearsed as a check) |
| P6 | API ready and which release | `kubectl port-forward -n rahbar deploy/api 8010:8000 &` then `curl -s localhost:8010/readyz` (the loader pod has no network, so it cannot do this) | JSON with `release_id` (R1-nomic on the baseline release) | `/metrics` through the same port-forward: `F/F4-metrics-port-forward.txt`; the `release_id` field is in `api/app/routes/health.py` (the readyz output itself was not saved: not rehearsed) |
| P7 | loader pod and the stored baseline | `kubectl apply -f k8s/loader-pod.yaml && kubectl wait --for=condition=Ready pod/ragops-loader -n rahbar`; `kubectl exec -n rahbar ragops-loader -- ls /results /results/baselines` | the result files and `baselines/live.json` | gate runs against it in `C/C1-gate-fail.txt` (not rehearsed: the `ls`) |
| P8 | a question works end to end and warms the model | `make ask Q="What CGPA puts a student on academic warning?"` | answer plus `trace_id`, 90-130 s | `D/D4-injection-rail-b08.txt` (latency 87 s) |
| P9 | stale Jobs gone, images present | `kubectl delete job eval --ignore-not-found -n rahbar`; `minikube image ls \| grep rahbar-` | api, ui, indexer, ragops | n/a |
| P10 | cue card ready | one trace id from `kubectl exec -n rahbar ragops-loader -- ls /traces`; the names of two stored results, e.g. `/results/20261125T074817Z_cand-llama1b.json` (gate FAIL) and `/results/20261125T054522Z_cand-minilm.json` (gate PASS) | on paper | `C/release-decisions.md` |
| P11 | the unseen-batch rehearsal folder | three files you have never ingested (one pdf, one html, one md or txt) in `./unseen-rehearsal/`; run section 3 on them once | accepted or quarantined with reasons, never a crash | `A/A1-verification-report-batch-b.txt` |

Rehearse everything in section 2 twice, swapping drivers, and write the real timings on the cue card.

---

## 2. The live script (core: 10 steps, about 25 minutes; extras: 5 optional)

Clock is the plan, not a measurement. The long parts are model answers (3 in the eval, 2 live questions).

### Part 0 — orientation (0:00-2:00) · driver A

**Step 1 (2 min).** Show the namespace.
```bash
kubectl get all,pvc,configmap,cronjob,job -n rahbar
```
Evidence `F/F1-namespace-overview.txt`. Say: `api` x3 with an HPA, `chroma` StatefulSet on a PVC, `redis`, the ingest CronJob,
PVCs `ragops-data`, `ragops-traces`, `ragops-results`, ConfigMaps `ragops-gate` and `ragops-eval-target`, `api-candidate`;
only the ingestion Job writes the vector store.

### Part 1 — the evaluation as a Kubernetes Job (2:00-12:00) · driver B

**Step 2 (about 6 min, wall clock).** The reduced suite Job.
```bash
make eval-demo
# = scripts/ragops/eval.sh suite demo --suite-args "--batches A --levels component,endpoint --limit 3 --no-judge"
```
What it does: `eval.sh` rewrites the ConfigMap `ragops-eval-target`, deletes the old Job, applies `k8s/eval-job.yaml`, waits for
Complete or Failed and prints the log (`eval.sh`). Scope, said openly: the **same code** as the full run, on the first 3 golden
questions (g001-g003, all answerable) of batch A, at the component level (retrieval only, no model) and the endpoint level
(3 answers from the model), judge off (the deterministic faithfulness proxy remains). It **generates 3 answers** at about
100 s each = 5 to 6.5 minutes, plus pod start. There is no gate: a 3-question result is not comparable with the 20-question
baseline, so the target runs `MODE=suite` and ends `RESULT=SUITE_DONE`.
Status of the evidence: `eval.sh suite ...` is the command that produced `B/B1-eval-summary.txt` (full run); `--limit`, `--no-judge`
and `--levels` are `run_suite.py` options with unit tests, but **this exact combination was not run on the cluster
(not rehearsed)**. Rehearse it and write the real duration on the card; if it exceeds 8 minutes, drop to `--limit 2`.
Expected last lines: the summary table (`component recall@3/@5`, `endpoint latency p50/p95`, `endpoint faithfulness`),
`RESULT=/results/<timestamp>_demo.json`, `RESULT=SUITE_DONE`. With no unanswerable question in the first 3, the abstention
rows show no data (not rehearsed). While it runs (second terminal, no model calls): `kubectl get pods -n rahbar -l app=ragops-eval`
and talk: three levels, fixed seeds, cache bypassed during evaluation, `backoffLimit: 0`, exit code = verdict.

**Step 3 (about 1 min, unmeasured Job start).** The gate on a stored result, in seconds.
```bash
make eval-gate-rerun RESULT=/results/20261125T074817Z_cand-llama1b.json
# = scripts/ragops/eval.sh gate gate-rerun --candidate <file> --baseline /results/baselines/live.json
```
`MODE=gate` skips the suite and applies `ragops.gate.apply` to the stored file with the thresholds read from ConfigMap
`ragops-gate`. Expected (this result file, rule table from `C/C1-gate-fail.txt`): `recall5_drop FAIL` (0.80 to 0.60, limit 0.02),
`faithfulness_min FAIL` (0.8571 against 0.89), `abstention`, `citation_validity`, `p95_latency` PASS, `GATE FAILED`,
`RESULT=GATE_FAIL decision=...`, Job `Failed`, and `make` ends with an error because `eval.sh` exits 1. The failing exit is the
correct outcome. That the gate step is quick is by construction (it reads two JSON files); the standalone run time of `MODE=gate`
was **not measured (not rehearsed)**. For a pass, use `/results/20261125T054522Z_cand-minilm.json` (decision PASS, `C/release-decisions.md`).
Why a stored result: the gate compares `golden_hash`, `corpus_digest`, `seed`, `profile_hash`; two stored results from the same corpus state
are comparable, a fresh 3-question result is not.

### Part 2 — open a trace (12:00-16:00) · driver A

Do not start this while the eval Job is still running (both call the model).

**Step 4 (about 2 min).** One live question.
```bash
make ask Q="How much is the semester parking fee for a car?"
```
Prints the answer, citations and `trace_id` (`api/app/routes/ask.py` sets `trace_id` and the `X-Trace-Id` header). Answer time 90-130 s
(`D/D4-injection-rail-b08.txt`: 87 s). Use a question from the examiner if they give one. Copy the `trace_id`.

**Step 5 (1 min).** Open it through the loader pod, inside the cluster.
```bash
kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.show <trace_id> --traces /traces --lake /data
```
Evidence: `D/D4-injection-rail-b08.txt` is this exact command on the parking question. It prints query, release, embedding model and
version, collection and index revision, the ranked chunks with document versions and scores, guardrail actions (here: `injection
neutralised` on chunk `campus-parking-policy@2026-09#0002`), prompt hash, model and parameters, answer, latency split
(`retrieve` 12 ms, `generate` 87 s), cache state, then `prompt hash verified` and one `rebuilt from snapshot; text present in the prompt`
line per chunk, then the exact prompt. Say: the trace store is the PVC, so the prompt can be rebuilt after the pod is gone
(`F/F6-trace-after-undo.txt` is a trace opened after a rollback and shows the release and collection that served it).
Metrics over the window: `kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.summary --traces /traces --route /api/ask --release R1-nomic`
(`D/D3-trace-summary.txt`: 62 requests, abstention 0.2258, generate p50 111.9 s). Note: `kubectl logs ... | grep '"type": *"trace"' | python -m json.tool`
did **not** parse in our attempt (`D/D1-trace-record.txt`, exit 1); use the loader command.

### Part 3 — ingest an unseen batch (16:00-25:00) · driver B

The one-page procedure is section 3 below. Steps:

**Step 6 (1 min).** Deliver the folder.
```bash
kubectl cp ./unseen/. rahbar/ragops-loader:/data/inbox/batch-c/
kubectl exec -n rahbar ragops-loader -- ls -la /data/inbox/batch-c
```
Evidence: `A/A0-deliver-batch-b.txt` (same mechanism, folder `batch-b`, 12 files, `exit 0`). The folder name `batch-c` is
read by `indexer/pipeline/catalog.py::_batch_from_path` (see section 3); the exact name `batch-c` was not rehearsed, `batch-b` was.

**Step 7 (1-2 min).** Run the ingestion Job.
```bash
scripts/ragops/job.sh sync
```
Evidence `A/A1-sync-batch-b.txt`: Job `ingest-sync-<ts>`; last log line is the run summary: for Batch B `docs_new 6, docs_quarantined 6,
docs_superseded 1, docs_unchanged 9, chunks_embedded 52` on two indexes (26 + 26), `seconds 42.13`, `run_id ingest-20261125T100821Z-sgc8`,
`revision r0002, revision_bumped true`. The log line `exit: 1 mapped to 0` means "finished, some quarantined": the Job is
Complete on purpose. (The same output shows a line `EOF marker not found` from the script's wait step; the Job still
succeeded, cause not investigated.) Write down `run_id`.

**Step 8 (2 min).** Read the verification report.
```bash
kubectl exec -n rahbar ragops-loader -- cat /data/reports/verification/<run_id>.md
kubectl exec -n rahbar ragops-loader -- ls /data/quarantine
```
Evidence `A/A1-verification-report-batch-b.txt`: a row per document with four checks (quality, completeness, recency, uniqueness),
outcome and reason code, then `accepted 6 . quarantined 6 . archived 1 . unchanged 9`. (`ls /data/quarantine` not rehearsed.)

**Step 9 (2 min).** Prove an accepted document is searchable and traceable.
```bash
make ask Q="<a question whose answer is in one accepted new file>"
kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.show <trace_id> --traces /traces --lake /data
```
Example from Batch B: the parking question retrieves `campus-parking-policy@2026-09` (`D/D4-injection-rail-b08.txt`, collection `rahbar @ r0009`).
Counts per document: `scripts/ragops/job.sh count -- count` (`A/A3-count-before-batch-b.txt`; counts and orphans, not rehearsed on the unseen files).

**Step 10 (under 1 min).** Incrementality.
```bash
scripts/ragops/job.sh sync
```
Evidence `A/A2-unchanged-rerun.txt`: `chunks_embedded 0`, `docs_unchanged 9`, `seconds 0.06`, `revision_bumped false`.

Core total: steps 1-10 about 25 minutes (2 + 6 + 1 + 2 + 1 + 1 + 2 + 2 + 2 + 1 plus pauses), unrehearsed as a whole. Say "25 minutes
core, up to 35 with extras" to the examiner and adapt.

### Extras (pick one or two, 2-4 minutes each)

* **E1 Threshold edit without a rebuild** (`scripts/ragops/gate-demo.sh /results/20261125T074817Z_cand-llama1b.json`): runs the gate on the failing
  result, relaxes `recall5_drop` to 0.25 and `faithfulness_min` to 0.80 in ConfigMap `ragops-gate`, re-applies the same Job (it passes, same image
  printed twice), restores the committed ConfigMap. **Not rehearsed**: no raw output of this script is in `docs/a3-evidence/`. Rehearse before use.
* **E2 Release refused**: `scripts/ragops/release.sh cand-llama1b` prints `REFUSED: gate decision for cand-llama1b is 'fail', not pass`, exit 1,
  deployment history unchanged (`F/F3-release-refused.txt`). Dry run of a passing one: `scripts/ragops/release.sh cand-minilm --dry-run` (`F/F3-release-hardened-checks.txt`).
* **E3 Rolling release and undo**: a release rolled out in about 25 s with 47 of 47 probe requests 200 (`F/F5-release-rollout.txt`, `F/F5-zero-downtime.txt`;
  start the probe first with `scripts/ragops/rollout-probe.sh start`, stop with `... stop`). Undo: `kubectl -n rahbar rollout undo deployment/api` and
  `kubectl -n rahbar rollout status deployment/api` (`F/F6-bad-release-and-undo.txt`: a bad config stalls at 1 of 3 new replicas, old pods keep
  serving, 150 of 150 requests 200, undo succeeds). Do not do this live on the demo release unless you are ready to roll back to `R1-nomic`
  (`kubectl -n rahbar rollout undo deployment/api --to-revision=1`, `F/F6-return-to-baseline.txt`). A live bad release is destructive to the demo state: rehearsed, but optional.
* **E4 Network matrix**: `scripts/ragops/netmatrix.sh` (`F/F7-network-matrix.txt`): eval pod reaches api, api-candidate and Ollama, **denied** to chroma and
  redis; UI denied to chroma; API allowed to chroma and redis; the loader has no network at all.
* **E5 Restore an archived version**: `scripts/ragops/job.sh restore -- restore <doc>@<version>` (`A/A4-restore-rollback-demo.txt`: restore
  `faculty-entrepreneurship-and-technical-start-ups-policy@2022-05`, `chunks_embedded 0`, retrieval returns 2022-05 at index revision r0005, then back).
  Coverage check: `kubectl apply -f k8s/coverage-job.yaml` ends `Failed` by design with `COVERAGE GAP` (`E/E1-coverage-before.txt`: 0.595 against 0.85).

---

## 3. The unseen batch: one page (what to do if the examiner hands over a folder)

1. **Do not read or edit the files first.** Plug the folder in, copy it as it is.
2. **Supported formats**: `.pdf`, `.html`/`.htm`, `.md`, `.txt` (`catalog.py::SUPPORTED`). Anything else, and files starting with `.` or `_`, or named `readme*`,
   is silently skipped: if the report is shorter than the folder, check `ls -la` and extensions.
3. **No catalog is needed.** Title, date and version are taken, in this order, from an optional `_batch.yaml`, from inside the file (front matter, `<title>` and `<meta name="date">`,
   PDF title and creation date), or derived (first heading-like line, a date in the text or in the file name). The version defaults to the date.
   If title or date cannot be found the file is **quarantined** (`C-MISSING-TITLE`, `C-MISSING-DATE-VERSION`), not guessed.
4. **How the folder name tags the batch**: any folder in the path named `batch-x`, `batch_x`, `batchx` or `batch x` (case-insensitive) gives batch `X`;
   anything else, `A` (`_batch_from_path`, `DEFAULT_BATCH`). Use `batch-c` (batches A and B exist already). The tag only matters for the evaluation suite's
   "requires batch" rule; ingestion treats all folders alike (the demo notice in `A/A5-changed-and-deleted-document.txt` was ingested from a folder named `demo`, tagged A).
5. **Commands** (steps 6-8 above): `kubectl cp ./unseen/. rahbar/ragops-loader:/data/inbox/batch-c/`, `scripts/ragops/job.sh sync`, then
   `kubectl exec -n rahbar ragops-loader -- cat /data/reports/verification/<run_id>.md` (run id on the summary line).
6. **What the report will show** (all seen in `A/A1-verification-report-batch-b.txt`): per file four checks and one outcome. Reason codes that appeared:
   `U-EXACT-DUP` (byte-identical to an indexed document), `U-NEAR-DUP` (near duplicate of an accepted one), `C-TRUNCATED` (ends mid-sentence),
   `C-MISSING-DATE-VERSION`, `C-MISSING-TITLE`, `Q-EXTRACT-FAIL` (damaged PDF), `R-SUPERSEDED-BY` (an older indexed version was **archived**
   because a newer one arrived). Accepted files say `all four checks passed` or `newer version detected: supersedes ...`. Quarantine is correct behaviour, not a crash.
7. If the Job is `Failed` rather than `Complete`: `kubectl logs -n rahbar job/<ingest-sync-...> --all-containers` (the script prints the last 40 lines on failure),
   remove the offending file with `kubectl exec ... rm`, run `job.sh sync` again, and say which file and why.
8. A late older version of an existing document is quarantined (`R-NEWER-EXISTS`) rather than replacing the newer one; seen in
   `A/A1b-sync-late-b13.txt` and `A/A1b-verification-report-b13.txt` (`docs_quarantined 1`, nothing embedded).

---

## 4. Likely viva questions, short true answers

* **Why can the eval not be the full suite?** 26-30 questions at about 2 minutes each (answer plus judge) is 65-85 minutes on a CPU-only laptop. The live Job is the same code on 3 questions without the judge; the full results are committed (`eval/results/*_baseline.json`, `B/B1-eval-summary.txt`).
* **How deterministic is it?** Two baseline runs: retrieval metrics identical (Delta 0.0000), module determinism `max |d| = 0`; latency and judge faithfulness vary (`B/B2-stochasticity.txt`). Run 1 was 17:46 UTC, run 2 03:42 UTC after a stall.
* **What does the gate do and who stops a bad release?** `ragops.gate.apply` compares a result with the baseline under thresholds from ConfigMap `ragops-gate`; the Job exits with its verdict. Kubernetes does not know about the gate: `release.sh` refuses unless a fresh passing decision exists for this candidate (`F/F3-release-refused.txt`, `F/F3-release-hardened-checks.txt`).
* **Which change did you test?** The embedding model: minilm released (PASS), llama3.2:1b as embedder rejected (recall@5 0.80 to 0.60, faithfulness 0.857), mxbai rejected (abstention correctness 0.833 against 1.000) (`C/release-decisions.md`).
* **Zero downtime?** `maxSurge 1`, `maxUnavailable 0`, readiness probe; 47 of 47 probe requests were 200 during a release (`F/F5-zero-downtime.txt`). A bad release stalls at 1 of 3 new pods while the 3 old ones serve; `rollout undo` fixes it (`F/F6-bad-release-and-undo.txt`).
* **Why does undo restore the collection and embedding version?** They live in the Deployment's pod template (set by `release.sh`), not in a shared ConfigMap (`k8s/README.md`). A side effect: `kubectl apply -k` after a release rolls it back to the committed values.
* **What does the trace prove?** The exact prompt: stored by hash, re-hashed on open, each chunk rebuilt from the lake snapshot (`prompt hash verified`, `rebuilt from snapshot`, `D/D4-injection-rail-b08.txt`).
* **Injection?** The parking policy carries "Ignore all previous instructions..."; the retrieval rail neutralised that chunk (guardrail action in the trace) and the answer was the true fee (`D/D4-injection-rail-b08.txt`).
* **Why verify before chunking, and what is checked?** Four checks (quality, completeness, recency, uniqueness) with reason codes; bad documents never cost embeddings or enter the index (`A/A1-verification-report-batch-b.txt`).
* **How is the update incremental?** The ledger records each file by hash: re-run embeds 0 chunks in 0.06 s (`A/A2-unchanged-rerun.txt`); a changed document replaces only its own chunks, a new one adds only its own (`A/A5-changed-and-deleted-document.txt`).
* **Archive instead of delete?** An older version is archived, kept in the lake, excluded from retrieval, and `restore` brings it back with 0 chunks re-embedded (`A/A4-restore-rollback-demo.txt`).
* **Only one writer to the vector store?** The ingest Job and CronJob (`concurrencyPolicy: Forbid`), a lock file, and NetworkPolicy: the eval pod is denied to Chroma (`F/F7-network-matrix.txt`). Chroma itself has no authentication (`k8s/README.md` Limits).
* **Coverage?** 25 of 42 live queries covered (0.595) against 0.85: a gap, the job fails by design (`E/E1-coverage-before.txt`); after Batch B, `E/E3-drift-diff.txt` shows no backward regression and the 4 new questions retrieved.
* **Judge reliability?** Agreement 0.875 on 16 labelled items but Cohen kappa -0.067, so we also report the deterministic proxy (`B/B3-judge-agreement.txt`).
* **What went wrong with the AI help?** `docs/AI-USAGE.md` section "Assignment 03": the eval endpoint was reachable through the Ingress (now token-guarded), `release.sh` built shell strings (now argument arrays), a GPU laptop was assumed, an exit-code bug would have mapped a crash to success.

---

## 5. Failure modes we actually hit, and the fix

| What we saw | Where | Fix |
|---|---|---|
| Laptop on battery went to sleep mid-run; run 2 stalled 8.5 h, timers distorted | `B/run2-stalled-by-suspend.md` | AC power, `systemd-inhibit --what=sleep:idle:handle-lid-switch`, re-run from the start |
| Eval Job `Failed` after 42 min: the gate failed (expected for a bad candidate) | `C/C1-gate-fail.txt` | read the rule table; `RESULT=GATE_FAIL` is the verdict, not an error; `eval.sh` exits 1 |
| Coverage Job pod `Error` in the namespace listing | `F/F1-namespace-overview.txt`, `E/E1-coverage-before.txt` | by design: `COVERAGE GAP` exit 1; say so |
| Ingest log shows `exit: 1 mapped to 0` | `A/A1-sync-batch-b.txt` | quarantine is not a failure; the Job is Complete; read the report |
| `kubectl logs ... \| grep trace \| json.tool` fails to parse | `D/D1-trace-record.txt` | use `ragops.trace.show` in the loader pod |
| Bad config rollout never becomes Ready (1 of 3 new pods) | `F/F6-bad-release-and-undo.txt` | by design: old pods keep serving; `kubectl rollout undo deployment/api -n rahbar` |
| A release is lost after `make apply` | `k8s/README.md` | the manifests in Git say `R1-nomic`; apply rolls the release back; commit values to keep a release |
| Chroma crashed on start (`CHROMA_PORT=tcp://...`) | `docs/AI-USAGE.md` item 3 (assignment 2) | `enableServiceLinks: false` on every pod (already in the manifests) |
| API pods killed by the startup probe while Chroma was down | `docs/AI-USAGE.md` item 4 | fixed in code (heartbeat, 5 s client timeout); if pods are not Ready, check Chroma first: `kubectl get pods -n rahbar` |
| First ingestion 561 s for 532 chunks | `F/F2-ingest-first-run.txt` | not a problem for the demo (unseen batches are small); do not start from an empty cluster live |

Not seen in evidence, from the brief (all **not rehearsed**): `ErrImagePull` after a rebuild, an unseen file that crashes extraction. If a live step fails twice: say what you saw, show the logs, show the committed evidence for that step, continue.

### Recovery checklist

1. **Power and sleep**: AC connected; `systemd-inhibit --what=sleep:idle:handle-lid-switch --why=demo sleep 7200 &`; screen lock off.
2. **Ollama address**: it must listen on `192.168.49.1:11434` (the minikube gateway, `host.minikube.internal`). `make ollama-host` starts it on the right address; check with `ss -ltn | grep 11434`. If the gateway IP differs, the `ipBlock` in `k8s/base/networkpolicy.yaml` and `k8s/base/ragops-networkpolicy.yaml` must change (`k8s/README.md`). An eval Job with `RESULT=INFRA_ERROR` almost always means Ollama or the API was unreachable.
3. **After rebuilding an image**: `make images TAG=dev` (it runs `minikube image load` for each of the four images). The tag stays `dev` with `imagePullPolicy: IfNotPresent`, so running pods keep the old image until they are replaced: `kubectl -n rahbar rollout restart deployment/api` (and `deployment/ui`); Jobs and the loader pod pick up the new image when recreated (`kubectl delete pod ragops-loader -n rahbar` then `kubectl apply -f k8s/loader-pod.yaml`). A restart keeps the release env in the pod template (not rehearsed).
4. **Cluster**: `minikube status`; `minikube start` if stopped; `kubectl get pods -n rahbar` until all Running; Chroma data survives (PVCs).
5. **Stuck Job**: `kubectl delete job eval -n rahbar --ignore-not-found` (`eval.sh` does this itself); ingestion Jobs are named per run; a held lock makes the run exit 3 (`indexer/pipeline/run.py`), check `kubectl get jobs -n rahbar` for a running ingest.
6. **Only one heavy process at a time.** If the model is slow, wait for the running Job; `kubectl top pods -n rahbar`.
7. **Last resort**: switch to the committed evidence for the step and say so.
