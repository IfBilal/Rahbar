# 12 — Part G: report, screenshots, README and the submission checklist

Covers **G1–G5, G-09, G-10, G-11, G-13** and the final definition of done. The PDF asks for **two things**: the GitHub repository and **one report PDF (≤ 8 pages, screenshots as an appendix that does not count)**. Everything in the report is evidence-backed: *"Every number in your report must come from runs of your own pipeline, and the result files must be committed."*

> **Rules for the writer (human or AI):** never paste a number you did not produce; every table cell cites a committed file (put the short file name in a footnote or a "Source" column); use `MEASURE` until the run exists; say plainly what is missing or weak (a grader rewards honest limits — the paper itself does); both members must be able to defend every sentence at the demo.

---

## 1. Page budget (8 pages, body only)

| Page(s) | Content | Notes |
|---|---|---|
| 1 | **Title, names and roll numbers of both members** (as the PDF demands), repo URL, one-paragraph summary of what was built, one architecture figure (small) | take names/roll numbers from the root `README.md`; do not retype from memory |
| 1–2 | **Table 1 — Figure-3 stage map** (7 rows) | §3 |
| 2 | **Table 2 — five qualities** (5 rows) | §4 |
| 3 | **Part A results**: Batch B outcome table, unchanged-rerun counts, incremental/delete/restore proofs | §5.1 |
| 3–4 | **Part B results**: three-level summary (baseline), stochasticity table, judge agreement | §5.2 |
| 4–5 | **Part C**: baseline vs candidates, both gate decisions, **release decision (release/reject with reasons)** | §5.3 |
| 5–6 | **Part D**: trace excerpt (not the whole record), metrics summary, D4 rail test, **D5 five-line root cause** | §5.4 |
| 6 | **Part E**: coverage before/after, uncovered topics, drift (E3) findings | §5.5 |
| 6–7 | **Part F**: object-responsibility table, resource table, rollout/undo timeline | §5.6 |
| 7–8 | **Short answers (a)–(f)** | §7 |
| 8 | **Contribution table and AI statement (2–3 lines)** | §9 |
| Appendix (not counted) | screenshots A1…F6, each labelled | §6 |

Tight budget ⇒ tables over prose, **at most three figures** (architecture; metric comparison bar chart; coverage before/after), captions that state the source file. If you must cut, cut prose, never evidence.

---

## 2. Page 1 content checklist
Names and roll numbers (both) · repository URL · commit SHA of the submitted state · date · one sentence on what RAGOps layer was added to RAHBAR · one sentence stating the **corpus and batches** (Batch A = nine public FAST-NUCES documents, Batch B = thirteen group-authored planted-problem fixtures) · note that all numbers come from `eval/results/` files.

---

## 3. Table 1 — "Map each stage of Figure 3" (G1)

Columns required by the PDF: **stage → what your pipeline does → the file that does it → what is missing**. Draft from [04](04-ARCHITECTURE.md) §2 (copy and keep the "missing" column **honest**):

| Figure-3 stage | What our pipeline does | File | What is missing |
|---|---|---|---|
| 1 Ingest | inbox drop-zone on a PVC, polled by a CronJob or run on demand; adds/changes/removals detected against the ledger; PDF/HTML/MD/TXT extraction incl. OCR | `indexer/pipeline/catalog.py`, `extract.py`, `run.py` | no webhook/CDC/watchers; text formats only |
| 2 Verify | quality · completeness · recency · uniqueness per document with reasons; failures quarantined; report per run | `indexer/pipeline/verify.py`, `report.py` | consistency check; malicious-content detection (paper §8 admits the gap) |
| 3 Update data lake | verified versions on PVC, stale versions archived (restorable), deletions tombstoned, versioned ledger | `lake.py`, `ledger.py`, `ops.py` | access-control metadata; multi-system sharing |
| 4 Update retrieval sources | incremental chunk/embedding; 0 embeds on no change; doc-scoped replace/delete; superseded flag; registry revision | `incremental.py`, `store.py` | embedding/chunking change = full rebuild of a new collection |
| 5 Offline testing | golden set + three-level suite, seeds, run twice, one command; gate over config thresholds | `ragops/suite/**`, `ragops/gate/**` | public benchmarks; larger golden; stronger judge |
| 6 Live testing | shadow-style candidate (same suite, no user impact); staged rolling release; traces/metrics/summary | `k8s/candidate.yaml`, `scripts/ragops/release.sh`, `ragops/trace/**` | A/B traffic split; alerting |
| 7 Check coverage | embedding similarity live vs golden; share vs threshold; uncovered topics; exit code | `ragops/coverage/coverage.py` | retrieval/generation coverage (unless the optional bonus was done) |

Update the right-hand cells with what you *actually* finished. If an item moved from "missing" to done, say so.

---

## 4. Table 2 — "Five qualities" (G2)

Columns: **quality → what you measure → your threshold → the evidence**. Draft rows are in [08](08-OBSERVABILITY-TRACING.md) §12. Rules: (1) only list what you really measure; (2) the *threshold* is a number from your config (`gate.yaml`, `coverage.yaml`, `ragops-config`) or a stated design limit; (3) the *evidence* is a file in `eval/results/`, `traces/`, or `docs/a3-evidence/`.

| Quality | What we measure | Threshold | Evidence |
|---|---|---|---|
| Adaptability | | | |
| Monitorability | | | |
| Observability | | | |
| Traceability | | | |
| Reliability | | | |

---

## 5. Results tables and figures (G3)

### 5.1 Part A
**Table A1 — Batch B outcomes** (one row per planted file; *Observed* comes from the verification report):

| File | Planted problem | Expected check | Observed outcome + code | Caught? |
|---|---|---|---|---|
| B01 `Student_Handbook_Copy.pdf` | exact duplicate | uniqueness | `U-EXACT-DUP` → quarantine | ✔/✘ |
| … (13 rows, B01–B13) | | | | |

**Table A2 — counters:** Batch A first sync, unchanged re-run (0 embeds), Batch B sync, one changed doc, one deleted doc (orphans 0), supersede + restore — columns: `docs_new/unchanged/updated/quarantined`, `chunks_embedded/written/deleted`, `revision_bumped`, seconds. **Failures by check** (from the report summary) feeds short answer (a).

### 5.2 Part B
**Table B1 — three-level summary (baseline, label, corpus digest, git SHA):** every metric of 06 §8 with `N`. **Table B2 — stochasticity** (metric, run 1, run 2, |Δ|, explanation). **Judge agreement** (n, agreement %, κ). **Noise test** (clean vs noisy, Δ). One bar chart is enough if you chart anything here.

### 5.3 Part C
**Table C1 — comparison** (07 §4 layout) with baseline, bad, good and Δ. **Gate decisions** (rules, limits, values, verdict) for both candidates — a compact two-column table. **Thresholds with derivation** (faithfulness minimum, p95 maximum: the arithmetic in one sentence each).
**Release decision** (the PDF asks: *release or reject, with reasons*): one paragraph per candidate using the template in [07](07-CHANGE-AND-RELEASE.md) §6, e.g.:

> *Candidate `cand-minilm` — **REJECT**. Gate FAIL: recall@5 fell 0.xxx below baseline (limit 0.02) and p95 latency …; not rolled out (release script refused; revision unchanged).*
> *Candidate `cand-mxbai` — **RELEASE** only if the gate **really** passed: …*

Do not write this text before the runs; the example above is a shape, not a result.

### 5.4 Part D
One **trace excerpt** (the key fields: query, collection/embedding versions, top-3 candidates with doc versions, rail action, prompt hash, latencies) — the full record is Screenshot D1. **Metrics/summary table** from `trace.summary` over a stated window (top-1 similarity p10/p50/p90, abstention rate, cache hit rate, p95 per stage, injection flags). **D4**: two sentences + the rail action. **D5 root cause (5 lines)**, as in [08](08-OBSERVABILITY-TRACING.md) §11.

### 5.5 Part E
**Coverage before/after table** (share, in/out-of-domain, τ and `min_share` with their justification in one line each), **uncovered topics table**, **drift findings** (what changed and why, with the common-subset vs new-subset numbers).

### 5.6 Part F
**Object-responsibility table** (short answer (f)), **resource table** (measured peak/steady, request, limit, file), **release timeline** (S1 stopped; S2 released; S3 undone; trace after undo showing the previous collection and embedding version), PVC-survival statement with the evidence file, network-matrix result in one line.

---

## 6. Screenshot appendix — rules and exact commands

**Rules (PDF):** each screenshot **shows the command you ran and its output, in the terminal, with nothing cropped**, **labelled with part and item**, **from your own cluster and your own runs**.

Practical rules: terminal ≥ 120 columns; prompt shows the kube context/namespace (`kubectl config current-context`); the command line is visible at the top of each capture; if the output is longer than one screen, capture **two** screenshots (`B1a`, `B1b`) rather than trimming; add the label as a caption in the report **and** in the file name (`A1_verification_report_batchB.png`); keep the timestamp visible (`date -u` before the command). Take screenshots **at the time of the run** and store the raw text next to them in `docs/a3-evidence/<label>/` (so you can prove, and re-take, if needed).

| Label | What | Command(s) to run (adapt names) |
|---|---|---|
| **A1** | verification report for Batch B (pass/fail per check, reasons) | `kubectl exec -n rahbar ragops-loader -- cat /data/reports/verification/<run>.md` or `python -m pipeline.run report --last --md` inside a Job pod |
| **A2** | second ingestion on an unchanged corpus: **0 chunks embedded** | `kubectl delete job ingest --ignore-not-found; kubectl apply -f k8s/ingest-job.yaml; kubectl wait --for=condition=complete job/ingest; kubectl logs job/ingest | tail -3` (the summary line shows `chunks_embedded":0`) |
| **B1** | evaluation summary with all three levels | `kubectl logs job/eval -n rahbar | tail -40` (or the `.md` summary in `/results`) |
| **C1** | release gate **failing** | `kubectl logs job/eval` (MODE=gate on the bad candidate) → `GATE_FAIL`, rule table; and `kubectl get job eval` shows `Failed` |
| **C2** | release gate **passing** | same for the good candidate → `GATE_PASS`; `kubectl get job eval` shows `Complete` |
| **D1** | one full trace record | `kubectl logs deploy/api -n rahbar --since=5m | grep '"type":"trace"' | tail -1 | jq .` |
| **D2** | trace tool rebuilding the prompt | `python -m ragops.trace.show <trace_id>` (or via `kubectl exec` into a ragops pod) — shows `sha256 verified: OK` and `REBUILD OK` |
| **E1** | coverage **before** | `python -m ragops.coverage.coverage …` (or Job logs) — verdict `COVERAGE GAP`, exit code shown (`echo $?` → 1) |
| **E2** | coverage **after** | same — `COVERAGE OK` (`echo $?` → 0) |
| **F1** | namespace overview | `kubectl get all,pvc,configmap,cronjob,job -n rahbar` |
| **F2** | logs of a completed **ingestion** Job | `kubectl logs job/ingest -n rahbar` (Job shown `Complete`) |
| **F3** | logs of a completed **evaluation** Job | `kubectl logs job/eval -n rahbar` |
| **F4** | gate result **changing after a ConfigMap edit** | two captures: Job logs `GATE_FAIL` → `kubectl edit cm ragops-gate` (or `patch`) → Job logs `GATE_PASS`; include `kubectl get job eval -o jsonpath='{.spec.template.spec.containers[0].image}'` both times |
| **F5** | `kubectl rollout status` | `kubectl rollout status deployment/api -n rahbar` during the release |
| **F6** | `kubectl rollout undo` **and** a trace afterwards showing previous collection + embedding version | `kubectl rollout undo deployment/api -n rahbar; kubectl rollout status …; curl … /api/ask …; python -m ragops.trace.show <id> | head -30` (collection `rahbar`, embedding `nomic-embed-text@…`, release `R1`) |

Extras worth appending (not required): network matrix, `kubectl top`, PVC-survival, port-forward `/metrics`, the B08 rail trace.

---

## 7. Short answers (G4) — how to derive each (replace with *your* measured answers)

Each answer should be **4–6 lines**, cite a number or file, and be consistent with the rest of the report.

**(a) Which verification check caught the most problems in Batch B, and which problem did you *not* catch? What would catch it?**
*How:* read `summary.failures_by_check` from the Batch-B report. The check with the highest count is the answer (expected shape: uniqueness fires for B01–B03; completeness for B05–B06; quality for B04; recency (B13 quarantined; the 2022 version re-evaluated `R-SUPERSEDED-BY`) — your *measured* counts decide). *The uncaught problem:* the **injected-instruction document (B08)** passes all four checks (it is well-formed, complete, current and unique) — the paper (§8) names this gap. *Anything else you found* (e.g., a near-duplicate under the threshold, a document whose content is plausible but wrong) is more convincing than the textbook example. *What would catch it:* an advisory injection scan at ingest (pattern/classifier), source trust weighting or human review for new sources, the paper's *consistency* check for contradictory content; **until then the retrieval rail (D4) is the defence** — show it neutralised B08 at query time.

**(b) A module-level metric looked fine but component/end-to-end did not — or why not?**
*How:* compare embedding-gap results with recall/faithfulness across baseline and candidates. A strong paraphrase-vs-unrelated gap with **lower recall on exact terms** (clause numbers, course codes) or **higher false-abstention** after a floor mismatch is the typical pattern; the 07 §2.3 score-scale issue is a concrete candidate. Give the two numbers side by side. If you saw none, explain *why not* in terms of your data (e.g., the corpus is small, the golden set has few exact-term questions, the exact-term assist hides embedding weaknesses).

**(c) Did you archive or delete old versions, and what breaks if you delete?**
*Answer shape:* **archived** (superseded flag + lake archive; restore demonstrated). *What breaks on delete:* (1) **rollback** is impossible without re-ingesting the old source (and the source may no longer exist online — A2 noted a dead URL risk for the 2023 rules); (2) **version-sensitive questions** ("what did the 2023 rules say?") can no longer be answered; (3) **traceability** — old traces cite chunk ids/versions that no longer resolve, so the trace tool's rebuild check fails; (4) **cache and citations** referencing the old version dangle; (5) audit/governance history is lost (paper §4.2.3). Mention the cost of archiving (storage, retrieval filter correctness — a bug in the filter would surface old rules).

**(d) Which metric do you trust least, and why?**
*Pick one with evidence.* Strong candidates: **LLM-judge faithfulness** (3B model judging 3B output; report agreement κ and n); **coverage share** (it measures similarity of *wording*, and the new golden questions can be written to raise it — say what you did to avoid that); **latency** on a shared laptop CPU (varies run to run; report the stochasticity Δ); **recall@k on a ~24-question set** (a single question moves it by ~4 points — compare to the 0.02 gate!). Connect it to the paper's §6.2 (no standard metrics).

**(e) Which of the paper's ideas was hardest to apply, and what did you change?**
*Candidates:* the **consistency check** (not required; the 2023 vs 2026 rules *do* contradict each other — we handle that by versioning rather than detection); **live testing as A/B** (replaced by shadow-style candidate + rolling release); **three-level testing with a 3B model on CPU** (cost forced `/api/retrieve` and a typo noise test instead of distractor documents); **coverage with a calibrated threshold** (the paper gives a share, not a similarity). State *what you changed from the paper* explicitly (e.g., archive via metadata instead of a separate store; document-level incremental; no access-control metadata).

**(f) Which Kubernetes object carries which RAGOps responsibility?** Use the table in [10](10-KUBERNETES.md) §9 (shortened to 8–10 lines) and the honest single-writer sentence: *"the only writer is the ingestion Job; this is enforced by the Job/CronJob (`concurrencyPolicy: Forbid`, `parallelism 1`) plus a lock on the data PVC, NetworkPolicy limiting Chroma to three clients, and boundary tests — Chroma itself has no authentication, so Kubernetes alone does not make the API read-only."*

---

## 8. README (G-11) — what the root `README.md` must add

A new section **"Assignment 03 — RAGOps"** with, per part, the **exact command(s)** (copy-paste, tested from a clean clone), the expected output file, and where the screenshot label applies. Skeleton:

```markdown
## Assignment 03 — RAGOps
Prerequisites: … (see k8s/README.md for the fresh-cluster order)
| Part | Command | Output |
| A | kubectl apply -f k8s/ingest-job.yaml ; make drop-batch DIR=corpus/batch-b ; make ingest | /data/reports/verification/<run>.md ; ingest summary line |
| B | make eval TARGET=live LABEL=baseline        # applies k8s/eval-job.yaml | eval/results/<ts>_baseline.json (+ .md summary) |
| C | make eval TARGET=candidate LABEL=cand-… ; scripts/ragops/release.sh cand-… | decision.json ; rollout |
| D | python -m ragops.trace.show <id> ; python -m ragops.trace.summary --since 24h | trace + summary |
| E | python -m ragops.coverage.coverage … | eval/results/<ts>_coverage.json ; exit code |
| F | see k8s/README.md | |
```
Also: repository layout (`k8s/`, `eval/`, `traces/`, `ragops/`, `corpus/batch-b/`, `docs/a3-ragops/`), the two member names, a link to the report PDF in the repo (optional), CI badge (A2). Keep the A2 README content; add, do not remove.

---

## 9. Contribution table and AI statement (G5)

**Contribution table** — one row per person per area; must match `git shortlog -sn` and PR history. Do **not** flatter: if one member did more infra and the other more data, say so; both must have explained each other's half in rehearsal.

| Area | Member A | Member B |
|---|---|---|
| Part A (verify, update, Batch B) | | |
| Part B (golden, suite) | | |
| Part C (change, gate, release) | | |
| Part D (traces, rails, tools) | | |
| Part E (coverage, drift) | | |
| Part F (Kubernetes) | | |
| Report, README, demo | | |

**AI statement (2–3 lines)** — honest and specific; the assignment allows AI use and A2 stated honest disclosure carries no penalty. Template: *"We used an AI coding assistant to draft [planning documents, boilerplate, test scaffolding, manifest sketches]. All numbers in this report come from our own runs; each of us reviewed, ran and can explain the code we submit. The AI did not produce any metric, trace or screenshot."* Mirror it in `docs/AI-USAGE.md` (update with A3 entries).

---

## 10. Final submission checklist (single list; tick only with evidence)

**Repository**
- [ ] URL submitted; branch `main` contains everything; commits from **both** members (`git shortlog -sn`)
- [ ] `k8s/` — all manifests, `k8s/eval-job.yaml`, `k8s/ingest-job.yaml`, `k8s/candidate.yaml`, `k8s/README.md`
- [ ] `eval/golden.jsonl` (≥ 30 incl. E4 additions), `eval/pairs.jsonl`, `eval/live_queries.jsonl`, `eval/judge_labels.jsonl`, `eval/results/*` (baseline, two stochasticity runs, bad, good, E3 before/after, coverage before/after, decisions)
- [ ] `traces/` — curated sample (≤ a few hundred lines; include the B08 rail trace, the undo trace, the D5 trace)
- [ ] `corpus/batch-b/` (13 files + README of planted problems)
- [ ] `ragops/` code, `indexer/pipeline/` changes, `api/app/services/{trace,rails}.py`, tests green (`make test lint`)
- [ ] root README: command per part A–F (tested from a clean clone)
- [ ] no secret in the tree or history; `make check` / A2 checker still clean; no `:latest`
- [ ] `docs/a3-evidence/` raw outputs behind every screenshot and number

**Cluster (demo-ready)**
- [ ] minikube + Calico running; pipeline answers a question through the Ingress
- [ ] `kubectl get all,pvc,configmap,cronjob,job -n rahbar` healthy; `ragops-data/traces/results` PVCs bound
- [ ] baseline present; demo-profile baseline present; `ragops-gate` ConfigMap at its committed values
- [ ] Ollama running with all models pulled and warm; laptop will not sleep

**Report**
- [ ] ≤ 8 pages body; page 1 has both names and roll numbers
- [ ] Table 1 (Figure 3 stages) and Table 2 (five qualities) complete and honest
- [ ] Parts A–F results; **release decision** for each candidate; D5 five lines
- [ ] Short answers (a)–(f); contribution table; AI statement
- [ ] Appendix screenshots **A1, A2, B1, C1, C2, D1, D2, E1, E2, F1–F6**, labelled, uncropped, with commands visible
- [ ] every number traceable to a committed file; no `MEASURE` left

**Demo**
- [ ] both members present, laptop with the cluster; rehearsal ×2 incl. the unseen batch; each member can explain the other's half

**Submit:** repo URL + report PDF to Google Classroom **before the deadline** (late = 0).
