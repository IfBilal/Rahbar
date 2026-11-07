# Failure analysis

We broke five stages on purpose, one at a time, on the live stack (minikube, real corpus,
real embeddings), measured each, and restored it. Every break is a configuration change
run by `scripts/failure-experiments.sh`, so it can be repeated. Outputs are in
`docs/evidence/failures/`. The healthy reference is the shipped index (300/40, OCR on,
superseded filter on, top_k 5): **recall@3 0.906, recall@5 0.906**. These experiments ran
before the numeric table assist was added (shipped recall@5 is now 0.969; `docs/PIPELINE.md`),
so every row is compared with that 0.906 reference.

For A–E the API used the stub generator. All of them are retrieval-side breaks, and recall
is measured on what is retrieved, so the stub removes model noise and an hour of CPU time
per run. F needs the real model.

| Stage | What we broke | recall@5 | What the number hides |
| --- | --- | ---: | --- |
| (healthy) | none | 0.906 | |
| A · Extraction | OCR off | **0.781** | two whole documents vanish |
| B · Chunking | 100 tokens, no overlap | 0.938 | recall *rises*; context per passage collapses |
| C · Retrieval | `TOP_K=1` | **0.781** | exact terms 0.5; the injection question's evidence is gone |
| E · Source | superseded filter off | 0.906 | **unchanged**: the repealed clause ranks 2nd |
| F · Generation | temperature 1.2 | n/a | facts held (6/6 easy, 0/8 hard answered from context); only wording varied |

## Stage A · Extraction
- **What we broke:** `OCR_ENABLED=false` in the ConfigMap, then a re-index through the
  CronJob template. Pages without a text layer come back empty instead of going to Tesseract.
- **Symptom:** overall recall@5 fell from 0.906 to **0.781**. q08 (faculty start-up
  eligibility, answerable only from the scanned ORIC policy) and v03 (the 2023 withdrawal
  deadline, answerable only from the scanned 2023 rules) dropped to 0. The version type fell
  to 0.667. A user asking either question would get a confident "the documents do not cover
  this", and in v03's case the 2026 rule might be quoted for a 2023 question.
- **Diagnosis, as if we had not caused it:** the indexer's own per-document log line is
  decisive (`docs/evidence/failures/A-no-ocr-indexer.txt`, re-captured on 7 Nov from the
  same image and pinned corpus, both settings side by side):
  `"source": "faculty-entrepreneurship-and-technical-start-ups-policy.pdf", "ocr_pages": [],
  "empty_pages": [1, 2, 3, 4, 5, 6, 7, 8], "chunks": 0` and, for the 2023 rules,
  `"empty_pages": [2, ..., 25], "chunks": 1`. A healthy run says `"ocr_pages": [1, ..., 8],
  "chunks": 23`. In metrics: recall by source collapses to zero for exactly those two files
  while every born-digital document is unaffected. That pattern points at extraction, not
  retrieval. The retrieved lists in the request logs never contain those sources at all.
- **Remedy:** `OCR_ENABLED=true` (the default) and re-index; recall returned to 0.906
  (`restored-results.json`). Guard: the Job logs `ocr_pages` and `empty_pages` for every
  document, and a document that yields zero chunks is visible in the log.

## Stage B · Chunking
- **What we broke:** `CHUNK_SIZE=100`, `CHUNK_OVERLAP=0`, re-index.
- **Symptom:** chunk count nearly doubled (964 against 532), and recall@5 *rose* to
  **0.938**. Exact terms reached 1.0, because tiny chunks isolate single table rows such as
  `B- | 2.67` on the grading page. The damage is what each passage carries. With
  `MAX_CONTEXT_PASSAGES=3`, the model sees about 300 words instead of about 900. The
  five-item list of unacceptable uses of Generative AI, or a fee table with its header row,
  no longer fits in what the model receives, so answers become partial while every metric
  says retrieval is fine.
- **Diagnosis, as if we had not caused it:** the indexer log line `"chunking done",
  "chunks": 964, "chunk_size": 100, "chunk_overlap": 0, "amplification": 1.046` (twice the
  usual count). In the request log, the cited passages for list questions are fragments of
  one section that appear together in the top 5. The tell for this failure is answer
  completeness, not recall: recall@k at the *section* level cannot see it.
- **Why it did not break harder:** our chunker still splits on structure at 100 tokens:
  sections, then paragraphs, then sentences. So nothing is cut mid-sentence and every chunk
  keeps its section label. A pure fixed-window splitter would also cut clauses from their
  headings and mislabel sections. The structure-aware splitter is the guard.
- **Remedy:** restore 300/40 (the measured setting) and re-index.

## Stage C · Retrieval
- **What we broke:** `TOP_K=1` on the API only (`kubectl set env deployment/api TOP_K=1`,
  no re-index).
- **Symptom:** recall@5 fell to **0.781** (every k now equals 1). Exact terms fell to 0.5:
  e02's fee table ranks second behind the handbook's rechecking clause. The injection
  question i01 fell to 0: for "attendance requirement" the prospectus's clause 1 outranks
  handbook clause 1.21, so the one passage the model sees states 80%, not "100% with up to
  20% condonable". Questions whose best passage is unambiguous (ordinary, version) were
  unaffected, so averages hide this break.
- **Diagnosis, as if we had not caused it:** every request log line carries `"top_k": 1`
  and a single entry in `chunk_ids` and `scores`. `GET /readyz` is healthy and nothing
  errors, so the per-request log is where it shows. In metrics: recall@3 = recall@5 exactly.
- **Remedy:** `TOP_K` back to 5 (ConfigMap value); recall returned to 0.906.

The other stage C break, **`EMBED_MODEL` changed on the API only**, cannot happen silently
here: the API refuses readiness. We demonstrated that separately
(`docs/evidence/pin-mismatch.txt`, engineering note 6).

## Stage E · Source (outdated document)
- **What we broke:** `SUPERSEDED_FILTER=false` on the API: the 2023 rules become eligible
  for every question.
- **Symptom:** recall@5 **did not move** (0.906), because recall only asks whether the
  current section is present, and it still is. But the retrieved lists change
  (`docs/evidence/failures/E-retrieved-lists.txt`). For "What is the deadline to withdraw
  from a course?" the **repealed 2023 clause ranks second, 0.818 against the current
  clause's 0.838**, and lands in the three passages sent to the model. Clause 4.25 says
  "last day of classes" in 2023 and "last day of the makeup week" in 2026. For "How many
  weeks of teaching ...?" three of the top five are 2023 passages. A 0.02 margin is one
  rephrasing away from the model quoting the repealed rule as current.
- **Diagnosis, as if we had not caused it:** a user reports an answer that cites
  `undergraduate-academic-rules-aug-2023.pdf`. The request log's `chunk_ids` start with that
  file's id prefix for a question with no year in it. The fix is metadata, not prompting:
  the passages carry `superseded: true` and the query should exclude them.
- **Remedy:** restore the filter (`SUPERSEDED_FILTER-`); the 2023 passages disappear from
  all three lists. Guard: version-sensitive golden questions (v01–v03) and
  `api/tests/test_retrieval.py::test_superseded_chunks_only_come_back_when_asked_for`. The
  version gate in the eval only catches this if a question's *answer* changes, which is why
  we also check `expect` strings for v01/v02 in the final evaluation.

## Stage F · Generation
- **What we broke:** `TEMPERATURE=1.2` (shipped: 0.2) on the API, with the semantic cache
  off so every repeat reached the model. Each question was asked twice at each temperature
  with the real `llama3.2:3b`: three easy questions (q01, v01, e02) and four hard ones, the
  two must-abstain questions that clear the floor (a01, a02) and the two weakest answers
  (q09, e01). Output: `docs/evidence/failures/F-*.txt`.
- **Symptom (or the lack of one):**

  | Set | Temperature | Correct (`expect`) | Answered from context | Fallbacks | Distinct wordings per question |
  | --- | --- | ---: | ---: | ---: | --- |
  | easy (q01, v01, e02) | 0.2 | 6/6 | 6/6 | 0 | 2, 2, 2 |
  | easy | **1.2** | 6/6 | 6/6 | 0 | 2, 2, 2 |
  | hard (a01, a02, q09, e01) | 0.2 | 0/8 | **1/8** (q09 once) | 0 | 2, 2, 2, 1 |
  | hard | **1.2** | 0/8 | 0/8 | 0 | 2, 2, 2, 1 |

  Temperature 1.2 changed wording, not facts. Constrained decoding (`format` = the
  `Answer` schema) kept every reply valid JSON, the guard kept every citation real, and
  both must-abstain questions stayed declined. The instability that matters sits at the
  decision boundary and is **present at 0.2 as well**: with the faculty table not retrieved,
  q09 answered from context once and declined once at 0.2. Low temperature does not make a
  wrong judgement right; it only makes it repeatable.
- **Diagnosis, as if we had not caused it:** the same question answered differently
  minutes apart, with identical `chunk_ids` and `scores` in the two request log lines.
  Retrieval is deterministic, so a change with identical evidence is the generation stage.
  Check `TEMPERATURE` in the pod's environment (`kubectl exec ... env`) and the provider's
  request. If it had broken the schema we would see `rahbar_fallbacks_total{reason="invalid_output"}`
  rise and `generation rejected` log lines; at 1.2 it did not.
- **Remedy:** `TEMPERATURE` back to 0.2 (`kubectl set env deployment/api TEMPERATURE-`).
  The lesson is the case study's: temperature is not a fix for hallucination. For q09 the
  remedy is upstream, at stages A–C (getting the table row into the evidence).
- **A side finding:** repeating a question took 5–15 s instead of 60–140 s. Ollama reuses
  the KV cache of an identical prompt prefix, so most of the cost is prompt evaluation,
  which is why we cut the context to three passages and 300-token chunks.

## What the order of diagnosis taught us
Only F is the model's fault. In A, C and E the model did exactly what it was given, and in
B the metric looked better. Each time, the signal was in the indexer log or the per-request
`chunk_ids`/`scores` line, never in the model output. We now read those two first.
