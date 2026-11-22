"""Batch B end to end: every planted problem is handled as corpus/batch-b/README.md says.

Batch A is stood in for by a few small documents (the real corpus is third-party and is
fetched on the cluster); the two exact duplicates are copies of two of those stand-ins.
The verification uses the real extractors and checks, with a deterministic fake embedder.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from pipeline.verify import Thresholds

from .pdfmaker import text_pdf
from .test_incremental import Env, doc

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("batch_b_build", ROOT / "corpus" / "batch-b" / "build.py")
build_mod = importlib.util.module_from_spec(_spec)           # type: ignore[arg-type]
_spec.loader.exec_module(build_mod)                          # type: ignore[union-attr]

HANDBOOK = ["Student Handbook", "Version 2026-06", "",
            "Students must carry the university card at all times on campus and show it to "
            "the security staff when they are asked to do so at any gate or building entrance."]
GRADING = ("<html><head><title>Grading Page</title><meta name='date' content='2026'></head><body>"
           "<h1>Grading Page</h1><p>A grade of A means excellent work and carries four grade "
           "points. A grade of B carries three grade points and a grade of C carries two grade "
           "points. A grade of F means that the student has failed the course and must repeat it "
           "in a later semester, which is described in the academic rules of the university.</p>"
           "</body></html>")


@pytest.fixture
def world(tmp_path: Path):
    env = Env(tmp_path / "w")
    pdf = text_pdf(tmp_path / "handbook.pdf", [[(50.0, 60.0 + 16 * i, t) for i, t in enumerate(HANDBOOK)]
                                                + [(50.0, 140.0 + 16 * i, f"{t}.") for i, t in enumerate(
                                                    ["Visitors must register at the main gate before they enter the campus",
                                                     "Lost cards must be reported to the student affairs office on the same day",
                                                     "A replacement card is issued after the payment of a small fee"])]])
    html = tmp_path / "grading.html"
    html.write_text(GRADING)
    env.put("student-handbook-jun-2026.pdf", pdf.read_bytes())
    env.put("grading-page.html", GRADING)
    env.put("fee-policy.md", doc("Fee Policy", "Tuition fees are due in August and in January of each year. "))
    env.put("faculty-2022.md", "---\ntitle: Faculty Entrepreneurship and Technical Start-ups Policy\n"
            "doc_id: faculty-entrepreneurship-and-technical-start-ups-policy\ndoc_version: 2022-05\n---\n"
            "# Start-ups\n\nThe university receives an equity share of ten percent in every start-up "
            "that uses university facilities, and the committee reviews applications within thirty "
            "days of receiving them. " * 4)
    first, _ = env.run()
    assert first.summary["docs_quarantined"] == 0, first.verification["documents"]
    out = tmp_path / "out"
    build_mod.build(out, real_pdf=pdf, real_html=html)
    return env, out, first


def by_name(res) -> dict:
    return {d["file"].split("/")[-1]: d for d in res.verification["documents"]}


def test_batch_b_plants_are_each_handled_as_documented(world, tmp_path: Path) -> None:
    env, out, _ = world
    shutil.copytree(out / "batch-b", env.lake.inbox / "batch-b")
    env.embed.calls.clear()
    res, led = env.run()
    d = by_name(res)
    code = lambda f, c: d[f]["checks"][c]["code"]                                   # noqa: E731
    # the four problems the PDF names, one check each
    assert code("Student_Handbook_Copy.pdf", "uniqueness") == "U-EXACT-DUP"        # B01
    assert code("grading-page-backup.html", "uniqueness") == "U-EXACT-DUP"         # B02
    assert code("library-lending-regulations.md", "uniqueness") == "U-NEAR-DUP"    # B03
    assert code("lab-safety-notice.pdf", "quality") == "Q-EXTRACT-FAIL"            # B04
    assert code("exam-schedule-policy-trunc.md", "completeness") == "C-TRUNCATED"  # B05
    assert code("untitled-notes.txt", "completeness") == "C-MISSING-TITLE"         # B06
    assert d["untitled-notes.txt"]["checks"]["completeness"]["evidence"]["codes"] == [
        "C-MISSING-TITLE", "C-MISSING-DATE-VERSION"]
    quarantined = {"Student_Handbook_Copy.pdf", "grading-page-backup.html", "library-lending-regulations.md",
                   "lab-safety-notice.pdf", "exam-schedule-policy-trunc.md", "untitled-notes.txt"}
    assert {f for f, v in d.items() if v["outcome"] == "quarantined"} == quarantined
    for f in quarantined:
        assert all(len(d[f]["checks"]) == 4 for f in d)
        assert env.index.count_where({"source": f}) == 0                           # never indexed
    # the newer version (B07) passes and archives the 2022 edition; the rest are accepted
    assert code("faculty-entrepreneurship-policy-2026.md", "recency") == "R-SUPERSEDES"
    assert [r["code"] for r in res.verification["reevaluated"]] == ["R-SUPERSEDED-BY"]
    assert led.get("faculty-entrepreneurship-and-technical-start-ups-policy", "2022-05")["status"] == "archived"
    for f in ("faculty-entrepreneurship-policy-2026.md", "campus-parking-policy.md",   # B07, B08
              "library-borrowing-rules.md", "student-clubs-guidelines.pdf",            # B09, B10
              "transport-routes-2026.html", "scholarship-faq.md"):                     # B11, B12
        assert d[f]["outcome"] == "accepted", (f, d[f]["checks"])
    assert res.summary["docs_quarantined"] == 6 and res.summary["docs_new"] == 6
    fb = res.verification["summary"]["failures_by_check"]
    assert fb["uniqueness"] == 3 and fb["completeness"] == 3 and fb["quality"] == 1   # B04 also has no page count
    assert fb["recency"] == 1                       # the re-evaluated 2022 edition (R-SUPERSEDED-BY)


def test_the_injected_document_passes_every_check_and_is_indexed(world) -> None:
    env, out, _ = world
    shutil.copytree(out / "batch-b", env.lake.inbox / "batch-b")
    res, _ = env.run()
    parking = by_name(res)["campus-parking-policy.md"]
    assert parking["outcome"] == "accepted" and all(c["status"] == "pass" for c in parking["checks"].values())
    texts = " ".join(t for t, _, m in env.index.rows.values() if m["doc_id"] == "campus-parking-policy")
    assert "Ignore all previous instructions" in texts          # still there: the rail handles it at query time


def test_the_late_old_version_is_quarantined_by_recency(world) -> None:
    env, out, _ = world
    shutil.copytree(out / "batch-b", env.lake.inbox / "batch-b")
    env.run()
    shutil.copytree(out / "late" / "batch-b", env.lake.inbox / "batch-b", dirs_exist_ok=True)
    res, led = env.run()
    d = by_name(res)["faculty-entrepreneurship-policy-2019.md"]
    assert d["checks"]["recency"]["code"] == "R-NEWER-EXISTS" and d["outcome"] == "quarantined"
    assert led.get("faculty-entrepreneurship-and-technical-start-ups-policy", "2019-01") is None


def test_batch_b_is_tagged_b_and_a_rerun_embeds_nothing(world) -> None:
    env, out, _ = world
    shutil.copytree(out / "batch-b", env.lake.inbox / "batch-b")
    env.run()
    led_batches = env.run()[1].data["batches"]
    assert led_batches == ["A", "B"]
    env.embed.calls.clear()
    res, _ = env.run()
    assert res.summary["chunks_embedded"] == 0 and res.summary["verification_embeddings"] == 0
    assert res.summary["docs_unchanged"] >= 6 and env.embed.calls == []
    assert Thresholds().near_dup_cosine == 0.97
