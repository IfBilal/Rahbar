# ADR 0002: Structure-aware chunking, sized by measurement

## Status
Accepted · 5 November 2026 · implemented in `indexer/pipeline/chunk.py`; settings measured
in `docs/PIPELINE.md`

## Context
Our documents are rule books. The handbook is chapters, then titled sub-sections, then
numbered clauses (`4.25 The deadline to withdraw ...`). The Student Handbook's Generative
AI policy runs to numbered lists over several pages. The fee and grade pages are tables. A
student's question usually maps to one sub-section, and the answer must be cited by that
sub-section. A fixed-size window ignores all of that: it cuts a clause from its heading,
splits "Acceptable" from "Unacceptable" uses mid-list, and produces citations whose
`section` is wherever the window happened to start. Chunk size also trades recall against
precision and prompt length, and on our CPU every extra token in the prompt costs seconds.

## Decision
- **Split by structure first**: sections (by heading path), then paragraphs (blank lines,
  clause numbers, list items, table boundaries), then sentences, then word windows only
  for a single sentence longer than the budget. Tables split between rows, never inside one.
- **The section label is the heading path** (`4. Registration > Withdrawal from a Course`).
  It is stored as `section` metadata, used for citations, and **prepended to the chunk
  text**, so a two-line clause still carries the words "Withdrawal from a Course" into its
  embedding.
- **Overlap stays inside a section** and is guaranteed to fit: units are capped at
  `size − overlap`, so the carried tail is never dropped (a bug our tests caught).
- **Unit: whitespace tokens.** Model-independent and easy to audit.
- **Size and overlap from the ConfigMap, chosen by measurement**: three settings, each a
  full re-index through the CronJob and the 19-question golden set. Shipped:
  @@MEASURE: shipped setting and its numbers@@.
- **Exact terms**: dense retrieval blurs clause numbers, so the API also asks Chroma for
  chunks that literally `$contains` a clause number or course code named in the question,
  and puts them first. Cheap, deterministic, and it uses the chunk text we already store.

## Options considered
- **Fixed-size windows** (the starter's 400/50 default applied blindly): simplest, but
  breaks the structure the citations depend on. We ran it as failure experiment B.
- **One chunk per page**: page breaks fall mid-clause in these PDFs, and a page holds
  several unrelated sub-sections, which dilutes the embedding.
- **One chunk per clause**: precise, but many clauses ("4.22 Fee is not refunded for a
  withdrawn course.") are too short to embed meaningfully alone.
- **BM25 hybrid retrieval** for exact terms: the textbook fix, but it needs a second index
  built and kept in step with each generation, inside API pods or a new service. The
  `$contains` assist covers clause numbers and codes with no new moving parts. Proper-noun
  failures turned out to be an embedding casing bug, not a missing lexical index (note 7).

## Consequences
- Easier: citations name real sub-sections; a definition stays in one piece or splits
  between sentences; re-tuning is a ConfigMap edit plus one Job.
- Harder: heading detection is heuristic (numbering, capitalisation, standalone short
  lines) and tuned to these documents. A new document style may need a new rule, and OCR'd
  headings are noisier.
- Storage amplification is about 1.08 at the shipped setting, a little above the overlap
  alone, because every chunk repeats its section label.
