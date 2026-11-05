"""Stage 2: Clean. Remove artefacts without destroying structure.

Rules (docs/PIPELINE.md lists them with examples):
  1. Unicode NFKC, so ligatures like 'ﬁ' become 'fi' and full-width digits become digits.
  2. Running headers and footers: a line whose shape (digits and roman numerals masked)
     repeats on at least half the pages of a document of 3+ pages is dropped.
  3. Bare page numbers ('7', 'IV', 'Page 13 of 85') are dropped.
  4. Table-of-contents dot leaders ('Attendance........ 4') are collapsed.
  5. A word hyphenated across a line break is re-joined ('regu-' + 'lations').
  6. Runs of spaces and of blank lines are collapsed.
Deliberately NOT stripped: clause numbers at the start of a line ('1.21', '5.4'). They
look like list numbering, but they are the exact terms students ask about, and the
chunker uses them as paragraph boundaries. Headings, table rows, fees and years stay too.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import Document, Page

_ROMAN = re.compile(r"^[ivxlc]+$")
_PAGE_NUMBER = re.compile(r"^(page\s+)?(\d{1,3}|[ivxlc]{1,6})(\s+of\s+\d{1,3})?$", re.I)
_LEADER = re.compile(r"\s*\.{4,}\s*")
_HYPHEN = re.compile(r"([a-z])-\n([a-z])")
_CLAUSE = re.compile(r"^\d{1,2}\.\d{1,2}\b")     # never stripped, even when repeated
# A contents entry: an optional chapter number, a title with no digits, a page number.
_TOC_LINE = re.compile(r"^(?:[\dIVX]{1,4}[.\-\s]+)?[A-Za-z][^\d|]{2,90}?(?:\.{3,}\s*|\s)\d{1,3}$")
_TOC_MIN = 5   # this many entries on one page make it a contents page


def line_shape(line: str) -> str:
    """Mask numbers so 'Rules 2026   7' and 'Rules 2026   8' compare equal."""
    words = ["#" if _ROMAN.match(w) else w for w in re.sub(r"\d+", "#", line.lower()).split()]
    # A folio sits left on even pages and right on odd ones: ignore it at either end.
    while len(words) > 1 and words[0] == "#":
        words.pop(0)
    while len(words) > 1 and words[-1] == "#":
        words.pop()
    return " ".join(words)


def repeating_lines(pages: list[str], min_share: float = 0.5) -> set[str]:
    """Shapes of lines that occur on at least `min_share` of the pages."""
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for text in pages:
        counts.update({line_shape(ln) for ln in text.splitlines() if ln.strip()})
    need = max(3, int(len(pages) * min_share + 0.999))
    return {shape for shape, n in counts.items() if n >= need and shape != "#"}


def clean_text(text: str, drop: set[str]) -> str:
    out = []
    toc = sum(1 for raw in text.splitlines() if _TOC_LINE.match(" ".join(raw.split())))
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line and not _CLAUSE.match(line) and (line_shape(line) in drop
                                                 or _PAGE_NUMBER.match(line)):
            continue
        if toc >= _TOC_MIN and _TOC_LINE.match(line):
            continue                     # a contents page: 'Academic Year ..... 1'
        line = _LEADER.sub(" ", line)
        out.append(line)
    joined = _HYPHEN.sub(r"\1\2", "\n".join(out))
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    texts = [unicodedata.normalize("NFKC", p.text) for p in doc.pages]
    drop = repeating_lines(texts)
    return Document(
        source=doc.source,
        doc_version=doc.doc_version,
        superseded=doc.superseded,
        pages=[Page(source=p.source, page=p.page, text=clean_text(t, drop), ocr=p.ocr)
               for p, t in zip(doc.pages, texts)],
    )
