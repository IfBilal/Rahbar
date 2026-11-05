# Corpus

Source: **FAST-NUCES public website (nu.edu.pk)** · Documents: **9** (7 PDFs, 2 HTML pages) ·
Pages: **279 PDF pages** + 2 web pages · Indexed chunks: **532** (300/40 tokens)

Every file is public (no SLATE, Flex, NU Mail or anything behind a login). We commit
`corpus/sources.yaml` (what to fetch, with `doc_version` and `superseded`) and
`corpus/MANIFEST.md` (URL, size and SHA-256 of every file), never the documents.
`python corpus/fetch.py` downloads them one at a time with a pause between requests, and
`python corpus/fetch.py --verify` re-hashes them: **9 of 9 matched on 4 November 2026**
(`docs/evidence/corpus-pdffonts-and-pages.txt`). The indexer Job fetches the same list at
start-up and refuses to index bytes that differ from the committed manifest.

| Document | File | Pages | Version | Superseded |
| --- | --- | ---: | --- | --- |
| Undergraduate Academic Rules (Aug 2023) | `undergraduate-academic-rules-aug-2023.pdf` | 26 | 2023-08 | **yes** |
| Academic Rules Handbook (Jun 2026) | `academic-rules-handbook-jun-2026.pdf` | 58 | 2026-06 | no |
| Prospectus 2026: Academic Rules and Regulations | `prospectus-2026-academic-rules-and-regulations.pdf` | 5 | 2026 | no |
| Student Handbook (Jun 2026) | `student-handbook-jun-2026.pdf` | 64 | 2026-06 | no |
| Annual Report 2019-20 | `annual-report-2019-20.pdf` | 33 | 2019-20 | no |
| Annual Report 2023-24 | `annual-report-2023-24.pdf` | 85 | 2023-24 | no |
| Fee Structure page | `fee-structure-page.html` | web | 2026-27 | no |
| Grading page | `grading-page.html` | web | 2026 | no |
| Faculty Entrepreneurship and Technical Start-ups Policy | `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` | 8 | 2022-05 | no |

| # | Required property | Document(s) that provide it | Evidence or notes |
| --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | All nine above | 9 documents, 279 PDF pages plus two HTML pages; `pdfinfo` page counts in `docs/evidence/corpus-pdffonts-and-pages.txt`. |
| 2 | Two versions of one policy | Undergraduate Academic Rules **Aug 2023** (superseded) and Academic Rules Handbook **Jun 2026** (current); the 2026 Prospectus restates the same rules with different clause numbers | The 2026 handbook supersedes the 2023 rules. `corpus/sources.yaml` sets `superseded: true` on the 2023 file; the indexer copies `doc_version` and `superseded` onto every chunk, and the API filters `superseded == false` unless the question asks about an older version. The two editions genuinely disagree (table below), so a retriever without the filter quotes repealed rules. The two annual reports are editions over time, not a revision of one policy, so neither is marked superseded. |
| 3 | Scanned, image-only PDF | Faculty Entrepreneurship and Technical Start-ups Policy; also the 2023 Academic Rules | `pdffonts` lists **no fonts** for the entrepreneurship policy: no text layer at all, 0 extractable characters over 8 pages. The 2023 rules have 3 fonts but only **191** text characters over 26 pages, so their bodies are images too. The indexer OCRs every page with fewer than 40 letters or digits: pages 1–8 of the policy and pages 2–25 of the 2023 rules (job log `ocr_pages`). Loss is documented in `docs/PIPELINE.md`. |
| 4 | A table with real information | Annual Report 2023-24 (Faculty Summary by campus and rank), Annual Report 2019-20 (faculty and staff by campus), Fee Structure page (miscellaneous fees, refund timeline), Grading page and handbook clause 2.3 (grade points) | Example: Islamabad has **236** faculty in 2023-24 (19 professors, 14 associate professors, ...). Plain PDF text interleaves table columns with neighbouring text; the extractor re-emits detected tables as `cell \| cell` rows. Before/after in `docs/PIPELINE.md`. |
| 5 | Long definitions | Student Handbook and Academic Rules Handbook: **Policy on Generative AI Based Tools** (12 numbered sub-sections over about 16 pages, e.g. "Unacceptable Uses of Generative AI Tools" with numbered examples) | A fixed-size splitter cuts "Acceptable" and "Unacceptable" uses mid-list. The chunker splits on section, then paragraph, then sentence, so each sub-section stays whole or splits between sentences with overlap. |
| 6 | A deliberately absent topic | **Hostel accommodation**: rules, fees, application, curfew, visitors. We left out the prospectus's *Transport and Hostel Facilities* PDF on purpose. | A student would plausibly ask how to apply for a hostel room or what it costs. The corpus only says hostels *exist* ("In-Campus Hostel Facility is exclusively provided at Chiniot-Faisalabad and Peshawar Campuses", Student Handbook p. 45; campus descriptions in the annual reports). That makes it a hard near-miss: retrieval returns hostel-adjacent passages, and the system must still decline. Three must-abstain golden questions (a01–a03) ask about it. |
| 7 | Exact-term content | Clause numbers (**1.21** attendance, **5.4** academic warning, **4.25** withdrawal deadline), CGPA thresholds (**2.00**), grade points (**B- = 2.67**), fees (**Rs. 500** paper rechecking, **Rs. 12,000** per credit hour, refund **80%** up to day 15) | The same rule carries different numbers in different documents: attendance is clause **1.21** in the handbook and clause **1** in the prospectus, and the prospectus states an **80%** minimum where the handbook says 100% with up to 20% condonable. Embeddings blur these terms; see recall by question type in `docs/PIPELINE.md`. |

## The version pair: where 2023 and 2026 disagree

Read off both PDFs (the 2023 text via our OCR). These are what the version-sensitive golden
questions (v01–v03) test.

| Rule | 2023 rules (superseded) | 2026 handbook (current) |
| --- | --- | --- |
| 4.25 Deadline to withdraw from a course | "the last day of classes" | "the last day of the makeup week of every semester" |
| 1.6 Length of a regular semester | "15/16 weeks of teaching, and 2 weeks of final examinations" | "16 weeks of teaching, one makeup week and 2 weeks of final examinations" |
| 1.25 Degree requirement | "minimum of 130 credit hours" | clause now states the CGPA 2.00 graduation requirement |
| 5.8 Failed courses | "must repeat a course in which s/he gets an F grade, whenever that course is offered again" | "Any failed or missed course ... should become mandatory in the subsequent semester (if Offered)" |
| Chapters 9 and 10 | none | Policy on Retake Examination; Policy on Generative AI Based Tools |

## Other traps we noticed and kept
- The prospectus says "Minimum attendance requirement for Undergraduate degree programs are
  80%", while handbook clause 1.21 says 100% with up to 20% condonable. Both are current
  documents; an answer must cite which one it uses.
- The handbook PDFs were imposed from two-page spreads: every page also carries its
  neighbour's text at negative x coordinates, invisible but extractable. Our extractor
  keeps only what is inside the page box (`docs/PIPELINE.md`).
- The 2023 rules' contents page OCRs dot leaders as `cccsss...`; those lines survive
  cleaning as junk text (documented loss).
