# 01 — Requirements ledger (the PDF, sentence by sentence)

Source: `docs/A3.pdf`, "Assignment 03 — RAGOps", Fall 26, CS4032, group of 2, **185 marks**. This file turns every obligation in the PDF into an ID you can tick off. IDs are used in PR descriptions, in [`11-IMPLEMENTATION-PLAN.md`](11-IMPLEMENTATION-PLAN.md) and in the report's evidence column.

Status legend for your own tracking: `☐` not started · `◐` in progress · `☑` done **and evidenced**.

---

## 1. General rules (G)

| ID | The PDF says | What it means for us | Check |
|---|---|---|---|
| G-01 | "The pipeline must be deployed on Kubernetes during the demo. If it is run on Docker containers only … the demo will receive 0." | Local cluster (minikube + Calico, as in A2) running at demo time. No Compose, no `docker run` shortcuts, not even "just for the eval". | Demo rehearsal in [13](13-DEMO-RUNBOOK.md) |
| G-02 | "You will build on your RAHBAR pipeline from Assignment 02 … must run on Kubernetes (minikube is fine) for Part F." | Extend this repo. Keep ingestion, vector store, retriever, LLM generator. | [03](03-GAP-ANALYSIS.md) |
| G-03 | "Both members must be able to explain every part of the work at the demo." | Cross-review; the viva list in [13](13-DEMO-RUNBOOK.md) §7 is for both. | rehearsal |
| G-04 | "AI tools and libraries are allowed. Every number in your report must come from runs of your own pipeline, and the result files must be committed to your repository." | No quoted numbers from the paper or from an LLM. Every table cell points to a committed file. | report §10 |
| G-05 | "Late submissions will receive zero marks." | Plan to finish early; the deadline is **not in the PDF** — read Classroom. | [11](11-IMPLEMENTATION-PLAN.md) §1 |
| G-06 | "Plagiarism may result in zero marks in the whole assignments category." | Our own code, our own words; disclose AI in the 2–3 line statement. | report |
| G-07 | "There will be no credit if the given requirements are changed." | Implement the parts as written. Interpretations are listed in §9 and must be stated in the report. | §9 |
| G-08 | Repository: "Commits must come from both members." | Both authors appear in `git log`. | `git shortlog -sn` |
| G-09 | Report: "one PDF, at most 8 pages, with the screenshots … as an appendix (the appendix does not count). The first page lists the names and roll numbers of both members." | 8 pages of body max; page 1 carries names and roll numbers. | [12](12-REPORT-AND-EVIDENCE.md) |
| G-10 | "all result files, trace samples and reports produced by your scripts are committed under `eval/results/` and `traces/`. All Kubernetes manifests are committed under `k8s/`." | Exact directories. Result files must be pulled off the cluster volume and committed. | [10](10-KUBERNETES.md) §11 |
| G-11 | "README: the repository README gives the exact command to run each part (A to F)." | A README section per part, copy-paste commands, verified from a clean clone. | [12](12-REPORT-AND-EVIDENCE.md) §8 |
| G-12 | Demo: "both members attend and bring a laptop with the pipeline running on your local Kubernetes cluster … you will run your evaluation as a Kubernetes Job, open a trace, and ingest a small batch of documents you have not seen by running your ingestion Job." | Three live actions. The unseen batch implies **no hand-written catalog for those files**. | [13](13-DEMO-RUNBOOK.md) |
| G-13 | Screenshots: "show the command you ran and its output, in the terminal, with nothing cropped. Label it with the part and item (for example 'B3'). Screenshots must come from your own cluster and your own runs." | Full terminal window, command visible, label burned into the file name and caption. | [12](12-REPORT-AND-EVIDENCE.md) §6 |
| G-14 | "Fix random seeds" (Part B) and "the whole suite twice". | Seeds in config, recorded in every result file. | [06](06-OFFLINE-TESTING.md) §9 |
| G-15 | "A fresh cluster must reach a working pipeline by applying [the manifests], with any extra commands listed in a `k8s/README.md`." | Clean-cluster rehearsal; `k8s/README.md` lists every non-`apply` step. | [10](10-KUBERNETES.md) §12 |

---

## 2. Part A — Data management: verify and update (paper 4.2.1–4.2.4)

| ID | Requirement (PDF wording, condensed faithfully) | Planned deliverable | Evidence |
|---|---|---|---|
| A1-01 | A verification step that "runs after ingestion and before chunking". | `indexer/pipeline/verify.py`, called from `run.py` between extract and chunk | code + log order |
| A1-02 | "For every document it records pass or fail, with a reason, for each of four checks." | per-doc, per-check `{status, reason, evidence}` records | verification report |
| A1-03 | Check **quality**: "empty, garbled or failed extraction". | `check_quality` | unit tests + Batch B corrupt/garbled doc |
| A1-04 | Check **completeness**: "required metadata present: source, title, date or version, page count; text not truncated". | `check_completeness` | unit tests + Batch B missing-metadata and truncated docs |
| A1-05 | Check **recency**: "a newer version of the same document is detected". | `check_recency` against the ledger | Batch B newer version |
| A1-06 | Check **uniqueness**: "exact duplicates by hash, near-duplicates by embedding similarity". | `check_uniqueness` (SHA-256 + embedding cosine) | Batch B 2 exact + 1 near-duplicate |
| A1-07 | "Documents that fail are moved to a quarantine folder and are not indexed." | `lake.quarantine()`; failing doc never reaches chunk | `/data/quarantine/**` listing |
| A1-08 | "The output is a verification report file per run." | `/data/reports/verification/<run_id>.json` (+ `.md`), copied to `eval/results/` | **Screenshot A** |
| A2-01 | "Re-running ingestion on an unchanged corpus must embed zero chunks (show the counts)." | run summary counters; second run `chunks_embedded: 0` | **Screenshot A** (second run) |
| A2-02 | "A changed document replaces only its own chunks." | doc-scoped delete + add; other docs' chunk ids untouched | before/after id-set diff |
| A2-03 | "A deleted document leaves no orphan chunks in the vector store (prove it with a count by document id)." | `ops count --doc-id` = 0 after delete; global count = ledger sum | count output |
| A2-04 | "A superseded version is archived and excluded from retrieval through metadata." | `superseded=true`/`status=archived` flag; lake `archive/` | retrieval test |
| A2-05 | "…and you can restore it (rollback demo)." | `ops restore` flips flags back, swaps lake dirs | demo output |
| A-B-01 | "Batch B. Create a second batch of **at least 10 documents** with planted problems." | `corpus/batch-b/` (≥ 10 files) + `MANIFEST`-style README | file listing |
| A-B-02 | at least **2 exact duplicates** | B01, B02 | report |
| A-B-03 | **1 near-duplicate** | B03 | report |
| A-B-04 | **1 truncated or corrupt file** | B04 (corrupt PDF), B05 (truncated text) | report |
| A-B-05 | **1 with missing metadata** | B06 | report |
| A-B-06 | **1 newer version of an existing document** | B07 | report + rollback demo |
| A-B-07 | **1 containing an injected instruction** | B08 (also used by D4) | trace |
| A-B-08 | "Run both batches through A1 and A2." | Batch A (current corpus) and Batch B both ingested with verification and incremental logic | two verification reports |

---

## 3. Part B — Offline testing at three levels (paper 4.2.5, Table 1)

| ID | Requirement | Planned deliverable | Evidence |
|---|---|---|---|
| B-G-01 | "At least **25 questions** in `eval/golden.jsonl`" | `eval/golden.jsonl` | validator output |
| B-G-02 | ≥ **15 answerable**, each "with ground-truth document and page" | fields `gold: [{doc, page}]` | validator |
| B-G-03 | ≥ **5 unanswerable** (correct behaviour: abstain) | `answerable:false` | validator |
| B-G-04 | ≥ **5 hard** (paraphrased, or > 1 chunk, or from Batch B) | `category:"hard"` with `hard_kind` | validator |
| B-G-05 | "At least **8 questions are written by hand** by the group." | `origin:"human"` ≥ 8 | validator |
| B-G-06 | "Each question is labelled **human or synthetic**." | `origin` mandatory, enum | validator |
| B-G-07 | "At least **8 synthetic questions are reviewed by hand**." | `review:{by,date,verdict}` on ≥ 8 synthetic | validator |
| B-M-01 | Module: "Mean cosine similarity for **≥ 15 paraphrase pairs** against **≥ 15 unrelated pairs**, and the gap between them." | `eval/pairs.jsonl`, `module_level.py` | summary table |
| B-M-02 | Module: "Embedding time per chunk." | ms/chunk (mean, p95) on N sampled chunks | summary |
| B-M-03 | Module: "Determinism: embed the same text twice and report the largest difference." | max abs component diff over a sample | summary |
| B-C-01 | Component: "recall@3, recall@5, MRR and nDCG@5 on the golden set." | `component_level.py` using `/api/retrieve` | summary |
| B-C-02 | Component: "noise test: add ≥ 3 irrelevant documents, or add typos to the queries, and report how each metric changes." | typo perturbation (seeded) [+ optional 3 distractor docs] | summary delta table |
| B-E-01 | End-to-end: "Faithfulness (is the answer supported by the retrieved context)." | judge + deterministic proxy | summary |
| B-E-02 | End-to-end: "abstention correctness on the unanswerable questions." | rate over `answerable:false` | summary |
| B-E-03 | End-to-end: "citation validity." | A2 definition, extended | summary |
| B-E-04 | End-to-end: "latency p50 and p95." | wall-clock per question (cache bypassed) | summary |
| B-E-05 | "If you use an LLM as the judge … label ≥ 8 answers by hand and report how often the judge agrees with you." | `eval/judge_labels.jsonl` + agreement % (+ Cohen's κ) | summary |
| B-S-01 | "Fix random seeds and run the whole suite twice. Report the difference for each metric and explain any remaining variation." | `stochasticity.py`, two result files, diff table | report table |
| B-1C-01 | "One command runs the whole suite and writes a **timestamped result file** to `eval/results/` with a **summary table**." | `python -m ragops.suite.run_suite …` | **Screenshot B** |

---

## 4. Part C — Change experiment and release gate (paper 4.1(d), 4.2.5, 4.2.6)

| ID | Requirement | Planned deliverable | Evidence |
|---|---|---|---|
| C1-01 | "Choose **one** pipeline change: chunk size or overlap, embedding model, reranker, top-k, or prompt template." | decision D-09 in [04](04-ARCHITECTURE.md); [07](07-CHANGE-AND-RELEASE.md) §2 | report |
| C1-02 | "Run the Part B suite on the baseline and on the candidate and compare **all three levels**." | two result files + comparison table | report table |
| C2-01 | "Write thresholds in a **config file**" (recall@5 drop ≤ 2 points; faithfulness ≥ justified value; p95 ≤ justified value; abstention ≥ baseline). | `ragops/config/gate.yaml` (and the ConfigMap copy) | file |
| C2-02 | "A script applies the gate and exits with pass or fail." | `python -m ragops.gate.apply` (exit 0/1) | **Screenshot C** |
| C2-03 | "Show one candidate that **fails** … and one that **passes**." | candidates `bad` and `good` | **Screenshot C** (×2) |
| C2-04 | Justify the faithfulness and p95 thresholds. | derivation recorded in [07](07-CHANGE-AND-RELEASE.md) §5, committed before the candidate runs | report |
| C3-01 | "The candidate is released and, if needed, rolled back on Kubernetes. See F3." | = F3 | Screenshot F |

---

## 5. Part D — Observability and traceability (paper 3.2.3, 5.1, Table 2)

| ID | Requirement | Planned deliverable | Evidence |
|---|---|---|---|
| D1-01 | "Every query writes **one JSON line**" with the fields listed in D1-02. | `api/app/services/trace.py` | `traces/*.jsonl` |
| D1-02 | Fields: trace id; timestamp; user query; any rewritten query; embedding model **and version**; collection name or version; retrieved chunk ids with **document ids, document versions and scores**; filters applied; reranked order; prompt hash (or full prompt); model and parameters; response; citations; guardrail actions; latency per stage; cache hit or miss. | one-to-one field mapping in [14](14-INTERFACE-CONTRACTS.md) §6 | **Screenshot D** (full record) |
| D2-01 | "A command takes a trace id and prints the exact context and prompt that produced that answer." | `python -m ragops.trace.show <id>` | **Screenshot D** |
| D3-01 | Metrics "expose or report": top-1 retrieval similarity distribution; abstention rate; cache hit rate; p95 latency per stage; number of injection attempts flagged. | Prometheus series **and** summary script | summary output |
| D3-02 | "A script summarizes the trace log over a time window." | `python -m ragops.trace.summary --since …` | output |
| D4-01 | "The injection defence you built in A2 (or one simple retrieval rail) writes its action into the trace." | rail actions field | trace |
| D4-02 | "Test it with the injected document from Batch B." | question aimed at B08; trace shows the rail action | trace |
| D5-01 | "Pick one wrong or abstained answer from Part B. Using **only its trace**, find the cause (which chunk, document version or filter), and write **5 lines** in the report." | root-cause note | report §3 |

---

## 6. Part E — Drift and coverage (paper 4.2.7)

| ID | Requirement | Planned deliverable | Evidence |
|---|---|---|---|
| E1-01 | "Create **≥ 40 queries** as if from users: about **28** in the domain of your golden set and **≥ 12** from a topic your corpus or tests do not cover." | `eval/live_queries.jsonl` | file |
| E2-01 | "For each live query find the most similar golden question." | embedding nearest neighbour | report |
| E2-02 | "Report the share above a similarity threshold **you choose and justify** (the paper's example flags a gap when under **85 percent** reach a score)." | `coverage.py`, `eval/coverage.yaml` | **Screenshot E** |
| E2-03 | "List the uncovered queries and group them into topics." | uncovered list + topic groups | report |
| E3-01 | "Ingest Batch B, re-run the Part B suite, and report what changed and why." | before/after result files + analysis | report |
| E4-01 | "Add **≥ 6 new golden questions** from the uncovered topics, re-run, and show that coverage rises." | new rows in `golden.jsonl` | **Screenshot E** (before/after) |
| E4-02 | "A script returns a **non-zero exit code** when coverage falls below your threshold." | `coverage.py` exit 1 | output |

---

## 7. Part F — Run it on Kubernetes (paper 4.1(e)(f), 5.1 reliability)

| ID | Requirement | Planned deliverable | Evidence |
|---|---|---|---|
| F1-01 | "The API runs as a **Deployment**." | `k8s/base/api.yaml` (A2, extended) | `kubectl get` |
| F1-02 | "The vector store as a **StatefulSet** (or a Deployment with a PVC)." | `chroma` StatefulSet (A2) | `kubectl get` |
| F1-03 | "A **Service** exposes the API." | `Service/api` (A2) | `kubectl get` |
| F1-04 | "The **data lake, quarantine folder and archived document versions live on a PVC**, so they survive pod restarts." | PVC `ragops-data` | delete-pod survival test |
| F2-01 | "Ingestion with verification runs as a **Kubernetes Job**." | `k8s/ingest-job.yaml` | job logs |
| F2-02 | "A **CronJob** re-runs it on a schedule." | `k8s/ragops/ingest-cronjob.yaml` | `kubectl get cronjob` |
| F2-03 | "The **only writer** to the vector store is that Job." | design + code boundary + `concurrencyPolicy: Forbid` | tests + [10](10-KUBERNETES.md) §9 |
| F2-04 | "The Part B suite runs as a Job (`kubectl apply -f k8s/eval-job.yaml`), writes its result file to a volume, and exits with a failing status when the release gate (C2) fails." | `k8s/eval-job.yaml` (that exact path) | Job status |
| F2-05 | "The gate thresholds (C2) are a **ConfigMap**, and you show that changing a threshold changes the outcome **without rebuilding the image**." | `ConfigMap/ragops-gate`; two Job runs, same image digest, opposite outcomes | **Screenshot F** |
| F3-01 | "The candidate … runs as a **second Deployment with its own Service and its own collection name**, and the Part B suite Job is run against it." | `api-candidate` + `Service/api-candidate` | `kubectl get` |
| F3-02 | "If the gate passes, release it to the live Deployment with a **rolling update (`maxUnavailable: 0`)**, watched with `kubectl rollout status`." | release script | **Screenshot F** |
| F3-03 | "Show a candidate that is **stopped by the gate and never rolled out**." | the `bad` candidate | **Screenshot F** |
| F3-04 | "…and a **bad release that you reverse with `kubectl rollout undo`**." | a release that is wrong in production | **Screenshot F** |
| F3-05 | "After the undo, a **new trace must show the previous collection and embedding version**." | release identity in the Deployment pod template + trace fields | **Screenshot F** |
| F4-01 | "Trace records go to **standard output** as JSON lines and are readable with `kubectl logs`." | trace logger on stdout | logs |
| F4-02 | "They are also written to a **volume** for the report scripts." | `ragops-traces` PVC | file listing |
| F4-03 | "The metrics endpoint is reachable with `kubectl port-forward`." | `/metrics` | curl output |
| F5-01 | "Set resource requests and limits for the API, the vector store and the Jobs, **from measurements you take** (copy the numbers into the report)." | `kubectl top` method in [10](10-KUBERNETES.md) §10 | report table |
| F-ALL-01 | "Every manifest is committed under `k8s/`." | — | `git ls-files k8s` |

---

## 8. Part G — Report (≤ 8 pages)

| ID | Requirement | Where we handle it |
|---|---|---|
| G1 | A table mapping each stage of **Figure 3** (ingest, verify, update data lake, update retrieval sources, offline testing, live testing, check coverage) to **what your pipeline does, the file that does it, and what is missing**. | [12](12-REPORT-AND-EVIDENCE.md) §3, draft rows in [04](04-ARCHITECTURE.md) §2 |
| G2 | A table for the **five qualities** of the paper's Table 2 (adaptability, monitorability, observability, traceability, reliability): what you measure, your threshold, the evidence. | [12](12-REPORT-AND-EVIDENCE.md) §4, draft rows in [08](08-OBSERVABILITY-TRACING.md) §12 |
| G3 | Results tables and figures from Parts A–F, **and the release decision for Part C (release or reject, with reasons)**. | [12](12-REPORT-AND-EVIDENCE.md) §5 |
| G4(a) | Which verification check caught the most problems in Batch B, and which problem did you **not** catch? What would catch it? | [12](12-REPORT-AND-EVIDENCE.md) §7 |
| G4(b) | An example where a **module-level metric looked fine but a component or end-to-end one did not**, or why you did not see one. | same |
| G4(c) | Did you **archive or delete** old versions, and **what breaks if you delete**? | same |
| G4(d) | Which metric in your suite do you **trust least**, and why? | same |
| G4(e) | Which of the paper's ideas was **hardest to apply**, and what did you change from the paper? | same |
| G4(f) | Which **Kubernetes object carries which RAGOps responsibility** (e.g., which object makes sure only one component writes to the vector store)? | same |
| G5 | A **contribution table** (what each member did) and an **AI statement of 2 to 3 lines**. | same |

---

## 9. Ambiguities, and the reading we adopt (confirm with the instructor/TA if you can)

Write the chosen reading in the report so a grader sees a deliberate decision. None of these changes a requirement; each fixes a gap in the wording.

| # | Ambiguity | Reading adopted | Why |
|---|---|---|---|
| Q1 | "Documents that fail are moved to a quarantine folder and are not indexed" vs "A superseded version is archived and excluded from retrieval through metadata". Does a document that fails **recency** go to quarantine? | **No.** Failing *quality*, *completeness* or *uniqueness* → quarantine (not indexed). A *stale* version (recency) → **archive**: kept, flagged `superseded`, excluded from default retrieval, restorable. | A2-04/A2-05 say superseded versions are archived and restorable; quarantining them would make restore meaningless and break version-sensitive questions from A2. |
| Q2 | "At least 25 questions: ≥ 15 answerable, ≥ 5 unanswerable, ≥ 5 hard" — are the three counts disjoint (15+5+5 = 25)? | Build **≥ 30** with disjoint categories, `hard` questions also carrying ground truth. Then it satisfies both the disjoint and the overlapping reading. | Costs one extra afternoon; removes the risk. |
| Q3 | "add ≥ 3 irrelevant documents, **or** add typos" | **Typos** (seeded, deterministic, read-only, no writes to Chroma). Distractor documents only if time remains. | The PDF offers either; typos keep the single-writer rule trivially true. |
| Q4 | Which retrieval levels does "component level" measure — Chroma directly or the API? | Through the API's read-only retrieval endpoint, so it tests the same code path that serves users, including the superseded filter and exact-term assist. | Table 1 puts retrieval quality at the component level. |
| Q5 | "Embedding model and version" in the trace | Model name **and** the Ollama model digest (plus the release id). | Names alone do not identify what ran. |
| Q6 | "Prompt hash (or the full prompt)" | Store the **hash in the line** and the **full prompt in a content-addressed prompt store**, so the trace tool can print and re-verify it. | Satisfies "or", and makes D2 provable. |
| Q7 | Unseen batch at the demo | The ingestion Job must derive metadata from the files themselves (PDF info, headings, text) when no catalog row exists. | The instructor cannot know our catalog format. |
| Q8 | Which "latency" for p50/p95 | End-to-end wall-clock of `/api/ask` with the cache bypassed, plus per-stage from the trace. | A cached answer would hide model latency. |
| Q9 | "Live testing" in Figure 3 | We implement *shadow-style* testing: the candidate Deployment receives the same eval traffic in parallel with live; staged rollout by `maxSurge`/`maxUnavailable`. | Paper 4.2.6 lists shadow, A/B and staged roll-out as options, not obligations. |
| Q10 | Deadline | Not in the PDF. | Read Classroom. |

---

## 10. Requirement → screenshot map (appendix, "each shows the command and its output")

| Label | Must show | Requirement IDs |
|---|---|---|
| **A1** | the verification report for Batch B: pass/fail per check with reasons | A1-02…A1-08, A-B-* |
| **A2** | a second ingestion run on an unchanged corpus showing **0 chunks embedded** | A2-01 |
| **B1** | the evaluation summary with all three levels | B-M-*, B-C-*, B-E-* |
| **C1** | the release gate **failing** | C2-02, C2-03 |
| **C2** | the release gate **passing** | C2-02, C2-03 |
| **D1** | one full trace record | D1-* |
| **D2** | the trace tool rebuilding the prompt for a trace id | D2-01 |
| **E1** | coverage output **before** adding the new questions | E2-02 |
| **E2** | coverage output **after** | E4-01 |
| **F1** | `kubectl get all,pvc,configmap,cronjob,job` for the namespace | F1-*, F2-* |
| **F2** | logs of a completed **ingestion** Job | F2-01 |
| **F3** | logs of a completed **evaluation** Job | F2-04 |
| **F4** | the gate result **changing after a ConfigMap edit** | F2-05 |
| **F5** | `kubectl rollout status` | F3-02 |
| **F6** | `kubectl rollout undo` **and** a trace afterwards showing the previous collection and embedding version | F3-04, F3-05 |

The PDF lists the screenshot groups as A, B, C, D, E, F; the numeric suffixes above are our own, for the "A1/B3" style label it asks for.
