# 13 — Demo runbook, rehearsal and viva preparation

The PDF's demo rules (verbatim in spirit): **both members attend and bring a laptop with the pipeline running on your local Kubernetes cluster. Running only on Docker containers gives 0 for the demo.** During the demo you will **(1) run your evaluation as a Kubernetes Job, (2) open a trace, and (3) ingest a small batch of documents you have not seen by running your ingestion Job.** And: *"Both members must be able to explain every part of the work at the demo."*

This file is the script, the safety net and the question bank. Rehearse it **twice** (T62).

---

## 1. Principles

1. **Everything live is `kubectl`.** Not `docker`, not `python …` on the laptop against a local Chroma. Helper `make` targets are fine **if they only wrap `kubectl`** — show the underlying command once.
2. **Fast by design.** A full suite takes hours on CPU. The live eval uses a **demo profile** (below) that finishes in minutes; the full results are in the committed files. Say this openly — it is a scoped run of the same code, not a different one.
3. **No surprises.** Anything that depends on the internet, a cold model, or a long download is done **before** the demo.
4. **Unseen documents must not crash anything.** The worst acceptable outcome for a bad document is *quarantined with a reason*.
5. **Split the speaking.** One member drives, the other narrates; swap at each part so both show they understand every part.

---

## 2. The demo profile (so the live Job finishes in minutes)

`ragops/config/suite-demo.yaml` — same code, reduced scope:

```yaml
# inherits suite.yaml, overrides:
levels: [module, component, endpoint]
module: {embed_sample_chunks: 10, determinism_texts: 5}
component: {limit: 12}                      # first 12 answerable questions, retrieval only
e2e: {limit: 3, ids: [g001, g0xx, g0yy]}    # 2 answerable + 1 unanswerable, fixed ids
judge: {enabled: false}                     # keep the deterministic proxy; judge adds minutes
```
Create `eval/results/baseline-demo.json` **in advance** with exactly this profile (same seed), and promote it as `/results/baselines/demo.json`. The demo Job runs with `SUITE_ARGS="--profile demo"`, `BASELINE_RESULT=/results/baselines/demo.json`. Time it on the demo laptop (**target ≤ 8 minutes** end to end including Job start; `MEASURE` and write it on the cue card). The gate's `require_same` compares the *profile hash* too, so a demo result is never compared to a full baseline.

If the endpoint level is still too slow on the demo laptop, run `levels: [module, component]` live and show the **endpoint results from the committed full run** — say so.

---

## 3. Pre-demo checklist

**T−24 h**
- [ ] `git status` clean on `main`; the demo uses the **submitted** commit
- [ ] minikube started with Calico; `kubectl get nodes` Ready; ingress and metrics-server addons enabled
- [ ] images present: `minikube image ls | grep rahbar-` (api, ui, indexer, ragops)
- [ ] Ollama serving on the address the cluster reaches (`make ollama-host`); `ollama list` shows `nomic-embed-text`, `llama3.2:3b` and the candidate models; **warm** each (one embed, one generation)
- [ ] `kubectl get all,pvc,configmap,cronjob,job -n rahbar` — everything Running/Bound/Complete; HPA shows numbers
- [ ] a question works through the Ingress (`make ask Q="…"`)
- [ ] the `ragops-gate` ConfigMap equals the committed file (`kubectl get cm ragops-gate -o yaml` vs `k8s/base/ragops-gate.yaml`)
- [ ] results PVC has `baselines/demo.json` and `baselines/live.json`
- [ ] delete leftover Jobs (`eval`, `ingest`) so logs are fresh; keep the *evidence* Jobs' logs saved in files
- [ ] laptop: power adapter, sleep/suspend disabled, notifications off, terminal ≥ 120 columns, font large, second terminal pre-opened

**T−1 h**
- [ ] repeat the cluster sanity checks; run `kubectl apply -f k8s/loader-pod.yaml` and wait Ready
- [ ] **prepare the unseen-batch rehearsal folder** (not the real one): 3 documents you have never ingested (a PDF, an HTML, a text/Markdown file) — different from Batch B
- [ ] have the previous trace ids and the commands on a cue card (not in your head)
- [ ] close everything that eats RAM/CPU (browser tabs, IDEs) — the 3B model and Chroma share the machine

---

## 4. The live script (≈ 20–25 minutes; adjust to the examiner's time)

### Part 0 — orientation (1–2 min) · Driver: A · Narrator: B
```bash
kubectl config current-context
kubectl get all,pvc,configmap,cronjob,job -n rahbar          # also Screenshot F1
```
*Say:* namespace `rahbar`; `api` ×3 (HPA 3–8), `chroma` StatefulSet with PVC, `redis`, the **ingest CronJob**, PVCs `ragops-data/traces/results`, ConfigMaps `ragops-gate` and `ragops-eval-target`; *only the ingestion Job writes the vector store*.

### Part 1 — run the evaluation as a Kubernetes Job (6–8 min) · Driver: B · Narrator: A
```bash
kubectl -n rahbar patch cm ragops-eval-target --type merge -p '{"data":{"TARGET_URL":"http://api:8000","LABEL":"demo-live","MODE":"suite+gate","SUITE_ARGS":"--profile demo","BASELINE_RESULT":"/results/baselines/demo.json"}}'
kubectl -n rahbar delete job eval --ignore-not-found
kubectl apply -f k8s/eval-job.yaml                           # the PDF's literal command
kubectl -n rahbar logs -f job/eval                           # module → component → endpoint → gate
kubectl -n rahbar get job eval                               # Complete (gate passed) or Failed (gate failed)
```
*Say while it runs (this is where the paper is used):* the three levels of Table 1; seeds fixed; cache bypassed; the **gate** compares to the baseline with thresholds from a ConfigMap; exit code = verdict. *Then show:* the summary table; `RESULT=GATE_PASS`; the result file on the PVC (`kubectl exec ragops-loader -- ls /results`).
**Optional (60 s) — the ConfigMap threshold demo (F2-05):** run with `MODE=gate` on an existing result, show `GATE_FAIL`, `kubectl patch cm ragops-gate …` to relax one rule, re-apply the same Job, show `GATE_PASS`; print the image reference both times to prove no rebuild.

### Part 2 — open a trace (3–4 min) · Driver: A · Narrator: B
```bash
curl -s -X POST http://$(minikube ip)/api/ask -H 'Host: rahbar.local' -H 'Content-Type: application/json' \
     -d '{"question":"<a question the examiner chooses or one from the cue card>"}' | jq '{trace_id, answer, citations}'
kubectl -n rahbar logs deploy/api --since=2m | grep '"type":"trace"' | tail -1 | jq .       # Screenshot D1 style
kubectl -n rahbar exec ragops-loader -- ls /traces | head                                     # also written to a volume
kubectl -n rahbar exec ragops-loader -- python -m ragops.trace.show <trace_id>                 # exact context + prompt, hash verified, REBUILD OK
```
(The loader pod runs the `rahbar-ragops` image, so the trace tool runs **inside the cluster** — no Python environment on the laptop is involved, which keeps the "Kubernetes only" rule beyond argument. Rehearse this exact command.)
*Say:* every query writes one JSON line (stdout **and** the traces PVC); the tool rebuilds the **exact prompt** and **re-verifies its hash** from the immutable lake snapshots — that is traceability across data versions; show the retrieved chunks with **document versions**, the **filters**, the **rail** result.
If asked "show me a flagged injection": ask the B08 question and show `guardrails[]`.

### Part 3 — ingest documents you have not seen (6–8 min) · Driver: B · Narrator: A
1. The examiner provides a few files (USB / shared folder). Copy them **as they are** into the inbox:
   ```bash
   kubectl cp ./unseen-batch/. rahbar/ragops-loader:/data/inbox/unseen/
   kubectl -n rahbar exec ragops-loader -- ls -l /data/inbox/unseen
   ```
2. Run the ingestion Job:
   ```bash
   kubectl -n rahbar delete job ingest --ignore-not-found
   kubectl apply -f k8s/ingest-job.yaml
   kubectl -n rahbar wait --for=condition=complete job/ingest --timeout=900s
   kubectl -n rahbar logs job/ingest | tail -30                 # summary line with counters
   ```
3. Show the **verification report** (`kubectl exec ragops-loader -- cat /data/reports/verification/<latest>.md`): per document, four checks, reasons; show anything **quarantined** and why (`ls /data/quarantine/<run>/`).
4. Show that **accepted** documents are searchable: ask a question about one of them; show the trace with the new `doc_id`/version; `kubectl … run … count --doc-id <id>` (or the ingest image's `count`) shows the chunk count.
5. *Say:* verification precedes chunking; incremental update embedded only the new chunks (`chunks_embedded` equals the new documents' chunks; existing documents untouched; `revision_bumped: true` so the API cache scope changed); the CronJob does the same on a schedule; the Job is the **only writer**.
6. **Optional proof of incrementality:** run the Job again — `chunks_embedded: 0`.

### Part 4 — extras if time allows (pick one) · whoever is ready
* **Rolling release / undo** (S3-a): `scripts/ragops/release.sh cand-bad` is **refused** (gate) → show; release a prepared, deliberately broken config → `rollout status --timeout=120s` stalls while old pods keep serving → `kubectl rollout undo` → new trace shows the previous collection and embedding version.
* **Persistence:** `kubectl delete pod -n rahbar -l app=api` / `chroma-0`, show data/traces still there.
* **Network isolation:** `kubectl exec` from the UI pod to Chroma fails; from the eval pod to Chroma fails; to the API works.
* **Resources:** `kubectl top pods -n rahbar`; `kubectl get hpa`.

---

## 5. Talk track per part (what the paper lets you say)

| Part | One sentence the examiner should hear |
|---|---|
| A | *Data is checked before it is indexed (paper 4.2.2) — four checks, reasons, quarantine — and updates are incremental and versioned: archive instead of delete, so we can roll back (4.2.3–4.2.4).* |
| B | *We test at three granularities — module, component, end-to-end (4.2.5, Table 1) — with fixed seeds because RAG is stochastic, and one command produces a timestamped result.* |
| C | *A release is gated by thresholds from a ConfigMap; a bad candidate is stopped, a good one is rolled out with zero downtime, a bad release is undone (4.1(d), 4.2.6).* |
| D | *Every query leaves a trace that lets us rebuild the exact prompt and see which document versions, filters and guardrails were involved — that is traceability and observability (Table 2, §3.2.3).* |
| E | *The test set can go stale; coverage compares live queries with the golden set and flags a gap below a calibrated threshold (4.2.7).* |
| F | *Each RAGOps responsibility has a Kubernetes object: Job, CronJob, PVC, ConfigMap, second Deployment, rollout history.* |

---

## 6. Failure modes and recovery (keep this open on the second screen)

| Symptom | Likely cause | Quick fix |
|---|---|---|
| `ErrImagePull` / `ImagePullBackOff` | image not in minikube's Docker | `minikube image load <img>`; `imagePullPolicy: IfNotPresent` |
| Job pod `Pending` | PVC unbound / quota | `kubectl describe pvc,pod`; check the storage class; re-create the PVC (**lose data** — only on a throw-away cluster) |
| Eval Job `Failed` with `RESULT=INFRA_ERROR` | API/Ollama unreachable (network policy, wrong host IP) | `kubectl logs job/eval`; check `host.minikube.internal` IP in the policy; `make ollama-host` running |
| Eval Job `Failed` with `GATE_FAIL` when you expected pass | thresholds/profile/baseline mismatch | read the rule table; confirm the profile hash and baseline file |
| First answer takes minutes | cold model | warm up before the demo; keep `OLLAMA_KEEP_ALIVE` high |
| `kubectl cp` fails | loader pod not Ready / no `tar` | `kubectl get pod ragops-loader`; recreate with an image that has `tar` |
| Ingest Job exits non-zero | lock held (previous run), Chroma down, embedding failure | `kubectl logs job/ingest`; stale lock auto-expires; `kubectl get pods -l app=chroma` |
| Unseen document **crashes** the Job | extraction bug | it must not — if it does, `kubectl logs` shows the file; remove it from the inbox and re-run; fix after the demo; this is why you rehearse with unfamiliar files |
| Unseen document quarantined | missing title/date, scanned image, duplicate | that is correct behaviour; show the reason; if it is a false positive, say which threshold and why |
| `ingest` shows `docs_unchanged` for a new file | file placed in the wrong folder / hidden file | `ls -la /data/inbox`; extension supported? |
| API pods not Ready after ingest | embedding pin mismatch / empty collection | `kubectl logs deploy/api | grep -i mismatch`; `kubectl get pods`; `readyz` output |
| Trace not found | wrong pod's file not mounted / rotated | `ls /traces`; search `*.jsonl*`; use `kubectl logs` stream mode (`--stdin`) |
| Port/IP wrong for the Ingress | minikube IP changed | `minikube ip`; update the `Host` header usage |
| Rollout stalls (S3-a) | by design | wait for `--timeout`, then `rollout undo` |
| Laptop sleeps mid-Job | power settings | disable suspend; re-run the Job (it is idempotent) |

If a live step fails twice: **say what you saw, show the logs, switch to the committed evidence for that step, and continue.** Never improvise a Docker-only workaround.

---

## 7. Viva question bank (both members must answer every one)

**Part A — data**
1. Why does verification run *before* chunking? What would break if it ran after? *(cost, bad chunks in the index, orphan cleanup)*
2. Name the four checks and show the code for one. What is the reason string for a truncated file?
3. What happens when a **newer** version arrives, and what when an **older** version arrives late? Why is the first *archived* and the second *quarantined*? How is an archived version excluded from retrieval and how is it restored? *(R-SUPERSEDES/R-SUPERSEDED-BY vs R-NEWER-EXISTS; metadata flag + the A2 filter; `ops restore`)*
4. How do you detect a near-duplicate? How did you choose the threshold? What is the false-positive risk? *(matrix, Jaccard)*
5. How does the second run embed zero chunks? What if a file is renamed? What if its bytes change?
6. Delete a document: what exactly is removed, where, and how do you prove no orphans remain?
7. What happens if the Job is killed between writing Chroma and writing the ledger?
8. How does the ingestion Job process a document it has never seen with no catalog? Where does the title/date come from? What if none can be found?
9. Why is the ledger a JSON file on a PVC and not a database? What are the limits?

**Part B — tests**
10. Define recall@5, MRR and nDCG@5 for one golden question (do the example). Why are unanswerable questions excluded from recall?
11. Why `(document, page)` ground truth? What if a chunk spans two pages?
12. What does "module level" tell you that "component level" does not? Give your example for (b).
13. How do you make the suite deterministic? Where does variation remain? What was your largest Δ and why?
14. How is faithfulness measured? How good is the judge (agreement/κ)? Why a deterministic proxy too?
15. Why is the semantic cache bypassed during evaluation? What would happen otherwise?
16. Why does the component level call `/api/retrieve` instead of `/api/ask`?

**Part C — change and release**
17. Which change did you test and why that one? What is the relevance-floor issue with a new embedding model?
18. Show `gate.yaml`. Where did the faithfulness and p95 thresholds come from? When were they committed relative to the candidate runs? *(before)*
19. What exactly makes the gate Job "fail"? Why `backoffLimit: 0`?
20. How do you show a threshold change alters the outcome without rebuilding the image?
21. Why does `rollout undo` restore the collection and embedding version? Where would it *not* if you had used the ConfigMap?
22. How does `maxUnavailable: 0` combine with the readiness probe to protect users during a bad release?
23. How is "stopped by the gate and never rolled out" enforced? *(the release script — and be honest that Kubernetes does not know about the gate)*

**Part D — observability**
24. List the fields of a trace and where each comes from in the code. What is `reranked_order` in a system without a reranker?
25. How does the trace tool prove it rebuilt the *same* prompt? What if the chunk was updated afterwards? *(lake snapshots + versions)*
26. What does the retrieval rail do with B08? What is logged and what is deliberately not?
27. Metrics vs traces: when do you use which? *(known unknowns vs unknown unknowns; paper §2.2)*
28. Why are traces written per pod? What breaks at 8 replicas on a multi-node cluster?
29. A2 refused to log questions; A3 logs them. What changed and what protects it?

**Part E — drift**
30. How is coverage computed? How did you choose τ? What does 85% mean in the paper?
31. What did Batch B change in the metrics? Which changes were regressions and which were expected?
32. How do you stop coverage being gamed by writing new questions that copy the live ones?

**Part F — Kubernetes**
33. Which object does what? (the table in 10 §9). *Which object makes sure only one component writes to the vector store?* *(be honest: Job + Forbid + lock + NetworkPolicy + code tests; Chroma has no auth)*
34. What survives `kubectl delete pod` and why (PVCs)? What would not survive an `emptyDir`?
35. Why are Jobs not in the kustomization? Why `delete` before `apply`?
36. How did you choose resource requests and limits? Show a measurement. What does exit 137 mean?
37. Why is the candidate's cache off? What happens if live and candidate share Redis? *(thrash)*
38. What do the NetworkPolicies allow for the eval Job and why not Chroma?

**General**
39. What is hardest to explain to someone who has not read the paper? Which idea did you change?
40. What would you do with another week? *(consistency check; real A/B; alerting; bigger golden)*

---

## 8. Rehearsal protocol (T62)

1. **Rehearsal 1 (full, timed):** from a *cold-started* cluster state (restart minikube, restart Ollama), follow §4 exactly with a stopwatch; record per-part durations and every hiccup in `docs/a3-evidence/rehearsal-1.md`.
2. Fix the hiccups; **swap drivers**; **rehearsal 2** with the unseen-batch folder replaced by 3 *different* unfamiliar documents (include one scanned image-only PDF, one document with no obvious title/date, one that duplicates an existing document under another name) — outcomes must be graceful (accepted/quarantined with reasons), not crashes.
3. Examiner Q&A drill: each member answers §7 questions chosen at random about the **other** member's half.
4. Final dry run the evening before on the **demo laptop**; commit nothing after that unless it is a documented fix; leave the cluster running.

---

## 9. Demo acceptance matrix (all must be "yes" before you walk in)

| Check | Yes? |
|---|---|
| `kubectl apply -f k8s/eval-job.yaml` runs end to end and ends `Complete` or `Failed` according to the gate | |
| the demo profile completes within the measured time | |
| a trace can be opened, printed and its prompt hash verified (`REBUILD OK`) | |
| the unseen-batch rehearsal (3 documents) is handled gracefully; verification report readable; accepted docs searchable | |
| a second ingestion run embeds 0 chunks | |
| the gate-threshold ConfigMap edit flips the outcome with the same image | |
| the bad candidate is refused by `release.sh`; the good one is released; a bad release is undone; the trace after undo shows the previous collection + embedding version | |
| PVC survival after `kubectl delete pod` | |
| UI → Chroma and eval → Chroma are denied; eval → API allowed | |
| both members can answer the §7 questions about both halves | |
| cluster, Ollama and models are up and warm on the demo laptop | |
