# Indexing and retrieval pipeline

Everything here was measured on our stack (minikube with Calico, Ollama on the laptop,
`nomic-embed-text` for embeddings, `llama3.2:3b` for generation) unless it says otherwise.
Raw outputs are under `docs/evidence/`.

**How the documents reach the indexer Job.** They are *fetched at start-up*. The Job's init
container `fetch-corpus` runs `corpus/fetch.py` on the committed `corpus/sources.yaml`
into an `emptyDir` at `/work`. It then compares the fresh `MANIFEST.md` with the committed
one and **exits non-zero if any URL, size or SHA-256 differs**, so changed bytes never
reach the index without a reviewed commit, and the previous generation keeps serving
meanwhile. We chose fetching over baking the PDFs into the image because the image is
public on Docker Hub, and we do not redistribute the university's files. We chose it over
a PersistentVolume because a volume would need its own seeding step. The CI image also
carries our own fictional fixtures (`eval/fixtures`), which the `ci` overlay indexes
instead.

## Extraction

`indexer/pipeline/extract.py`, one `Page` per PDF page (1-based), HTML and Markdown as one
page each.

- **OCR.** A PDF page with fewer than 40 letters or digits in its text layer is rasterised
  at 300 dpi with poppler and read with Tesseract (`ocr=True` on the page). Two documents
  needed it. The **Faculty Entrepreneurship policy** has no fonts at all, so all 8 pages
  were OCR'd. The **2023 Academic Rules** have 191 characters of real text over 26 pages,
  so pages 2–25 were OCR'd (the Job log lists `ocr_pages` per document). On this laptop OCR
  costs about 46 s for the 8-page policy.
- **Tables.** pdfplumber finds ruled tables; each is re-emitted as one `cell | cell` row
  per line at its position on the page. HTML `<tr>` rows become the same rows; headings
  become Markdown `#` lines.
- **Off-page text.** The two handbooks were imposed from two-page spreads, so every page
  also carries its *neighbour's* text at negative x coordinates. That text is invisible
  but extractable. `pdftotext` clips it; pdfplumber does not. We keep only objects inside
  the page box.
- **Columns.** The prospectus page has three columns (a grade table and two text columns).
  Read line by line, each output line glued three unrelated sentences together. The
  extractor finds empty vertical strips between 15% and 85% of the page width and reads
  each column in turn, but never splits through a detected table.

**Before and after: a mangled table** (`docs/evidence/extraction-before-after.txt`,
Annual Report 2023-24, page 13):

```text
BEFORE (pdfplumber extract_text)
Campuses Prof. Assoc. Asst. Profs. Asst. Profs. Lect. Instr. Lab Total
Profs. Engrs.
(PhD) (non-PhD)
Islamabad 19 14 46 16 83 50 8 236

AFTER (extract.py::page_text)
Campuses | Prof. | Assoc. Profs. | Asst. Profs. | Asst. Profs. | Lect. | Instr. | Lab Engrs. | Total
(PhD) | (non-PhD)
Islamabad | 19 | 14 | 46 | 16 | 83 | 50 | 8 | 236
```

Before, the two-line headers ("Assoc." over "Profs.") are split across lines and the value
columns cannot be matched to them. After, each header is one cell and every row keeps its
column order. The handbook's page 13 is worse: without the page-box filter, the
neighbouring page's grade table ("A+ 4.00 C+ 2.33") is interleaved line by line with
clauses 2.8–2.11.

**What we could not recover.**
- The entrepreneurship policy's clause numbers sit in a narrow left margin; Tesseract reads
  that column as noise ("lel.", "ese", "G3.", "6d."), so its sections have headings but
  no reliable clause numbers.
- The 2023 rules' contents page OCRs dot leaders as `cccsss...`; those junk lines survive
  cleaning.
- The second header row of the faculty table ("(PhD)", "(non-PhD)") stays a separate row:
  the fact that it qualifies the two "Asst. Profs." columns is lost.
- Pages that are pure images (the logo cover pages) come back empty and are listed as
  `empty_pages` in the log rather than dropped silently.

## Cleaning

`indexer/pipeline/clean.py`. Rules, in order:

1. Unicode NFKC: ligatures (`ﬁ` → `fi`), full-width digits.
2. **Running headers and footers**: a line whose shape repeats on at least half the pages
   of a 3+ page document is dropped. Shape means digits and roman numerals masked, *and*
   the folio removed at either end, because the handbook prints "Undergraduate Academic
   Rules and Regulations 2026 7" on odd pages and "8 Undergraduate Academic Rules ..." on
   even ones; neither variant alone reaches 50%.
3. Bare page numbers (`7`, `IV`, `Page 13 of 85`).
4. **Contents pages**: on a page with 5+ lines shaped "title ... page-number", those lines go.
5. Dot leaders collapsed; words hyphenated across a line break re-joined
   (`regu-` + `lations`); runs of spaces and blank lines collapsed.

**Deliberately not stripped: clause numbers** at the start of a line (`1.21`, `4.25`,
`5.4`). They look exactly like list numbering, and a generic cleaner removes them. But
they are the exact terms students ask about ("what does clause 1.21 require?"), the
chunker uses them as paragraph boundaries, and the exact-term assist searches for them.
A test pins this: a clause line is kept even when it repeats on every page
(`indexer/tests/test_clean.py`).

## Chunking

`indexer/pipeline/chunk.py`. Unit: **whitespace tokens** (`len(text.split())`), roughly
0.75 of a BPE token count.

Structure first. Headings open sections: Markdown `#`, numbered titles ("5. Academic
Assessment"), ALL-CAPS titles, and short standalone title lines ("Attendance
Requirements"). A section's label is its heading path, e.g. `5. Academic Assessment >
Academic Warning/Probation`, and is stored as the chunk's `section`. Inside a section,
paragraphs break on blank lines, clause numbers, list items and table boundaries. A
paragraph cut by a page break continues if the next page starts in lower case. Paragraphs
are packed greedily up to `CHUNK_SIZE`; a longer one splits into sentences (tables into
rows), and a longer sentence into word windows. Neighbouring chunks of one section share
the last `CHUNK_OVERLAP` tokens; overlap never crosses a section boundary. Each chunk's text
starts with its section label, so a short clause still carries its heading into the
embedding and the prompt.

**Storage amplification** = tokens stored in all chunk texts / tokens in the cleaned
documents (the lecture's 150/120 example is 1.25). It counts overlap and the repeated
section labels.

### Three measured settings

Each row is a full re-index of the real corpus through the CronJob template
(`scripts/chunk-sweep.sh`), then the 19-question golden set through the Ingress. Embedding
is `nomic-embed-text` with the lowercase fix; `TOP_K=5`; exact-term assist on. Recall only
depends on retrieval, so these runs use the stub generator.

| Size (tokens) | Overlap (tokens) | recall@3 | recall@5 | Chunks stored | Storage amplification | Questions missed at k=5 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **300** | **40** | **0.906** | **0.906** | 532 | 1.085 | q09 (faculty table), e03 (½: grading page) |
| 400 | 60 | 0.875 | 0.906 | 486 | 1.078 | q09, e03 (½); q06 drops to rank 4–5 |
| 550 | 80 | 0.875 | 0.906 | 449 | 1.055 | q09, e03 (½); q06 drops to rank 4–5 |
| 400 | 60 | 0.719 | 0.719 | 486 | 1.078 | *before the lowercase fix*: q04, q06, q09, e02, e03 (½) |

Raw results: `docs/evidence/chunking/results-*.json` and the indexer's `chunking done`
log lines (`index-*.log`). Amplification is a little above the overlap fraction because
every chunk repeats its section label.

**Shipped: 300 tokens with 40 overlap** (`CHUNK_SIZE`/`CHUNK_OVERLAP` in the ConfigMap).
recall@5 ties at 0.906 across all three settings, so it cannot decide. **recall@3 does,
and it is the number that matters here**: the API sends only the best three passages to
the model (`MAX_CONTEXT_PASSAGES=3`). At 300/40, q06's "Unacceptable Uses of Generative AI
Tools" sub-section ranks in the top three; at 400 and 550 a broader chunk of "Generative
AI and Assessments" outranks it. Smaller chunks also shorten the prompt by about a quarter,
and prompt evaluation dominates latency on our CPU (about 12 tokens/s). The cost is 46
more chunks than 400/60 and slightly more amplification (1.085 against 1.078).
**Caveat:** 16 answerable questions; the recall@3 difference is one question, so the
decision rests as much on prompt length as on recall.

The two misses that remain are both **tables**: q09 asks for one cell (Islamabad, Total)
of a numeric grid that embeds as a bag of numbers, and e03's second source is a grade
table on the web page. That is where embeddings struggle most (`docs/ENGINEERING-NOTES.md`,
note 5).

## Embedding

- Model **`nomic-embed-text`** (Ollama), vector dimension **768** (observed, not assumed:
  the indexer logs it and writes it to the collection metadata).
- **Where the pin lives:** one ConfigMap key, `EMBED_MODEL` in `k8s/base/configmap.yaml`,
  read through `envFrom` by both the indexer Job and the API Deployment. A test checks that
  neither overrides it (`tests/test_manifests.py`).
- **How the API checks it:** the indexer stores `embed_model` and `dimension` on the
  generation collection and on the registry. `/readyz` compares them with the API's
  `EMBED_MODEL` on every probe, returns 503 with `embedding model mismatch: index ... was
  built with embed_model=... but this API has EMBED_MODEL=...`, and the pod stays 0/1 READY.
  Every query also compares the query vector's dimension with the index's
  (`api/app/retrieval/chroma.py::pin_problem`).
- **More than a name.** Both sides add nomic's task prefix (`search_document:` /
  `search_query:`) and **lowercase the text**. Ollama 0.17 does not lowercase input for
  this uncased model, so before the fix every capitalised word became `[UNK]`: "Rector"
  and "Dean", "Islamabad" and "Lahore", "BS" and "MS" embedded *identically* (cosine
  1.0000, `docs/evidence/cache-threshold-before-lowercase-fix.txt`). Both rules derive from
  the model name on both sides, and a test asserts the two sides prepare text identically
  (`tests/test_boundaries.py`).
- Batches of 32 per `POST /api/embed`, 3 attempts with backoff; the Job fails rather than
  store a missing, non-finite or mixed-dimension vector.

## Store

`indexer/pipeline/store.py`, Chroma 1.0.12 over HTTP. **532 chunks** at the shipped
setting. Each run writes a new generation collection `rahbar-g<UTC timestamp>-<digest>`,
checks the count, then points the registry collection `rahbar-registry` at it (ADR 0001).

| Level | Field | Type | Example |
| --- | --- | --- | --- |
| record | `id` | str, stable | `academic-rules-handbook-jun-2026-pdf-2026-06-0028-4dcbdc1e` (file, version, ordinal, content hash) |
| record | `document` | str | the chunk text, starting with its section label |
| record | `embedding` | 768 floats | `nomic-embed-text` |
| metadata | `source` | str | `academic-rules-handbook-jun-2026.pdf` |
| metadata | `section` | str | `4. Registration > Withdrawal from a Course` |
| metadata | `page` | int, 1-based | `22` (the page where the chunk's own text starts) |
| metadata | `doc_version` | str | `2026-06` |
| metadata | `superseded` | bool | `false` (the API filters on it) |
| collection | `embed_model`, `dimension` | str, int | `nomic-embed-text`, `768`: the pin the API checks |
| collection | `generation`, `chunk_size`, `chunk_overlap`, `hnsw:space` | | `20261104230304-a7b3528e`, `300`, `40`, `cosine` |
| registry | `active`, `previous`, `generation`, `embed_model`, `dimension` | | the pointer the API follows, and the one kept for rollback |

## Semantic cache

Redis (ADR 0003). We embedded paraphrase pairs (same answer) and near-miss pairs
(different answer) exactly as the API does, and counted hits per threshold
(`scripts/cache_threshold.py`, output in `docs/evidence/cache-threshold.txt`):

| Threshold | Paraphrase hits (of 6) | False hits (of 8 near-misses) | The false hit that rules it out |
| --- | ---: | ---: | --- |
| 0.85 | 6 | 6 | "What is the deadline to withdraw from a course?" vs "Under the older 2023 rules, what was the deadline ...?" (0.894): a current answer served for a historical question |
| 0.90 | 1 | 2 | Undergraduate vs **MS** minimum CGPA to avoid warning (0.912): 2.00 served for 2.50 |
| 0.92 | 1 | 1 | **Rector's** List vs **Dean's** List of Honors (0.936): SGPA 4.00 vs 3.50–3.99 |
| **0.95** | 0 | **0** | shipped: the lowest threshold with zero false hits |

The finding is uncomfortable but real. In this domain one word changes the answer, and
the embedding barely notices: the two closest near-misses (0.936, 0.912) score *higher*
than five of the six genuine paraphrases.
At 0.95 the cache serves repeated and near-verbatim questions only, which is what it can do
safely. Before the lowercase fix, the BS-vs-MS and Rector-vs-Dean pairs scored exactly
1.0000, so no threshold at all was safe.

## Relevance floor

Best retrieved similarity per golden question at 400/60 with the corrected embedding
(`docs/evidence/retrieval-scores-400-60.txt`). The answerable questions' relevant
passages scored as low as **0.646** (e01: clause 1.21, found by the exact-term assist).
The must-abstain questions' best passages scored **0.645** (a01 finds the fee page for a
hostel *fee* question), **0.631** and **0.573** (a03 finds "Student Facilities at Campuses",
the page that says hostels exist). The worst answerable and the best absent topic are
0.001 apart, so **no similarity threshold can separate them**. We ship
**`RELEVANCE_FLOOR=0.60`**: the highest floor that keeps every answerable question's
evidence above it with margin. It declines a03 before any model call, and declines the CI
fixture's hostel question (best 0.587) deterministically. a01 and a02 clear the floor and
must be declined by the model, the second layer, which the gate measures at 100%.

## Generation checks (5.3)

Shipped run: `eval/results.json` (real `llama3.2:3b`, temperature 0.2, through the Ingress,
cache flushed first). The two automated checks are gated:

- **Citation validity: 100%** (15 of 15 citations name a passage retrieved for that request).
- **Abstention correctness: 100%** (3 of 3). a03 is declined by the floor; the model itself
  declines a01 and a02, whose best passages clear it.

The other four checks we did by hand, reading every answer against its source:

| Question | Correct? | Uses the retrieved evidence? | Answers the question asked? | Unsupported claims? | Notes |
| --- | --- | --- | --- | --- | --- |
| q01 CGPA to avoid warning | yes (2.00) | yes, clause 5.4 | yes | none | |
| q02 three semesters below 2.00 | yes (admission closed) | yes | yes | none | |
| q03 summer repeats | yes (2 courses) | yes, 6.6 | yes | none | fell back in runs 1 and 3; fixed by the citation-matching change |
| q04 Rector's List | yes (SGPA 4.00, 30 credit hours) | yes, 7.3 | yes | none | missed entirely before the lowercase fix |
| q05 cheating to the DDC | yes (F in that course) | yes, 8.15 | yes | none | |
| q06 AI-written assignment | yes (not allowed) | yes, Unacceptable Uses | yes | none | |
| q07 refund in 15 days | yes (80%) | yes, refund table | yes | none | |
| q08 start-up eligibility | yes (more than 1 year) | yes, OCR'd policy | yes | none | depends on OCR (stage A) |
| q09 Islamabad faculty 2023-24 | **no** | campus description only | **no** | no number invented | the Faculty Summary table is never retrieved; the model describes the faculty instead of declining |
| v01 withdrawal deadline | yes (makeup week, 2026) | yes, 4.25 | yes | none | |
| v02 semester length | yes (16 weeks + makeup week) | yes | yes | none | fell back in run 3 |
| v03 2023 withdrawal deadline | yes (last day of classes, says "older rules") | yes, 2023 edition | yes | none | the explicit-history path |
| e01 clause 1.21 | **no** (declined) | clause retrieved, not used | no | none | a false abstention: safe, but unhelpful |
| e02 rechecking fee | yes (Rs. 500) | yes, fee table | yes | none | |
| e03 B- points | yes (2.67) | yes, prospectus table | yes | none | |
| i01 injection | yes (100%, 20% condonable) | yes | yes, ignores the instruction | none | |
| a01–a03 hostel | correctly declined | n/a | says the documents do not cover it | none | |

**14 of 16 answerable questions are correct** (the `expect` check agrees: 0.875), with **no
fabricated fact or citation** across the run. The two failures are the two safe directions:
q09 retrieves the wrong evidence and gives a vague but not invented answer; e01 has the
right evidence and declines. Neither is caught by the gate, which is why we read the answers.

## Evaluation method

`eval/run_eval.py` sends each golden question to the live API through the Ingress and
scores the `retrieved` list the API returns.

- **Matching**: a golden pair `(source, section)` is found in the top k when a retrieved
  passage has the **same source file** and a section label that **contains** the golden
  section, compared case-insensitively with curly quotes normalised. Labels are heading
  paths, so the golden `"Academic Warning/Probation"` matches the chunk label `"5. Academic
  Assessment > Academic Warning/Probation"`. Source must match exactly, so the 2023
  edition's "Withdrawal from a Course" does not count for a question about the 2026 one.
- **recall@k** per question = golden pairs found in the top k / golden pairs. Undefined
  (not 1.0) for must-abstain questions; averaged over answerable questions, overall and
  per type.
- **Citation validity** = citations whose `(source, section, page)` equals a passage in that
  response's `retrieved` / all citations, pooled over the run. An answer that claims
  grounding with no citation counts as one invalid citation.
- **Abstention correctness** = must-abstain questions with `answered_from_context: false` /
  must-abstain questions; must be 1.0.
- **Gate** (5.4): fail when recall@5 is more than 0.05 below `eval/baseline.json`,
  abstention < 1.0, or citation validity < 0.95. The boundary is exact: a drop of exactly
  0.05 passes (tested).
- `expect` substrings are reported (`expect_found_rate`), never gated: the gate measures
  the pipeline, not the model's wording.
