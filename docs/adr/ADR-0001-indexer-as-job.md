> **Submission integration:** This standalone ADR is included at ZIP root by request. For the final graded repository, maintain the accepted ADR in `docs/adr/0001-indexer-as-job.md` (and update any related links). The original `docs/adr/0000-template.md` remains untouched.

# ADR 0001 — Indexer as a Kubernetes Job

**Assignment-mandated architectural decision.** This document is the authoritative location for the single-writer/read-only API rationale, controlled re-indexing and proof checklist. Keep its acceptance status separate from unverified runtime evidence.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-adr-0001-indexer-as-job-md"></a>

## ADR 0001 — One-shot indexing is separate from query-serving API


- **Status:** Accepted as assignment requirement
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
The assignment explicitly demands one writer and many readers. Three API replicas sharing a mutable vector store cannot safely each build the index during startup. Pod restarts and rollouts would recompute OCR/embeddings and race to write; readiness would either be falsely ready or hold pods unavailable for long rebuilds.
### Decision
Run `indexer/pipeline/run.py` in Kubernetes `Job` with `restartPolicy: OnFailure`, explicit `backoffLimit` and a weekly `CronJob` reusing image+args. The indexer is the only application workload permitted to add/delete Chroma data. API lifespan only initializes read adapters and validates active collection metadata; `/readyz` requires a nonempty compatible collection but never triggers indexing. Manual reindex from CronJob template, no API rebuild.
### Consequences
+ Reproducible, batch failure visible, does not multiply with replicas. + Can update corpus without API deploy. − Must make documents available in Job and coordinate safe publication. − Job may OOM and needs memory measurement. Rollback must keep prior active collection until new build verified.
### Proof
`kubectl get jobs,cronjobs -n rahbar`, indexer logs, API source read-only, reindex while API serves, no API pod restarts. Files/lines to insert after implementation: `MEASURE`.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

