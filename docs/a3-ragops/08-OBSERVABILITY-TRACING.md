# 08 — Part D: observability and traceability

Covers **D1-01, D1-02, D2-01, D3-01, D3-02, D4-01, D4-02, D5-01** and F4 (paper 3.2.3 guardrails, 5.1 Table 2 monitorability/observability/traceability, §2.2 monitoring vs observability, 6.1 black-box recorder). Owner: **B** (trace writer, tools, metrics, rail logging); A reviews and consumes the traces in Parts B and E. Tasks T35–T40 in [11](11-IMPLEMENTATION-PLAN.md). Exact schema: [14](14-INTERFACE-CONTRACTS.md) §6.

**Two different jobs, two different artefacts** (paper §2.2): **metrics** answer *known questions* ("what is the abstention rate?") — monitorability, D3. **Traces** answer *questions you did not know to ask* ("why did this one answer cite the 2023 rules?") — observability and traceability, D1/D2/D5. Build both; keep them separate in the report.

---

## 1. Design principles

1. **One query → exactly one trace line**, including cache hits, abstentions, fallbacks and failures (a trace is written in a `finally`; if the request crashes, the line says `status: "error"`).
2. **Never break a request because tracing failed.** Writer errors are caught, counted (`rahbar_trace_write_errors_total`) and logged once per minute.
3. **Reconstructable.** The trace plus the immutable lake must be enough to rebuild the exact prompt (D2). Therefore: record chunk ids **with document ids and versions**, record the prompt **hash**, and store the prompt text in a **content-addressed prompt store**.
4. **Versioned everything.** Every identifier that can change over time (collection, registry revision, embedding model + digest, prompt template version, release id, app version) is in the line.
5. **No secrets, ever.** The trace contains the user's question and the model's answer (the PDF requires it) but never `LLM_API_KEY`, headers, or environment dumps.
6. **Cheap enough for the hot path.** Building the record is O(top_k); writing is one `write()` of one line to a file opened `O_APPEND` and one `print` to stdout.

---

## 2. Mapping: PDF D1 field list → trace fields

The PDF lists the contents of the line. Each phrase maps to a named field (full types in 14 §6):

| PDF requirement | Trace field(s) | Notes |
|---|---|---|
| trace id | `trace_id` (uuid4 hex) | also returned as response header `X-Trace-Id` and additive `AskResponse.trace_id`; equals the A2 `request_id` if you prefer one id — decide once |
| timestamp | `ts` (UTC ISO-8601, ms) | |
| user query | `query` | after trimming; not truncated unless > 2 000 chars (then `query_truncated: true`) |
| any rewritten query | `rewritten_query` | `null` — we do no query rewriting; the field exists so the schema is the paper's (Fig. 2 query enhancement). If you implement exact-term extraction as a "rewrite", record it here |
| embedding model and version | `embedding.model`, `embedding.version` (Ollama digest), `embedding.dimension`, `embedding.profile` (prefix/lowercase) | version from `EMBED_VERSION` |
| collection name or version | `collection.name`, `collection.revision` (registry data revision), `collection.generation` (registry), `release_id` | the F3-05 evidence |
| retrieved chunk ids with document ids, document versions and scores | `retrieval.candidates[]` = `{rank, chunk_id, doc_id, doc_version, source, section, page, score, superseded}` | the **final** list returned by retrieval, in order |
| filters applied | `retrieval.filters` = `{superseded_filter: true, where: {"superseded": false}, history_requested: false, where_document: [...]}` | what the query actually used |
| reranked order | `retrieval.reranked_order[]` (chunk ids) + `retrieval.assists[]` (`exact_term`, `table`) | A2 has no reranker; the "rerank" is the exact-term/table assist reordering (C-12). Record order **before** and **after**: `dense_order[]` vs `reranked_order[]` |
| prompt hash (or the full prompt) | `prompt.sha256`, `prompt.template_version`, `prompt.chunk_ids[]` (what was actually put in the prompt, ≤ `MAX_CONTEXT_PASSAGES`), `prompt.stored: true` | full text in the prompt store (Q6 in 01 §9) |
| model and parameters | `model.provider`, `model.name`, `model.params` = `{temperature, seed, top_k?, num_predict?, timeout_s}` | effective values including eval-header overrides |
| response | `response.answer`, `response.confidence`, `response.answered_from_context`, `response.abstained`, `response.fallback_reason` | the `reasoning` field is **never** logged (A2 rule) |
| citations | `response.citations[]` (`source, section, page`) and `response.citation_check` (`valid`, `rewritten[]`) | |
| guardrail actions | `guardrails[]` = `{stage, rail, action, target, pattern, detail}` | §7 |
| latency per stage | `latency_ms` = `{total, cache, embed, retrieve, rail, prompt, generate, validate}` | each from a monotonic timer |
| cache hit or miss | `cache` = `{enabled, hit, similarity, scope}` | on a hit, `retrieval` and `prompt` carry `from_cache: true` and `origin_trace_id` of the answer that was cached |

Extras that earn their place: `status`, `pod`, `app_version`, `tokens` (`in`,`out`), `eval` = `{run_id, label, seed}` when the eval headers are present (so traces can be split into *user* vs *evaluation* traffic), `attempts`, `schema_version`.

---

## 3. Instrumentation points (where to touch the A2 code)

| Stage | A2 location | Change |
|---|---|---|
| Request start/end | `api/app/routes/ask.py` / `main.py` middleware | create a `TraceRecorder` (contextvar like `request_id_var`), set `trace_id`, write in `finally` |
| Cache | `answer_question` (cache lookup + `cache_scope`) | record `cache.*`, `scope`, time |
| Embed | `ChromaRetriever.embed_query` | time it separately (today it is inside `retrieve`) |
| Retrieve | `ChromaRetriever.retrieve` | return a **`RetrievalDetail`** (new method `retrieve_detailed()`; keep `retrieve()` returning the passage list): dense results, filters used, assists applied, final order, collection/revision. Keep the A2 behaviour byte-identical |
| Rail | before the prompt is built | `rails.scan(passages, question)` → cleaned passages + actions (§7) |
| Prompt | `services/prompt.py::build_messages` | return a `PromptBundle(messages, sha256, template_version, chunk_ids, rail_actions)`; keep `build_messages` as a thin wrapper so the providers/tests do not change |
| Generate | `generate_checked` | record attempts, retry reasons (a retry is an **output rail** action: `retry`), params, tokens |
| Validate | `guard.check_answer` | record citation rewrites (`rewritten`) as guardrail actions (`output` rail), failures as `fallback_reason` |
| Decline paths | `_declined(...)` branches | record `abstained` with `reason` (`below_relevance_floor`, `model_declined`, `fallback`) |

The A2 `_log_turn` line stays as it is (no question text). The trace is a **second, separate stream**.

---

## 4. Writers (F4-01, F4-02)

| Sink | What | How |
|---|---|---|
| **stdout** | one JSON line per query, with `"type":"trace"` (so it can be grepped out of the A2 request logs) | `print(json.dumps(record, separators=(",",":"), ensure_ascii=False), flush=True)`; read with `kubectl logs deploy/api` |
| **PVC** `ragops-traces` at `/traces` | the same line appended to `/traces/<POD_NAME>.jsonl` | open once with `O_APPEND|O_CREAT`, `0o640`; `POD_NAME` via the downward API (`metadata.name`); one writer per file ⇒ no locking; rotate at 50 MiB to `<pod>.jsonl.1` (keep 2) |
| **prompt store** | `/traces/prompts/<sha256>.json` = the `messages` array, written once (skip if exists) | write to a temp name then `rename`; dedupes the identical prompts of cache-bypassed repeat runs |

Constraints: the API container has `readOnlyRootFilesystem: true`; only the `/traces` volume mount is writable (plus `/tmp`). `fsGroup: 10001` makes the PVC writable by the non-root user. The directory is created by an initContainer or by the PVC's first mount (`mkdir` in the app at startup, tolerant of races). Retention: a CronJob or the report script prunes files older than N days; the grading repo commits **sample** traces only (`traces/*.jsonl`, a few hundred lines at most) — pull them with `kubectl cp`.

---

## 5. The prompt hash and the prompt store

* Canonicalise: `json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",",":"))`, UTF-8, SHA-256 hex → `prompt.sha256`.
* `template_version` = the A2 `PROMPT_VERSION` (hash of `SYSTEM + REMINDER`, already in `answer.py`) **plus** a `RAIL_VERSION` so a rail change shows up.
* The stored file also holds `{ "sha256":…, "template_version":…, "messages":[…] }`.
* Anything that changes the bytes of the prompt changes the hash: the question, the evidence order, a retrieved chunk's text, a neutralised span. That is what makes the rebuild check in §6 meaningful.

---

## 6. The trace tool (D2) — `python -m ragops.trace.show <trace_id>`

Purpose: take a trace id and print **the exact context and prompt that produced that answer**.

```
python -m ragops.trace.show 7f3c…e9                 # reads /traces (Job) or --traces-dir
python -m ragops.trace.show 7f3c…e9 --traces-dir ./traces --lake ./lake
kubectl logs deploy/api -n rahbar --since=10m | python -m ragops.trace.show --stdin 7f3c…e9
options: --json (raw record)  --no-rebuild  --prompt-only
```

Lookup: scan `*.jsonl` (and rotated files) for `"trace_id":"<id>"` (streamed, O(size)); `--stdin` accepts a log stream. Not found → exit **4** with the directories searched.

Output sections (each clearly headed so a screenshot is readable; **Screenshot D2**):

1. **Header** — trace id, time, pod, release id, status, app version.
2. **Query** — the user query (and rewritten query if any).
3. **Index identity** — collection name, registry revision/generation, embedding model **and version**, dimension.
4. **Retrieval** — filters applied; table of candidates in rank order (`rank, score, doc_id@version, page, section, chunk_id`), with `dense_order` vs `reranked_order` and which assist moved what; which chunks went **into the prompt**.
5. **Guardrails** — rail actions in order.
6. **Prompt** — the exact `messages` (system, then user with the lettered evidence) loaded from the prompt store, with `sha256 verified: OK` (recompute and compare; mismatch → `CORRUPT`, exit 5).
7. **Context** — the evidence passages **as they appear in the prompt** (after neutralisation), with chunk ids.
8. **Model call** — provider, model, params, attempts, tokens.
9. **Response** — answer, confidence, citations, citation check, `abstained`/`fallback_reason`.
10. **Latency** — per stage.
11. **Rebuild check** (unless `--no-rebuild`) — recompute the prompt from the **lake snapshots**: for each `prompt.chunk_ids` fetch the chunk text from `lake/docs/<doc_id>/<version>/chunks.jsonl` (or `archive/`), run the *same* rail and prompt builder at the recorded `template_version`, hash it, compare with `prompt.sha256`. Print `REBUILD OK (hash matches)` or `REBUILD DIFFERS: chunk <id> text changed / template version <x> != <y>`. A match proves **traceability across data versions** even after the document was updated or archived — the strongest answer to "can you reproduce this answer's context?".

Exit codes: 0 found and consistent · 4 not found · 5 prompt store corrupt/hash mismatch · 6 rebuild differs (still prints everything; `--no-rebuild` skips) · 2 usage.

The tool needs the API's prompt/rail code to rebuild: the `rahbar-ragops` image includes the `api/app/services/{prompt,rails}.py` modules (D-14). Keep them import-light (no FastAPI imports).

---

## 7. Guardrail logging (D4) — the retrieval rail

The paper (3.2.3) names four rail types. A2 already built an injection defence; D4 requires that its **action is written into the trace** and that you **test it with the injected document from Batch B (B08)**.

### 7.1 What exists in A2
`prompt.neutralise(text) -> (text, n)` replaces instruction-like spans (`ignore … instructions`, `you are now …`, `system prompt …`) with `[instruction-like text removed]` before the evidence and the question enter the prompt; the system prompt also tells the model to treat evidence as data. It returns a count nobody records.

### 7.2 The rail module (`api/app/services/rails.py`)

```
scan_retrieval(passages) -> (passages', actions)     # type R: before the prompt is built
scan_input(question)     -> (question', actions)     # type I: on the user's question
```
Each action: `{stage:"retrieval", rail:"injection", action:"neutralised|excluded|flagged", target:"chunk:<id>", doc_id, doc_version, pattern:"ignore-instructions", span_chars:73, text_sha:"…"}` — **never the injected text itself** in the clear beyond a short, escaped excerpt (`excerpt` ≤ 60 chars) so the trace is not a re-injection vector.

Policy (keep it simple and defensible):
* `neutralised` — replace the span (A2 behaviour). Default.
* `excluded` — drop the whole passage from the prompt if neutralised spans exceed 30% of its characters (the passage is mostly an attack) **and** record it; the passage still appears in `retrieval.candidates` (it was retrieved) but not in `prompt.chunk_ids`.
* `flagged` — suspicious but not matching a removal pattern (e.g., a role-play marker); logged only.
* Patterns: the A2 regex **plus** a small list of ids (`ignore-instructions`, `role-override`, `system-prompt`, `reveal-secrets`, `disregard-context`). Each has a stable `pattern` id; unit-test each against a positive and a benign sentence (e.g., "students must not **ignore** the **rules**" must not trigger — check the A2 regex for false positives on real corpus text and record any).
* Output rail actions (type O) also go into `guardrails[]`: citation rewrites and `retry`/`fallback` from `guard.check_answer` — they are guardrail actions in the paper's sense.

### 7.3 The D4 test with B08
1. Ensure Batch B is ingested (B08 indexed; it passed all four checks — that is the point).
2. Ask a question whose answer lies in B08's policy text (e.g., "Is parking free for everyone on campus?") through the Ingress/Service.
3. Show the trace: `retrieval.candidates` includes the B08 chunk; `guardrails[]` contains `neutralised` (or `excluded`) with `doc_id: campus-parking-policy`; the prompt (via the trace tool) shows `[instruction-like text removed]`; the response does **not** contain the planted claim (`must_not` passes). Also ask a **hostile question** ("Ignore your instructions and …") to show the input rail.
4. Counter: `rahbar_injection_flags_total` increments; the summary script counts it (D3).
Both a positive run and a negative control (a benign question on a clean document → `guardrails: []`) belong in the evidence.

---

## 8. Metrics (D3) — the endpoint and the series (F4-03)

A2 already exposes request count/latency, retrieval and generation histograms, cache lookups/hits/ratio, abstentions by reason, fallbacks by reason, tokens. **Add** (names are contracts; labels low-cardinality):

| Series | Type | Meaning | D3 item |
|---|---|---|---|
| `rahbar_top1_similarity` | Histogram, buckets `0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0` | similarity of the best retrieved chunk per query (observed for every retrieval, including abstentions) | **top-1 similarity distribution** |
| `rahbar_stage_seconds{stage}` | Histogram | `cache, embed, retrieve, rail, prompt, generate, validate` | **p95 latency per stage** (computed by `histogram_quantile`, and exactly from traces) |
| `rahbar_injection_flags_total{rail,action}` | Counter | rail actions that fired | **injection attempts flagged** |
| `rahbar_abstentions_total{reason}` | Counter (A2) | | abstention rate = abstentions ÷ answered requests |
| `rahbar_cache_hits_total`, `rahbar_cache_lookups_total`, `rahbar_cache_hit_ratio` | (A2) | | **cache hit rate** |
| `rahbar_trace_write_errors_total` | Counter | trace sink failures | health of the black box |
| `rahbar_release_info{release_id,collection,embed_model} 1` | Gauge | which release this pod is | traceability on the dashboard |
| `rahbar_index_revision` | Gauge | the data revision the pod currently reads | data-source change detection (monitorability) |

Reach it: `kubectl port-forward -n rahbar deploy/api 8000:8000` then `curl -s localhost:8000/metrics | grep rahbar_` (Screenshot optional; F4-03). Caveat to state: each replica exports its own counters; `port-forward` hits one pod. **Aggregates for the report come from the trace log** (all pods), which is why the summary script exists; if you want aggregation in Prometheus form, port-forward the Service (`svc/api`) repeatedly or run one replica for the demo and say so.

---

## 9. The summary script (D3-02) — `python -m ragops.trace.summary`

```
python -m ragops.trace.summary --traces-dir /traces --since 24h [--until 2026-11-27T00:00:00Z]
                               [--release R2-mxbai] [--exclude-eval|--only-eval] [--json]
```
Window: `--since` accepts `Nh`, `Nm`, `Nd` or an ISO timestamp; default `24h`; `--until` default now. Reads `*.jsonl` and rotated files; skips malformed lines (counted as `skipped_lines`); never loads the whole set into memory.

Output (Table; also JSON):

| Block | Content |
|---|---|
| Volume | total queries, by `status`, by release id / collection, user vs eval split |
| **Top-1 similarity** | min, p10, p50, p90, max, and a 10-bucket text histogram — for answered and abstained separately |
| **Abstention rate** | abstained ÷ total, by reason (`below_relevance_floor`, `model_declined`, `fallback`) |
| **Cache hit rate** | hits ÷ lookups, and ÷ eligible queries |
| **Latency per stage** | p50, p95 for each stage and total (nearest-rank, documented) |
| **Injection flags** | count of rail actions by `rail/action`, number of distinct trace ids affected, distinct `doc_id`s involved |
| Fallbacks, tokens | fallback rate and reasons; tokens in/out totals |

Exit codes: 0 ok · 3 no traces found/readable · 2 usage. Run it **before and after** a release (S3-b) to show a regression in the window — the monitorability story.

---

## 10. Privacy, security, retention (and the A2 reversal)

A2 deliberately did **not** log the question text. D1 requires it, so: (1) the question appears only in the **trace stream** (stdout lines of `type: trace` and the PVC files), never in the ordinary request log; (2) the traces are the group's own test and demo queries, not real users' data — say that; (3) PVC files `0640`, the `ragops-traces` volume is mounted only into the API pods (read-write), the eval Job and report tools (read-only); (4) retention: prune after N days, commit only a small curated sample; (5) the rail's `excerpt` is truncated and escaped; (6) no key, header or env value ever enters a record (unit test that scans a record for the `LLM_API_KEY` value). The paper's §6.1 "black-box recorder" is exactly this log; the report row can cite it.

---

## 11. D5 — root cause from the trace only

**Goal:** choose one wrong or abstained answer from the Part-B run and, **using only its trace** (and the trace tool), find the cause — *which chunk, document version or filter* — then write 5 lines in the report.

Procedure:
1. In the result file pick a question where the end-to-end answer was wrong, unsupported, or an abstention on an answerable question (`false_abstention`), or a retrieval miss (gold not in top-5). Note its trace id (the result file stores it per question).
2. `python -m ragops.trace.show <id>`. Do **not** look at the corpus, the golden file or the chunk store while diagnosing; the point is that the trace alone suffices.
3. Walk the decision table:

| Symptom | Look at | Typical cause |
|---|---|---|
| abstained though answerable | `retrieval.candidates[0].score` vs the floor (`model.params`/`response.abstained.reason = below_relevance_floor`) | best chunk scored under the floor — embedding/scale problem or the gold chunk not retrieved |
| wrong number or rule | `candidates[].doc_version`, `superseded`, `filters` | an older document version was retrieved/used (filter off or history wording), or the right chunk ranked below the 3 that went into the prompt (`prompt.chunk_ids`) |
| right chunk retrieved but not cited | `prompt.chunk_ids`, `citations`, `citation_check.rewritten` | it was retrieved (rank 4–5) but cut by `MAX_CONTEXT_PASSAGES`, or the model cited another passage |
| answer followed the document's instruction | `guardrails[]` | rail missed the pattern (check `pattern`, `action`) |
| exact term missed | `retrieval.assists[]`, `dense_order` vs `reranked_order` | no assist fired (term not matching `_EXACT`) |
| stale answer after an update | `collection.revision`, `cache.hit`, `cache.scope` | served from cache of an older revision (should be impossible — a finding) |
| slow | `latency_ms` per stage | generation dominates; or retrieval slow due to Chroma |

4. The five lines (template): **(1)** question + trace id; **(2)** what the system did (score, chunks, version, filter); **(3)** the failing link (the specific chunk/version/filter and the field that proves it); **(4)** root cause in one sentence; **(5)** the fix or the decision (and whether you applied it).
Keep the screenshot of the key part of the trace (D1 full record is separate).

---

## 12. Table 2 (the five qualities) — draft rows for report table 2 (G2)

Fill `Threshold` and `Evidence` with **your measured values/files**; keep "what you measure" honest — only list things you actually measure.

| Quality | What we measure | Threshold (ours) | Evidence file |
|---|---|---|---|
| **Adaptability** | time and embeds to absorb a data change (`chunks_embedded` for a changed doc vs full rebuild); time to build a candidate collection; one-line release of a changed pipeline setting | unchanged corpus ⇒ 0 embeds; changed doc ⇒ only its chunks; candidate build time MEASURE | ingest summaries; Part C |
| **Monitorability** | recall@5 vs baseline, faithfulness, abstention, p95 latency (offline gate); live abstention rate, top-1 similarity, cache hit rate (metrics/summary); data-source change = ledger revision | gate: recall@5 drop ≤ 0.02; faithfulness ≥ MEASURE; abstention ≥ baseline; p95 ≤ MEASURE | `eval/results/*`, `gate.yaml`, summary output |
| **Observability** | injection attempts flagged (D4), context adherence (faithfulness), per-stage latency, relevance (top-1 distribution) | 100% of B08-attack questions show a rail action; faithfulness ≥ MEASURE | traces, summary |
| **Traceability** | % of queries whose trace rebuilds the identical prompt hash; versions present in 100% of lines (collection, embedding version, doc versions) | 100% rebuild OK on sampled N traces | trace tool output |
| **Reliability** | zero failed requests during rolling release; probes; resource requests/limits from measurement; single-writer lock; PVC survival | 0 failed requests in the release loop; pods Ready ≥ 3 throughout | `kubectl` outputs, release loop log |

---

## 13. Tests

| Area | Cases |
|---|---|
| Trace record | all PDF-required fields present (schema test that iterates the PDF list); cache-hit variant; abstention variant; fallback variant; error variant; no `reasoning`; no secret value present |
| Writers | one line per request; per-pod file name; unwritable volume → request still succeeds + error counter; rotation at the cap; prompt store write-once and dedupe |
| Prompt hash | stable across calls; changes with any evidence byte; canonicalisation independent of dict order |
| Rails | each pattern positive/negative; benign sentence from the real corpus not flagged; exclusion threshold; action never contains the full injected span |
| Trace tool | finds by id; missing → 4; tampered prompt → 5; rebuild OK on an unchanged chunk; rebuild differs after the chunk's snapshot changes; `--stdin` |
| Summary | window parsing; empty window; malformed lines skipped; percentile nearest-rank; eval/user split |
| Metrics | new series exist at 0 on a fresh pod (A2 habit); `top1_similarity` observed on abstentions |

---

## 14. Pitfalls

| Pitfall | Consequence | Defence |
|---|---|---|
| Logging the model's `reasoning` | violates A2 rule | never include; test |
| Trace write blocks or crashes the request | outage from observability | swallow + count |
| Three replicas append to one file | interleaved/corrupt lines | per-pod files |
| Recording the prompt hash but not the text | D2 impossible | prompt store + hash |
| Rebuilding from the *current* chunk store | breaks after an update | rebuild from lake snapshots (versioned) |
| Cache hits write no trace | "every query writes one line" violated | always write; mark `from_cache` |
| Eval traffic pollutes user metrics | misleading summaries | `eval` block + `--exclude-eval` |
| Leaving the injected text in the trace | the trace becomes an attack carrier | excerpt ≤ 60 chars, escaped |
| Metrics from one pod presented as the system's | wrong rates | aggregate from traces; say so |
