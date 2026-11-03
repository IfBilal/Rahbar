> **Submission integration:** This standalone ADR is included at ZIP root by request. For the final graded repository, maintain the accepted ADR in `docs/adr/0004-llm-provider-and-data-governance.md` (and update any related links). The original `docs/adr/0000-template.md` remains untouched.

# ADR 0004 — Provider, data governance and readiness pin

Combines provider and public-corpus policies with the mandatory separation of readiness vs liveness and embedding-model compatibility. Internal reasoning must never be sent to clients; no answer may claim more evidence than the current retrieved passages support.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-adr-0004-llm-provider-and-data-governance-md"></a>

## ADR 0004 — Pluggable low-temperature schema-enforced model and public corpus


- **Status:** Proposed default: Ollama on host
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
Need low-memory cluster, truthful citations and prompt-injection resistance. Public FAST-NUCES PDF content can contain obsolete policy; model output has no implicit authority.
### Decision
Keep `LLMProvider.generate` contract; support `ollama-host` fully with 0.2 temperature (within 0..0.3), JSON schema mode and strict Pydantic validation. Hosted provider remains optional future adapter behind same Protocol and Kubernetes Secret. Embedding pin remains a **separate** ConfigMap key shared by writer/reader. All retrieved content is untrusted data; no private SLATE/Flex data or third-party PDF bytes committed. Retry once then safe fallback; only return citations matching retrieved chunks; strip `reasoning`.
### Consequences
+ No LLM weights needed in minikube, deterministic-ish structured output and provider swap. − Ollama host requires network bind + egress; generating answer can still hallucinate, necessitating evidence checks and abstention. Hosted fallback requires token/Secret and updated network policy.
### Proof
Contract tests, poisoned chunk test, malformed JSON fallback, no secret in Git and live model answer with valid citations.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

<a id="merged-docs-adr-0007-readiness-embedding-pin-md"></a>

## readiness design (consolidated in ADR 0004) — Dependency-aware readiness and dependency-free liveness


- **Status:** Accepted as assignment requirement
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
An incompatible embedding model causes silent nonsense; Chroma/Redis outage makes an API unfit for traffic but does not mean its process is crashed. Kubernetes needs separate failure semantics.
### Decision
`/healthz` pure process check; startupProbe checks `/healthz` with generous threshold; livenessProbe uses same shallow endpoint; `/readyz` checks active Chroma reachable/non-empty, collection metadata embed_model == `EMBED_MODEL`, observed vector dim compatible with query embedder, and Redis reachable. On any failure return 503 naming dependency without secrets. HPA CPU must have requests.cpu; API Deployment rolling maxUnavailable:0/maxSurge:1.
### Consequences
+ Pod removed from Service without restart storm; incompatible index never silently served. − API can be unavailable while Redis is down (required behavior); readiness checks must be cheap and timed out. Test Chroma 90-second slowdown, Redis failure, initial empty collection and ConfigMap-only pin change.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

<a id="merged-docs-adr-0000-template-md"></a>

## ADR NNNN: Title in a few words


Copy this file to `0001-indexer-as-job.md` and so on. Keep each ADR to about a page.

### Status
Accepted · date

### Context
What forced a decision. The constraints, in your own words.

### Decision
What you chose.

### Options considered
What else you could have done, and why you did not.

### Consequences
What this makes easier, what it makes harder, and what you would watch for.

---

