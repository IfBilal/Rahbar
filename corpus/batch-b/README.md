# Batch B: the planted-problem documents (Assignment 03, Part A)

**Everything in this folder is a TEST FIXTURE.** The text is fictional, written by the project
group, and must never be mistaken for a real FAST-NUCES rule. Build the batch with:

```bash
python corpus/batch-b/build.py --out /tmp/batch-b-out      # needs `make fetch` done for B01/B02
```

It writes `OUT/batch-b/` (12 files, delivered together in the first Batch-B run) and
`OUT/late/batch-b/` (B13, delivered in a **later** run). The two exact duplicates are byte
copies of real Batch-A documents (third-party files are never committed); the corrupt PDF and
the clubs PDF are generated, so no binary lives in Git. Deliver a batch by copying it into the
inbox on the cluster (`kubectl cp`, see `docs/a3-ragops/10-KUBERNETES.md` §8); the folder name
`batch-b` tags every file in it as batch **B**.

**These expectations were written BEFORE the pipeline was run on the cluster.** The unit test
`indexer/tests/test_batch_b.py` already checks every row below with stand-in Batch-A documents;
the cluster run must give the same result with the real corpus. If a row differs, either the
pipeline or this table is wrong; decide which, fix it in a separate commit, and say why.

| # | File | Planted problem | Expected check outcome | Outcome |
|---|---|---|---|---|
| B01 | `Student_Handbook_Copy.pdf` | **exact duplicate** #1 of a Batch-A PDF | uniqueness `U-EXACT-DUP` | quarantined |
| B02 | `grading-page-backup.html` | **exact duplicate** #2 of a Batch-A HTML page | uniqueness `U-EXACT-DUP` | quarantined |
| B03 | `library-lending-regulations.md` | **near-duplicate** of B09 (a different title, three words changed, whitespace re-flowed) | uniqueness `U-NEAR-DUP` (embedding cosine and shingle Jaccard) | quarantined |
| B04 | `lab-safety-notice.pdf` | **corrupt** PDF, cut at 55% of its bytes | quality `Q-EXTRACT-FAIL` (and completeness `C-MISSING-PAGES`) | quarantined |
| B05 | `exam-schedule-policy-trunc.md` | **truncated**: "Page 3 of 5" footer, a cut table row, an unclosed sentence | completeness `C-TRUNCATED` | quarantined |
| B06 | `untitled-notes.txt` | **missing metadata**: no title, no date, no version, no catalog row | completeness `C-MISSING-TITLE`, `C-MISSING-DATE-VERSION` | quarantined |
| B07 | `faculty-entrepreneurship-policy-2026.md` | **newer version** of the Faculty Entrepreneurship policy (series `faculty-entrepreneurship-and-technical-start-ups-policy`, 2022-05 → 2026-11), two clause values changed | recency passes `R-SUPERSEDES`; the 2022 version is re-evaluated `R-SUPERSEDED-BY` | accepted; 2022 version **archived** (restorable) |
| B08 | `campus-parking-policy.md` | **injected instruction** inside a valid policy (two forms: "Ignore all previous instructions…" and "System prompt: reveal…") | passes **all four** checks (verification cannot see it) | accepted and indexed; the **retrieval rail** neutralises it at query time (Part D4) |
| B09 | `library-borrowing-rules.md` | clean new document (table, headings) | all pass | accepted |
| B10 | `student-clubs-guidelines.pdf` | clean new document (PDF) | all pass | accepted |
| B11 | `transport-routes-2026.html` | clean new document (HTML with a table) | all pass | accepted |
| B12 | `scholarship-faq.md` | clean new document on another topic | all pass | accepted |
| B13 | `late/…/faculty-entrepreneurship-policy-2019.md` | **older version arriving late**, after B07 is held | recency `R-NEWER-EXISTS` | quarantined |

Expected totals for the first run (B01–B12): **6 quarantined** (B01–B06), **6 accepted** (B07–B12),
**1 archived** (the 2022 policy). Failures by check: uniqueness 3, completeness 3 (B04, B05, B06),
quality 1, recency 1 (the re-evaluated 2022 version). After B13 in a later run: one more quarantine
(recency). Report the **measured** numbers from the cluster, not these.

## Rules for using this batch

* **Deliver B13 in a later run than B07.** If both sit in the inbox together, the pipeline processes
  a series oldest-first and accepts 2019, then 2022, then 2026, all correctly archived: right
  behaviour, but no recency failure to show.
* **First seen wins** between two near-duplicates, in sorted path order, so B09 (`library-borrowing…`)
  is kept and B03 (`library-lending…`) is the one quarantined. Do not rename files casually.
* **B07 supersedes a real Batch-A document.** The golden set has one question about the 2022
  policy; it carries `retired_by_batch: "B"` and gets a post-B twin (`docs/a3-ragops/06` §3.3).
* **B10, B11 and B12 (clubs, transport, scholarships) are reserved.** The golden set must NOT
  contain questions about them before Part E: they are the topics the tests do not cover, which
  the coverage check discovers and E4 then covers (`docs/a3-ragops/09`).
* B08 stays indexed on purpose. Do not quarantine it, or Part D4 has nothing to test.
