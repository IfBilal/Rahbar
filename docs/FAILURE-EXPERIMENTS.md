> **Status (5 November 2026):** executed; results are in `docs/FAILURE-ANALYSIS.md` and `docs/evidence/failures/`. This guide is kept as the plan of record.

> **Required output file:** Implement the material in this *supplementary planning guide* and record the final, evidence-backed results in the instructor-provided `docs/FAILURE-ANALYSIS.md`. That original file is not included in this archive.

# Required four controlled RAG fault experiments

The rubric requires **four** deliberately induced failures among extraction (A), chunking (B), retrieval (C), prompting (D), source freshness (E), generation (F). Perform experiments one at a time in a scratch/dev collection, record observed symptom, diagnosis, metric/log, remediation and recovery. The following experiments are **unexecuted templates**, not fictitious findings. Do not corrupt the only known-good index for screenshots.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-failure-analysis-md"></a>

## Failure analysis — controlled experimental worksheet


**Required:** cause a failure in **at least four of six** stages, **one at a time**, capture measured symptom, diagnostic signal/command, correction and restored pass. This document initially lists experiment designs; results are not yet executed. Do not submit speculative observations as a completed failure report.

### Stage A — extraction, omit OCR (planned experiment)
- **Controlled break:** on a scratch/dev index, disable OCR for the confirmed image-only PDF, do not overwrite a working production index.
- **Predicted symptom (not observed yet):** empty scanned passages and poor answers to scan-only questions.
- **How we would diagnose without causing it:** compare extracted character counts per page, `Page.ocr`, raw PDF text and OCR logs; relevant source absent from retrieved chunks.
- **Signal to capture:** `MEASURE` page count, text chars before/after, recall@5 for scan question, index Job log line.
- **Remedy:** restore `extract.py` OCR path; reindex; prove correct source retrieved.

### Stage B — chunking, no overlap (planned experiment)
- **Controlled break:** run 100-token fixed-size chunks with zero overlap into a **separate** scratch generation.
- **Predicted symptom:** cross-paragraph definitions split; multiple chunks needed to answer.
- **Diagnosis without knowing cause:** inspect chunk boundary examples and recall by type; document section/answer span split across chunks.
- **Capture:** `MEASURE` recall@5 diff, chunk count, exact chunk IDs and remedy result.
- **Remedy:** reinstate structure-aware chunking; select measured size/overlap.

### Stage C — retrieval top_k=1 or pin mismatch (planned experiment)
- **Controlled break:** set TOP_K to 1 for one test OR change `EMBED_MODEL` on API only in a dev overlay; restart and observe.
- **Predicted symptom:** missing evidence at top-1 or `/readyz` 503 for mismatch (should **not** serve garbage).
- **Diagnosis without knowing cause:** `kubectl logs deployment/api -n rahbar`, pin metadata, retrieval JSON scores and Kubernetes readiness events.
- **Capture:** `MEASURE` commands, logs, top_k and exact mismatch; confirm restoration and baseline.
- **Remedy:** restore k and consistent embedding pin; redeploy only after real reindex if model changed.

### Stage D — prompting, remove evidence rule (optional alternative)
- **Controlled break:** in disposable test variant remove `use ONLY evidence` instruction, never expose to student users.
- **Predicted symptom:** uncited claims or answer beyond retrieval.
- **Diagnosis:** inspect prompt template version, citation validation/fallback metrics; compare with golden expected.
- **Capture/remedy:** `MEASURE` actual bad response if safely reproducible; restore rules, schema+source guard.

### Stage E — source version, remove superseded filter (planned experiment)
- **Controlled break:** query both policy revisions without `superseded:false` filter in a dev test.
- **Predicted symptom:** old policy wins top-k and is cited as current.
- **Diagnosis without knowing cause:** log retrieved IDs, `doc_version` and `superseded`; compare canonical current text.
- **Capture:** `MEASURE` source/section/year, retrieved ranking, old-vs-new answer, fixed result.
- **Remedy:** reinstate metadata filter, add version-sensitive golden regression.

### Stage F — generation, temperature 1.2 (optional alternative)
- **Controlled break:** in disposable dev test set temp=1.2; capture variation and schema failure counts.
- **Diagnosis:** model configuration log, JSON validation retries, unsupported claims and provider output.
- **Remedy:** return to a deliberate 0–0.3 temperature and keep Pydantic guard; do not claim low temperature cures hallucinations.

### Execution protocol
Before each fault: save baseline metrics and active generation, ensure dev isolation; inject *one* fault; rerun selected golden; collect timestamped command/log/metric/screenshots; restore code/config and reindex where required; rerun healthy regression; open PR with actual before/after findings. Replace `MEASURE` and predicted symptom labels only with **observed** evidence. Also include your hardest unrelated >1h incident in `ENGINEERING-NOTES.md` Question 7.

---

<a id="merged-docs-templates-incident-template-md"></a>

## Incident [ID] — title


- **Date/time PKT, environment, commit:** TO FILL
- **Symptoms and user-facing impact:** TO FILL
- **Actual command/log/metric:** TO FILL (redact secrets)
- **First hypothesis, why wrong:** TO FILL
- **Root cause / exact code line:** TO FILL
- **Safe containment and repair command:** TO FILL
- **Regression test and observed result:** TO FILL
- **Time consumed (>1 hour if used in engineering Q7):** TO FILL
- **Follow-up owner/task:** TO FILL

Never invent an incident. Link a real >1 hour incident from `ENGINEERING-NOTES-GUIDE.md` Q7.

---

