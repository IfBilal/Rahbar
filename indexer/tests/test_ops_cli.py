"""The ingestion CLI end to end: sync, restore, delete, count, build-index, unregister."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import run
from pipeline.ledger import ARCHIVED, CURRENT, DELETED, Ledger, ledger_lock

from .fakes import CountingEmbed, FakeClient
from .test_incremental import doc

# Distinct topics, so the near-duplicate check (rightly) treats these as different documents.
BETA = ("Library fines accrue every day after the due date and books must be returned within "
        "fourteen days of issue unless the member renews them online before the deadline. "
        "Lost books are replaced at the current market price plus a handling charge. ")
GAMMA = ("Hostel rooms are allotted by lottery each June to first year students who live more "
         "than fifty kilometres from the campus. Mess dues are collected monthly in advance and "
         "visitors must register at the gate before entering the residential blocks. ")


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("EMBED_MODEL", "fake-embed")
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("CHUNK_SIZE", "60")
    monkeypatch.setenv("CHUNK_OVERLAP", "10")
    client, embed = FakeClient(), CountingEmbed()
    monkeypatch.setattr("pipeline.store.get_client", lambda settings: client)
    monkeypatch.setattr("pipeline.embed.embed", lambda texts, settings: embed(texts))

    class Cli:
        def __init__(self) -> None:
            self.client, self.embed, self.data = client, embed, data

        def inbox(self, name: str, text: str) -> None:
            p = data / "inbox" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

        def go(self, *argv: str) -> tuple[int, dict]:
            capsys.readouterr()
            code = run.main(list(argv))
            lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")]
            return code, (json.loads(lines[-1]) if lines else {})

        def ledger(self) -> Ledger:
            return Ledger.load(data / "ledger" / "ledger.json")

        def collection(self, name: str = "rahbar"):
            return client.collections[name]

    return Cli()


def test_sync_prints_one_summary_line_writes_reports_and_a_ledger(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    code, s = cli.go("sync")
    assert code == 0 and s["type"] == "ingest_summary" and s["docs_new"] == 1
    reports = list((cli.data / "reports" / "verification").iterdir())
    assert {p.suffix for p in reports} == {".json", ".md"}
    assert cli.ledger().get("alpha-policy", "2026-06")["status"] == CURRENT
    registry = cli.collection("rahbar-registry").metadata
    assert registry["active"] == "rahbar" and registry["generation"] == "r0001"


def test_second_sync_embeds_nothing_and_keeps_the_revision(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    cli.embed.calls.clear()
    code, s = cli.go("sync")
    assert code == 0 and s["chunks_embedded"] == 0 and s["docs_unchanged"] == 1
    assert cli.embed.calls == [] and s["indexes"]["rahbar"]["revision_bumped"] is False
    assert cli.collection("rahbar-registry").metadata["generation"] == "r0001"


def test_quarantine_makes_exit_code_one_and_status_lists_the_rest(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.inbox("junk.txt", "x")
    code, s = cli.go("sync")
    assert code == 1 and s["docs_quarantined"] == 1 and s["exit"] == 1
    code, st = cli.go("status")
    assert code == 0 and st["quarantined"] == 1 and "alpha-policy" in st["documents"]


def test_restore_rolls_back_to_the_archived_version_without_embedding(cli) -> None:
    cli.inbox("r23.md", doc("Academic Rules", "Old. ", "2023-08"))
    cli.inbox("r26.md", doc("Academic Rules", "New. ", "2026-06"))
    cli.go("sync")
    cli.embed.calls.clear()
    code, s = cli.go("restore", "academic-rules@2023-08")
    assert code == 0 and s["chunks_embedded"] == 0 and cli.embed.calls == []
    led = cli.ledger()
    assert led.get("academic-rules", "2023-08")["status"] == CURRENT
    assert led.get("academic-rules", "2026-06")["status"] == ARCHIVED
    rows = cli.collection().rows
    old = [m for _, _, m in rows.values() if m["doc_version"] == "2023-08"]
    new = [m for _, _, m in rows.values() if m["doc_version"] == "2026-06"]
    assert old and all(m["superseded"] is False and m["status"] == "current" for m in old)
    assert new and all(m["superseded"] is True and m["status"] == "archived" for m in new)
    code, s2 = cli.go("restore", "academic-rules@2023-08")                  # already current: a no-op
    assert code == 0 and s2["noop"] is True
    code, s3 = cli.go("restore", "academic-rules@2026-06")                  # and back again
    assert code == 0 and cli.ledger().get("academic-rules", "2026-06")["status"] == CURRENT


def test_restore_of_an_unknown_version_exits_four(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    assert cli.go("restore", "alpha-policy@1999")[0] == 4


def test_delete_leaves_no_orphans_and_the_file_does_not_come_back(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.inbox("b.md", doc("Beta Policy", BETA))
    cli.go("sync")
    code, s = cli.go("delete", "beta-policy")
    assert code == 0 and s["chunks_deleted"] > 0
    assert not (cli.data / "inbox" / "b.md").exists()
    assert cli.ledger().get("beta-policy", "2026-06")["status"] == DELETED
    _, counted = cli.go("count", "--doc-id", "beta-policy")
    idx = counted["indexes"]["rahbar"]
    assert idx["per_doc"]["beta-policy@*"] == 0 and idx["orphans"] == [] and idx["missing"] == []
    assert idx["chroma_total"] == idx["ledger_expected_total"]
    code, s2 = cli.go("sync")
    assert s2["docs_new"] == 0 and s2["docs_deleted"] == 0
    assert cli.go("delete", "no-such-doc")[0] == 4


def test_count_reports_orphans_in_both_directions(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    col = cli.collection()
    col.add(["ghost"], ["x"], [[0.0] * 32], [{"doc_id": "ghost", "doc_version": "1"}])
    victim = cli.ledger().get("alpha-policy", "2026-06")["chunk_ids"][0]
    col.delete([victim])
    _, counted = cli.go("count")
    idx = counted["indexes"]["rahbar"]
    assert idx["orphans"] == ["ghost"] and idx["missing"] == [victim]


def test_a_held_lock_is_a_fatal_exit_three(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    lock = cli.data / "ledger" / "ingest.lock"
    with ledger_lock(lock, "other"):
        assert cli.go("sync")[0] == 3


def test_build_index_makes_a_candidate_collection_and_sync_keeps_it_current(cli, monkeypatch) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    live_before = dict(cli.collection().rows)
    code, s = cli.go("build-index", "--collection", "rahbar-cand", "--embed-model", "other-embed")
    assert code == 0 and s["chunks_embedded"] == len(live_before)
    assert cli.collection().rows == live_before                              # live index untouched
    cand = cli.collection("rahbar-cand")
    assert len(cand.rows) == len(live_before)
    assert cli.ledger().indexes["rahbar-cand"]["embed_model"] == "other-embed"
    cli.inbox("c.md", doc("Gamma Policy", GAMMA))
    _, s2 = cli.go("sync")
    assert set(s2["indexes"]) == {"rahbar", "rahbar-cand"}
    assert s2["indexes"]["rahbar-cand"]["chunks_embedded"] > 0 and s2["indexes"]["rahbar-cand"]["revision_bumped"]
    assert len(cli.collection("rahbar-cand").rows) == len(cli.collection().rows)


def test_candidate_with_other_chunk_size_is_rechunked_from_the_lake(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy", n=6))
    cli.go("sync")
    live = len(cli.collection().rows)
    code, s = cli.go("build-index", "--collection", "rahbar-small", "--embed-model", "fake-embed",
                     "--chunk-size", "30", "--chunk-overlap", "5")
    assert code == 0 and len(cli.collection("rahbar-small").rows) > live


def test_unregister_drops_a_candidate_but_never_the_live_index(cli) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    cli.go("build-index", "--collection", "rahbar-cand", "--embed-model", "other")
    assert cli.go("unregister", "--collection", "rahbar-cand")[0] == 0
    assert "rahbar-cand" not in cli.client.collections and "rahbar-cand" not in cli.ledger().indexes
    assert cli.go("unregister", "--collection", "rahbar")[0] == 4
    assert "rahbar" in cli.client.collections


def test_report_command_prints_the_stored_markdown(cli, capsys) -> None:
    cli.inbox("a.md", doc("Alpha Policy"))
    cli.go("sync")
    capsys.readouterr()
    assert run.main(["report", "--last", "--md"]) == 0
    out = capsys.readouterr().out
    assert "| document | quality |" in out and "a.md" in out


def test_legacy_invocation_without_a_command_still_means_the_a2_pipeline(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr(run, "run_pipeline", lambda s: called.setdefault("n", 7))
    assert run.main([]) == 0 and called["n"] == 7
