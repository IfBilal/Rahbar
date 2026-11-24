# Data review: golden set, pairs, live queries (2026-11-24)

Checked by Claude Code at Taimoor's direction. This is NOT a human sign-off: Taimoor and/or Bilal must spot-check
at least 8 of the 11 synthetic golden questions (g020-g030) against the cited pages before the demo. The
`review.by` field says so explicitly.

Method: every PDF was extracted with `pdftotext -layout` page by page; HTML and Batch-B files are virtual page 1.
Two PDFs have no text layer (`undergraduate-academic-rules-aug-2023.pdf`, `faculty-entrepreneurship-and-technical-start-ups-policy.pdf`);
for those the cited page was rendered to an image and read by eye. Validator: `python -m ragops.suite.golden --validate eval/golden.draft.jsonl` -> VALID
(total 30, answerable 16, unanswerable 6, hard 8, human 19, synthetic reviewed 11).

## Golden questions

| id | doc / page | what was verified | verdict |
|---|---|---|---|
| g001 | academic-rules-handbook p24 | 5.4 "Minimum CGPA ... to avoid academic warning is 2.00" | ok |
| g002 | academic-rules-handbook p24 | 5.6 "3 consecutive semesters ... admission ... automatically closed" (also 3.28 on p17) | ok |
| g003 | academic-rules-handbook p28 | 6.6 "repeat a maximum of 2 courses" | ok |
| g004 | academic-rules-handbook p30 | 7.3 "SGPA of 4.00 with at least 30 credit hours ... Rector's List" (sentence continues on p31) | ok |
| g005 | academic-rules-handbook p35 | 8.15 DDC referral: "maximum punishment of 'F' ... in that course" | ok |
| g006 | academic-rules-handbook p45; student-handbook p53 | generative-AI section: generating an entire assignment and passing it off as own work is unacceptable (both pages) | ok |
| g007 | fee-structure-page.html | refund table "Upto 15th day ... 80% Fee Refund" | ok |
| g008 | faculty-entrepreneurship...policy.pdf p1 (scan, viewed) | 4.2 "full-time faculty member for more than 1 year"; retired by batch B | ok |
| g009 | annual-report-2023-24 p13 | Faculty Summary row Islamabad total 236 | ok |
| g010 | academic-rules-handbook p23 | 4.25 "last day of the makeup week" | ok |
| g011 | academic-rules-handbook p7 | 1.6 "16 weeks of teaching, one makeup week and 2 weeks of final examinations" | ok |
| g012 | undergraduate-academic-rules-aug-2023 p16 (scan, viewed) | 4.25 "Deadline to withdraw from a course is the last day of classes" | ok |
| g013 | academic-rules-handbook p10 | 1.21 "100% attendance" | ok |
| g014 | fee-structure-page.html | "Paper Rechecking Fee (Per Course/Lab) Rs. 500" | ok |
| g015 | academic-rules-handbook p12; grading-page.html | B- = 2.67 in both | ok |
| g016 | academic-rules-handbook p10 | 1.21 (injection prefix is in the question only; must_not strings fine) | ok |
| g017 | none | grepped all text: hostel appears only as a mention (handbook p45, annual reports); no fee or application rules | ok (absent) |
| g018 | none | no curfew text anywhere | ok (absent) |
| g019 | none | no guest/overnight text anywhere | ok (absent) |
| g020 | none | off-domain, nothing in corpus | ok |
| g021 | none | only "cafeteria/restaurant" mention (handbook p45), no recommendations | ok |
| g022 | none | no visa/Canada text (only a "Choose France" fair, annual p55) | ok |
| g023 | handbook p24 + p17 | 5.6 and 3.28; warning count becomes three | ok |
| g024 | handbook p10 | 1.21 "maximum of 20% ... condoned by the HoD for genuine reasons" | ok |
| g025 | handbook p23 + 2023 rules p16 | makeup week vs last day of classes | ok |
| g026 | fee-structure-page.html | "refundable security deposit of Rs 20,000" | ok |
| g027 | faculty-entrepreneurship-policy-2026.md | sec 2 "equity share of fifteen percent" | ok |
| g028 | campus-parking-policy.md | sec 2 car "five thousand rupees"; injected sentence is in the same clause | ok |
| g029 | library-borrowing-rules.md | sec 2 "fourteen days" for undergraduates | ok |
| g030 | library-borrowing-rules.md | table: course reserve book 20 rupees/day | ok |

No golden question was edited or rejected; no id changed. B10/B11/B12 topics (clubs, transport, scholarships) are not in the set.

## Changes

1. `eval/golden.draft.jsonl`: g020-g030 `review` filled (by, date 2026-11-24, verdict ok, notes with quote).
2. `eval/pairs.jsonl`: p05 b ("first fortnight" narrowed the meaning) -> "How much of my tuition do I get back if I drop out early?";
   p06 b ("top honour students" could mean the Dean's List) -> names the Rector's honours list and credits;
   p08 b "employees" was broader than faculty -> "faculty members". All 40 pairs `review` -> ok. Unrelated pairs: hard ones are same domain, different fact; easy ones are off-domain; no defects.
3. `eval/live_queries.jsonl`: l040-l042 (internship, job fair, campus recruitment) were labelled corpus-absent but ARE covered by the annual reports
   (2023-24 p26, p42, p54, p81-82). Replaced with truly absent topics (swimming pool membership fee, cafeteria menu, degree attestation). l003, l004, l007 reworded shorter / with typos
   so they are not near-copies of g011, g010, g014. All 42 `review` -> ok. Validator: 42 queries, 28 in / 14 out, no duplicates, none identical to a golden question, no warnings.
   In-domain queries were grepped for an answer in the corpus (e.g. l016 handbook p7, l018 p8, l021 p27, l024 p37, l025 annual p13, l026 fee page, l028 p30).

## Not verified / caveats

- No Tesseract in this environment, so the two scanned PDFs were not full-text searchable. The "absent" claims for g017-g022 and l040-l042 cover all text-layer documents, Batch B and HTML, but not the
  full 2023 rules scan or the faculty policy scan (only the cited pages were read). Low risk (academic rules, faculty policy), not proven.
- The 14 out-of-domain live queries on clubs/transport/scholarships were not checked against the clubs PDF (B10, generated at build time), only against batch-b/src and the README. Main-corpus annual
  reports do mention societies and scholarships in passing; that is expected (these are the Part E "gap" topics).
- Paraphrase/unrelated pair semantics were judged by reading, not by measured cosine.
- Origin of all pairs and live queries is still `synthetic` / `assistant-draft`; the plan asks members to rewrite a share in their own words.
