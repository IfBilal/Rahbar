> **Status (5 November 2026):** measured results are in `docs/CORPUS.md` and `docs/evidence/corpus-pdffonts-and-pages.txt`. This guide is kept as the plan of record.

> **Required output file:** Implement the material in this *supplementary planning guide* and record the final, evidence-backed results in the instructor-provided `docs/CORPUS.md`. That original file is not included in this archive.

# Corpus sourcing, manifest, version control and seven properties

**Required:** at least six documents totaling 40+ pages, a genuine old/current policy pair, a scanned image-only PDF, a meaningful table, long definitions, a deliberately absent realistic topic, and exact terms such as codes/clauses/fees. These are the seven explicit assignment properties. Verify each candidate URL and hash in the team environment; sample URLs in the starter are suggestions, not proof of availability.

**Permissions:** use only public or owned sources; no SLATE/Flex/NU Mail, paywalled material, other people's private files or LLM-generated corpus. Commit `corpus/MANIFEST.md`, `corpus/sources.yaml`, fetch scripts and SHA-256 checksums, **not** third-party PDF bytes. Put actual PDF availability, pages, OCR state and old-version differences in the table after verifying them.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-corpus-md"></a>

## Corpus — selection protocol and seven required properties


**Status: candidate list from supplied `corpus/sources.example.yaml`; actual downloads, page counts, hashes, image-only property and version differences still require verification.** Do not submit this as completed evidence. Corpus choice: public FAST-NUCES website. Use `corpus/fetch.py`, not manual re-typed policy content. Commit manifest + script, not third-party PDFs.

### Planned source inventory
| Candidate source | Proposed doc_version | superseded | Required coverage | Verify |
|---|---|---|---|---|
| Undergraduate Academic Rules (Aug 2023) | `2023-08` | true | genuine old policy in version pair | **URL may fail**; download, compare revision |
| Academic Rules Handbook (Jun 2026) | `2026-06` | false | new pair, clauses, exact terms, long content | actual pages and clauses |
| Prospectus Academic Rules and Regulations 2026 | `2026` | false | alternate clause numbering | distinguish shortened summary from true revision |
| Student Handbook (Jun 2026) | `2026-06` | false | long Generative AI definitions | count pages, section extent |
| Annual Report 2019–20 | `2019-20` | false | campus/faculty tables | verify table extract |
| Annual Report 2023–24 | `2023-24` | false | period tables | verify availability |
| Fee Structure (HTML) | `2026-27` candidate | false | fees/threshold exact terms | capture live date/values from page |
| Grading (HTML) | `2026` candidate | false | tabular grade points | validate current content |
| Faculty Entrepreneurship and Technical Start-ups Policy | `2022-05` | false | potentially image-only scanned PDF | verify `pdffonts`, text layer and OCR |

The starter `sources.example.yaml` contains actual candidate URLs; **do not treat its filenames as proof of accessibility or exact page numbers.** Use final `corpus/sources.yaml` as the reviewed source list.

### Seven required properties (update evidence in final PR)
| # | Property | Candidate evidence | Required measured evidence | Status |
|---|---|---|---|---|
| 1 | >=6 documents / >=40 pages, public or owned | Academic Handbook + others | count **downloaded** files and PDF pages; URL+SHA for each | NOT VERIFIED |
| 2 | two revisions of same policy | 2023 Undergraduate Rules + 2026 Handbook | compare actual policy clauses; document which supersedes which | NOT VERIFIED |
| 3 | scanned image-only PDF | ORIC Faculty Entrepreneurship policy | `pdffonts`, pypdf extracted char count, OCR sample and loss | NOT VERIFIED |
| 4 | genuine table with meaning | annual report or fee/grading HTML | before-after extraction with preserved columns | NOT VERIFIED |
| 5 | long definitions across chunk limits | Student Handbook GenAI definitions | heading/pages and overlap section sample | NOT VERIFIED |
| 6 | deliberately absent realistic topic | hostel-room application procedure | exclude official detailed hostel document; 2 must-abstain questions | NOT VERIFIED |
| 7 | exact-term clauses/codes/thresholds | current academic rules + fee content | copy exact reference from verified document, not guessed | NOT VERIFIED |

### Acquisition procedure
```bash
cp corpus/sources.example.yaml corpus/sources.yaml
# Inspect/remove/add candidates, then:
make install
make fetch
python corpus/fetch.py --verify
# Also inspect metadata and page count locally; command examples:
pdffonts 'corpus/raw/<scanned-name>.pdf'
python - <<'PYCODE'
from pathlib import Path
from pypdf import PdfReader
for p in Path('corpus/raw').glob('*.pdf'):
    r=PdfReader(str(p))
    print(p.name, len(r.pages), sum(len(x.extract_text() or '') for x in r.pages))
PYCODE
```
Review `corpus/raw/_index.json`, source versions, and `corpus/MANIFEST.md` SHA-256. The provided downloader handles public source links and pauses requests; don't hammer the university site. Never use private Flex/SLATE/NU Mail, lecture slides, generated fake PDFs or paywalled content as the graded corpus.

### Version governance
A 2020 annual report is historical, not 'superseded' by a 2024 annual report in the same way a revised policy is. Prefer **document-specific applicability** over a global date rule. Verify that current-versus-2023 policy content actually differs. If older URL fails, replace with another authentic revision pair early and update the golden questions.

### Absent topic design
Example intentionally absent topic: **detailed hostel application/booking process**. Exclude the dedicated facilities policy/prospectus item. If another indexed handbook actually contains those details, the question is **not** a valid must-abstain label; change topic/question based on verified full corpus contents.

### Measured summary (4 November 2026)
- Downloaded document count: **9** (7 PDF, 2 HTML).
- Sum of PDF page counts: **279** (26 + 58 + 5 + 64 + 33 + 85 + 8), plus two HTML pages.
- Confirmed scanned files: **Faculty Entrepreneurship policy** (no fonts, pages 1–8 OCR'd) and the **2023 Academic Rules** (191 text characters over 26 pages, pages 2–25 OCR'd).
- Confirmed revision pair and clause diff: 2023 rules vs Jun 2026 handbook, e.g. clause 4.25 withdrawal deadline "last day of classes" → "last day of the makeup week" (`docs/CORPUS.md`).
- MANIFEST SHA verified: **9 of 9** match (`python corpus/fetch.py --verify`, `docs/evidence/corpus-pdffonts-and-pages.txt`).
- Exclusions and access rights: public nu.edu.pk pages only; the Transport and Hostel Facilities PDF is excluded on purpose (absent topic).

**G1 DoD:** 7 rows verified with file/page/example, >=6 documents/40 pages, true revision pair, no unauthorized documents. `CORPUS-PLAN.md` is not complete until measured values replace `MEASURE`.

---

<a id="merged-docs-specs-corpus-selection-md"></a>

## Implementation spec — Corpus Selection


**Owner:** A. **WBS:** T03,T07. **Primary paths:** `corpus/sources.yaml; corpus/MANIFEST.md; CORPUS-PLAN.md`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Input and boundary
Use verified public/owned university sources only. `corpus/sources.example.yaml` is a starting catalog, not guaranteed-valid truth. The starter fetch script writes hashes and `_index.json` for metadata, which `pipeline.run.discover()` consumes. Choose >=6 docs totaling >=40 actual PDF pages, one true same-policy revision pair, one genuine scanned PDF, a table, long definitions, deliberately absent topic and exact term.

### Algorithm
1. Copy candidate YAML to `corpus/sources.yaml`, remove impossible URLs, add fallback revision pair if needed. Validate `doc_version`, `superseded`; do not infer policy supremacy from a report year.
2. Download once at modest rate; SHA-256 verify; inspect count/page/text layer; record URL/method/source rights in MANIFEST.
3. Compare a specific changed clause in both revisions and write explicit new-vs-old evidence. Exclude selected absent-topic policy and verify no other document answers it.
4. Author >=15 golden questions with `(source,section)` manually from documents **before tuning**, not from retriever outputs.

### Negative tests and failure handling
Dead PDF link -> change corpus choice and re-verify; scan with hidden OCR layer -> find a real image-only PDF; generated policy -> reject; 40 pages only after counting PDFs; repeated sources with identical content -> still need true policy version pair; absent topic answered elsewhere -> change must-abstain question.

### Handoff
Give B verified fetch command, corpus acquisition strategy for Job, expected path `/corpus`, source SHA and version metadata. Give A's evaluator exact headings/filenames for golden matching. Check `CORPUS-PLAN.md` seven rows. No invented claims.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

