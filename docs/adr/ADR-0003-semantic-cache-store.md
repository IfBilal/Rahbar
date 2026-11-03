> **Submission integration:** This standalone ADR is included at ZIP root by request. For the final graded repository, maintain the accepted ADR in `docs/adr/0003-semantic-cache-store.md` (and update any related links). The original `docs/adr/0000-template.md` remains untouched.

# ADR 0003 — Redis semantic cache and safe Chroma reindex cutover

Combines cache-store choice with the related proposed immutable-generation publish strategy. The former follows the assignment's Redis/PVC topology; the latter is a **design proposal requiring a real integration test**, not a feature already delivered by the starter. If you choose a simpler proven safe cutover, amend this ADR jointly.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-adr-0003-semantic-cache-store-md"></a>

## ADR 0003 — Redis semantic cache with safe exclusions and version-scoped invalidation


- **Status:** Proposed default: Redis
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
Assignment allows Redis or second Chroma collection but requires persistent Redis Deployment/PVC in the reference topology. Reusing an unrelated earlier answer is more dangerous than a cache miss.
### Decision
Choose Redis, persist with AOF on PVC. Cache eligible independent validated grounded answer + normalized question embedding, similarity score and index generation. Threshold from ConfigMap, select lowest threshold showing zero false hits in measured candidate sweep. Cache must exclude follow-up, abstention, out-of-scope, failed validation and sources not current. API loads current generation from Chroma registry and uses generation-prefixed cache keys; on generation change API purges/expires old-prefix entries, so **indexer needs no Redis network access**.
### Alternatives
Chroma second collection: convenient vectors but mixes read/write and index lifecycle; exact-key Redis only is not semantic; no cache fails rubric.
### Consequences
+ Shared among API replicas, datastore protection and strict NetworkPolicy. − Similarity scan can be O(N), bound collection size and TTL; cache thresholds require measured negative pairs. Test hit, false hit, reindex and Redis outage.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

<a id="merged-docs-adr-0005-safe-reindex-cutover-md"></a>

## safe-reindex design (consolidated in ADR 0003) — Immutable Chroma generations, Chroma registry pointer, cache namespace


- **Status:** Proposed for adoption at G2; not in starter
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
The starter's dummy writer deletes and recreates one collection, adequate for a **dummy-only development index** but unsafe for production reindex while 3 API readers are querying. In-place deletion can cause intermittent 404/empty retrieval and stale Redis answers. The rubric requires reindex without redeploy/downtime, and NetworkPolicy specifically wants Redis access only from API.
### Decision
For real indexing, write a **staging collection** `rahbar__g_<source-and-config-digest>` with full metadata; build and verify all chunks and model/dimension before publish. Maintain a small **control collection in Chroma** (e.g. `rahbar_registry`) whose metadata stores `active_collection`, `generation`. The writer switches this control metadata only after the new collection is validated (atomicity of this update MUST be tested with selected Chroma version). API resolves active collection from Chroma; readiness compares *same active collection* name/model/dimension; cache key includes `generation`. API automatically deletes/expires old-generation Redis keys when a different generation is observed, and excludes prior namespace immediately. Writer does **not** access Redis. Retain old collection for rollback; GC only after verified grace period. Weekly CronJob uses `concurrencyPolicy: Forbid`; operator avoids simultaneous manual Jobs.
### Compatibility
`CHROMA_COLLECTION=rahbar` serves as base name; `--dummy` still writes `rahbar` in G2 stub mode and can use a direct dummy development fallback. Real mode uses registry; make sure both API and indexer share policy. If Chroma metadata modify is not atomic/testable, stop and adopt a simpler demonstrated safe alternative with reviewed ADR update; don't claim perfect atomicity without proof.
### Consequences
+ No partial live corpus; version-aware cache expiry; Redis remains API-only as security policy requires. − Registry/control collection resolution adds complexity and a temporary storage overhead; concurrent manual jobs remain a risk without a robust lease. Test interrupted staging, switch under load, rollback, consumer using old pointer, and collection cleanup.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

