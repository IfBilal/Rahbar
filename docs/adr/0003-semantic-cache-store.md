# ADR 0003: Semantic cache in Redis, keyed by index generation and settings

## Status
Accepted · 4 November 2026 · implemented in `api/app/services/cache.py`

## Context
Generation is the slow, expensive step: on our laptop CPU one answer costs one to four
minutes. Many students ask the same thing in different words. A semantic cache returns a
stored answer when a new question's embedding is close enough to a cached question's.
Three things make this dangerous. A cached mistake is served to everyone. A cached answer
outlives the index that produced it. And three API replicas must share one cache.

The case study allows Redis or a second Chroma collection.

## Decision
**Redis**, as a Deployment with its own PVC and append-only persistence
(`k8s/base/redis.yaml`), reachable only from the API pods (NetworkPolicy
`redis-from-api`).

- **What is stored.** One Redis list per scope; each entry holds the question, its
  embedding (the same vector the retriever used, so a hit costs no extra model call) and
  the validated `AskResponse` without its request id. The list is trimmed to the newest
  `CACHE_MAX_ENTRIES` (500) and expires after `CACHE_TTL_SECONDS` (7 days).
- **A hit** is cosine similarity at or above `CACHE_THRESHOLD` from the ConfigMap. The
  threshold was chosen with data: the lowest value with zero false hits on our paraphrase
  and near-miss pairs (`docs/PIPELINE.md`, "Semantic cache").
- **Never cached:** follow-ups (no conversation state exists, so anything that leans on an
  earlier turn is detected and skipped), abstentions, out-of-scope answers, the canned
  fallback, and anything that failed validation. Only an answer that is grounded, has
  citations, and passed the citation guard is stored.
- **Scope = generation + embedding model + a digest of every answer-shaping setting**
  (provider, LLM model, temperature, relevance floor, top_k, passages sent, exact-term
  assist). We added the settings digest after a real bug: on the cluster, answers cached
  under the old floor and a different provider kept being served after a ConfigMap
  change (`api/tests/test_answer.py::test_a_settings_change_starts_a_fresh_cache_scope`).
- **Invalidation on re-index** happens without the indexer talking to Redis. A new index
  is a new generation id. On its next request the API computes a new scope, finds no
  entries in it, and `observe()` deletes every key of the previous scope. Old entries are
  unreachable from the moment the pointer moves, even before the delete runs.

## Options considered
- **A second Chroma collection.** Vector search comes free, but the cache would then be
  written by the API, breaking the rule that only the indexer writes Chroma, and cache
  churn would share a disk and a process with the index.
- **Exact-match Redis keys.** Safe but nearly useless: "What is the withdrawal deadline?"
  and "When is the last day to withdraw from a course?" never match.
- **Letting the indexer flush Redis.** Simple, but it needs indexer-to-Redis network
  access (the case study allows Redis from the API only), and a flush racing a pointer
  switch can re-cache an old answer. Generation scoping cannot race.

## Consequences
- Repeated questions return in milliseconds, and the UI shows a cache chip (`cached: true`).
- A lookup scans up to 500 vectors in Python (about 1 ms). That is a declared shortcut; at
  a larger scale this moves to RediSearch vector search.
- Redis being down makes `/readyz` fail (the case study requires it), but a Redis error
  inside a request only logs a warning and answers without the cache.
- Redis has no password. The control is the NetworkPolicy (Redis from the API only),
  enforced by Calico. A `requirepass` from a Secret would add a manual step to a
  clean-clone run; we record it as a residual risk in `docs/SECURITY-OBSERVABILITY.md`.
