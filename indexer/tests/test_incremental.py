"""Incremental ingestion end to end over a temp inbox, a fake index and a fake embedder."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.extract import extract
from pipeline.incremental import SyncConfig, Target, sync
from pipeline.lake import Lake
from pipeline.ledger import ARCHIVED, CURRENT, DELETED, Ledger
from pipeline.verify import Thresholds

from .fakes import CountingEmbed, FakeIndex

BODY = ("Students must keep an attendance of at least eighty percent in every course during "
        "the semester. A student below this requirement shall not sit in the final examination "
        "of that course. The dean may grant relief in exceptional cases after reviewing the "
        "application submitted by the student. ")


def doc(title: str, extra: str = "", version: str = "2026-06", n: int = 3) -> str:
    return f"---\ntitle: {title}\ndoc_version: {version}\n---\n# {title}\n\n" + (BODY + extra + "\n\n") * n


class Env:
    def __init__(self, tmp: Path, ocr: bool = False) -> None:
        self.lake = Lake(tmp / "data")
        self.lake.ensure()
        self.index = FakeIndex()
        self.embed = CountingEmbed()
        self.n = 0
        self.ocr = ocr

    def put(self, name: str, text: str | bytes) -> Path:
        p = self.lake.inbox / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode())
        return p

    def run(self, th: Thresholds | None = None):
        self.n += 1
        ledger = Ledger.load(self.lake.ledger_dir / "ledger.json")
        target = Target(self.index, self.embed, "fake-embed", 60, 10)
        cfg = SyncConfig(run_id=f"run{self.n}", thresholds=th or Thresholds(), extract=extract,
                         ocr=self.ocr)
        res = sync(self.lake, ledger, [target], cfg, self.embed)
        ledger.save()
        return res, Ledger.load(self.lake.ledger_dir / "ledger.json")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_first_sync_builds_everything(env: Env) -> None:
    env.put("attendance.md", doc("Attendance Policy"))
    env.put("fees.md", doc("Fee Policy", "Fees are due in August. "))
    res, ledger = env.run()
    s = res.summary
    assert s["docs_new"] == 2 and s["docs_quarantined"] == 0 and res.exit_code == 0
    assert s["chunks_embedded"] == s["chunks_written"] == env.index.count() > 4
    assert s["indexes"]["rahbar"]["revision"] == "r0001" and s["indexes"]["rahbar"]["revision_bumped"]
    assert set(ledger.documents) == {"attendance-policy", "fee-policy"}
    v = ledger.get("attendance-policy", "2026-06")
    assert v["status"] == CURRENT and v["chunk_ids"] and (env.lake.root / v["lake_path"]).is_dir()
    meta = next(iter(env.index.rows.values()))[2]
    assert {"source", "section", "page", "doc_version", "superseded"} <= set(meta)
    assert meta["doc_id"] and meta["status"] == "current" and meta["superseded"] is False


def test_second_run_on_an_unchanged_corpus_embeds_zero_chunks(env: Env) -> None:
    env.put("attendance.md", doc("Attendance Policy"))
    env.put("fees.md", doc("Fee Policy", "Fees are due in August. "))
    env.run()
    env.embed.calls.clear()
    env.index.writes.clear()
    res, _ = env.run()
    s = res.summary
    assert s["docs_unchanged"] == 2 and s["docs_new"] == 0
    assert s["chunks_embedded"] == 0 and s["verification_embeddings"] == 0
    assert env.embed.calls == [] and env.index.writes == []         # the embedder was never called
    assert s["indexes"]["rahbar"]["revision_bumped"] is False and s["indexes"]["rahbar"]["revision"] == "r0001"


def test_a_changed_document_replaces_only_its_own_chunks(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    env.put("b.md", doc("Beta Policy", "Beta only. "))
    _, led = env.run()
    b_before = set(led.get("beta-policy", "2026-06")["chunk_ids"])
    a_before = set(led.get("alpha-policy", "2026-06")["chunk_ids"])
    env.put("a.md", doc("Alpha Policy", "A brand new sentence about library fines. "))
    res, led = env.run()
    assert res.summary["docs_updated"] == 1 and res.summary["docs_unchanged"] == 1
    a_after = set(led.get("alpha-policy", "2026-06")["chunk_ids"])
    assert a_after != a_before and set(led.get("beta-policy", "2026-06")["chunk_ids"]) == b_before
    assert set(env.index.ids_where({"doc_id": "alpha-policy"})) == a_after
    assert b_before <= set(env.index.all_ids())
    assert env.index.count() == len(a_after) + len(b_before)         # no orphans of the old Alpha
    assert res.summary["indexes"]["rahbar"]["revision"] == "r0002"


def test_deleting_a_file_leaves_no_orphan_chunks_and_keeps_the_bytes(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    env.put("b.md", doc("Beta Policy", "Beta only. "))
    env.run()
    (env.lake.inbox / "b.md").unlink()
    res, led = env.run()
    assert res.summary["docs_deleted"] == 1 and res.summary["chunks_deleted"] > 0
    assert env.index.count_where({"doc_id": "beta-policy"}) == 0
    assert led.get("beta-policy", "2026-06")["status"] == DELETED
    assert (env.lake.archive / "beta-policy" / "2026-06" / "tombstone.json").exists()
    assert set(env.index.all_ids()) == set(led.get("alpha-policy", "2026-06")["chunk_ids"])


def test_older_and_newer_edition_in_one_run_archive_the_old_without_quarantine(env: Env) -> None:
    env.put("rules-2023.md", doc("Academic Rules", "Old rule eighty. ", version="2023-08"))
    env.put("rules-2026.md", doc("Academic Rules", "New rule seventy. ", version="2026-06"))
    res, led = env.run()
    assert res.summary["docs_quarantined"] == 0 and res.summary["docs_superseded"] == 1
    assert led.get("academic-rules", "2023-08")["status"] == ARCHIVED
    assert led.get("academic-rules", "2026-06")["status"] == CURRENT
    old = env.index.ids_where({"$and": [{"doc_id": "academic-rules"}, {"doc_version": "2023-08"}]})
    assert old and all(env.index.rows[i][2]["superseded"] is True
                       and env.index.rows[i][2]["status"] == "archived" for i in old)
    assert (env.lake.archive / "academic-rules" / "2023-08").is_dir()
    assert res.verification["reevaluated"][0]["code"] == "R-SUPERSEDED-BY"
    new = env.index.ids_where({"$and": [{"doc_id": "academic-rules"}, {"doc_version": "2026-06"}]})
    assert all(env.index.rows[i][2]["superseded"] is False for i in new)


def test_a_newer_version_arriving_later_archives_the_old_one_without_re_embedding_it(env: Env) -> None:
    env.put("p-2022.md", doc("Entrepreneurship Policy", "Original clause. ", version="2022-05"))
    env.run()
    env.embed.calls.clear()
    env.put("p-2026.md", doc("Entrepreneurship Policy", "Amended clause. ", version="2026-11"))
    res, led = env.run()
    assert led.get("entrepreneurship-policy", "2022-05")["status"] == ARCHIVED
    new_chunks = len(led.get("entrepreneurship-policy", "2026-11")["chunk_ids"])
    old_rows = env.lake.read_chunks("entrepreneurship-policy", "2022-05")
    assert old_rows                                          # snapshots stay readable after archiving
    embedded = {t for call in env.embed.calls for t in call}
    assert not embedded & {r["text"] for r in old_rows}      # the old version was NOT re-embedded
    assert env.embed.texts_embedded >= new_chunks
    assert res.summary["docs_superseded"] == 1


def test_a_late_stale_file_is_quarantined_not_indexed(env: Env) -> None:
    env.put("p-2026.md", doc("Entrepreneurship Policy", "Amended. ", version="2026-11"))
    env.run()
    env.put("p-2019.md", doc("Entrepreneurship Policy", "Ancient. ", version="2019-01"))
    res, led = env.run()
    assert res.summary["docs_quarantined"] == 1 and res.exit_code == 1
    rec = res.verification["documents"][0]
    assert rec["checks"]["recency"]["code"] == "R-NEWER-EXISTS" and rec["outcome"] == "quarantined"
    assert led.get("entrepreneurship-policy", "2019-01") is None
    assert not (env.lake.inbox / "p-2019.md").exists()
    assert (env.lake.quarantine / "run2" / "p-2019.md.reason.json").exists()
    assert env.index.count_where({"doc_version": "2019-01"}) == 0


def test_planted_problems_are_each_caught_and_never_indexed(env: Env) -> None:
    good = doc("Library Rules", "Fines are two rupees a day. ")
    env.put("library.md", good)
    env.run()
    env.put("library-copy.md", good)                                       # exact duplicate
    env.put("library-near.md", good.replace("eighty", "seventy five").replace("Library Rules", "Library Rules"))
    env.put("notes.txt", "just some words with no heading and nothing like a date " * 12)  # no metadata
    env.put("cut.md", "---\ntitle: Exam Policy\ndoc_version: 2026-01\n---\n" + BODY * 3
            + "\nPage 2 of 5\n\n```\nand then the file simply stops in the middle of")
    env.put("corrupt.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\n")
    res, led = env.run()
    by_file = {d["file"]: d for d in res.verification["documents"]}
    assert by_file["library-copy.md"]["checks"]["uniqueness"]["code"] == "U-EXACT-DUP"
    assert by_file["notes.txt"]["checks"]["completeness"]["status"] == "fail"
    assert by_file["cut.md"]["checks"]["completeness"]["code"] == "C-TRUNCATED"
    assert by_file["corrupt.pdf"]["checks"]["quality"]["code"] == "Q-EXTRACT-FAIL"
    for name in ("library-copy.md", "notes.txt", "cut.md", "corrupt.pdf"):
        assert by_file[name]["outcome"] == "quarantined"
        assert env.index.count_where({"source": name}) == 0
        assert all(len(d["checks"]) == 4 for d in by_file.values())
    assert env.index.count_where({"doc_id": "library-rules"}) == len(
        led.get("library-rules", "2026-06")["chunk_ids"])


def test_a_changed_file_that_fails_verification_keeps_the_old_version(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    _, led = env.run()
    before = set(led.get("alpha-policy", "2026-06")["chunk_ids"])
    env.put("a.md", "x")                                                    # replaced by junk
    res, led = env.run()
    assert res.summary["docs_quarantined"] == 1
    assert set(env.index.ids_where({"doc_id": "alpha-policy"})) == before   # still serving
    res, led = env.run()                                                    # and a later run must not delete it
    assert res.summary["docs_deleted"] == 0 and set(env.index.ids_where({"doc_id": "alpha-policy"})) == before


def test_a_renamed_file_is_not_re_embedded(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    env.run()
    env.embed.calls.clear()
    (env.lake.inbox / "a.md").rename(env.lake.inbox / "alpha-renamed.md")
    res, led = env.run()
    assert res.summary["docs_renamed"] == 1 and res.summary["chunks_embedded"] == 0
    assert env.embed.calls == [] and led.get("alpha-policy", "2026-06")["status"] == CURRENT
    assert res.summary["docs_deleted"] == 0 and res.summary["docs_quarantined"] == 0


def test_a_run_that_died_before_the_ledger_is_healed(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    _, led = env.run()
    ids = led.get("alpha-policy", "2026-06")["chunk_ids"]
    env.index.delete(ids[:2])                                                # chunks lost
    env.index.add(["ghost"], ["x"], [[0.0] * 32], [{"doc_id": "alpha-policy", "doc_version": "2026-06"}])
    res, _ = env.run()
    assert res.summary["repairs"] == 3
    assert set(env.index.ids_where({"doc_id": "alpha-policy"})) == set(ids)


def test_an_embedding_failure_leaves_the_old_state_untouched(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    _, led = env.run()
    before = dict(env.index.rows)
    env.put("a.md", doc("Alpha Policy", "Something new. "))

    def boom(texts):
        raise RuntimeError("ollama down")
    env.embed = boom                                                          # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        env.run()
    assert env.index.rows == before


def test_report_has_four_checks_per_document_and_failure_counts(env: Env) -> None:
    env.put("a.md", doc("Alpha Policy"))
    env.put("junk.txt", "x")
    res, _ = env.run()
    fb = res.verification["summary"]["failures_by_check"]
    assert fb["quality"] == 1 and set(fb) == {"quality", "completeness", "recency", "uniqueness"}
    from pipeline.report import render_markdown
    md = render_markdown(res.verification)
    assert "| document | quality | complete | recency | unique | outcome |" in md
    assert "junk.txt" in md and "FAIL" in md and "PASS" in md
    block = md.split("**junk.txt**")[1].split("**")[0]      # every check has a status and a reason
    for c in ("quality", "completeness", "recency", "uniqueness"):
        assert f"- {c}: " in block
    assert md.count("Q-OK") >= 1 and "…" not in md
