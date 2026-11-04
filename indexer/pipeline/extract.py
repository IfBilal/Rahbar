"""Stage 1: Extract. PDF (or HTML, or Markdown, or text) to text, page by page.

PDF pages are read with pdfplumber. A page whose text layer is empty (a scan) is
rasterised with poppler and read with Tesseract, and marked ocr=True. Tables found by
pdfplumber are re-emitted as `cell | cell` rows at their position on the page, because
the plain text layer interleaves table columns with neighbouring text (docs/PIPELINE.md
shows the before and after). HTML headings become Markdown `#` lines and HTML tables
become `cell | cell` rows, so the chunker sees one structure whatever the format.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .models import Document, Page

# A page with fewer letters/digits than this has no usable text layer: OCR it.
MIN_TEXT_CHARS = 40
OCR_DPI = 300


def extract(path: str, doc_version: str, superseded: bool, ocr: bool = True) -> Document:
    """Return the document's text page by page (1-based pages).

    `ocr=False` exists for failure experiment A (index the scan without OCR): scanned
    pages then come back empty and the loss is logged, never hidden.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        pages = _pdf_pages(p, ocr)
    elif suffix in (".html", ".htm"):
        pages = [(html_to_text(p.read_text(encoding="utf-8", errors="replace")), False)]
    elif suffix == ".md":
        pages = [(strip_front_matter(p.read_text(encoding="utf-8")), False)]
    elif suffix == ".txt":
        pages = [(p.read_text(encoding="utf-8", errors="replace"), False)]
    else:
        raise ValueError(f"unsupported document type: {p.name}")
    doc = Document(source=p.name, doc_version=doc_version, superseded=superseded)
    for number, (text, was_ocr) in enumerate(pages, start=1):
        doc.pages.append(Page(source=p.name, page=number, text=text, ocr=was_ocr))
    return doc


# --------------------------------------------------------------------------- PDF
def _pdf_pages(path: Path, ocr: bool) -> list[tuple[str, bool]]:
    import pdfplumber

    out: list[tuple[str, bool]] = []
    with pdfplumber.open(str(path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = page_text(page)
            if _usable(text):
                out.append((text, False))
            elif ocr:
                out.append((ocr_page(path, number), True))
            else:
                out.append(("", False))
    return out


def _usable(text: str) -> bool:
    return len(re.findall(r"[A-Za-z0-9]", text)) >= MIN_TEXT_CHARS


def page_text(page: Any) -> str:
    """Text of one pdfplumber page: lines outside tables plus rendered tables, in
    reading order, with a blank line wherever the vertical gap marks a new paragraph."""
    # The handbooks were imposed from two-page spreads: every page also carries its
    # neighbour's text at negative x, invisible but extractable. Keep what is on the page.
    page = page.within_bbox(page.bbox)
    splits = column_splits(page)
    if splits:
        x0, top, x1, bottom = page.bbox
        edges = [x0, *splits, x1]
        columns = [page.crop((a, top, b, bottom)) for a, b in zip(edges, edges[1:])]
        return "\n\n".join(_region_text(c) for c in columns)
    return _region_text(page)


def column_splits(page: Any) -> list[float]:
    """x positions of empty vertical strips that divide a multi-column page (the 2026
    prospectus has three columns). Reading such a page line by line glues unrelated
    sentences from neighbouring columns together."""
    chars = [c for c in page.chars if c["text"].strip()]
    if len(chars) < 200:
        return []
    x0, _, x1, _ = page.bbox
    width = int(x1 - x0)
    cover = [0] * (width + 2)
    for c in chars:
        for x in range(max(0, int(c["x0"] - x0)), min(width, int(c["x1"] - x0)) + 1):
            cover[x] += 1
    # A full-width table has empty strips between its columns too: never split one.
    spans = [(b[0] - x0, b[2] - x0) for b in
             (t.bbox for t in page.find_tables() if _real_table(t.extract()))]
    tolerance = max(2, int(len(chars) * 0.003))     # a title may run across the gutter
    splits: list[float] = []
    run: list[int] = []
    for x in range(int(width * 0.15), int(width * 0.85)):
        if cover[x] <= tolerance and not any(a < x < b for a, b in spans):
            run.append(x)
            continue
        if len(run) >= 8:
            splits.append(x0 + (run[0] + run[-1]) / 2)
        run = []
    edges = [x0, *splits, x1]
    shares = [sum(1 for c in chars if a <= c["x0"] < b) / len(chars)
              for a, b in zip(edges, edges[1:])]
    return splits if splits and min(shares) >= 0.12 else []


def _region_text(page: Any) -> str:
    tables = [t for t in page.find_tables() if _real_table(t.extract())]
    boxes = [t.bbox for t in tables]

    def outside(obj: dict) -> bool:
        x, top = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(b[0] <= x <= b[2] and b[1] <= top <= b[3] for b in boxes)

    region = page.filter(outside) if boxes else page
    items: list[tuple[float, float, str]] = [
        (ln["top"], ln["bottom"], ln["text"]) for ln in region.extract_text_lines()
    ]
    items += [(t.bbox[1], t.bbox[3], render_table(t.extract())) for t in tables]
    items.sort(key=lambda it: it[0])
    lines: list[str] = []
    prev_bottom: float | None = None
    heights = sorted(b - t for t, b, _ in items if b > t) or [10.0]
    gap = heights[len(heights) // 2] * 0.9    # about one empty line
    for top, bottom, text in items:
        if prev_bottom is not None and top - prev_bottom > gap:
            lines.append("")
        lines.append(text)
        prev_bottom = bottom
    return "\n".join(lines)


def _real_table(rows: list[list[str | None]]) -> bool:
    """pdfplumber also reports ruled boxes and one-cell frames; keep real grids only."""
    cells = [[c for c in row if c and c.strip()] for row in rows]
    return sum(1 for r in cells if len(r) >= 2) >= 2


def render_table(rows: list[list[str | None]]) -> str:
    """One row per line, non-empty cells joined with ' | '. Cell line breaks become
    spaces, so 'Assoc.\\nProfs.' stays one header cell instead of two words apart."""
    out = []
    for row in rows:
        cells = [" ".join(c.split()) for c in row if c and c.strip()]
        if cells:
            out.append(" | ".join(cells))
    return "\n".join(out)


def ocr_page(path: Path, number: int) -> str:
    """Rasterise one page and OCR it. One page at a time keeps the Job's memory flat."""
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(str(path), dpi=OCR_DPI, first_page=number, last_page=number)
    return "\n\n".join(pytesseract.image_to_string(img) for img in images)


# --------------------------------------------------------------------------- Markdown
def strip_front_matter(text: str) -> str:
    """Drop a leading '---' ... '---' block; run.discover() already read it."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


# --------------------------------------------------------------------------- HTML
_SKIP = {"script", "style", "head", "nav", "header", "footer", "noscript", "svg", "form",
         "button", "select", "iframe"}
_BLOCK = {"p", "div", "section", "article", "main", "ul", "ol", "li", "br", "table",
          "tbody", "thead", "dl", "dt", "dd", "blockquote", "pre", "hr"}


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.heading: int | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
            self.heading = int(tag[1])
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n")
            self.heading = None
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [c for c in self.row if c]
            if cells:
                self.out.append("\n" + " | ".join(cells))
            self.row = None
        elif tag == "table":
            self.out.append("\n\n")
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip or (self.row is not None and self.cell is None):
            return
        data = re.sub(r"\s+", " ", data)   # HTML whitespace collapses; only blocks break lines
        if self.cell is not None:
            self.cell.append(data)
        elif self.heading is not None:
            self.out.append(" ".join(data.split()))
        else:
            self.out.append(data)


def html_to_text(source: str) -> str:
    parser = _HtmlText()
    parser.feed(source)
    text = html.unescape("".join(parser.out)).replace("﻿", "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
