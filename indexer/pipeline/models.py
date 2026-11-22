"""The shapes passed between stages. Metadata fields are required (section 3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Page:
    """Text of one page, as extraction produced it."""

    source: str              # file name, e.g. Academic_Rules_Handbook_2026.pdf
    page: int                # 1-based
    text: str
    ocr: bool = False        # True when this page had no text layer and was OCR'd


@dataclass
class Document:
    source: str
    doc_version: str         # e.g. "2026-06"; from corpus/sources.yaml
    superseded: bool         # True for an older version of a policy
    pages: list[Page] = field(default_factory=list)


@dataclass
class Chunk:
    id: str                  # stable: same document + same position gives the same id
    text: str
    source: str
    section: str             # the heading this chunk sits under, e.g. "5.4 Academic Warning"
    page: int
    doc_version: str
    superseded: bool
    # Assignment 03 (docs/a3-ragops/14 section 2): set by the incremental pipeline only, so
    # chunks built the Assignment 02 way keep exactly the five required metadata keys.
    doc_id: str = ""
    status: str = ""             # "current" | "archived"
    content_sha: str = ""        # SHA-256 of the source file's bytes
    chunk_sha: str = ""          # first 8 hex digits of the chunk text digest
    ingest_run: str = ""
    revision: int = 0

    def metadata(self) -> dict[str, str | int | bool]:
        """Chroma metadata values must be str, int, float or bool."""
        meta: dict[str, str | int | bool] = {
            "source": self.source,
            "section": self.section,
            "page": self.page,
            "doc_version": self.doc_version,
            "superseded": self.superseded,
        }
        if self.doc_id:
            meta.update(doc_id=self.doc_id, status=self.status or "current",
                        content_sha=self.content_sha, chunk_sha=self.chunk_sha,
                        ingest_run=self.ingest_run, revision=self.revision)
        return meta
