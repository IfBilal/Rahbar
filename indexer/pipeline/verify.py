"""Stage 2 (Assignment 03): verify a document before it is chunked.

Four checks run for EVERY document, each returning pass or fail with a reason, a stable
code and the evidence behind it (docs/a3-ragops/05 section 4, paper 4.2.2):

    quality       empty, garbled or failed extraction
    completeness  required metadata present (source, title, date or version, page count)
                  and the text is not truncated
    recency       a newer version of the same document is detected
    uniqueness    exact duplicates by hash, near-duplicates by embedding similarity

A check that cannot be evaluated is recorded with `evaluated: False`, never skipped, and
passes unless the inability is itself the defect. Thresholds are data (`Thresholds`, read
from the ConfigMap), because calibrating them on the real corpus is part of the job.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .catalog import ResolvedMeta, is_newer
from .ledger import CURRENT, Ledger

PASS, FAIL = "pass", "fail"
Embedder = Callable[[list[str]], list[list[float]]]
DocVecLoader = Callable[[str, str], dict[str, Any] | None]


@dataclass(frozen=True)
class Thresholds:
    quality_min_chars: int = 200
    quality_min_chars_per_page: int = 40
    empty_page_share: float = 0.5
    garbled_max_bad_ratio: float = 0.02
    garbled_min_word_ratio: float = 0.35
    garbled_hard_word_ratio: float = 0.12
    garbled_min_wordlike: float = 0.60
    garbled_min_alpha_share: float = 0.30
    truncation_fail_score: int = 3
    near_dup_cosine: float = 0.97
    near_dup_jaccard: float = 0.80
    series_similarity: float = 0.80

    @classmethod
    def from_env(cls) -> Thresholds:
        def num(name: str, default: Any) -> Any:
            return type(default)(os.environ.get(name, default))
        d = cls()
        return cls(
            quality_min_chars=num("QUALITY_MIN_CHARS", d.quality_min_chars),
            quality_min_chars_per_page=num("QUALITY_MIN_CHARS_PER_PAGE",
                                           d.quality_min_chars_per_page),
            empty_page_share=num("EMPTY_PAGE_SHARE", d.empty_page_share),
            garbled_max_bad_ratio=num("GARBLED_MAX_BAD_RATIO", d.garbled_max_bad_ratio),
            garbled_min_word_ratio=num("GARBLED_MIN_WORD_RATIO", d.garbled_min_word_ratio),
            garbled_hard_word_ratio=num("GARBLED_HARD_WORD_RATIO", d.garbled_hard_word_ratio),
            garbled_min_wordlike=num("GARBLED_MIN_WORDLIKE", d.garbled_min_wordlike),
            garbled_min_alpha_share=num("GARBLED_MIN_ALPHA_SHARE", d.garbled_min_alpha_share),
            truncation_fail_score=num("TRUNCATION_FAIL_SCORE", d.truncation_fail_score),
            near_dup_cosine=num("NEAR_DUP_COSINE", d.near_dup_cosine),
            near_dup_jaccard=num("NEAR_DUP_JACCARD", d.near_dup_jaccard),
            series_similarity=num("SERIES_SIMILARITY", d.series_similarity))

    def as_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class CheckResult:
    status: str
    code: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    evaluated: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "code": self.code, "reason": self.reason,
                "evidence": self.evidence, "evaluated": self.evaluated}


@dataclass
class DocContext:
    """Everything the checks need about one document, gathered by the orchestrator."""
    file: str                      # inbox-relative path
    path: Path
    sha: str
    meta: ResolvedMeta
    pages: list[str]
    extraction_error: str | None = None
    ocr_pages: int = 0

    @property
    def text(self) -> str:
        return "\n".join(self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass
class Verification:
    checks: dict[str, CheckResult]
    outcome: str                                   # accepted | quarantined
    supersedes: list[tuple[str, str]] = field(default_factory=list)
    docvec: dict[str, Any] | None = None
    text_sha: str = ""

    @property
    def codes(self) -> list[str]:
        return [c.code for c in self.checks.values() if c.status == FAIL]

    @property
    def reasons(self) -> list[str]:
        return [c.reason for c in self.checks.values() if c.status == FAIL]


# ----------------------------------------------------------------------------- quality
_COMMON = set("""
the of and to in a is that for it as with was on be by this are or from at an which have
has had not but they their will would can could should may must shall any all each other
such than then there these those its into also more most only own same so some very when
where who whom whose why how what about above after again against before below between
both during under until while out off over up down here both further once few being does
did do done doing been were you your we our us he she him her his hers if no nor too
student students university course courses semester semesters credit credits grade grades
marks program programs degree faculty department campus academic rules policy policies
fee fees dean office head committee exam exams examination examinations attendance
admission admissions requirements requirement minimum maximum percent percentage per year
years month months week weeks day days date time total number shall must required eligible
eligibility apply applied application approved approval allowed allowed permitted notice
procedure procedures process following include includes including provided provide
within without upon under per both either neither whether during upon through across
report reports annual research publications information general section clause article
table list page pages see note notes details detail one two three four five six seven
eight nine ten first second third new old current previous next last case cases given
using used use made make makes may might need needs needed per via
""".split())
_VOWELS = set("aeiouyAEIOUY")


def _wordlike(token: str) -> bool:
    if len(token) > 25 or not (set(token) & _VOWELS):
        return False
    if re.search(r"[^aeiouyAEIOUY]{6,}", token) or len(set(token.lower())) == 1:
        return False
    return True


def text_stats(text: str) -> dict[str, float]:
    non_ws = re.sub(r"\s", "", text)
    bad = sum(1 for ch in text if ch == "�" or (ord(ch) < 32 and ch not in "\n\r\t"))
    alpha = sum(1 for ch in non_ws if ch.isalpha())
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    common = sum(1 for t in tokens if t.lower() in _COMMON)
    wordlike = sum(1 for t in tokens if _wordlike(t))
    n = len(tokens)
    return {"chars": float(len(non_ws)), "bad_ratio": bad / max(len(text), 1),
            "alpha_share": alpha / max(len(non_ws), 1), "tokens": float(n),
            "word_ratio": common / n if n else 0.0, "wordlike_ratio": wordlike / n if n else 0.0}


def check_quality(ctx: DocContext, th: Thresholds) -> CheckResult:
    if ctx.extraction_error or ctx.page_count == 0:
        return CheckResult(FAIL, "Q-EXTRACT-FAIL",
                           f"extraction failed: {ctx.extraction_error or 'no pages found'}",
                           {"error": ctx.extraction_error or "no pages"})
    stats = text_stats(ctx.text)
    per_page = stats["chars"] / ctx.page_count
    empty_pages = sum(1 for p in ctx.pages if len(re.sub(r"\s", "", p)) < 20)
    ev = {k: round(v, 4) for k, v in stats.items()} | {"pages": ctx.page_count,
                                                       "chars_per_page": round(per_page, 1),
                                                       "empty_pages": empty_pages,
                                                       "ocr_pages": ctx.ocr_pages}
    if stats["chars"] < th.quality_min_chars or per_page < th.quality_min_chars_per_page:
        return CheckResult(FAIL, "Q-EMPTY", f"almost no text: {int(stats['chars'])} characters "
                           f"over {ctx.page_count} page(s)", ev)
    if ctx.page_count > 1 and empty_pages / ctx.page_count > th.empty_page_share:
        return CheckResult(FAIL, "Q-EMPTY", f"{empty_pages} of {ctx.page_count} pages are empty "
                           "(scan without a usable text layer?)", ev)
    if stats["bad_ratio"] > th.garbled_max_bad_ratio:
        return CheckResult(FAIL, "Q-GARBLED", f"{stats['bad_ratio']:.1%} replacement or control "
                           "characters (encoding damage)", ev)
    not_language = ((stats["tokens"] >= 30 and stats["word_ratio"] < th.garbled_min_word_ratio
                     and stats["wordlike_ratio"] < th.garbled_min_wordlike)
                    or (stats["tokens"] >= 50 and stats["word_ratio"] < th.garbled_hard_word_ratio))
    mostly_symbols = (stats["alpha_share"] < th.garbled_min_alpha_share
                      and stats["word_ratio"] < th.garbled_min_word_ratio)
    if not_language or mostly_symbols:
        return CheckResult(FAIL, "Q-GARBLED", "text does not look like language: common-word "
                           f"share {stats['word_ratio']:.2f}, word-like share "
                           f"{stats['wordlike_ratio']:.2f}, alphabetic share "
                           f"{stats['alpha_share']:.2f}", ev)
    return CheckResult(PASS, "Q-OK", f"{ctx.page_count} page(s), {int(stats['chars'])} "
                       f"characters, common-word share {stats['word_ratio']:.2f}", ev)


# ----------------------------------------------------------------------------- completeness
_PAGE_OF = re.compile(r"\bpage\s+(\d+)\s+of\s+(\d+)\b", re.I)
_TERMINATOR = tuple(".!?:)]\"'”’")


def truncation_signals(ctx: DocContext) -> list[tuple[str, int, str]]:
    """(signal, weight, detail) for each truncation signal that fired. Weights in
    docs/a3-ragops/05 section 4.2: one weak signal alone never fails a document."""
    fired: list[tuple[str, int, str]] = []
    text = ctx.text.rstrip()
    if len(text) > 200:
        last_line = text.splitlines()[-1].strip()
        words = re.findall(r"\S+", last_line)
        # a sentence-like last line (not a short heading or signature) with no ending
        if len(words) >= 6 and not last_line.endswith(_TERMINATOR) and words[-1].isalpha():
            fired.append(("S1-ends-mid-sentence", 2, f"the last line ends with {words[-1]!r} and "
                                                     "no sentence end"))
    seen = [(int(n), int(m)) for n, m in _PAGE_OF.findall(ctx.text)]
    if seen and max(n for n, _ in seen) < max(m for _, m in seen):
        fired.append(("S2-page-x-of-y", 3, f"last page marker is {max(n for n, _ in seen)} of "
                                           f"{max(m for _, m in seen)}"))
    declared = ctx.meta.row.get("pages")
    if declared and int(declared) > ctx.page_count:
        fired.append(("S3-declared-pages", 3, f"declared {declared} pages, found {ctx.page_count}"))
    suffix = ctx.path.suffix.lower()
    raw = ""
    if suffix in (".html", ".htm", ".md"):
        raw = ctx.path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm") and "</html>" not in raw.lower():
        fired.append(("S4-unclosed-html", 2, "no closing </html>"))
    if suffix == ".md" and raw.count("```") % 2 == 1:
        fired.append(("S4-open-code-fence", 2, "a ``` fence is never closed"))
    last_line = text.splitlines()[-1].strip() if text else ""
    if last_line.startswith("|") and not last_line.endswith("|"):
        fired.append(("S4-cut-table-row", 2, "the last table row is cut off"))
    toc = _outline_gap(ctx.text)
    if toc:
        fired.append(("S5-outline-gap", 2, toc))
    return fired


def _outline_gap(text: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines[:60]):
        if re.match(r"^\s*#*\s*(table of )?contents\s*$", line, re.I):
            entries = []
            for ln in lines[i + 1:i + 40]:
                m = re.match(r"^\s*(\d{1,2})[.)]\s+\S", ln)
                if m:
                    entries.append(int(m.group(1)))
                elif entries and ln.strip():
                    break
            if len(entries) >= 3:
                body = "\n".join(lines[i + 1 + len(entries):])
                heads = [int(h) for h in re.findall(r"(?m)^\s*#{0,3}\s*(\d{1,2})[.)]?\s+[A-Z]", body)]
                if heads and max(heads) < max(entries):
                    return f"contents lists sections up to {max(entries)}, text stops at {max(heads)}"
    return None


def check_completeness(ctx: DocContext, th: Thresholds) -> CheckResult:
    missing: list[tuple[str, str]] = []
    if not ctx.meta.source:
        missing.append(("C-MISSING-SOURCE", "source"))
    if not ctx.meta.title.value:
        missing.append(("C-MISSING-TITLE", "title"))
    if not (ctx.meta.version.value or ctx.meta.date.value):
        missing.append(("C-MISSING-DATE-VERSION", "date or version"))
    if ctx.page_count == 0:
        missing.append(("C-MISSING-PAGES", "page count"))
    fired = truncation_signals(ctx) if ctx.page_count else []
    score = sum(w for _, w, _ in fired)
    truncated = score >= th.truncation_fail_score
    ev = {"missing": [f for _, f in missing],
          "signals": [{"signal": s, "weight": w, "detail": d} for s, w, d in fired],
          "truncation_score": score}
    codes = [c for c, _ in missing] + (["C-TRUNCATED"] if truncated else [])
    if codes:
        parts = [f"missing {', '.join(f for _, f in missing)}"] if missing else []
        if truncated:
            parts.append("looks truncated (" + "; ".join(d for _, _, d in fired) + ")")
        ev["codes"] = codes
        return CheckResult(FAIL, codes[0], "; ".join(parts), ev)
    note = f"; weak signal only ({fired[0][0]})" if fired else ""
    return CheckResult(PASS, "C-OK", "title, version or date, source and pages present, "
                       f"no truncation{note}", ev)


# ----------------------------------------------------------------------------- recency
def check_recency(ctx: DocContext, ledger: Ledger) -> tuple[CheckResult, list[tuple[str, str]]]:
    label = ctx.meta.version.value
    known = {v: r for v, r in ledger.versions(ctx.meta.doc_id).items()
             if r["status"] in (CURRENT, "archived")}
    if not label:
        return CheckResult(PASS, "R-OK-FIRST", "no version or date could be resolved, so recency "
                           "cannot be compared", evaluated=False), []
    if not known:
        return CheckResult(PASS, "R-OK-FIRST", "no other version of this document is known"), []
    newer = sorted((v for v in known if is_newer(v, label)), key=lambda v: _order(v))
    if newer:
        top = newer[-1]
        return CheckResult(FAIL, "R-NEWER-EXISTS",
                           f"a newer version is already held: {ctx.meta.doc_id}@{top} "
                           f"(this file is {label})",
                           {"newer": [f"{ctx.meta.doc_id}@{v}" for v in newer],
                            "this": label}), []
    if label in known:
        return CheckResult(PASS, "R-OK-REVISION", f"same version label {label} as an earlier "
                           "copy; treated as a revision that replaces it",
                           {"replaces": f"{ctx.meta.doc_id}@{label}"}), []
    older = sorted(v for v in known if is_newer(label, v))
    current = [(ctx.meta.doc_id, v) for v in older if known[v]["status"] == CURRENT]
    return CheckResult(PASS, "R-SUPERSEDES",
                       f"newer version detected: supersedes {', '.join(f'{ctx.meta.doc_id}@{v}' for v in older)}",
                       {"supersedes": [f"{ctx.meta.doc_id}@{v}" for v in older]}), current


def _order(label: str) -> tuple[int, tuple[Any, ...]]:
    from .catalog import version_key
    return version_key(label)


# ----------------------------------------------------------------------------- uniqueness
def normalised_text_sha(pages: list[str]) -> str:
    text = " ".join(" ".join(pages).lower().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sketch(text: str, k: int = 256) -> list[int]:
    """Bottom-k sketch of the document's 5-word shingles: a small, deterministic stand-in
    for the full shingle set, good enough to estimate Jaccard similarity."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    if len(words) < 5:
        words = words + [""] * (5 - len(words))
    hashes = {int.from_bytes(hashlib.sha1(" ".join(words[i:i + 5]).encode()).digest()[:8], "big")
              for i in range(len(words) - 4)}
    return sorted(hashes)[:k]


def jaccard_estimate(a: list[int], b: list[int], k: int = 256) -> float:
    if not a or not b:
        return 0.0
    union = sorted(set(a) | set(b))[:k]
    sa, sb = set(a), set(b)
    both = sum(1 for h in union if h in sa and h in sb)
    return both / len(union) if union else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else -1.0


def windows(pages: list[str], count: int = 8, size: int = 250) -> list[str]:
    """Up to `count` text windows: the first `size` words plus evenly spaced others.

    `size` is in whitespace words, and a word is often several tokens: numbers, table cells and
    OCR noise tokenize at 3-5 tokens each. 400 words overflowed nomic-embed-text's 2048-token context
    on the real corpus (Ollama answered 400 'input length exceeds the context length', first cluster
    run, 24 Nov); 250 stays inside it, below the 300-word chunks that always fitted."""
    words = " ".join(pages).split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    starts = [0] + [int(i * (len(words) - size) / (count - 1)) for i in range(1, count)]
    return [" ".join(words[s:s + size]) for s in dict.fromkeys(starts)]


def _embed_windows(wins: list[str], embed: Embedder) -> list[list[float]]:
    """Embed the windows; if the model refuses one as too long, halve that window and retry (up to
    4 times). Only the document vector tolerates this: it is an approximation used to find
    near-duplicates. Chunk embeddings never shorten text, they fail the run."""
    try:
        return embed(wins)
    except Exception:
        out: list[list[float]] = []
        for w in wins:
            text = w
            for _ in range(5):
                try:
                    out.append(embed([text])[0])
                    break
                except Exception:
                    words = text.split()
                    if len(words) < 8:
                        raise
                    text = " ".join(words[: len(words) // 2])
            else:
                raise RuntimeError("document window could not be embedded even when shortened")
        return out


def build_docvec(pages: list[str], embed: Embedder) -> dict[str, Any]:
    """Document vector = mean of the embeddings of up to 8 windows, plus a shingle sketch."""
    wins = windows(pages)
    vecs = _embed_windows(wins, embed) if wins else []
    mean = [sum(col) / len(vecs) for col in zip(*vecs)] if vecs else []
    return {"vector": mean, "sketch": sketch(" ".join(pages)), "windows": len(wins)}


@dataclass
class RunSeen:
    """Documents accepted earlier in this run, so duplicates inside one batch are caught
    (the first one seen wins, in sorted path order)."""
    shas: dict[str, str] = field(default_factory=dict)
    text_shas: dict[str, str] = field(default_factory=dict)
    docvecs: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)


def check_uniqueness(ctx: DocContext, ledger: Ledger, th: Thresholds, embed: Embedder | None,
                     load_docvec: DocVecLoader, seen: RunSeen
                     ) -> tuple[CheckResult, dict[str, Any] | None, str]:
    text_sha = normalised_text_sha(ctx.pages) if ctx.pages else ""
    hit = ledger.find_by_sha(ctx.sha)
    other = f"{hit[0]}@{hit[1]}" if hit else seen.shas.get(ctx.sha)
    if other:
        return CheckResult(FAIL, "U-EXACT-DUP", f"byte-identical to {other} (sha256 {ctx.sha[:12]})",
                           {"duplicate_of": other, "sha256": ctx.sha}), None, text_sha
    if text_sha:
        thit = ledger.find_by_text_sha(text_sha)
        tother = f"{thit[0]}@{thit[1]}" if thit else seen.text_shas.get(text_sha)
        if tother:
            return CheckResult(FAIL, "U-EXACT-DUP", f"same text as {tother} after normalising "
                               "whitespace and case", {"duplicate_of": tother,
                                                       "match": "normalised-text"}), None, text_sha
    if not ctx.pages or embed is None:
        return CheckResult(PASS, "U-OK", "byte hash is unique; near-duplicate check not run "
                           "(no text or no embedding service)", evaluated=False), None, text_sha
    vec = build_docvec(ctx.pages, embed)
    best: tuple[float, float, str] = (-1.0, 0.0, "")
    candidates = [(d, v, load_docvec(d, v)) for d, v, _ in ledger.iter_versions()
                  if d != ctx.meta.doc_id] + list(seen.docvecs)
    for doc_id, version, other_vec in candidates:
        if not other_vec or doc_id == ctx.meta.doc_id:
            continue
        cos = cosine(vec["vector"], other_vec["vector"])
        jac = jaccard_estimate(vec["sketch"], other_vec["sketch"])
        if cos > best[0]:
            best = (cos, jac, f"{doc_id}@{version}")
        if cos >= th.near_dup_cosine and jac >= th.near_dup_jaccard:
            return CheckResult(FAIL, "U-NEAR-DUP", f"near-duplicate of {doc_id}@{version}: "
                               f"embedding cosine {cos:.3f}, shingle Jaccard {jac:.2f}",
                               {"near_duplicate_of": f"{doc_id}@{version}",
                                "cosine": round(cos, 4), "jaccard": round(jac, 3)}), vec, text_sha
    ev = {"closest": best[2], "cosine": round(best[0], 4), "jaccard": round(best[1], 3)} \
        if best[2] else {}
    return CheckResult(PASS, "U-OK", "no exact or near duplicate" + (
        f" (closest {best[2]}, cosine {best[0]:.3f})" if best[2] else ""), ev), vec, text_sha


# ----------------------------------------------------------------------------- the whole thing
def verify_document(ctx: DocContext, ledger: Ledger, th: Thresholds, embed: Embedder | None,
                    load_docvec: DocVecLoader, seen: RunSeen) -> Verification:
    """Run all four checks. Quarantine on any failure; otherwise accept."""
    quality = check_quality(ctx, th)
    completeness = check_completeness(ctx, th)
    recency, supersedes = check_recency(ctx, ledger)
    uniqueness, docvec, text_sha = check_uniqueness(ctx, ledger, th, embed, load_docvec, seen)
    checks = {"quality": quality, "completeness": completeness, "recency": recency,
              "uniqueness": uniqueness}
    ok = all(c.status == PASS for c in checks.values())
    return Verification(checks=checks, outcome="accepted" if ok else "quarantined",
                        supersedes=supersedes if ok else [], docvec=docvec, text_sha=text_sha)
