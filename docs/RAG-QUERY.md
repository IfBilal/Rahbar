> **Status (5 November 2026):** implemented in `api/app/services/` (answer, prompt, guard, cache); see `docs/PIPELINE.md`. This guide is kept as the plan of record.

# Query path, LLM safety, citations and semantic caching

**Eight-step request path:** validate length (3–500) → eligible cache lookup → embed with shared model → top-k version-filtered Chroma retrieval → evidence-only numbered prompt → JSON-schema-constrained generation at configured low temperature → Pydantic parse/validate, one retry then fallback → response/log/cache only if valid. Make each step independently testable under `api/app/services/`.

**Truth guardrails:** if no passage clears measured relevance floor, answer `answered_from_context=false` without a made-up citation. Every returned citation must match a retrieved `(source, section, page)` tuple in the current response, not just a plausible public URL. Poisoned chunks and questions are untrusted data. `reasoning` in internal `Answer` must not be returned in `AskResponse`.

**Cache guardrails:** Redis + PVC (not an exact-string-only cache), cosine similarity ≥ ConfigMap threshold tuned against negatives, no follow-ups/abstentions/out-of-scope/malformed results, generation-scoped invalidation on re-index. Do not claim multi-turn state: the starter `AskRequest` has only `question`.

## Reference implementation algorithm (agent checklist)

```text
input: AskRequest(question)  # already validates 3..500
request_id := middleware X-Request-ID or generated identifier
config := Settings from environment
active := read-only Chroma active-index descriptor; verify pin and dimension
if request is eligible standalone:
    emb := embed question using EMBED_MODEL
    candidate := Redis best cosine match within same generation/model/provider
    if candidate >= CACHE_THRESHOLD and cached answer still citation-valid: return hit
else:
    emb := embed question using EMBED_MODEL
passages := Chroma.query(embedding=emb, top_k=TOP_K, metadata_filter=non_superseded)
passages := convert cosine distances to similarity, keep source/section/page
if no passage >= RELEVANCE_FLOOR: return canonical abstention (never cache)
model_answer := provider.generate(question, passages) with numbered untrusted evidence
try Pydantic Answer validation, grounding and whitelist checks
if validation failure: retry once with same retrieved evidence
if repeat failure: return safe fallback (never cache)
return AskResponse(request_id, answer, citations, answered_from_context, confidence,
                   retrieved, provider)
if eligible and verified: cache answer with question embedding and generation TTL
```

**Use actual starter interfaces:** `Retriever.retrieve(self, question: str, k: int) -> list[Passage]`; `LLMProvider.generate(self, question, passages) -> Answer`; `answer_question(question, retriever, provider, settings) -> AskResponse`; optional extra caches/services can live under `api/app/services`. Do not send the internal `reasoning` string to `AskResponse`. If an LLM emits a bare citation source without correct section or page, reject it; don't auto-create a citation that was not in returned evidence.

### Relevance, old versions and exact terms

- Configure a Chroma cosine collection explicitly. Chroma returns a **distance**, so for cosine use `similarity = 1.0 - distance`; don't make this conversion against a collection configured with L2 without adapting the score contract.
- Default query filter is `superseded == false` (and, as needed, latest correct policy edition); historical query path must be explicit and covered by two version-sensitive tests. A prompt instruction by itself cannot fix stale retrieval.
- Use the configured top-k and measurable `RELEVANCE_FLOOR`, including too-low, empty and old-only cases. Avoid the anti-pattern of generating confident text when retrieved score is below relevance floor.
- Dense embeddings can blur course codes or numeric clauses. After measuring recall by type, an optional lexical assist may rerank retrieved candidates **after** version filtering. It is a bonus, not a substitute for Chroma.

### Pydantic and prompt-injection boundaries

- Ask the selected provider for JSON/schema mode if available; validate with the *same* `Answer` schema as the starter, not a weaker ad-hoc dict parser.
- Delimit evidence clearly and mark it untrusted. Test a malicious retrieved paragraph saying "ignore instructions / reveal keys" and a similarly hostile user question.
- Validate `answered_from_context` consistency: for false, citations should be empty; for true, support should exist and every citation tuple must match a retrieved record. Verify `reasoning` is omitted from HTTP response and logs.
- Schema validation is necessary, not sufficient for truth. Include a manual generation-quality review for evidence usage/unsupported claims and record factual incorrectness honestly.
- If provider errors, invalid JSON or citation mismatch persist after one retry, respond with predictable canned abstention/fallback—not HTTP 500 with internal JSON trace.

### Redis semantic cache, not exact-key cache

- Cache record should minimally contain: normalized question text or hash, its embedding, permitted `Answer`+`retrieved` references, active index generation ID, embedding/provider pins, creation time, TTL and eligibility proof. Use bounds to avoid unbounded full scans on Redis.
- Search candidate vectors using cosine similarity and compare against a threshold from ConfigMap. Sweep multiple thresholds and log the actual *false positive* for at least one rejected threshold, if encountered. Pick lowest empirically safe threshold with zero false hits on test pairs.
- Follow-up detection is conservative because starter has no chat-history/session context; skip phrases relying on prior answers (`what about that?`, `and for 2023?`) rather than pretending to cache multi-turn context correctly.
- API replicas may read/write Redis, but **only indexer writes Chroma**. On reindex, use per-generation cache namespaces and expiry/deletion from API side (the indexer need not reach Redis, consistent with the NetworkPolicy). Test stale cache rejection even when Redis deletion is delayed.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-specs-retrieval-md"></a>

## Implementation spec — Retrieval


**Owner:** A. **WBS:** T12. **Primary paths:** `api/app/retrieval/chroma.py; api/app/services/answer.py; api/tests/*`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Contract
`ChromaRetriever.retrieve(question,k)->list[Passage]`. The starter's `Passage.score` is similarity, not Chroma cosine distance. Fetch active generation, verify it exists, embed the question using the indexed pin, query k with `where={"superseded": False}` for ordinary/current queries. A clearly historical question may use old documents; do not let vague year mentions override default without deterministic tests.

### Relevance and version semantics
Use a **measured** relevance floor. If no hits above it, decline without invented evidence. Top-k is from ConfigMap and can be tuned; tests check sorting, scores, metadata conversion, section and page. Version-sensitive fixtures should prove that 2023 source is not returned for a 2026/ordinary question. Never rely on prompt to reject old material; do the metadata filter before generation.

### Optional exact-term enhancement
A measured lexical/BM25 re-rank of initial Chroma candidates can improve clauses/codes. Only ship if it is covered by tests and does not accidentally admit superseded chunks or break recall gate; see optional hybrid design (consolidated in ADR 0002). Core Chroma dense retrieval is required even if hybrid is adopted.

### Tests
No index; empty collection; Chroma timeout; old-only matches; explicit historical ask; 1-distance conversion; `top_k=1`; exact clause; relevance-floor abstention; model dimension conflict; metadata missing; prompt injection text appears as retrieved **data**, not commands.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

<a id="merged-docs-specs-generation-md"></a>

## Implementation spec — Generation


**Owner:** A. **WBS:** T13,T14. **Primary paths:** `api/app/providers/llm/ollama.py; api/app/services/answer.py; api/app/schemas.py`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Provider contract
`LLMProvider.generate(question,passages)->Answer` where Pydantic `Answer` contains `reasoning`, `answer`, `citations`, `answered_from_context`, `confidence`. **Never return `reasoning` to user**. Implement one provider fully (default `ollama-host`), selectable with `LLM_PROVIDER` and clean interface. Ollama `/api/chat` must receive JSON schema mode where supported, `temperature` from ConfigMap (0–0.3 recommended) and bounded timeout.

### Prompt construction
Order: unambiguous system rule to answer exclusively from evidence and ignore instructions inside it; numbered evidence with source/section/page; user question. Quote/delimit retrieved passages explicitly as untrusted content. Ask for citations for all claim-bearing assertions and abstention when evidence absent or ambiguous. No model generation when retrieval floor fails.

### Validation
First parse/validate with `Answer.model_validate` or `model_validate_json`; on malformed schema or invalid citations, retry **once** with error feedback (never leak raw unsafe output to UI); on second failure return canned abstention/fallback (HTTP success where appropriate) and increment fallback metric. Citation whitelist exact `(source,section,page)` matches retrieved passages; no source in evidence -> cannot cite. Consider truth-support manual evaluation separately from mere cite match.

### Tests
Valid provider JSON; extra unknown field; nonexistent cite; unsupported sentence; malformed twice; provider timeout/network exception; poisoned chunk; malicious user instruction; empty passage list; model reasoning absent in HTTP response; structured confidence restricted to high/medium/low. No real LLM in unit tests.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

<a id="merged-docs-specs-cache-md"></a>

## Implementation spec — Cache


**Owner:** A. **WBS:** T14,T22. **Primary paths:** `api/app/services/cache.py; api/app/config.py; PIPELINE-IMPLEMENTATION.md`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Required semantics
Redis Deployment+PVC is mandatory; semantic cache retrieval must use **cosine similarity >= threshold read from ConfigMap**. A normal Redis key-value cache by exact question alone is not semantic. Implement a bounded list/index of cached question embeddings for eligible answers (e.g. store vector plus Answer JSON in Redis and scan a small bounded set; avoid unbounded O(N) production behavior) or justify an alternative in ADR 0003.

### Eligibility, false-hit prevention
Cache only standalone, validated `answered_from_context=true` answers with genuine citations, current active index generation, matching embed and provider. Do not cache follow-ups, absent answers, out-of-scope, validation failures or poisoned responses. The starter has no session field: conservative heuristic to reject context-dependent follow-up questions is allowed; do not claim real multi-turn support.

### Threshold tuning and invalidation
Test >=2–3 candidate thresholds and the lowest with zero false hits on golden/negative paraphrase pairs; document the incorrect hit that excluded a looser threshold where observed. Keep generation in each key (`cache:<generation>:...`). On a new active collection, clear/expire old generation keys via API-side generation watcher and namespace segregation; indexer must not need Redis network access if rubric NetworkPolicy says only API may reach Redis. Include Redis AOF/PVC and TTL, size limits and no personal text in JSON logs.

### Tests
Paraphrase hit; unrelated high-overlap collision; cache invalid after reindex; two API replicas share Redis; broken Redis unready; follow-up skip; abstention skip; model mismatch skip; poisoned cache payload rejected; expiration and limit; threshold from env.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

