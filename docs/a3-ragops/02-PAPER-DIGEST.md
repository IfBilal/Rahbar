# 02 — The paper, end to end

**Xu, Weytjens, Zhang, Lu, Weber, Zhu — *RAGOps: Operating and Managing Retrieval-Augmented Generation Pipelines*.** arXiv:2506.03401 [cs.SE], 3 Jun 2025 (the assignment calls it a 2026 preprint; it is the same paper). 21 pages, 8 sections, 2 tables, 3 figures, 35 references.

This digest follows the paper in order. For each part it says **what the paper claims**, **where the assignment uses it**, and **what you must therefore build or say**. Quotations are short and exact; everything else is paraphrase. Read the paper itself for Sections 3.2, 4.2, 5.1 and 6.2 and Table 1, Table 2, Figure 3 — the PDF says these matter most.

> **Verification note.** The assignment's reference (authors, title, the section and table numbers it cites, "Figure 3 is the map") matches arXiv:2506.03401 exactly: §3.2 is *Process View*, §4.2 *Data management*, Table 1 the three-level testing platform, Table 2 the RAG system qualities, §5.1 *RAG system Qualities*, §6.2 *Lack of Standard Evaluation Metrics*, Figure 3 the intertwined lifecycles. A Google-Drive copy shared by the group could not be opened from the tooling (it requires sign-in), so the text here comes from the arXiv PDF. If your Drive copy differs, the PDF assignment still wins.

---

## 0. One-page summary (what to remember)

* A RAG system is a **compound system**: retrieval sources + retriever + generator (+ LLM). LLMOps tools mostly manage the *model and prompts*; they give little support for the **data that changes after deployment**.
* **RAGOps = two intertwined lifecycles** (Figure 3):
  1. the **query processing pipeline** — the ordinary seven-phase DevOps loop (plan, build, test, release, deploy, operate & monitor, analyse & feedback);
  2. a **data management lifecycle** — (1) ingest → (2) verify → (3) update data lake → (4) update retrieval sources, then (5) offline testing, (6) live testing, (7) check coverage.
* The distinctive ideas you must show: **verification before indexing**, **versioned/archived updates without orphans**, **three-level testing with fixed seeds**, **thresholds that gate a release**, **traceability of every query to data versions**, and **coverage checking** that keeps the test set honest against real usage.
* Five qualities to evidence (Table 2): **adaptability, monitorability, observability, traceability, reliability**.

---

## 1. Introduction and Figure 1 (scope)

**Paper.** 60% of enterprise LLM compound systems use some RAG. RAG fights hallucination, stale knowledge and the difficulty of removing knowledge from model weights. LLMOps manages models; RAGOps adds data lifecycle and operational aspects, "grounded in the paradigm of Observability". Figure 1 scopes RAGOps: the RAG system (query processing + data sources + genAI model) is inside; the LLM's own development pipeline is **outside** (excluded).

**Assignment use.** Justifies why Part A–E exist at all. Your report's framing sentence: *we operate the retrieval/data side; the LLM (llama3.2:3b via Ollama) is treated as a black box that we pin, parameterise and trace*.

**Build/say.** Nothing to build. In short answer (e) you may note you excluded LLM training/fine-tuning exactly as the paper does.

---

## 2. Related work (§2)

* **LLMOps**: model versioning, prompt management, monitoring, scaling; weak on retrieval observability.
* **Monitorability** = tracking behaviour against **predefined metrics and alerts** — the "known unknowns".
* **Observability** = being able to investigate **unknown unknowns** by analysing historical outputs ("needle-in-a-haystack" queries); needs logging of data, traceability of artefacts, anomaly detection, accountability.

**Assignment use.** This distinction explains why Part D has *both* metrics (D3: monitorability) *and* traces with a reconstruction tool (D1, D2, D5: observability/traceability). In the Table-2 report table keep them in separate rows and give each its own evidence.

---

## 3. Characterisation of RAG architecture (§3) — the 4+1 view

Kruchten's 4+1 model: **logic**, **process**, **development**, **physical** views plus **scenarios**. Figure 2 is the conceptual architecture: users/experts/agents → user interface / expert interface → **generator** (query enhancement, query generation, response validation) ↔ **retriever** (reasoning & planning, embedding, retrieval, reranking) ↔ **retrieval sources** (chunking, embedding, indexing, vector DB, other stores) ↔ **data lake** ← **raw data**; plus the **GenAI model**, **embedding model**, and API/direct access sources. Guardrail icons I / D / R / O sit between components.

### 3.1 Logic view
Retriever fetches, generator answers. Safeguards: appropriateness, accuracy verification, regulatory compliance, user alignment, content validation. **Human-in-the-loop / human-in-the-retrieval**: experts as active retrieval sources.

### 3.2 Process view — *the part that matters most*
Two processes to keep distinct:

* **Query Processing Pipeline** (real time): optional **query enhancement** by the generator → retriever's **reasoning & planning** (choose source and method) → **embed** the (enhanced) query → **retrieve** from the vector DB → **rerank** (prioritise, remove redundancy) → generator builds the prompt from query + retrieved info → **LLM** → **response validation** → user. Agentic variants may iterate; *Retrieval Interleaved Generation* weaves retrieval into generation.
* **Data management** (ongoing): chunk text, embed, store; keep the **data lake** and **retrieval sources** current (details in §4.2).

#### 3.2.3 Guardrails (explicitly cited by Part D)
Four rail types: **input rails (I)** reject/modify user input (mask PII, rephrase); **dialog rails (D)** shape prompting/progression; **retrieval rails (R)** *exclude or modify retrieved segments, e.g., to conceal sensitive or poisoned information*; **output rails (O)** reject/modify the model's output. "Balance the number and placement of these guardrails to avoid redundancy".

**Assignment use (D4).** "The injection defence you built in A2 (or one simple **retrieval rail**)" is a type-**R** rail. Our A2 defence is the `neutralise()` step in `api/app/services/prompt.py` plus the system-prompt rule; A3 must make its *action* visible in the trace. See [`08`](08-OBSERVABILITY-TRACING.md) §7.

### 3.3 Development view
Retrieval sources can be vector DBs, knowledge graphs, document stores (TF-IDF/keyword), APIs, humans. **Assignment use:** none required; mention in (e) that we use only a vector DB (Chroma) plus an exact-term assist.

### 3.4 Physical view
Cloud vs on-prem per component; multiple LLMs (e.g., a separate "LLM guard"). **Assignment use:** our physical view is the Kubernetes deployment (Part F) with Ollama on the host.

### 3.5 Scenarios
Two usage types: **querying specific details** and **holistic understanding**. **Assignment use:** the golden set's *hard* questions (multi-chunk) test the second type; ordinary ones test the first.

---

## 4. RAGOps (§4)

### 4.1 Query processing pipeline = DevOps loop (the upper part of Figure 3)
Seven phases; the assignment explicitly cites **(d) Release** (Part C) and **(e) Deployment** and **(f) Operate & Monitor** (Part F):

| Phase | Paper's RAG-specific content | Our realisation |
|---|---|---|
| a. Plan & develop | domain, data sources, retrieval & generation strategy, models, vector DB, prompts | A2 `docs/` plan + [04](04-ARCHITECTURE.md) |
| b. Build | preprocessing, chunking, embeddings, indexing, containerise | Dockerfiles, `indexer/pipeline` |
| c. Test | functionality, performance, security **plus** retrieval relevance, response accuracy, coherence; **load testing**; benchmark datasets; automated frameworks | Part B suite; A2 unit tests |
| **d. Release** | validate retriever–generator–retrieval-sources compatibility, **versioning strategy**, approval, often a **staging environment** | gate (C2) + candidate Deployment (F3) |
| **e. Deploy** | infrastructure stability, scaling; **data updates treated as a separate component because of their frequency** | rolling update + ingestion Job/CronJob |
| **f. Operate & monitor** | infra health, logging, alerting; retrieval efficiency, response fidelity, **data drift** | traces, metrics, coverage |
| g. Analyse & feedback | diagnose retrieval errors, detect drift, refine matching; analyse logs and interactions | D5 root cause, E2 coverage |

### 4.2 Data management (the lower half of Figure 3)

> "Data entering it needs to be checked… Shifts in the data distribution and/or system usage patterns might also impact the system's end-to-end performance, requiring evaluations… These evaluations call for a test data set, whose coverage needs checking as well."

#### 4.2.1 Ingestion → Part A (input side)
Sources: file systems, DBs, APIs, web, feeds, humans. Methods: webhooks, **change data capture**, **polling**, file-system watchers, streams, crawlers; push or pull. **"In our context, ingestion also includes deletions and updates of data."** Includes format conversion: text from PDFs, descriptions of images, transcription of audio.
* **Ours:** pull by polling a drop-zone (the inbox) on a CronJob schedule, plus on-demand Jobs. PDF/HTML/Markdown/TXT extraction (A2) incl. OCR. Deletions and updates are first-class ([05](05-DATA-MANAGEMENT.md) §7).

#### 4.2.2 Verification → A1 (the four checks the assignment requires)
Five checks in the paper; the assignment requires four:

| Paper check | Paper wording | In assignment? | Ours |
|---|---|---|---|
| **Quality** | well-structured, not corrupted or malformed; external validation where relevant | **Yes** (A1) | `check_quality` |
| **Completeness** | all expected fields incl. metadata (timestamps, authorship, source); not truncated | **Yes** | `check_completeness` |
| **Recency** | older versions **not retained but archived and replaced**; evaluated from metadata timestamps, embedded timestamps, or semantic analysis | **Yes** | `check_recency` |
| **Consistency** | detect **contradictory information** via semantic similarity; weight sources by trust or ask a human | **No** (omitted from the PDF) | not built; discuss in short answer (e) as a gap |
| **Uniqueness** | eliminate duplicates e.g. hash dedup; semantic redundancy via embeddings + clustering; TF-IDF/LDA for similar topics | **Yes** | `check_uniqueness` (hash + embedding) |

Also: *external sources the retriever calls in real time cannot be verified this way (latency) — retrieval guardrails are the answer there.* **Future-work remark (Section 8):** the verification phase "lacks a mechanism to detect the **malicious insertion** of detrimental data". That is exactly the injected-instruction document of Batch B: it passes the four checks, so a *retrieval rail* (D4) is the only line of defence. This is the honest answer to short-answer (a).

#### 4.2.3 Updating the data lake → A2 (storage side)
A **separate data lake before chunking/embedding** centralises ingested, verified data: single source of truth, shared by several RAG systems, easier governance/auditing. Applying updates: remove duplicates, **replace outdated records**, correct errors. **"Instead of outright deletion, archiving old versions allows for rollback … Each modification must be versioned."** Data must remain logically sound — **free of orphans**; references to outdated data adjusted. Access-control metadata should be stored with each entry.
* **Ours:** the data lake is a directory tree on a PVC with a JSON **ledger** ([04](04-ARCHITECTURE.md) §4). Archive instead of delete; version every change; orphan proof by `count(where doc_id)`. Access-control metadata: *not required*; mention in (e) as skipped.

#### 4.2.4 Updating retrieval sources → A2
"Incremental chunking and embedding are performed on newly added or modified data. Indexing is also updated accordingly, ensuring that deletions and outdated information are properly removed from the retrieval process."
* **Ours:** the incremental reconcile loop ([05](05-DATA-MANAGEMENT.md) §6): unchanged = 0 embeds; changed = replace only that document's chunks; deleted = no orphans; superseded = metadata flag.

#### 4.2.5 Offline testing → Part B (and Table 1)
Triggered by **pipeline changes** (switch LLM, change query generator, new chunking, new embedding) **or data distribution shifts** (new domains/sources/languages; also gradual latent drift). Three granularities — **module** (e.g., chunking/embedding), **component** (e.g., retrieval), **system** (end-to-end). "After unit testing a module, its effect on the component, and end-to-end system are tested as well." Each level needs its own test data and metrics; metric choice should align with end-user priorities.

**Table 1 (the example is embedding):**

| Level | What we test | Test data | Traditional DevOps metrics | RAG-specific metrics |
|---|---|---|---|---|
| **Module** — embedding quality | similarity, drift, efficiency | benchmark datasets, synthetic tests | embedding generation time (ms), memory per embedding | cosine similarity, drift, t-SNE/UMAP clustering |
| **Component** — retrieval quality | rank relevance, resilience to noise | public RAG retrieval benchmarks (BEIR, MS MARCO), production queries | retrieval latency (ms), index update speed | **MRR, recall@K, precision@K, nDCG** |
| **End-to-end** — response quality | faithfulness, hallucination, correctness | human-labelled, production logs | full-pipeline latency, response generation time | **faithfulness score, hallucination rate**, BLEU, ROUGE, BERTScore |

*Observation the assignment wants you to make (short answer (b)):* "Module-level embedding affects both the 'retrieval' and 'retrieval sources' components, so these should be tested together at the second, component level before testing the end-to-end system." A model can have a great paraphrase-vs-unrelated gap yet retrieve badly on *your* corpus.

Other statements to honour:
* **Domain-specific test sets must be monitored against actual usage** (→ coverage, Part E); when introducing new domains the test sets should be **updated or expanded beforehand**; **new test sets** check the new data while **existing ones** guard against regressions ("forward adaptability and backward compatibility").
* **Standard benchmarks** (BEIR, MS MARCO) and **synthetic data** complement domain sets (edge cases, query variations). → Our synthetic questions + hand review.
* **Stochasticity:** ANN search, ranking tie-breaks, LLM sampling make runs non-reproducible; **"fixing random seeds will ensure more consistent and comparable test results."** → run the suite twice with fixed seeds and report the difference (B-S-01).
* Offline testing may reveal that you must swap the LLM, update prompts or embeddings → "further testing before being released".

#### 4.2.6 Live testing → Part C release + Part F3
Strategies: **shadow testing** (new version in parallel without affecting users), **A/B testing** (subset of users), **staged roll-out** (incremental). Live testing is **continuous** because data and usage drift; it too has module/component/end-to-end levels; metrics include latency, throughput, retrieval quality, generation quality, usage analytics; **"predefined thresholds should be established for key metrics"** — breaching one triggers investigation and a loop back to offline testing.
* **Ours:** the candidate Deployment is a **shadow-style** target for the suite Job (live users untouched); the release is a **staged rolling update** (`maxSurge 1`, `maxUnavailable 0`); thresholds live in a config file/ConfigMap and gate the release.

#### 4.2.7 Coverage checking → Part E
"Coverage checking ensures that the test data used during offline testing remains representative of the live usage patterns." Four kinds:

| Kind | Technique in the paper | Assignment |
|---|---|---|
| **Query coverage** | TF-IDF similarity or **embedding cosine** between live and test queries; low scores or new query clusters (t-SNE/UMAP) = gap | **E2** (required) |
| Retrieval coverage | do live queries retrieve documents outside the test set's scope? recall@K on test and live queries | optional extra |
| Generation coverage | topic/intent/style alignment of generated answers (embeddings, LDA) | not required |
| Vocabulary/domain coverage | TF-IDF term-frequency comparison to flag new terms | optional extra (useful to *group uncovered queries into topics*) |

The rule of thumb the PDF quotes: "if **less than 85%** of live queries achieve a certain similarity score to test queries, the system should prompt a test set expansion." The assignment makes you **choose and justify your own similarity threshold**; do not just write 0.85 — it is the *share* (85%) that the paper names; the *similarity* cut-off is yours ([09](09-DRIFT-COVERAGE.md) §4).

---

## 5. Impact of RAGOps on quality attributes (§5)

### 5.1 The five qualities (Table 2 — assignment Part G table 2)

| Quality | Operational design considerations (paper's Table 2) | Paper's explanation (paraphrased) |
|---|---|---|
| **Adaptability** | data structure construction; granularity configuration | The pipeline must absorb change: new LLM, query generator, chunking, embedding. Design choices such as chunk granularity decide how cheaply you can adapt. **Automated updates to retrieval sources** when raw data changes or performance degrades. |
| **Monitorability** | performance-degradation detection (**accuracy, latency, relevance**); **data-source change detection**; clear, consistent, meaningful performance metrics | Components that detect degradation and source changes; metrics defined to assess performance and utility. |
| **Observability** | retrieval: **injection-attack detection, relevance**; generation: **context adherence, toxicity, usefulness** | An observability layer **spanning all components**, logging all queries, responses and each component's inputs/outputs. Detect injection attacks against retrieval sources; generator monitors toxicity and context adherence. |
| **Traceability** | **versioning**; **retrieval routing**; **grounded source** | Data sources change, so version them; document each component's inputs/outputs — link queries to retrieved documents, **embedding IDs, filters, reranking**; **reconstruct the prompt** (query + retrieved context). Record securely; supports debugging by data version. |
| **Reliability** | **resource usage**; **bandwidth** | Unpredictable bandwidth and operating costs (e.g., large uploads); load balancing, autoscaling, prioritisation for consistent performance. |

**Assignment use (G2).** For each row write *what you measure*, *your threshold*, *the evidence file* — prefilled drafts are in [`08`](08-OBSERVABILITY-TRACING.md) §12 and [`12`](12-REPORT-AND-EVIDENCE.md) §4.

### 5.2 Human-in-the-retrieval
Experts' tacit knowledge as an active/passive retrieval source; store merged or separate (confidential feedback); trace human inputs. **Not required.** Mention only to say you did not implement it.

---

## 6. Overarching challenges (§6)

* **6.1 Responsible and safe AI** — GDPR, EU AI Act, voluntary AI safety standard ("keep and maintain records to allow third parties to assess compliance"), fairness/accountability/transparency; **black-box recorder** to collect critical runtime data. → Our trace log is a black-box recorder; mention in the observability row. *Privacy note:* A2 deliberately never logged raw questions; **A3's D1 requires the user query in the trace**. Document this reversal and its mitigation ([08](08-OBSERVABILITY-TRACING.md) §10).
* **6.2 Lack of standard evaluation metrics** *(the PDF names this section)* — no standard metrics across retrieval resources, retrieval, generation; early design decisions (chunking, embedding) shape later stages and are hard to evaluate. → This is why **short answer (d)** ("which metric do you trust least?") and **(e)** exist. Have a genuine, measured answer.
* **6.3 Continuous improvement through observability** — decoupling data quality, model quality and software quality is hard; monitoring changes in sources and their impact. → D5 root-cause-from-trace.
* 6.4 Multimodality, 6.5 Human-in-the-retrieval — not required.

---

## 7. Use cases (§7) — how to use them

Two industrial examples (a taxation assistant; the Magda Copilot for a scientific data catalogue). Useful borrowed ideas:

* **Granularity decision:** the taxation assistant chose *one Q&A per private ruling* as the chunk, trading cost and efficiency. → supports your chunk-size discussion (candidate in Part C).
* **Reranker with LLM evaluator; privacy guardrail** in the retriever → example of an R/I rail.
* **Ground truth built from certified replies, then synthesised by an LLM** → exactly the human + reviewed-synthetic golden set required by Part B.
* **Quality attributes by user story** (adaptability, observability, contestability) → inspiration for the Table-2 evidence column.
* Magda: **log tools selected and inputs/outputs of each step** → trace design.

---

## 8. Summary and future work (§8)

Open directions: **malicious insertion detection** in verification ("specific semantic checks complementing classical cybersecurity measures"); agentic RAG; **tooling** for monitoring retrieval behaviour, tracing generated outputs to sources, and evaluating the impact of data changes. **Assignment use:** this is a license for your short answers (a) and (e): the paper itself says verification cannot catch malicious content, and that tooling is immature — you built the tooling.

---

## 9. Figure 3 — the map (stage-by-stage, with our file)

```
 Query processing pipeline (DevOps):  a.Plan → b.Build → c.Test → d.Release → e.Deploy → f.Operate&Monitor → g.Analyse&Feedback ─┐
        ▲                                         ▲                                   │                    │
        │                                 5.Offline testing ──────────────► 6.Live testing                  │
        │                                         ▲        ╲                                                 │
        │                                  4.Update retr. ─► 7.Check coverage                                │
        │                                  sources    ▲                                                      │
 Data management:   1.Ingest ──► 2.Verify ──► 3.Update data lake                                           (loop)
     (self-loop: continuous)
```

| Figure-3 stage | Paper § | Assignment part | Our component (planned file) |
|---|---|---|---|
| 1. Ingest | 4.2.1 | A | `indexer/pipeline/catalog.py`, `extract.py`, inbox PVC dir |
| 2. Verify | 4.2.2 | A1 | `indexer/pipeline/verify.py` |
| 3. Update data lake | 4.2.3 | A2 | `indexer/pipeline/lake.py`, `ledger.py` |
| 4. Update retrieval sources | 4.2.4 | A2 | `indexer/pipeline/incremental.py`, `store.py` |
| 5. Offline testing | 4.2.5 | B, C | `ragops/suite/**`, `ragops/gate/**` |
| 6. Live testing | 4.2.6 | C3, F3, D | candidate Deployment, release script, traces/metrics |
| 7. Check coverage | 4.2.7 | E | `ragops/coverage/coverage.py` |
| a–g. DevOps loop | 4.1 | C, F | CI (A2), Kubernetes manifests |

---

## 10. What the paper has that the assignment does **not** require (and how to treat it)

| Paper idea | Required? | Recommended handling |
|---|---|---|
| Consistency check (contradictions) | No | Not built. State it in (e): the 2023 vs 2026 rules *do* contradict each other; our design handles that by versioning, not by detecting conflict. |
| Access-control metadata in the lake | No | Not built; say so. |
| Retrieval/generation/vocabulary coverage | No | Optionally compute vocabulary coverage (TF-IDF) to *group uncovered queries into topics* (E2). |
| t-SNE/UMAP visualisation of drift | No | Optional figure for the report (one embedding scatter of golden vs live queries) if space allows. |
| BEIR/MS MARCO benchmark | No | Skip; our domain set is the test. Mention in (d). |
| Shadow / A/B / staged | One option | Shadow-style candidate + rolling update ([04](04-ARCHITECTURE.md) D-12). |
| Query enhancement / reasoning-planning / reranker | Optional | `rewritten_query` and `reranked_order` fields exist in the trace (null / the A2 exact-term ordering). A reranker is one of the allowed *change* candidates for Part C. |
| Human-in-the-retrieval | No | Not built. |
