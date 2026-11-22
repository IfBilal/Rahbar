"""The four verification checks (docs/a3-ragops/05 section 4)."""

from __future__ import annotations

import random
import string
from pathlib import Path

from pipeline.catalog import Field, ResolvedMeta
from pipeline.ledger import ARCHIVED, CURRENT, Ledger
from pipeline.verify import (
    DocContext, RunSeen, Thresholds, build_docvec, check_completeness, check_quality,
    check_recency, check_uniqueness, jaccard_estimate, sketch, truncation_signals,
    verify_document,
)

TH = Thresholds()
GOOD = ("The student must maintain a minimum attendance of eighty percent in every course "
        "during the semester. A student who fails to meet this requirement shall not be "
        "allowed to sit in the final examination. The dean of the department may grant "
        "relief in exceptional cases after reviewing the application of the student. ") * 4


def ctx(tmp_path: Path, pages: list[str] | None = None, name: str = "doc.txt", sha: str = "a" * 64,
        title: str | None = "Attendance Policy", version: str | None = "2026-06",
        doc_id: str = "attendance", error: str | None = None, row: dict | None = None) -> DocContext:
    path = tmp_path / name
    if not path.exists():
        path.write_text("\n".join(pages or [GOOD]), encoding="utf-8")
    meta = ResolvedMeta(source=name, title=Field(title, "catalog" if title else "missing"),
                        version=Field(version, "catalog" if version else "missing"),
                        date=Field(None, "missing"), doc_id=doc_id, batch="A", row=row or {})
    return DocContext(file=name, path=path, sha=sha, meta=meta,
                      pages=[GOOD] if pages is None else pages, extraction_error=error)


# ------------------------------------------------------------------------------ quality
def test_good_text_passes_quality(tmp_path: Path) -> None:
    r = check_quality(ctx(tmp_path), TH)
    assert r.status == "pass" and r.code == "Q-OK"


def test_failed_extraction_and_no_pages(tmp_path: Path) -> None:
    assert check_quality(ctx(tmp_path, pages=[], error="PdfReadError: EOF marker not found"),
                         TH).code == "Q-EXTRACT-FAIL"
    assert check_quality(ctx(tmp_path, pages=[]), TH).code == "Q-EXTRACT-FAIL"


def test_empty_and_whitespace_documents_fail(tmp_path: Path) -> None:
    assert check_quality(ctx(tmp_path, pages=["   \n\t  "]), TH).code == "Q-EMPTY"
    assert check_quality(ctx(tmp_path, pages=["ok"]), TH).code == "Q-EMPTY"


def test_a_scan_with_mostly_empty_pages_fails(tmp_path: Path) -> None:
    pages = [GOOD] + [""] * 6
    r = check_quality(ctx(tmp_path, pages=pages), Thresholds(quality_min_chars_per_page=1))
    assert r.code == "Q-EMPTY" and "empty" in r.reason


def test_mojibake_fails_as_garbled(tmp_path: Path) -> None:
    text = GOOD[:300] + "�" * 40 + GOOD[300:]
    assert check_quality(ctx(tmp_path, pages=[text]), TH).code == "Q-GARBLED"


def test_random_letters_fail_as_garbled(tmp_path: Path) -> None:
    rng = random.Random(1)
    junk = " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 9)))
                    for _ in range(300))
    assert check_quality(ctx(tmp_path, pages=[junk]), TH).code == "Q-GARBLED"


def test_symbol_soup_fails_as_garbled(tmp_path: Path) -> None:
    assert check_quality(ctx(tmp_path, pages=["#@!$%^&*()_+{}|:<>?~ " * 40]), TH).code \
        == "Q-GARBLED"


def test_a_table_heavy_document_with_some_prose_passes(tmp_path: Path) -> None:
    table = "\n".join(f"Campus {i} | {1000 + i} | {2000 + 3 * i} | {i * 7}" for i in range(80))
    assert check_quality(ctx(tmp_path, pages=[GOOD + "\n" + table]), TH).status == "pass"


# ------------------------------------------------------------------------------ completeness
def test_complete_document_passes(tmp_path: Path) -> None:
    assert check_completeness(ctx(tmp_path), TH).status == "pass"


def test_each_missing_field_is_reported(tmp_path: Path) -> None:
    r = check_completeness(ctx(tmp_path, title=None), TH)
    assert r.status == "fail" and r.code == "C-MISSING-TITLE"
    r = check_completeness(ctx(tmp_path, version=None), TH)
    assert r.code == "C-MISSING-DATE-VERSION"
    r = check_completeness(ctx(tmp_path, title=None, version=None), TH)
    assert r.evidence["codes"] == ["C-MISSING-TITLE", "C-MISSING-DATE-VERSION"]
    assert check_completeness(ctx(tmp_path, pages=[]), TH).code == "C-MISSING-PAGES"


def test_a_missing_date_does_not_hide_behind_file_mtime(tmp_path: Path) -> None:
    c = ctx(tmp_path, version=None)
    c.path.touch()
    assert check_completeness(c, TH).code == "C-MISSING-DATE-VERSION"


def test_one_weak_truncation_signal_does_not_fail_a_document(tmp_path: Path) -> None:
    c = ctx(tmp_path, pages=[GOOD + " and the final line ends with a bare word"])
    signals = truncation_signals(c)
    assert [s for s, _, _ in signals] == ["S1-ends-mid-sentence"]
    assert check_completeness(c, TH).status == "pass"


def test_page_x_of_y_marker_fails_on_its_own(tmp_path: Path) -> None:
    r = check_completeness(ctx(tmp_path, pages=[GOOD + "\nPage 3 of 5"]), TH)
    assert r.code == "C-TRUNCATED" and "3 of 5" in r.reason


def test_declared_pages_exceeding_found_pages_fails(tmp_path: Path) -> None:
    r = check_completeness(ctx(tmp_path, row={"pages": 12}), TH)
    assert r.code == "C-TRUNCATED"


def test_unclosed_fence_plus_mid_sentence_end_fails(tmp_path: Path) -> None:
    body = "# Policy\n\n" + GOOD + "\n```\nsome code and then it just stops mid"
    c = ctx(tmp_path, pages=[body], name="cut.md")
    c.path.write_text(body, encoding="utf-8")
    r = check_completeness(c, TH)
    assert r.code == "C-TRUNCATED" and r.evidence["truncation_score"] >= 4


def test_cut_table_row_and_unclosed_html(tmp_path: Path) -> None:
    c = ctx(tmp_path, pages=[GOOD + "\n| Course | Credits |\n| CS101 | 3 |\n| CS102 | 3"], name="t.html")
    c.path.write_text("<html><body>" + GOOD, encoding="utf-8")
    r = check_completeness(c, TH)
    assert r.code == "C-TRUNCATED"


def test_toc_outline_gap_is_a_signal(tmp_path: Path) -> None:
    body = "Contents\n1. Intro\n2. Rules\n3. Fees\n4. Appeals\n\n1. Intro\n" + GOOD + "\n2. Rules\n" + GOOD
    c = ctx(tmp_path, pages=[body])
    assert any(s == "S5-outline-gap" for s, _, _ in truncation_signals(c))


# ------------------------------------------------------------------------------ recency
def _ledger(tmp_path: Path, versions: dict[str, str]) -> Ledger:
    led = Ledger.load(tmp_path / "l.json")
    for v, status in versions.items():
        led.put("attendance", v, {"status": status, "content_sha": v * 64, "chunk_ids": []})
    return led


def test_first_version_passes(tmp_path: Path) -> None:
    r, sup = check_recency(ctx(tmp_path), Ledger.load(tmp_path / "x.json"))
    assert r.code == "R-OK-FIRST" and sup == []


def test_newer_arrival_supersedes_the_current_version(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2023-08": CURRENT})
    r, sup = check_recency(ctx(tmp_path, version="2026-06"), led)
    assert r.status == "pass" and r.code == "R-SUPERSEDES" and "newer version detected" in r.reason
    assert sup == [("attendance", "2023-08")]


def test_already_archived_older_versions_are_not_superseded_again(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2020-01": ARCHIVED, "2023-08": CURRENT})
    _, sup = check_recency(ctx(tmp_path, version="2026-06"), led)
    assert sup == [("attendance", "2023-08")]


def test_a_late_old_file_fails_recency(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2026-06": CURRENT})
    r, sup = check_recency(ctx(tmp_path, version="2019-01"), led)
    assert r.status == "fail" and r.code == "R-NEWER-EXISTS" and "attendance@2026-06" in r.reason
    assert sup == []


def test_same_label_is_a_revision(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2026-06": CURRENT})
    assert check_recency(ctx(tmp_path, version="2026-06"), led)[0].code == "R-OK-REVISION"


def test_unresolvable_version_is_not_evaluated(tmp_path: Path) -> None:
    r, _ = check_recency(ctx(tmp_path, version=None), _ledger(tmp_path, {"2026-06": CURRENT}))
    assert r.status == "pass" and r.evaluated is False


# ------------------------------------------------------------------------------ uniqueness
def fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-words vectors: similar texts get similar vectors."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in t.lower().split():
            v[hash(w) % 64] += 1.0
        out.append(v)
    return out


def _load_none(doc: str, ver: str) -> dict | None:
    return None


def test_exact_duplicate_by_bytes_against_the_ledger(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2026-06": CURRENT})
    led.versions("attendance")["2026-06"]["content_sha"] = "d" * 64
    r, _, _ = check_uniqueness(ctx(tmp_path, sha="d" * 64, doc_id="copy"), led, TH, fake_embed,
                               _load_none, RunSeen())
    assert r.status == "fail" and r.code == "U-EXACT-DUP" and "attendance@2026-06" in r.reason


def test_exact_duplicate_within_the_same_run(tmp_path: Path) -> None:
    seen = RunSeen(shas={"e" * 64: "other@1"})
    r, _, _ = check_uniqueness(ctx(tmp_path, sha="e" * 64), Ledger.load(tmp_path / "n.json"), TH,
                               fake_embed, _load_none, seen)
    assert r.code == "U-EXACT-DUP"


def test_whitespace_and_case_copy_is_caught_by_the_text_hash(tmp_path: Path) -> None:
    from pipeline.verify import normalised_text_sha
    led = Ledger.load(tmp_path / "n.json")
    led.put("orig", "1", {"status": CURRENT, "content_sha": "1" * 64,
                          "text_sha": normalised_text_sha([GOOD]), "chunk_ids": []})
    twin = ctx(tmp_path, pages=[GOOD.upper().replace(". ", ".\n\n")], sha="2" * 64, doc_id="twin")
    r, _, _ = check_uniqueness(twin, led, TH, fake_embed, _load_none, RunSeen())
    assert r.code == "U-EXACT-DUP" and "normalising" in r.reason


def test_near_duplicate_needs_both_embedding_and_shingle_similarity(tmp_path: Path) -> None:
    led = Ledger.load(tmp_path / "n.json")
    base = ctx(tmp_path, pages=[GOOD], doc_id="orig")
    vec = build_docvec(base.pages, fake_embed)
    led.put("orig", "1", {"status": CURRENT, "content_sha": "1" * 64, "text_sha": "z", "chunk_ids": []})
    loader = lambda d, v: vec if (d, v) == ("orig", "1") else None      # noqa: E731
    near = ctx(tmp_path, pages=[GOOD.replace("eighty", "seventy-five")], sha="3" * 64,
               doc_id="near", name="near.txt")
    r, _, _ = check_uniqueness(near, led, TH, fake_embed, loader, RunSeen())
    assert r.status == "fail" and r.code == "U-NEAR-DUP" and r.evidence["jaccard"] >= 0.8
    other = ctx(tmp_path, pages=["Hostel rooms are allotted by lottery each June to first year "
                                 "students living outside the city. " * 20],
                sha="4" * 64, doc_id="hostel", name="hostel.txt")
    r2, _, _ = check_uniqueness(other, led, TH, fake_embed, loader, RunSeen())
    assert r2.status == "pass" and r2.evidence["closest"] == "orig@1"


def test_versions_of_the_same_series_are_never_near_duplicates(tmp_path: Path) -> None:
    led = Ledger.load(tmp_path / "n.json")
    vec = build_docvec([GOOD], fake_embed)
    led.put("attendance", "2023", {"status": CURRENT, "content_sha": "1" * 64, "text_sha": "z",
                                   "chunk_ids": []})
    r, _, _ = check_uniqueness(ctx(tmp_path, pages=[GOOD.replace("eighty", "seventy")], sha="5" * 64),
                               led, TH, fake_embed, lambda d, v: vec, RunSeen())
    assert r.status == "pass"


def test_no_embedder_means_near_duplicate_check_not_evaluated(tmp_path: Path) -> None:
    r, vec, _ = check_uniqueness(ctx(tmp_path), Ledger.load(tmp_path / "n.json"), TH, None,
                                 _load_none, RunSeen())
    assert r.status == "pass" and r.evaluated is False and vec is None


def test_sketch_jaccard_estimates_overlap() -> None:
    a = sketch(GOOD)
    assert jaccard_estimate(a, a) == 1.0
    assert jaccard_estimate(a, sketch("completely different words about hostels " * 30)) < 0.2


# ------------------------------------------------------------------------------ all four
def test_every_document_gets_all_four_check_records(tmp_path: Path) -> None:
    v = verify_document(ctx(tmp_path, pages=[], error="boom"), Ledger.load(tmp_path / "n.json"), TH,
                        fake_embed, _load_none, RunSeen())
    assert list(v.checks) == ["quality", "completeness", "recency", "uniqueness"]
    assert v.outcome == "quarantined" and "Q-EXTRACT-FAIL" in v.codes
    assert all(c.reason for c in v.checks.values())


def test_a_clean_new_document_is_accepted_and_carries_a_docvec(tmp_path: Path) -> None:
    v = verify_document(ctx(tmp_path), Ledger.load(tmp_path / "n.json"), TH, fake_embed,
                        _load_none, RunSeen())
    assert v.outcome == "accepted" and v.codes == [] and v.docvec and v.text_sha


def test_a_superseding_document_is_accepted_and_reports_what_it_supersedes(tmp_path: Path) -> None:
    led = _ledger(tmp_path, {"2023-08": CURRENT})
    v = verify_document(ctx(tmp_path, version="2026-06"), led, TH, fake_embed, _load_none, RunSeen())
    assert v.outcome == "accepted" and v.supersedes == [("attendance", "2023-08")]
