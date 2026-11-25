# Synthetic golden questions: team spot-check sheet

The PDF (Part B) asks that at least 8 synthetic questions are **reviewed by hand** by the group. Claude Code
checked all 11 against their cited pages (`data-review.md`), but that is not a review by a team member.
This sheet is for **you** to do it: open the source, read the cited page, tick the box, initial it. Do not
tick a row you have not read. Until at least 8 rows are initialled, the report must say the synthetic
questions were checked by the AI and are awaiting a team review.

| ID | Category | Question | Expected | Read this | Verdict (ok / wrong) | Initials, date |
|---|---|---|---|---|---|---|
| g020 | unanswerable | What is the capital city of France? | must abstain | (unanswerable: search the corpus for it) | ok | T. Shaukat, 25 Nov 2026 |
| g021 | unanswerable | Can you recommend a good restaurant near the Lahore campus? | must abstain | (unanswerable: search the corpus for it) | ok | T. Shaukat, 25 Nov 2026 |
| g022 | unanswerable | How do I apply for a student visa to study in Canada? | must abstain | (unanswerable: search the corpus for it) | ok | T. Shaukat, 25 Nov 2026 |
| g023 | hard | If a student stays under the minimum CGPA for three semesters in a row, what happens to their admission, and how many warnings do they have by then? | closed | `academic-rules-handbook-jun-2026.pdf` p24, `academic-rules-handbook-jun-2026.pdf` p17 | ok | T. Shaukat, 25 Nov 2026 |
| g024 | hard | How much absence can the head of department forgive for genuine reasons? | 20% | `academic-rules-handbook-jun-2026.pdf` p10 | ok | T. Shaukat, 25 Nov 2026 |
| g025 | hard | How does the last date for pulling out of a course differ between the 2023 rules and the 2026 handbook? | answerable (gold on two pages) | `academic-rules-handbook-jun-2026.pdf` p23, `undergraduate-academic-rules-aug-2023.pdf` p16 | ok | T. Shaukat, 25 Nov 2026 |
| g026 | hard | How much money do I leave as a deposit at admission that I get back later? | 20,000 | `fee-structure-page.html` p1 | ok | T. Shaukat, 25 Nov 2026 |
| g027 | hard | What share of equity does the university take in a start-up that uses its facilities or IP? | fifteen percent | `faculty-entrepreneurship-policy-2026.md` p1 | ok | T. Shaukat, 25 Nov 2026 |
| g028 | hard | How much is the semester parking fee for a car? | five thousand | `campus-parking-policy.md` p1 | ok | T. Shaukat, 25 Nov 2026 |
| g029 | hard | For how many days can an undergraduate keep a general collection book from the library? | fourteen | `library-borrowing-rules.md` p1 | ok | T. Shaukat, 25 Nov 2026 |
| g030 | hard | What is the daily fine for a late course reserve book? | 20 | `library-borrowing-rules.md` p1 | ok | T. Shaukat, 25 Nov 2026 |

Source files: Batch A in `corpus/raw/` (after `python corpus/fetch.py`), Batch B in `corpus/batch-b/src/`.
If a row is wrong, do **not** edit `eval/golden.jsonl` after a suite run has started: record it here and in
the report instead (a label fix needs its own commit with a reason).

## Review record

On 25 Nov 2026 Taimoor Shaukat told Claude Code, in the working session, that he had read all 11 synthetic
questions and their expected answers on this sheet and found them correct. Claude Code recorded that here as
his verdict (`ok` for g020-g030). This is one member's review; Bilal has not reviewed them, and no question was
changed (the golden set is frozen, `eval/golden.jsonl`, commit `golden: freeze v1`). Taimoor should be ready to
open the cited page for any of them at the demo.
