"""Ingest input: the inbox, and metadata resolution (docs/a3-ragops/05 section 3).

The inbox is the desired corpus. An optional `_batch.yaml` supplies catalog rows, but it
is never required: the unseen documents handed over at the demo have no catalog, so every
field is resolved by the first route that has it:

    catalog row  >  embedded in the file (PDF info, front matter, HTML meta)  >  derived
    from the text (first heading, a version or date pattern near the top)

The route that produced each value is recorded, so a report can say where a title came
from. File modification time is never used as a document date: a copy changes it, and
using it would let a file with no real date pass the completeness check.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

SUPPORTED = {".pdf", ".html", ".htm", ".md", ".txt"}
CATALOG_NAME = "_batch.yaml"
DEFAULT_BATCH = "A"

_MONTHS = ("january february march april may june july august september october "
           "november december").split()
_MONTH_RE = "|".join(m[:3] + r"[a-z]*\.?" for m in _MONTHS)
_MONTH_NUM = {m[:3]: i + 1 for i, m in enumerate(_MONTHS)}
_KEYWORD = r"(?:effective|issued|revised|dated|edition|version|updated|academic\s+year|session)"

_ISO = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?\b")
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\s*,?\s+((?:19|20)\d{{2}})\b", re.I)
_MDY = re.compile(rf"\b({_MONTH_RE})\s+(?:(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s+)?((?:19|20)\d{{2}})\b",
                  re.I)
_KEYED_YEAR = re.compile(rf"\b{_KEYWORD}\b[^\n\d]{{0,30}}((?:19|20)\d{{2}})\b", re.I)
_VERSION = re.compile(r"\bversion\s*[:\-]?\s*v?(\d+(?:\.\d+)*)\b|\bv(\d+(?:\.\d+)+)\b", re.I)
_FILENAME_NOISE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:" + "|".join(m[:3] for m in _MONTHS) + r")[a-z]*\b|"
    r"\bv\d+(?:\.\d+)*\b|\b(?:version|edition|draft|copy|final|backup|rev\d*|new|old|latest)\b",
    re.I)


@dataclass
class Field:
    value: str | None
    route: str          # catalog | embedded | derived | missing

    def as_dict(self) -> dict[str, str | None]:
        return {"value": self.value, "route": self.route}


@dataclass
class InboxFile:
    rel: str            # path relative to the inbox, '/' separated: the ledger key
    path: Path
    sha: str
    size: int
    batch: str


@dataclass
class ResolvedMeta:
    source: str
    title: Field
    version: Field      # the doc_version label
    date: Field
    doc_id: str
    batch: str
    row: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "title": self.title.as_dict(),
                "doc_version": self.version.as_dict(), "date": self.date.as_dict(),
                "doc_id": self.doc_id, "batch": self.batch}


# ---------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def derive_doc_id(title: str | None, file_name: str) -> str:
    """The series a document belongs to: the title (or file stem) with version, year and
    month words stripped, so 'Academic Rules 2023' and 'Academic Rules 2026' share an id."""
    base = title if title else Path(file_name).stem.replace("_", " ").replace("-", " ")
    slug = slugify(_FILENAME_NOISE.sub(" ", base))
    return slug or slugify(Path(file_name).stem) or "document"


def normalise_date(y: str, m: str | None = None, d: str | None = None) -> str:
    out = y
    if m:
        out += f"-{int(m):02d}"
        if d:
            out += f"-{int(d):02d}"
    return out


def find_date(text: str) -> str | None:
    """First date-like pattern in `text`, normalised to YYYY[-MM[-DD]]. Keyword-introduced
    dates win; a bare year counts only after a word like 'edition' or 'effective'."""
    head = text[:3000]
    for rx in (_ISO,):
        m = rx.search(head)
        if m:
            return normalise_date(m.group(1), m.group(2), m.group(3))
    m = _DMY.search(head)
    if m:
        return normalise_date(m.group(3), str(_MONTH_NUM[m.group(2)[:3].lower()]), m.group(1))
    m = _MDY.search(head)
    if m:
        return normalise_date(m.group(3), str(_MONTH_NUM[m.group(1)[:3].lower()]), m.group(2))
    m = _KEYED_YEAR.search(head)
    return normalise_date(m.group(1)) if m else None


def find_version(text: str) -> str | None:
    m = _VERSION.search(text[:3000])
    if not m:
        return None
    return "v" + (m.group(1) or m.group(2))


def version_key(label: str) -> tuple[int, tuple[Any, ...]]:
    """Orderable key: dates (kind 2) and dotted versions (kind 1) compare within their
    kind; anything else (kind 0) compares as text."""
    label = label.strip()
    m = re.fullmatch(r"((?:19|20)\d{2})(?:-(\d{2}))?(?:-(\d{2}))?", label)
    if m:
        return 2, tuple(int(x) if x else 0 for x in m.groups())
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", label, re.I)
    if m:
        return 1, tuple(int(x) for x in m.group(1).split("."))
    return 0, (label.lower(),)


def is_newer(a: str, b: str) -> bool:
    """True when version label `a` is strictly newer than `b`."""
    ka, kb = version_key(a), version_key(b)
    if ka[0] == kb[0]:
        return ka[1] > kb[1]
    return a.lower() > b.lower()


# ---------------------------------------------------------------------- the inbox
def _batch_from_path(rel: str) -> str | None:
    for part in rel.split("/")[:-1]:
        m = re.fullmatch(r"batch[-_ ]?([a-z0-9]+)", part, re.I)
        if m:
            return m.group(1).upper()
    return None


def load_catalog(inbox: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Catalog rows keyed by relative path and by bare file name, plus the batch declared
    by each `_batch.yaml` for the files in its folder."""
    rows: dict[str, dict[str, Any]] = {}
    folder_batch: dict[str, str] = {}
    for cat in sorted(inbox.rglob(CATALOG_NAME)):
        try:
            data = yaml.safe_load(cat.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        base = cat.parent.relative_to(inbox).as_posix()
        prefix = "" if base == "." else base + "/"
        if data.get("batch"):
            folder_batch[prefix] = str(data["batch"]).upper()
        for row in data.get("documents") or []:
            name = str(row.get("file", "")).strip()
            if name:
                rows[prefix + name] = row
                rows.setdefault(Path(name).name, row)
    return rows, folder_batch


def scan_inbox(inbox: Path) -> list[InboxFile]:
    """Every supported file under the inbox, in sorted order (deterministic runs)."""
    _, folder_batch = load_catalog(inbox)
    found: list[InboxFile] = []
    for path in sorted(p for p in inbox.rglob("*") if p.is_file()):
        rel = path.relative_to(inbox).as_posix()
        name = path.name
        if (path.suffix.lower() not in SUPPORTED or name.startswith((".", "_"))
                or name.lower().startswith("readme")):
            continue
        batch = _batch_from_path(rel)
        if batch is None:
            batch = next((b for pre, b in sorted(folder_batch.items(), key=lambda x: -len(x[0]))
                          if rel.startswith(pre)), DEFAULT_BATCH)
        found.append(InboxFile(rel=rel, path=path, sha=sha256_file(path),
                               size=path.stat().st_size, batch=batch))
    return found


# ---------------------------------------------------------------------- embedded metadata
def _front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        if value:
            meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta


def embedded_metadata(path: Path) -> dict[str, str]:
    """title / doc_version / date / doc_id stored inside the file, when there are any."""
    suffix = path.suffix.lower()
    out: dict[str, str] = {}
    try:
        if suffix in (".md", ".txt"):
            fm = _front_matter(path.read_text(encoding="utf-8", errors="replace"))
            out = {k: fm[k] for k in ("title", "doc_version", "date", "doc_id") if k in fm}
        elif suffix in (".html", ".htm"):
            text = path.read_text(encoding="utf-8", errors="replace")
            t = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            if t and t.group(1).strip():
                out["title"] = " ".join(t.group(1).split())
            for key in ("date", "doc_version", "doc_id"):
                m = re.search(rf'<meta[^>]+name=["\']{key}["\'][^>]+content=["\']([^"\']+)', text,
                              re.I)
                if m:
                    out[key] = m.group(1).strip()
        elif suffix == ".pdf":
            from pypdf import PdfReader
            info = PdfReader(str(path)).metadata
            title = (info.title or "").strip() if info else ""
            if title and not re.search(r"\.(pdf|docx?|indd)$|^untitled|^microsoft word", title,
                                       re.I):
                out["title"] = title
            created = info.creation_date if info else None
            if created:
                out["pdf_year"] = str(created.year)
    except Exception:           # a damaged file is the quality check's problem, not ours
        return {}
    return out


_BAD_TITLE = re.compile(r"^(page\s+\d+|\d+|table of contents|contents|abstract)$", re.I)


def derive_title(first_page_text: str) -> str | None:
    for raw in first_page_text.splitlines()[:25]:
        line = raw.strip().lstrip("#").strip()
        if (3 <= len(line) <= 120 and not line.endswith((".", ",", ";"))
                and sum(c.isalpha() for c in line) >= 3 and not _BAD_TITLE.match(line)):
            return line
    return None


# ---------------------------------------------------------------------- resolution
def resolve_metadata(f: InboxFile, pages: list[str],
                     rows: dict[str, dict[str, Any]] | None = None) -> ResolvedMeta:
    """Resolve source, title, version, date and doc_id for one inbox file."""
    row = (rows or {}).get(f.rel) or (rows or {}).get(f.path.name) or {}
    emb = embedded_metadata(f.path)
    top = "\n".join(pages[:2])

    def pick(key: str, derived: str | None) -> Field:
        for route, src in (("catalog", row), ("embedded", emb)):
            val = src.get(key)
            if val not in (None, ""):
                return Field(str(val), route)
        return Field(derived, "derived" if derived else "missing")

    title = pick("title", derive_title(pages[0]) if pages else None)
    derived_date = find_date(top)
    date = pick("date", derived_date)
    if date.route == "missing" and emb.get("pdf_year") and emb["pdf_year"] in top:
        date = Field(emb["pdf_year"], "embedded")      # PDF creation year, confirmed by the text
    derived_version = find_version(top)
    version = pick("doc_version", derived_version or (date.value if date.value else None))
    doc_id = (str(row.get("doc_id") or emb.get("doc_id") or "").strip()
              or derive_doc_id(title.value, f.path.name))
    return ResolvedMeta(source=f.path.name, title=title, version=version, date=date,
                        doc_id=slugify(doc_id), batch=str(row.get("batch") or f.batch).upper(),
                        row=row)
