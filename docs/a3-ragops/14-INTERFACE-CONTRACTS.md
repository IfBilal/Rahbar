# 14 — Interface contracts (the single source for formats)

If any other file in this folder disagrees with this one, **this one wins** — then fix the other file. Change a contract only with both members' review and a line in the PR. JSON examples are **shapes**, not results: every value is illustrative.

Conventions: UTC ISO-8601 timestamps with `Z`; SHA-256 as lowercase hex; ids are strings; floats rounded to 4 decimals in result files; `null` means "not applicable / not measured" and the gate treats an absent required metric as a **failure**; every JSON file carries `"schema": <int>`.

---

## 1. Ingestion CLI (`python -m pipeline.run`)

```
python -m pipeline.run sync [--inbox DIR] [--data-dir DIR] [--dry-run]
python -m pipeline.run verify-only [--inbox DIR]
python -m pipeline.run restore <doc_id>@<version>
python -m pipeline.run delete <doc_id> [--version V]
python -m pipeline.run count [--doc-id ID] [--collection NAME] [--json]
python -m pipeline.run status [--json]
python -m pipeline.run build-index --collection NAME --embed-model M [--chunk-size N --chunk-overlap N] [--register]
python -m pipeline.run unregister --collection NAME
python -m pipeline.run report [--run RUN_ID|--last] [--kind verification|ingest] [--md]
python -m pipeline.run --dummy                      # A2 compatibility
```
Defaults from the environment (§13). Every command ends by printing **one JSON summary line** (§4) as the last line of stdout. Logs before it are JSON lines too (`logger: rahbar.indexer`, `request_id` = run id, as in A2).

Exit codes: `0` done · `1` done, **one or more documents quarantined** (the Job wrapper maps it to 0) · `2` usage · `3` fatal (lock held, ledger unreadable, Chroma/Ollama unreachable, embedding failure, dimension/pin mismatch) · `4` nothing to do for `restore/delete` target (document or version unknown).

---

## 2. Ledger (`/data/ledger/ledger.json`, schema 1)

```json
{
 "schema": 1,
 "updated_at": "2026-11-25T10:02:11Z",
 "digest": "sha256 of canonical [(doc_id, version, content_sha, status)] for non-quarantined, non-deleted versions, sorted",
 "batches": ["A", "B"],
 "documents": {
  "academic-rules": {
   "series_title": "Undergraduate Academic Rules",
   "versions": {
    "2026-06": {
     "status": "current",                       // current | archived | deleted
     "batch": "A",
     "inbox_path": "academic-rules-handbook-jun-2026.pdf",
     "file_name": "academic-rules-handbook-jun-2026.pdf",
     "content_sha": "…", "text_sha": "…",
     "ledger_revision": 1,                       // per-doc counter, +1 per accepted new content
     "pages": 74,
     "resolved": {
       "title": {"value": "Academic Rules Handbook", "route": "catalog"},
       "doc_version": {"value": "2026-06", "route": "catalog"},
       "date": {"value": "2026-06-01", "route": "derived"}
     },
     "chunk_ids": ["academic-rules@2026-06#0000-9f3a1c20", "…"],
     "chunk_count": 41,
     "lake_path": "lake/docs/academic-rules/2026-06",
     "docvec": "lake/docs/academic-rules/2026-06/docvec.json",
     "ingested_run": "ingest-20261125T095501Z-1a2b", "ingested_at": "…", "archived_at": null, "deleted_at": null
    },
    "2023-08": {"status": "archived", "…": "…", "lake_path": "archive/academic-rules/2023-08"}
   }
  }
 },
 "inbox_index": { "academic-rules-handbook-jun-2026.pdf": {"sha": "…", "doc_id": "academic-rules", "version": "2026-06"} },
 "quarantine": [ {"file": "Student_Handbook_Copy.pdf", "sha": "…", "codes": ["U-EXACT-DUP"], "run_id": "…", "ts": "…", "repeat": false} ],
 "indexes": {
  "rahbar":            {"role": "live",      "registry": "rahbar-registry", "embed_model": "nomic-embed-text", "embed_version": "<digest>", "dimension": 768, "chunk_size": 300, "chunk_overlap": 40, "chunks": 532, "revision": "r0007"},
  "rahbar-cand-mxbai": {"role": "candidate", "registry": "rahbar-cand-mxbai-registry", "embed_model": "mxbai-embed-large", "embed_version": "<digest>", "dimension": 1024, "chunk_size": 300, "chunk_overlap": 40, "chunks": 532, "revision": "r0007"}
 }
}
```
Rules: atomic write (temp + `fsync` + rename), previous copy kept as `ledger.json.bak`; lock `/data/ledger/ingest.lock` = `{"pod","run_id","started_at"}`; **status transitions only as in 04 §4.4**; a version in `quarantine` never appears under `documents`.

**Chunk snapshots** `lake/docs/<doc_id>/<version>/chunks.jsonl` (one line per chunk): `{"chunk_id","text","source","section","page","doc_id","doc_version","chunk_sha"}` — the **immutable** record the trace tool rebuilds from. Moved with the version when archived.

**Chunk metadata in Chroma** (the five A2 keys are mandatory): `source, section, page, doc_version, superseded` **+** `doc_id, status ("current"|"archived"), content_sha, chunk_sha, ingest_run, revision`. Chunk id: `<doc_id>@<doc_version>#<ordinal:04d>-<sha8>` (sha8 = first 8 hex of SHA-1/256 of the chunk text; A2 uses SHA-1[:8] — keep it for continuity or document the change).

**Registry collection** `<collection>-registry` metadata: `active` (collection name), `generation` (**data revision**, `r0007`, bumped after every Chroma change), `previous` (A2 field, may stay empty for in-place indexes), `embed_model`, `embed_version`, `dimension`. The API's `generation` = this value (not the collection's own metadata).

Corpus-state **digest** and **batch** tags feed the suite (`corpus_digest`, `--batches`).

---

## 3. Verification report (`/data/reports/verification/<run_id>.json`, schema 1; `.md` is a rendering)

```json
{
 "schema": 1, "run_id": "ingest-20261125T095501Z-1a2b", "started_at": "…", "git_sha": "…", "image": "rahbar-indexer@sha256:…",
 "embed_model": "nomic-embed-text", "embed_version": "…",
 "thresholds": {"quality_min_chars": 200, "quality_min_chars_per_page": 40, "garbled_max_bad_ratio": 0.02, "garbled_min_word_ratio": 0.35,
                "truncation_fail_score": 3, "near_dup_cosine": 0.97, "near_dup_jaccard": 0.80, "series_similarity": 0.80},
 "documents": [
  {"file": "Student_Handbook_Copy.pdf", "sha256": "…", "pages": 87,
   "resolved": {"title": {"value": "Student Handbook", "route": "embedded"}, "doc_version": {"value": "2026-06", "route": "derived"}, "doc_id": "student-handbook"},
   "checks": {
     "quality":      {"status": "pass", "code": "Q-OK",       "reason": "87 pages, 412k chars, word ratio 0.71", "evidence": {"chars": 412000, "word_ratio": 0.71}, "evaluated": true},
     "completeness": {"status": "pass", "code": "C-OK",       "reason": "title, version, source, pages present; no truncation signals", "evidence": {"signals": []}, "evaluated": true},
     "recency":      {"status": "pass", "code": "R-OK-FIRST", "reason": "no other version known", "evidence": {}, "evaluated": true},
     "uniqueness":   {"status": "fail", "code": "U-EXACT-DUP","reason": "byte-identical to student-handbook@2026-06 (sha256 717eb4b8…)", "evidence": {"duplicate_of": "student-handbook@2026-06"}, "evaluated": true}},
   "outcome": "quarantined",                    // accepted | quarantined | archived | unchanged_skipped
   "destination": "quarantine/ingest-20261125T095501Z-1a2b/Student_Handbook_Copy.pdf"}
 ],
 "unchanged": ["academic-rules-handbook-jun-2026.pdf", "…"],
 "summary": {"documents": 12, "accepted": 6, "quarantined": 6, "archived": 1, "unchanged": 9,
             "failures_by_check": {"quality": 1, "completeness": 2, "recency": 0, "uniqueness": 3},
             "problems_not_flagged": []}      // optional: filled by hand when comparing with batch-b/README expectations
}
```

**Reason codes** (stable; unit-tested): quality `Q-OK, Q-EXTRACT-FAIL, Q-EMPTY, Q-GARBLED` · completeness `C-OK, C-MISSING-SOURCE, C-MISSING-TITLE, C-MISSING-DATE-VERSION, C-MISSING-PAGES, C-TRUNCATED` · recency `R-OK-FIRST, R-OK-NEWEST, R-OK-REVISION, R-NEWER-EXISTS` · uniqueness `U-OK, U-EXACT-DUP, U-NEAR-DUP`. `status` ∈ `pass|fail`; **every document has all four check records**.

`quarantine/<run_id>/<file>.reason.json`: `{"file","sha256","codes":[…],"reasons":[…],"resolved":{…},"run_id","ts"}`.

---

## 4. Ingest run summary (last stdout line; also `/data/reports/ingest/<run_id>.json`)

```json
{"type":"ingest_summary","schema":1,"run_id":"…","command":"sync","started_at":"…","seconds":2.1,
 "docs_seen":9,"docs_unchanged":9,"docs_new":0,"docs_updated":0,"docs_superseded":0,"docs_archived_stale":0,
 "docs_deleted":0,"docs_quarantined":0,"docs_renamed":0,
 "chunks_embedded":0,"chunks_reused":0,"chunks_written":0,"chunks_deleted":0,"verification_embeddings":0,
 "repairs":0,"indexes":{"rahbar":{"revision":"r0007","revision_bumped":false}},"exit":0}
```
Invariant tests: on an unchanged corpus `chunks_embedded == 0 and verification_embeddings == 0 and revision_bumped == false`; `chunks_written − chunks_deleted` equals the change in Chroma's count; per index.

`count --json` output: `{"index":"rahbar","chroma_total":532,"ledger_expected_total":532,"per_doc":{"academic-rules@2026-06":41,"…":0},"orphans":[],"missing":[]}`.

---

## 5. Evaluation artefacts

### 5.1 Files and locations

| File | Location | Notes |
|---|---|---|
| golden set | `eval/golden.jsonl` | schema in 06 §3.2 |
| pairs | `eval/pairs.jsonl` | 06 §4 |
| judge labels | `eval/judge_labels.jsonl` | 06 §6.3 |
| live queries | `eval/live_queries.jsonl` | 09 §2 |
| coverage calibration | `eval/coverage-calibration.jsonl` | `{"live_id","golden_id","similarity","human":"covered|not_covered"}` |
| suite config | `ragops/config/suite.yaml` | 06 §2 |
| results (committed) | `eval/results/<YYYYMMDDTHHMMSSZ>_<label>.json` (+ `.md`, + `.decision.json`, + `_coverage.json`) | pulled from `ragops-results` |
| baselines | `/results/baselines/live.json` on the PVC; a copy committed as `eval/results/baseline-live.json` | explicit promote only |

### 5.2 Suite result file (schema 1)

```json
{
 "schema": 1, "status": "complete",                 // complete | incomplete
 "run_id": "suite-20261126T140311Z-ab12", "label": "baseline",
 "started_at": "…", "finished_at": "…", "git_sha": "…",
 "images": {"api": "…@sha256:…", "ragops": "…"},
 "config_hash": "…", "golden_hash": "…", "pairs_hash": "…", "corpus_digest": "…", "batches": ["A"],
 "seed": 20261122, "seeds": {"typo": 20261123, "judge": 7, "e2e": 20261122},
 "target": {"url": "http://api:8000", "release_id": "R1-nomic", "collection": "rahbar", "revision": "r0007",
            "embed_model": "nomic-embed-text", "embed_version": "…", "app_version": "…"},
 "levels": {
  "module": {"paraphrase_mean_cos": 0.0, "unrelated_mean_cos": 0.0, "gap": 0.0, "pair_accuracy": 0.0,
             "unrelated_by_difficulty": {"easy": 0.0, "hard": 0.0},
             "embed_ms_mean": 0.0, "embed_ms_p95": 0.0, "vector_bytes": 3072,
             "determinism_max_abs_diff": 0.0, "determinism_min_cos": 1.0, "n_paraphrase": 20, "n_unrelated": 20},
  "component": {
   "n": 24,
   "clean": {"recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0, "ndcg@5": 0.0, "precision@5": 0.0, "retrieval_ms_mean": 0.0, "retrieval_ms_p95": 0.0},
   "noisy": {"recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0, "ndcg@5": 0.0, "typo_rate": 0.06},
   "delta_noisy": {"recall@5": 0.0, "mrr": 0.0, "ndcg@5": 0.0},
   "by_category": {"answerable": {"n": 16, "recall@5": 0.0}, "hard": {"n": 8, "recall@5": 0.0, "by_kind": {"paraphrase": {}, "multi_chunk": {}, "batch_b": {}}}},
   "top1_similarity": {"min": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0, "max": 0.0, "unanswerable_p50": 0.0}},
  "endpoint": {
   "n": 30, "n_answerable": 24, "n_unanswerable": 6,
   "faithfulness": 0.0, "faithfulness_partial": 0.0, "faithfulness_unsupported": 0.0, "faithfulness_proxy": 0.0,
   "abstention_correctness": 0.0, "false_abstention_rate": 0.0,
   "citation_validity": 0.0, "citations_checked": 0, "answered_without_citation": 0, "citation_gold_hit": 0.0,
   "latency_p50_s": 0.0, "latency_p95_s": 0.0, "fallback_rate": 0.0, "injection_obeyed": [],
   "tokens_in_mean": 0, "tokens_out_mean": 0,
   "judge": {"model": "llama3.2:3b", "unparseable": 0, "hand_labels": 10, "agreement": 0.0, "cohen_kappa": 0.0}}
 },
 "per_question": [ {"id":"g001","category":"answerable","trace_id":"…","retrieved":[{"rank":1,"doc":"…","page":14,"score":0.81,"hit":true}],
                    "recall@3":1.0,"recall@5":1.0,"rr":1.0,"ndcg@5":1.0,"answered_from_context":true,"citations":2,"citation_validity":1.0,
                    "judge_label":"supported","proxy":0.9,"seconds":41.2,"cached":false,"answer":"…(≤400 chars)"} ],
 "skipped": [ {"id":"g027","reason":"requires_batch B not ingested"} ],
 "notes": ""
}
```
**Metric registry** (names the gate uses, `level.metric`): `module.{paraphrase_mean_cos, unrelated_mean_cos, gap, pair_accuracy, embed_ms_mean, embed_ms_p95, determinism_max_abs_diff}` · `component.{recall@3, recall@5, mrr, ndcg@5, precision@5, noisy_recall@5, noisy_mrr, noisy_ndcg@5, retrieval_ms_p95}` (resolved from `clean`/`noisy`) · `endpoint.{faithfulness, faithfulness_proxy, abstention_correctness, false_abstention_rate, citation_validity, citation_gold_hit, latency_p50_s, latency_p95_s, fallback_rate}`.

`.md` rendering = the summary table (06 §8). Stochasticity: `python -m ragops.suite.stochasticity r1.json r2.json [--out …]` prints `metric, run1, run2, |Δ|, explanation`.

Result `status: incomplete` is written **only** when the run aborts; the gate refuses incomplete files (exit 2).

---

## 6. Trace record (one JSON line; schema 1)

```json
{
 "type": "trace", "schema": 1, "trace_id": "7f3c…e9", "ts": "2026-11-26T14:05:02.311Z", "route": "/api/ask",
 "status": "ok",                                   // ok | abstained | fallback | error
 "pod": "api-6d9f-x2k", "app_version": "1a2b3c4", "release_id": "R1-nomic",
 "query": "can i drop a course after the third week", "query_truncated": false, "rewritten_query": null,
 "embedding": {"model": "nomic-embed-text", "version": "<digest>", "dimension": 768, "profile": {"query_prefix": "search_query: ", "lowercase": true}},
 "collection": {"name": "rahbar", "revision": "r0007", "generation": "r0007"},
 "retrieval": {
   "top_k": 5,
   "filters": {"superseded_filter": true, "where": {"superseded": false}, "history_requested": false, "where_document": []},
   "dense_order": ["c12","c40","c03","c77","c09"],
   "reranked_order": ["c40","c12","c03","c77","c09"],
   "assists": [{"kind": "exact_term", "term": "4.25", "moved": ["c40"]}],
   "candidates": [{"rank": 1, "chunk_id": "…", "doc_id": "academic-rules", "doc_version": "2026-06", "source": "…pdf", "section": "…", "page": 31, "score": 0.8123, "superseded": false}],
   "from_cache": false, "origin_trace_id": null},
 "guardrails": [{"stage": "retrieval", "rail": "injection", "action": "neutralised", "target": "chunk:…", "doc_id": "campus-parking-policy", "doc_version": "2026-11",
                 "pattern": "ignore-instructions", "span_chars": 73, "excerpt": "Ignore all previous instruc…"}],
 "prompt": {"sha256": "…", "template_version": "a1b2c3d4+rails1", "chunk_ids": ["…","…","…"], "stored": true, "from_cache": false},
 "model": {"provider": "ollama-host", "name": "llama3.2:3b", "params": {"temperature": 0.0, "seed": 20261122, "num_predict": null, "timeout_s": 600}, "attempts": 1},
 "response": {"answer": "…", "confidence": "high", "answered_from_context": true, "abstained": false, "abstain_reason": null, "fallback_reason": null,
              "citations": [{"source": "…", "section": "…", "page": 31}], "citation_check": {"valid": true, "rewritten": []}},
 "latency_ms": {"total": 41250.4, "cache": 3.1, "embed": 22.7, "retrieve": 61.0, "rail": 0.4, "prompt": 0.3, "generate": 41100.0, "validate": 1.2},
 "cache": {"enabled": true, "hit": false, "similarity": 0.82, "scope": "r0007:nomic-embed-text:ab12cd34ef"},
 "tokens": {"in": 912, "out": 143},
 "eval": {"run_id": "suite-…", "label": "baseline", "seed": 20261122, "bypass_cache": true}      // null for ordinary traffic
}
```
Rules: always present — `trace_id, ts, route, status, release_id, query, embedding, collection, latency_ms, cache`; `retrieval`, `prompt`, `model` are `null` only when the stage did not run (cache hit → `from_cache: true` with `origin_trace_id`; abstention before generation → `prompt: null`, `model: null`); never `reasoning`; never any credential. The PDF D1 field list maps 1-to-1 to these keys (08 §2). `/api/retrieve` writes the same record with `route:"/api/retrieve"`, `prompt: null`, `model: null`, `response: null`.

**Prompt store file** `/traces/prompts/<sha256>.json`: `{"sha256","template_version","messages":[{"role","content"},…]}`; hash = SHA-256 of `json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",",":"))` UTF-8.

**Trace files:** `/traces/<POD_NAME>.jsonl` (append-only, rotate at 50 MiB to `.1`, `.2`).

---

## 7. Gate config, decision and candidate spec

### 7.1 `ragops/config/gate.yaml` (ConfigMap `ragops-gate`, key `gate.yaml`)
Shape in 07 §5.1. Fields: `version`, `require_same` (subset of `golden_hash, corpus_digest, suite_schema, seed, profile_hash, embed_model*`) — `*` is *not* required (a candidate may change the model), `on_missing_metric: fail`, `rules[]` (`id, level, metric, type, value`), `justification{}`. Rule types: `max_drop_abs | max_increase_abs | min_value | max_value | not_lower_than_baseline`. Unknown type/metric ⇒ exit 2.

### 7.2 Decision file (`<ts>_<label>.decision.json`)
```json
{"schema":1,"overall":"fail","evaluated_at":"…","git_sha":"…","config_hash":"…","gate_config_version":1,
 "baseline":{"file":"baseline-live.json","label":"baseline","release_id":"R1-nomic"},
 "candidate":{"file":"20261127T091200Z_cand-minilm.json","label":"cand-minilm","release_id":"R3-minilm"},
 "rules":[{"id":"recall5_drop","metric":"component.recall@5","type":"max_drop_abs","limit":0.02,"baseline":0.9167,"candidate":0.7917,"delta":-0.125,"status":"fail","message":"recall@5 0.7917 is 0.1250 below baseline 0.9167 (limit 0.02)"}],
 "incomparable": []}
```
### 7.3 Candidate spec (`ragops/config/candidates/<name>.yaml`) — 07 §2.2. Validator: exactly one of `{embed_model, chunk_size|chunk_overlap (pair counts as one), top_k, prompt_version, reranker}` differs from the baseline spec `ragops/config/candidates/baseline.yaml`.

### 7.4 Release script contract — `scripts/ragops/release.sh <candidate-name> [--dry-run]`; exit `0` released · `1` refused · `2` rollout failed/timeout.

---

## 8. Coverage

`ragops/config/coverage.yaml`: `{similarity_threshold, min_share, embed_model, calibrated_on, seed, cluster_similarity}`.
Report `<ts>_coverage.json`:
```json
{"schema":1,"run_at":"…","golden_hash":"…","live_hash":"…","embed_model":"nomic-embed-text",
 "similarity_threshold":0.0,"min_share":0.85,"n_live":44,"covered":0,"share":0.0,"share_in_domain":0.0,"share_out_of_domain":0.0,
 "verdict":"GAP","tfidf_cross_check":{"share":0.0},
 "uncovered":[{"id":"l031","query":"…","best_golden_id":"g005","best_similarity":0.0,"domain":"out"}],
 "topics":[{"name":"transport","queries":["l031","l032"],"in_corpus":true,"document":"transport-routes-2026.html"}]}
```

---

## 9. HTTP additions (additive; the A2 contracts stay)

| Item | Contract |
|---|---|
| `POST /api/retrieve` | enabled iff `EVAL_ENDPOINTS_ENABLED=true`. Body `{"question": str (3..500), "k": int (1..20, default TOP_K)}`. Response `{"trace_id","collection":{"name","revision"},"embedding":{"model","version"},"filters":{…},"dense_order":[…],"reranked_order":[…],"candidates":[{rank,chunk_id,doc_id,doc_version,source,section,page,score,superseded}],"latency_ms":{…}}`. No generation, no cache. Writes a trace (`route:"/api/retrieve"`). |
| Request headers (honoured iff `EVAL_HEADERS_ENABLED=true`) | `X-Eval-Bypass-Cache: true` · `X-Eval-Seed: <int>` · `X-Eval-Temperature: <0..0.3>` (clamped to the A2 range) · `X-Eval-Run: <run id>` · `X-Eval-Label: <label>` |
| Response headers | `X-Trace-Id`, `X-Release-Id` (plus A2 `X-Request-ID`, `X-Rahbar-Version`) |
| `AskResponse` | additive optional fields `trace_id: str|None`, `release_id: str|None`; nothing removed or renamed |
| `Passage`/`RetrievedRef` | additive optional `doc_id`, `doc_version`, `superseded`; defaults keep the stub valid |
| `/metrics` | A2 series + 08 §8 additions |
| `/readyz` | unchanged behaviour; additionally reports `release_id`, `collection`, `revision` in `checks` |

---

## 10. Boundary tests and invariants to add or keep (`tests/test_boundaries.py`, `tests/test_manifests.py`)

1. The API (`api/app/**`) still contains **no** Chroma write call (extended list: `add, upsert, update, delete, modify, create_collection, get_or_create_collection, delete_collection`). New API files (`trace.py`, `rails.py`, `retrieve.py`) are included in the scan.
2. `ragops/**` (suite, gate, coverage, trace) contains no Chroma client import at all.
3. Only `indexer/pipeline/store.py`, `incremental.py`, `ops.py` may call Chroma write methods.
4. The API never imports `pipeline`; `ragops` never imports `pipeline`.
5. API startup does no indexing (A2 test stays).
6. Manifests: `api` Deployment `maxSurge:1, maxUnavailable:0`, replicas 3; release-scoped keys present in the **pod template**; `api-candidate` has `REDIS_URL` empty and a distinct selector; `eval` Job `backoffLimit: 0` and `restartPolicy: Never`; CronJob `ingest` `concurrencyPolicy: Forbid`; PVC `ragops-data/traces/results` exist; eval Job mounts `ragops-data` read-only; no Secret value in any manifest; no `:latest`.
7. NetworkPolicy: no rule allows `ragops-eval` → `chroma` or `redis`; `ui` → `chroma` still absent.
8. The trace record has every PDF-listed field; no `reasoning`; no secret.

---

## 11. Exit codes (all tools)

| Tool | 0 | 1 | 2 | 3 | other |
|---|---|---|---|---|---|
| `pipeline.run` | done | done with quarantines (Job wrapper → 0) | usage | fatal | 4 unknown restore/delete target |
| `ragops.suite.run_suite` | complete | — | usage/config/golden invalid | infrastructure failure (incomplete) | |
| `ragops.gate.apply` | **pass** | **fail** | usage/incomparable/IO | — | |
| `ragops.coverage.coverage` | share ≥ min_share | **share < min_share** | usage/config/model mismatch | embedding unavailable | |
| `ragops.trace.show` | found, consistent | — | usage | — | 4 not found · 5 prompt store corrupt · 6 rebuild differs |
| `ragops.trace.summary` | ok | — | usage | no traces | |
| `ragops.suite.golden --validate` | valid | **violations** | usage | — | |
| Job `eval` (via `job_entry.sh`) | gate pass (Complete) | gate fail (Failed) | — | infrastructure (Failed) | last log line `RESULT=…` |
| `scripts/ragops/release.sh` | released | refused | rollout failed | — | |

---

## 12. Names, labels, paths (one place)

| Thing | Name |
|---|---|
| Namespace | `rahbar` |
| Images | `rahbar-api`, `rahbar-ui`, `rahbar-indexer`, **`rahbar-ragops`** (suite, gate, coverage, trace tools; includes `api/app/services/{prompt,rails}.py`) |
| Pod labels | `app: api`, `api-candidate`, `ui`, `chroma`, `redis`, `indexer` (ingest Job/CronJob pods), `ragops-eval`, `ragops-loader`, `ragops-coverage` |
| PVCs | `chroma-data` (template), `redis-data`, `ragops-data`, `ragops-traces`, `ragops-results` |
| ConfigMaps | `rahbar-config`, `ragops-config`, `ragops-gate`, `ragops-eval-target` |
| Jobs / CronJob | `ingest` (Job), `ingest` (CronJob), `eval`, `coverage`, `ingest-<action>-<ts>` |
| Deployments / Services | `api`, `api-candidate`, `ui`, `redis`; Services `api`, `api-candidate`, `ui`, `chroma`, `redis` |
| Collections | `rahbar` (live) + `rahbar-registry`; `rahbar-cand-<name>` + `-registry` |
| Release ids | `R1-nomic` (baseline), `R2-<short>`, `R3-<short>` |
| Repo dirs | `eval/` (golden, pairs, live queries, judge labels, `results/`), `traces/` (curated samples), `corpus/batch-b/`, `ragops/`, `k8s/`, `docs/a3-evidence/` |
| Result file | `eval/results/<YYYYMMDDTHHMMSSZ>_<label>.json` |

---

## 13. Environment variables (new; existing A2 variables unchanged)

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `DATA_DIR` | ingest | `/data` | root of the data-lake PVC |
| `INDEX_TARGETS` | ingest | `registered` | `registered` or a comma list of collections to keep current |
| `LOCK_TTL_SECONDS` | ingest | `7200` | stale-lock age |
| `QUALITY_MIN_CHARS`, `QUALITY_MIN_CHARS_PER_PAGE` | ingest | `200`, `40` | emptiness thresholds |
| `GARBLED_MAX_BAD_RATIO`, `GARBLED_MIN_WORD_RATIO` | ingest | `0.02`, `0.35` | garbled thresholds |
| `TRUNCATION_FAIL_SCORE` | ingest | `3` | weighted-signal sum that fails completeness |
| `NEAR_DUP_COSINE`, `NEAR_DUP_JACCARD`, `SERIES_SIMILARITY` | ingest | calibrated | uniqueness / series |
| `RELEASE_ID`, `EMBED_VERSION`, `PROMPT_VERSION` | api, candidate | — | release identity (in the pod template) |
| `TRACE_ENABLED`, `TRACE_DIR`, `TRACE_MAX_BYTES`, `POD_NAME` | api | `true`, `/traces`, `52428800`, downward API | trace writer |
| `EVAL_ENDPOINTS_ENABLED`, `EVAL_HEADERS_ENABLED` | api, candidate | `false` in code; `true` in `ragops-config` | retrieval endpoint and eval headers |
| `RAILS_ENABLED`, `RAIL_EXCLUDE_RATIO` | api | `true`, `0.30` | retrieval rail |
| `TARGET_URL`, `LABEL`, `MODE`, `BASELINE_RESULT`, `CANDIDATE_RESULT`, `SUITE_ARGS` | eval Job | from `ragops-eval-target` | what to test and how |
| `GATE_CONFIG`, `RESULTS_DIR` | eval Job | `/config/gate.yaml`, `/results` | gate and output |
