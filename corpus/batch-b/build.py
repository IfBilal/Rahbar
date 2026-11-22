#!/usr/bin/env python3
"""Build Batch B, the planted-problem document set for Assignment 03 (docs/a3-ragops/05 §11).

    python corpus/batch-b/build.py --out /tmp/batch-b-out
    python corpus/batch-b/build.py --out OUT --real-pdf corpus/raw/student-handbook-jun-2026.pdf \
                                   --real-html corpus/raw/grading-page.html

Writes   OUT/batch-b/        the 12 files delivered in the first Batch-B run
         OUT/late/batch-b/   B13, the older version that must arrive in a LATER run

Everything the group authored is committed under corpus/batch-b/src; the two exact
duplicates are byte copies of real Batch-A documents (never committed: third-party files),
and the corrupt PDF and the clubs PDF are generated here so nothing binary lives in Git.
See corpus/batch-b/README.md for what each file plants and what the pipeline must do.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "indexer" / "tests"))
from pdfmaker import text_pdf  # noqa: E402  (test helper that writes tiny PDFs, no extra dependency)

# planted name -> (source file in src/ or a generator key, description)
AUTHORED = {
    "library-borrowing-rules.md": "library-borrowing-rules.md",                       # B09 clean
    "library-lending-regulations.md": "library-lending-regulations.md",  # B03 near-dup
    "exam-schedule-policy-trunc.md": "exam-schedule-policy-trunc.md",                 # B05 truncated
    "untitled-notes.txt": "untitled-notes.txt",                                       # B06 no metadata
    "faculty-entrepreneurship-policy-2026.md": "faculty-entrepreneurship-policy-2026.md",  # B07
    "campus-parking-policy.md": "campus-parking-policy.md",                           # B08 injection
    "transport-routes-2026.html": "transport-routes-2026.html",                       # B11 clean
    "scholarship-faq.md": "scholarship-faq.md",                                       # B12 clean
}
LATE = "faculty-entrepreneurship-policy-2019.md"                                      # B13


def _lines(text: str, width: int = 88) -> list[str]:
    return [ln for para in text.split("\n") for ln in (textwrap.wrap(para, width) or [""])]


def _pdf_pages(blocks: list[list[str]]) -> list[list[tuple[float, float, str]]]:
    return [[(50.0, 60.0 + 16 * i, line) for i, line in enumerate(lines)] for lines in blocks]


CLUBS = [
    ["Student Clubs Guidelines", "Version 1.0", "",
     "TEST FIXTURE: fictional content written by the project group for Assignment 03.", "",
     *_lines("1. Forming a club. A group of at least ten enrolled students may form a club by "
             "submitting a constitution and the names of a faculty advisor and three office "
             "bearers to the student affairs office. The office approves a new club within "
             "two weeks if the constitution does not conflict with university rules.")],
    ["2. Funding. Every approved club receives a small grant at the start of each semester and "
     "may ask for more money for a named event by sending a budget to the student affairs "
     "office at least three weeks before the event.", "",
     *_lines("3. Events. A club that wishes to hold an event on campus books the venue through "
             "the student affairs office and informs the security office about the number of "
             "visitors expected. Events must end before ten in the evening."), "",
     *_lines("4. Annual report. Each club sends a short report of its activities and accounts "
             "to the student affairs office before the end of the spring semester. A club that "
             "does not send a report may lose its grant for the next year.")],
]
LAB_NOTICE = [
    ["Laboratory Safety Notice", "Version 2.0", "",
     *_lines("TEST FIXTURE: fictional content. Students must wear closed shoes in every "
             "laboratory and must not eat or drink near the equipment. Long hair must be tied "
             "back before a student works near a machine or a flame. Every accident, however "
             "small, must be reported to the laboratory assistant at once.")],
    [*_lines("Chemicals must be returned to the storage cabinet after use and labelled "
             "containers must never be reused for another substance. The laboratory is "
             "closed to students when no instructor or assistant is present.")],
]


def build(out: Path, real_pdf: Path | None = None, real_html: Path | None = None) -> dict[str, str]:
    """Write Batch B under `out` and return {planted id: path}. Missing real sources are
    reported, never silently replaced by something else."""
    first, late = out / "batch-b", out / "late" / "batch-b"
    first.mkdir(parents=True, exist_ok=True)
    late.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}
    ids = {"library-borrowing-rules.md": "B09", "library-lending-regulations.md": "B03",
           "exam-schedule-policy-trunc.md": "B05", "untitled-notes.txt": "B06",
           "faculty-entrepreneurship-policy-2026.md": "B07", "campus-parking-policy.md": "B08",
           "transport-routes-2026.html": "B11", "scholarship-faq.md": "B12"}
    for name, src in AUTHORED.items():
        shutil.copyfile(HERE / "src" / src, first / name)
        made[ids[name]] = str(first / name)
    text_pdf(first / "student-clubs-guidelines.pdf", _pdf_pages(CLUBS))                  # B10
    made["B10"] = str(first / "student-clubs-guidelines.pdf")
    good = text_pdf(out / "_lab-safety-full.pdf", _pdf_pages(LAB_NOTICE))               # B04 source
    raw = good.read_bytes()
    (first / "lab-safety-notice.pdf").write_bytes(raw[: int(len(raw) * 0.55)])           # cut off
    good.unlink()
    made["B04"] = str(first / "lab-safety-notice.pdf")
    if real_pdf and real_pdf.exists():                                                    # B01
        shutil.copyfile(real_pdf, first / "Student_Handbook_Copy.pdf")
        made["B01"] = str(first / "Student_Handbook_Copy.pdf")
    if real_html and real_html.exists():                                                  # B02
        shutil.copyfile(real_html, first / "grading-page-backup.html")
        made["B02"] = str(first / "grading-page-backup.html")
    shutil.copyfile(HERE / "late-arrivals" / LATE, late / LATE)                          # B13
    made["B13"] = str(late / LATE)
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Batch B.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--raw", type=Path, default=ROOT / "corpus" / "raw")
    ap.add_argument("--real-pdf", type=Path)
    ap.add_argument("--real-html", type=Path)
    args = ap.parse_args()
    pdf = args.real_pdf or args.raw / "student-handbook-jun-2026.pdf"
    html = args.real_html or args.raw / "grading-page.html"
    made = build(args.out, pdf, html)
    for key in sorted(made):
        print(f"{key}  {made[key]}")
    missing = [k for k in ("B01", "B02") if k not in made]
    if missing:
        print(f"WARNING: {', '.join(missing)} not built: the real Batch-A files were not found "
              f"({pdf}, {html}). Run `make fetch` first, or pass --real-pdf/--real-html.",
              file=sys.stderr)
        return 1
    print(f"\n13 files: 12 in {args.out}/batch-b, B13 (deliver LATER) in {args.out}/late/batch-b")
    return 0


if __name__ == "__main__":
    sys.exit(main())
