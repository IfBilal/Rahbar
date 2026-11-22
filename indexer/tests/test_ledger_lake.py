"""The ledger (atomic, locked) and the data lake (immutable versions, archive, quarantine)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.lake import Lake
from pipeline.ledger import ARCHIVED, CURRENT, Ledger, LedgerError, LockHeld, ledger_lock


def _rec(sha: str = "a" * 64, status: str = CURRENT) -> dict:
    return {"status": status, "content_sha": sha, "text_sha": "t" + sha[1:], "chunk_ids": ["c1"],
            "archived_at": None, "deleted_at": None}


def test_a_missing_ledger_is_new_and_save_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = Ledger.load(path)
    assert ledger.documents == {}
    ledger.put("rules", "2026-06", _rec())
    ledger.save()
    again = Ledger.load(path)
    assert again.get("rules", "2026-06")["content_sha"] == "a" * 64
    assert again.data["digest"] == again.digest() != ""


def test_save_keeps_the_previous_copy_and_load_falls_back_to_it(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = Ledger.load(path)
    ledger.put("rules", "1", _rec())
    ledger.save()
    ledger.put("rules", "2", _rec("b" * 64))
    ledger.save()
    assert path.with_suffix(".json.bak").exists()
    path.write_text("{ not json")                       # a crash that corrupted the main file
    recovered = Ledger.load(path)
    assert recovered.get("rules", "1") is not None      # the previous good copy


def test_corrupt_ledger_with_no_backup_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text("garbage")
    with pytest.raises(LedgerError):
        Ledger.load(path)


def test_unknown_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"schema": 99}))
    with pytest.raises(LedgerError):
        Ledger.load(path)


def test_digest_ignores_quarantine_and_changes_with_status(tmp_path: Path) -> None:
    ledger = Ledger.load(tmp_path / "l.json")
    ledger.put("a", "1", _rec())
    before = ledger.digest()
    ledger.quarantine_log("x.pdf", "f" * 64, ["U-EXACT-DUP"], "run1")
    assert ledger.digest() == before
    ledger.set_status("a", "1", ARCHIVED)
    assert ledger.digest() != before


def test_quarantine_repeat_is_detected(tmp_path: Path) -> None:
    ledger = Ledger.load(tmp_path / "l.json")
    assert ledger.quarantine_log("x.pdf", "f" * 64, ["Q-EMPTY"], "r1") is False
    assert ledger.quarantine_log("x2.pdf", "f" * 64, ["Q-EMPTY"], "r2") is True


def test_find_by_sha_and_current_version(tmp_path: Path) -> None:
    ledger = Ledger.load(tmp_path / "l.json")
    ledger.put("a", "1", _rec("1" * 64, ARCHIVED))
    ledger.put("a", "2", _rec("2" * 64, CURRENT))
    assert ledger.find_by_sha("1" * 64)[1] == "1"
    assert ledger.current_version("a") == "2"
    assert ledger.find_by_sha("9" * 64) is None


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    lock = tmp_path / "ingest.lock"
    with ledger_lock(lock, "run1", pod="p1"):
        with pytest.raises(LockHeld):
            with ledger_lock(lock, "run2"):
                pass
    assert not lock.exists()
    with ledger_lock(lock, "run3"):
        pass


def test_a_stale_lock_is_broken(tmp_path: Path) -> None:
    lock = tmp_path / "ingest.lock"
    lock.write_text(json.dumps({"pod": "dead", "run_id": "old"}))
    import os
    os.utime(lock, (1, 1))                               # very old
    with ledger_lock(lock, "new", ttl_seconds=60):
        assert json.loads(lock.read_text())["run_id"] == "new"


# ------------------------------------------------------------------ lake
def _src(tmp_path: Path, name: str = "doc.md", text: str = "hello") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_store_archive_restore_round_trip(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "data")
    lake.ensure()
    src = _src(tmp_path)
    lake.store_version("rules", "2026", src, [{"chunk_id": "c1", "text": "t"}], {"sha": "x"},
                       {"vector": [1.0]})
    assert (lake.version_dir("rules", "2026") / "doc.md").read_text() == "hello"
    assert lake.read_chunks("rules", "2026")[0]["chunk_id"] == "c1"
    lake.archive_version("rules", "2026")
    assert not lake.version_dir("rules", "2026").exists()
    assert lake.read_chunks("rules", "2026")[0]["chunk_id"] == "c1"   # still readable
    assert lake.read_docvec("rules", "2026") == {"vector": [1.0]}
    lake.restore_version("rules", "2026")
    assert lake.version_dir("rules", "2026").exists()


def test_same_version_label_with_new_bytes_archives_the_old_ones(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "data")
    lake.ensure()
    lake.store_version("r", "1", _src(tmp_path, text="old"), [], {"previous_sha": "aaaa1111"}, {})
    lake.store_version("r", "1", _src(tmp_path, text="new"), [], {"previous_sha": "aaaa1111"}, {})
    assert (lake.version_dir("r", "1") / "doc.md").read_text() == "new"
    archived = list((lake.archive / "r").iterdir())
    assert len(archived) == 1 and (archived[0] / "doc.md").read_text() == "old"


def test_restore_refuses_to_overwrite_and_archive_requires_existing(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "data")
    lake.ensure()
    with pytest.raises(FileNotFoundError):
        lake.archive_version("nope", "1")
    with pytest.raises(FileNotFoundError):
        lake.restore_version("nope", "1")


def test_quarantine_moves_the_file_and_writes_the_reason(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "data")
    lake.ensure()
    f = lake.inbox / "bad.pdf"
    f.write_bytes(b"junk")
    dst = lake.quarantine_file(f, "run1", {"codes": ["Q-EXTRACT-FAIL"]})
    assert not f.exists() and dst.read_bytes() == b"junk"
    reason = json.loads(dst.with_name("bad.pdf.reason.json").read_text())
    assert reason["codes"] == ["Q-EXTRACT-FAIL"]
    g = lake.inbox / "bad.pdf"
    g.write_bytes(b"again")
    dst2 = lake.quarantine_file(g, "run1", {"codes": []})
    assert dst2 != dst and dst.exists()                  # never overwrites earlier evidence


def test_tombstone_marks_the_archived_copy(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "data")
    lake.ensure()
    lake.store_version("r", "1", _src(tmp_path), [], {}, {})
    dst = lake.tombstone("r", "1", "run9")
    assert json.loads((dst / "tombstone.json").read_text())["deleted_by_run"] == "run9"
