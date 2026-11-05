> **Status (5 November 2026):** measured results are in `docs/PIPELINE.md` and `docs/evidence/chunking/`. This guide is kept as the plan of record.

> **Required output file:** Implement the material in this *supplementary planning guide* and record the final, evidence-backed results in the instructor-provided `docs/PIPELINE.md`. That original file is not included in this archive.

# Indexer pipeline: extraction, clean, chunk, embed and store

**Required five stages:** extract → clean → structure-aware chunk → embed → store. The indexer alone writes Chroma, invoked as `python -m pipeline.run` in Job/CronJob, not from API startup. Document output and information loss at each stage, including one OCR gap, a mangled-table before/after example, at least three measured chunk size/overlap combinations and storage amplification (stored/original tokens).

**Version metadata:** each chunk *must* preserve `source`, `section`, 1-based `page`, `doc_version`, `superseded`. Store actual `EMBED_MODEL` and observed vector dimension in collection metadata. Match client and server `1.0.12` as pinned by the starter unless both intentionally migrate and test together.

## Data-loss checkpoints and concrete indexes

**Stage 1 — extraction.** For each input, record `source` and `doc_version` before reading text. Check every PDF page separately: empty/no text layer → OCR page (Tesseract with the language actually present), not silent drop. Retain raw page number and source; scan a table region before/after text extraction because OCR/table parsing can jumble columns. Detect corrupt files and either fail the Job or explicitly record excluded page loss; never quietly omit documents from the manifest.

**Stage 2 — cleaning.** Strip repeated running headers/footers only when objectively repeated; normalize whitespace and ligatures conservatively. Deliberately **do not** strip clause identifiers, numbered headings, tables, fee amounts or course codes. Preserve page-to-section mapping and document the rule plus a concrete exception.

**Stage 3 — chunking.** Split by document→section→paragraph→sentence under a *token* target (do not confuse characters with tokens), with bounded overlap inside a section. Deterministic ID should incorporate stable doc identity/version, section+page and a chunk sequence/hash; repeated indexing must not accidentally create duplicates. Record token counts and amplification `sum(chunk token lengths) / original clean document tokens`. Run at least three actual `(size,overlap)` settings; e.g. **candidates only** `(300,40)`, `(400,60)`, `(550,80)`—not a final choice without measured recall@5.

**Stage 4 — embedding.** Use the same exact `EMBED_MODEL` name and provider method at index time and query time. For local Ollama, batching `POST /api/embed` with `{ "model": "nomic-embed-text", "input": ["..."] }` is a possible adapter; verify real endpoint and response before hardcoding. Validate one finite vector per chunk, uniform actual dimension, logged batch timings and retry/timeouts. Fixture CI mode may use a distinct deterministic embedding model *only if index and query agree and fixture metrics remain meaningful*.

**Stage 5 — Chroma store.** Configure cosine distance explicitly. Store `ids`, `documents`, numeric vectors and primitive `metadatas` with `source`, `section`, `page`, `doc_version`, `superseded` for every chunk. Record actual model and dimension in collection metadata and keep active generation immutable during a reindex; write candidate generation → verify → publish pointer. Any collection registry transaction/atomicity assumption must be tested on the selected Chroma server version; otherwise pick a proven design and update ADR 0003.

### Required measurement register (populate only after experiments)

| Candidate | Chunk size (tokens) | Overlap (tokens) | Chunk count | Storage amplification | recall@5 overall | recall@5 exact | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| A | 300 | 40 | MEASURE | MEASURE | MEASURE | MEASURE | Pending |
| B | 400 | 60 | MEASURE | MEASURE | MEASURE | MEASURE | Pending |
| C | 550 | 80 | MEASURE | MEASURE | MEASURE | MEASURE | Pending |

Choose after measuring against frozen `eval/golden.yaml`. For every iteration record corpus manifest SHA, embeddings model, relevance floor, top-k and exact retrieval configuration; changing these simultaneously makes the chunking experiment uninterpretable.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-pipeline-md"></a>

## Indexing, retrieval and semantic-cache experiments


**Status: experimental protocol and decisions; real measurements pending.** The assignment requires measured scores. Never turn candidate values into claimed performance. `indexer/pipeline/run.py` already discovers the corpus and invokes five stages; their implementations are your work.

### Stage 1 — Extract
Input: each verified public PDF/HTML/MD/TXT and its `doc_version`/`superseded` from `_index.json` or front matter. Process PDF per page, retain one-based page IDs, detect no-text pages, invoke `pdf2image` + Tesseract OCR, set `Page.ocr=True`. For HTML, convert headings/table rows without concatenating unrelated cells; for MD respect heading structure. Log per-file extracted pages/chars/OCR page list and extraction exceptions.

| Evidence | Capture after running |
|---|---|
| PDF requiring OCR | `MEASURE` filename and page(s), pdffonts output |
| Before OCR / after OCR sample | `MEASURE` faithful short text snippets |
| Table before vs after cleanup | `MEASURE` one meaningful table and column alignment |
| Irrecoverable content | `MEASURE` missing/smudged table footnote or none, honestly |

### Stage 2 — Clean
Normalize multiple spaces, carriage returns, broken hyphenation only when safe; remove repeating page headers/footers with **measured recurrence**. Preserve numbered clauses, tables, code names, headings, punctuation, links, version labels and page markers. Explain at least one deliberately **unstripped** item, e.g. clause `1.21` or policy revision stamp, because those support exact-term retrieval and sources.

### Stage 3 — Structure-aware chunk
Split by section, then paragraph, then sentence under a **token** budget (document chosen token counting method); overlap within the same section. Never silently splice a section heading into an unrelated chunk. ID stable from document checksum/version/section/page/ordinal and content. Test long definition, short section, multi-page table, repeated heading and overlap.

**Predeclared experiments (not results):**
| Trial | Target tokens | Overlap tokens | measured recall@5 | stored chunks | stored/original token ratio |
|---|---:|---:|---|---|---|
| E1 | 300 | 40 | `MEASURE` | `MEASURE` | `MEASURE` |
| E2 | 400 | 60 | `MEASURE` | `MEASURE` | `MEASURE` |
| E3 | 550 | 80 | `MEASURE` | `MEASURE` | `MEASURE` |

**Definition:** storage amplification = *sum of token counts of all stored chunk texts / sum of original cleaned source tokens*, consistently defined. Ship the trial with strongest supported retrieval quality/acceptable cost, not automatically E2. Capture result JSON for each before choosing. Thresholds above are experiment candidates, not instructions to set production blindly.

### Stage 4 — Embed
Read `EMBED_MODEL` from the shared ConfigMap (`nomic-embed-text` suggested), call Ollama `/api/embed` in bounded batches, verify 1 vector per chunk, all finite numerics, uniform dimension; log actual dimension. Never mix vectors from different model IDs. The CI fixture may use a documented deterministic **fixture-only** embedding mode that both indexer and API share; never present those vectors as real semantic embeddings.

### Stage 5 — Store
Chroma client/server 1.0.12, HTTP, `hnsw:space=cosine` where supported. Store ID, text, vector, and metadata (source, section, page, doc_version, superseded). Collection metadata includes embed_model and observed dimension. Preferred publish method: write a new generation, verify, switch active pointer, then invalidate prior cache generation; see safe-reindex design (consolidated in ADR 0003). The live API is read-only.

### Query retrieval/evaluation
Embed question with same model, read active collection, filter `superseded:false` except confirmed historical intent, convert Chroma cosine distance to similarity (`1-distance`), return top-k. Evaluate recall@3 and @5 on the prewritten `eval/golden.yaml`, keyed by **matching the exact `(source, section)` pairs** specified there. One question with several relevant passages has recall = matched relevant / total relevant. Skip recall for must-abstain questions with no relevant references, don't count them as perfect retrieval.

### Semantic cache experiments (candidate sweep, not results)
| Similarity threshold | False hits on negative pairs | Correct hits | Decision |
|---:|---|---|---|
| 0.88 | `MEASURE` | `MEASURE` | candidate |
| 0.92 | `MEASURE` | `MEASURE` | candidate |
| 0.96 | `MEASURE` | `MEASURE` | candidate |

Select the **lowest threshold with zero false hits** on the tested real questions. Show at least one actual incorrect collision that eliminated a looser threshold; if none observed, report that honestly and expand negative-pair tests. Cache only validated independent grounded answers. Invalidate on reindex by changed generation namespace + active purge, or another proven method. Do not reuse old answer after reindex, even if text similar.

### Recorded results — to be filled
`eval/results.json`: `MEASURE` file path / commit, recall@3 and @5 by type, citation validity, abstention percentage, cache hit ratio, selected chunk settings, selected semantic threshold. Baseline must come from a **live, documented run**, and `eval/run_eval.py` must enforce >5 percentage-point recall drop, citation <95%, any abstention failure. Use `TESTING-EVALUATION.md` for formulas and exact gate checks.

---

<a id="merged-docs-specs-extraction-md"></a>

## Implementation spec — Extraction


**Owner:** A. **WBS:** T08. **Primary paths:** `indexer/pipeline/extract.py; clean.py; indexer/tests/*`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Interfaces and algorithm
`extract(path, doc_version, superseded) -> Document`, each `Page(source, page, text, ocr)` with one-based page. PDF text extraction via installed pypdf/pdfplumber; if a page has no usable text, render page with pdf2image and call pytesseract. Install system dependencies (`tesseract-ocr`, `poppler-utils`) in **indexer image**. Cache OCR per page only if output provenance is identical, and never fail an entire multi-document run silently.

For HTML, convert heading hierarchy and table rows to stable plain text while preserving cell associations (e.g. `Term | amount | applicability`). For MD, skip front matter in body but retain headings; for TXT produce a source/page 1. Use explicit UTF-8 and no executing content embedded in files. Log counts of OCR pages and errors as JSON stdout.

### Verification
Unit: PDF text layer; scanned page lacking text; intentionally malformed PDF raises contextual error; HTML table retains row/column labels; markdown front matter correctly excluded; 1-based page mapping; long footnote/line wraps. Compare short before-after table and OCR excerpts in PIPELINE with exact filename and page.

### Done
All chosen corpus types produce nonempty pages or explicitly documented losses; tests run; no secrets; downstream cleaner can consume Document without extra assumptions.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

<a id="merged-docs-specs-chunking-md"></a>

## Implementation spec — Chunking


**Owner:** A. **WBS:** T09,T22. **Primary paths:** `indexer/pipeline/clean.py; chunk.py; PIPELINE-IMPLEMENTATION.md`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Rule
Preserve structure and source alignment. Cleaner may normalize repeated headers/footers, excess whitespace and split hyphenation only with safeguards. Do **not** remove numbered clauses, headings, grade points, tables or policy version stamps. Chunk on section/paragraph/sentence boundaries, with overlap kept inside the same source/section and a token-count convention.

### Algorithm / invariants
Flatten content by section, maintain page map. If section fits budget, use one chunk; otherwise group paragraphs under size, and only split overlong paragraphs at sentences, then controlled tokens. Carry source/section/page/version/superseded into all chunks. Stable IDs include version and content position. Overlap must not create complete duplicated chunks; original and stored token counts logged. Empty-page/empty-section handling explicit.

### Experiments
Before shipping run three *measured* combinations 300/40, 400/60, 550/80 tokens (or documented alternatives) against **same frozen golden**. Record chunk count, storage amplification, recall@5 and chosen rationale. Verify retrieval for long definitions and exact clauses. A sensible default alone receives no score.

### Negative tests
Heading exactly at boundary, 2000-token definition, section spans page, table row spanning page, no OCR text, unicode Greek/text, `overlap>=size` -> reject, repeated document/chunks -> deterministic IDs.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

<a id="merged-docs-specs-embedding-storage-md"></a>

## Implementation spec — Embedding Storage


**Owner:** A. **WBS:** T10. **Primary paths:** `indexer/pipeline/embed.py; store.py; run.py; api/app/retrieval/chroma.py`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Source of truth
Both workloads read the **same ConfigMap `EMBED_MODEL`**, e.g. `nomic-embed-text`. Actual model vector dimension must be observed, included in collection metadata and verified in API readiness; never assume dimension across model variants. `chromadb-client==1.0.12` must talk to matching `chromadb/chroma:1.0.12` server.

### Implementation
Batch Ollama `/api/embed` requests with `{model, input: [texts...]}` and timeouts; check one vector per chunk, fixed dimension, finite values, error messages with no sensitive text. Store `ids`, `documents`, `embeddings`, `metadatas` with five required metadata keys. Chroma similarity query uses cosine distance and converts to `1-distance` on read.

### Safe reindex
Prefer **immutable per-generation collections** and a Chroma registry metadata pointer; publish only once all chunks + metadata are verified. This avoids in-place destructive replacement of the collection served to 3 API pods. Cache generation changes must prevent stale answers; no index writes happen in API startup. CronJob `concurrencyPolicy: Forbid`; manually disallow concurrent indexer Jobs and document residual race risk.

### CI fixture exception
A fixture-only deterministic text hashing/lexical embedding may be implemented behind a distinct `EMBED_MODEL=fixture-text-v1` that **both** CI query and indexer use; do not use random dummy hashes for semantic fixture recall and do not claim fixture embeddings model the real corpus. Or use a fully local lightweight deterministic model, if resource limits allow. Document chosen method.

### Tests
No vectors; mismatched vector lengths; partial API timeouts; model metadata mismatch; reindex restores previous index on failure; deleted document not in active generation; hash pin; cache epoch changes; repeat Job; Job exits 0 only when complete.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

