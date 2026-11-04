"""Stage 3: Chunk. Structure-aware, with overlap.

Unit: a token here is a whitespace-separated word (`len(text.split())`). It is
model-independent and easy to audit; a BPE tokenizer typically counts ~1.3x more.

Algorithm (docs/adr/0002-structure-aware-chunking.md):
  1. Walk the cleaned pages line by line and detect headings. Headings open sections;
     a section's label is its heading path, e.g. '5. Academic Assessment > Academic
     Warning/Probation'. Paragraphs break on blank lines, on clause numbers ('1.21 ...'),
     on list items ('a)') and around tables. A paragraph cut by a page break continues
     when the next page starts in lower case.
  2. Inside one section, paragraphs are packed greedily up to `size` tokens. A paragraph
     longer than `size` is split into sentences (table rows for tables), and a sentence
     longer than `size` into word windows: the 'sections, then paragraphs, then
     sentences' order of the case study.
  3. Consecutive chunks of the same section share the last `overlap` tokens. Overlap
     never crosses a section boundary, so no chunk mixes two sections' text.
Every chunk text starts with its section label, so a short clause still carries the
heading that gives it meaning when it is embedded and when it is shown to the model.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import Chunk, Document

_MD_HEAD = re.compile(r"^(#{1,6})\s+(.+)$")
# '5. Academic Assessment', '10. Policy on Generative', 'XII.Policy on ...', 'IV - MIGRATION'
_NUM_HEAD = re.compile(r"^(?:\d{1,2}|[IVX]{1,5})\s*[.)\-–]\s*([A-Z].{1,80})$")
_CLAUSE = re.compile(r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})?\.?\s")      # '1.21 Students ...'
_ITEM = re.compile(r"^(?:[a-z]\)|\([a-z]\)|[ivx]+\)|\d{1,2}\)|[•▪●\-*]\s)")    # 'a) ...', '• ...'
_SENTENCE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9“\"(])")
_END = re.compile(r"[.,;:!?)]$")
_MAX_LABEL = 160


@dataclass
class _Para:
    page: int
    text: str


@dataclass
class _Section:
    label: str
    paras: list[_Para]


def tokens(text: str) -> int:
    return len(text.split())


def is_heading(line: str, standalone: bool) -> tuple[int, str] | None:
    """Return (level, title) when `line` is a heading. `standalone` means the line is a
    paragraph on its own (blank line or page edge before and after it)."""
    line = line.strip()
    if not line or "|" in line or len(line) > 90:
        return None
    m = _MD_HEAD.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    if _CLAUSE.match(line) or _ITEM.match(line) or _END.search(line):
        return None
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 3 or not line[0].isalnum():
        return None
    words = line.split()
    if _NUM_HEAD.match(line) and len(words) <= 10:
        long_words = [w for w in words[1:] if len(w) > 3]
        if not long_words or sum(w[0].isupper() for w in long_words) / len(long_words) > 0.5:
            return 1, line
    if line.isupper() and len(words) <= 10 and len(letters) >= 0.6 * len(line.replace(" ", "")):
        return 1, line
    if standalone and len(words) <= 10 and line[0].isupper():
        if sum(c.isdigit() for c in line) <= 4:
            return 2, line
    return None


def _paragraphs(doc: Document) -> list[tuple[int, str] | _Para]:
    """Flatten pages into a stream of headings (level, title) and paragraphs."""
    stream: list[tuple[int, str] | _Para] = []
    current: _Para | None = None

    def flush() -> None:
        nonlocal current
        if current and current.text.strip():
            stream.append(current)
        current = None

    for page in doc.pages:
        lines = page.text.splitlines()
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                flush()
                continue
            before = i == 0 or not lines[i - 1].strip()
            after = i == len(lines) - 1 or not lines[i + 1].strip()
            if i == 0 and current is not None and line[0].islower():
                current.text += " " + line           # paragraph continues across a page
                continue
            head = is_heading(line, standalone=before and after)
            if head:
                flush()
                stream.append(head)
                continue
            table_row = "|" in line
            starts_new = (_CLAUSE.match(line) or _ITEM.match(line) or before
                          or (current is not None and table_row != ("|" in current.text)))
            if current is None or starts_new:
                flush()
                current = _Para(page=page.page, text=line)
            else:
                current.text += ("\n" if table_row else " ") + line
        if current and not current.text.endswith((".", ":", ";")):
            continue                                  # may continue on the next page
        flush()
    flush()
    return stream


def sections(doc: Document) -> list[_Section]:
    """Group paragraphs under their heading path (at most two levels are kept)."""
    out: list[_Section] = []
    path: list[tuple[int, str]] = []
    for item in _paragraphs(doc):
        if isinstance(item, tuple):
            level, title = item
            path = [p for p in path if p[0] < level] + [(level, title)]
            continue
        label = " > ".join(t for _, t in path[-2:]) or "(untitled)"
        label = label[:_MAX_LABEL]
        if out and out[-1].label == label:
            out[-1].paras.append(item)
        else:
            out.append(_Section(label=label, paras=[item]))
    return out


def _split_long(para: _Para, size: int) -> list[_Para]:
    """A paragraph over `size` tokens: table rows, else sentences, else word windows.
    chunk() passes size - overlap, so the carried overlap always fits beside a unit."""
    if tokens(para.text) <= size:
        return [para]
    pieces = para.text.split("\n") if "|" in para.text else _SENTENCE.split(para.text)
    out: list[_Para] = []
    for piece in pieces:
        words = piece.split()
        for start in range(0, len(words), size):
            out.append(_Para(page=para.page, text=" ".join(words[start:start + size])))
    return out


def _pack(units: list[_Para], size: int, overlap: int) -> list[tuple[int, str]]:
    """Greedy packing under `size` tokens with `overlap` tokens carried forward.
    Returns (page, body) where page is the page of the first new (non-overlap) unit."""
    chunks: list[tuple[int, str]] = []
    body: list[str] = []
    count = 0
    page: int | None = None
    carried = 0                      # tokens at the front of `body` that are overlap
    for unit in units:
        n = tokens(unit.text)
        if body and count + n > size and count > carried:
            chunks.append((page or unit.page, "\n".join(body)))
            tail = " ".join("\n".join(body).split()[-overlap:]) if overlap else ""
            keep = min(tokens(tail), max(0, size - n))
            tail = " ".join(tail.split()[-keep:]) if keep else ""
            body, count, carried, page = ([tail], keep, keep, None) if tail else ([], 0, 0, None)
        body.append(unit.text)
        count += n
        page = page or unit.page
    if body and count > carried:
        chunks.append((page or units[-1].page, "\n".join(body)))
    return chunks


def chunk_id(source: str, doc_version: str, ordinal: int, text: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")[:60]
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{doc_version}-{ordinal:04d}-{digest}"


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` tokens, with `overlap` tokens shared between neighbours. Every chunk keeps
    the section heading it sits under, its page, doc_version and superseded."""
    if size < 10 or not 0 <= overlap < size:
        raise ValueError(f"need size >= 10 and 0 <= overlap < size, got {size}/{overlap}")
    out: list[Chunk] = []
    for section in sections(doc):
        units = [u for p in section.paras for u in _split_long(p, size - overlap)]
        for page, body in _pack(units, size, overlap):
            text = f"{section.label}\n{body}"
            out.append(Chunk(id=chunk_id(doc.source, doc.doc_version, len(out), text),
                             text=text, source=doc.source, section=section.label, page=page,
                             doc_version=doc.doc_version, superseded=doc.superseded))
    return out


def amplification(chunks: list[Chunk], docs: list[Document]) -> float:
    """Storage amplification: stored tokens / original (cleaned) tokens (3.1)."""
    original = sum(tokens(p.text) for d in docs for p in d.pages)
    return round(sum(tokens(c.text) for c in chunks) / original, 3) if original else 0.0
