> **Submission integration:** This standalone ADR is included at ZIP root by request. For the final graded repository, maintain the accepted ADR in `docs/adr/0002-structure-aware-chunking.md` (and update any related links). The original `docs/adr/0000-template.md` remains untouched.

# ADR 0002 — Measured structure-aware chunking and exact-term policy

Consolidates the original chunking ADR and the *optional/deferred* hybrid lexical retrieval proposal. Dense Chroma retrieval is mandatory; lexical reranking must be driven by actual recall-by-type measurements and must not delay P0.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-adr-0002-structure-aware-chunking-md"></a>

## ADR 0002 — Choose chunks using measured retrieval, not a fixed 400-token guess


- **Status:** Proposed pending measured results
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
The real corpus contains numbered clauses, long definitions, image-derived text and tables. Blind fixed-size splits can sever definition meaning and erase cited sections.
### Decision
Keep section boundaries, then paragraphs, then sentences; track one-based page, overlap within a section, preserve original source/version metadata, deterministic IDs. Evaluate three candidate (size,overlap) token pairs 300/40, 400/60, 550/80 against a frozen golden set. Calculate stored/original token ratio; ship only after recall@5 and latency tradeoffs are recorded in PIPELINE.
### Alternatives
Fixed-size split: simpler but breaks clauses; one chunk per page: poor retrieval resolution; no overlap: lower footprint but loses cross-boundary context.
### Consequences
+ More meaningful citations and reproducible comparison. − OCR headings can be noisy, requiring explicit cleaning; overlap expands storage. **Final choice and numbers remain MEASURE**.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

<a id="merged-docs-adr-0006-exact-term-hybrid-retrieval-md"></a>

## optional hybrid design (consolidated in ADR 0002) — Optional measured lexical assist for clauses and codes


- **Status:** Deferred P1; not a rubric substitute
- **Date:** 2026-11-03 (documentation design draft; implementation sign-off pending)
- **Owners:** Developer A + Developer B
- **Sources:** Assignment 02, starter `STARTER.md`, actual Python contracts


### Context
Semantic dense embeddings blur exact code numbers and fee strings, while assignment intentionally tests exact terms. Chroma semantic retrieval is the mandatory base.
### Decision
First measure baseline recall@5 by type with dense top-k and correct superseded filter. If exact-term recall is poor, trial a lightweight lexical/BM25 re-rank over candidate passages or explicit exact-term match in metadata/text. Apply source-version filtering *before* ranking. Record old/new scores in PIPELINE; only merge if it improves the intended group without breaking citation correctness, resource limits or CI baseline.
### Consequences
+ Better clause accuracy when demonstrated. − Extra moving parts and potential scoring bias. A feature can be left deferred if P0 milestones and actual measurement are prioritized. Never present unimplemented hybrid retrieval as delivered.


### Review and follow-up
- [ ] Both developers affirm this decision against assignment requirements.
- [ ] Code and tests implement the decision (or update ADR status and replacement).
- [ ] Actual file:line citations and evidence attached in final engineering notes.

---

