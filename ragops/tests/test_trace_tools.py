"""The trace tools read what the API wrote (docs/a3-ragops/08)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ragops.trace import show, summary


def make(tmp: Path, tamper: bool = False) -> tuple[Path, Path, str]:
    traces, lake = tmp / "traces", tmp / "lake"
    (traces / "prompts").mkdir(parents=True)
    text = "Students need a CGPA of 2.00."
    sha8 = hashlib.sha256(text.encode()).hexdigest()[:8]
    cid = f"rules@2026-06#0000-{sha8}"
    d = lake / "lake" / "docs" / "rules" / "2026-06"
    d.mkdir(parents=True)
    (d / "chunks.jsonl").write_text(json.dumps({"chunk_id": cid, "text": text}) + "\n")
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": f"<evidence>{text}</evidence>"}]
    sha = show.prompt_hash(msgs)
    (traces / "prompts" / f"{sha}.json").write_text(json.dumps(
        {"sha256": sha, "messages": [{"role": "system", "content": "s"},
                                     {"role": "user", "content": "CHANGED"}] if tamper else msgs}))
    recs = []
    for i, (status, ms) in enumerate([("ok", 100.0), ("abstained", 10.0), ("ok", 300.0)]):
        recs.append({"type": "trace", "schema": 1, "trace_id": f"t{i}", "ts": f"2026-11-26T10:0{i}:00Z",
                     "route": "/api/ask", "status": status, "release_id": "R1", "pod": "p", "query": "q",
                     "embedding": {"model": "m", "version": "v"}, "collection": {"name": "rahbar", "revision": "r1"},
                     "retrieval": {"candidates": [{"rank": 1, "source": "a.pdf", "page": 2, "chunk_id": cid, "score": 0.9}]},
                     "guardrails": [{"rail": "injection", "action": "neutralised", "target": f"chunk:{cid}", "excerpt": "Ignore"}] if i == 0 else [],
                     "prompt": {"sha256": sha, "chunk_ids": [cid]} if i == 0 else None,
                     "model": {"provider": "x", "name": "y", "params": {}, "attempts": 1} if i == 0 else None,
                     "response": {"abstained": False, "confidence": "high", "citations": [], "answer": "a"} if i == 0 else None,
                     "latency_ms": {"total": ms, "generate": ms - 5}, "cache": {"hit": i == 2}})
    (traces / "p.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return traces, lake, cid


def test_show_verifies_the_prompt_and_rebuilds_chunks_from_the_lake(tmp_path, capsys) -> None:
    traces, lake, cid = make(tmp_path)
    assert show.main(["t0", "--traces", str(traces), "--lake", str(lake)]) == 0
    out = capsys.readouterr().out
    assert "prompt hash verified" in out and "rebuilt from snapshot" in out and "neutralised" in out


def test_show_detects_a_tampered_prompt_and_a_missing_trace(tmp_path) -> None:
    traces, lake, _ = make(tmp_path, tamper=True)
    assert show.main(["t0", "--traces", str(traces)]) == 5
    assert show.main(["nope", "--traces", str(traces)]) == 4
    assert show.main(["t0", "--traces", str(tmp_path / "missing")]) == 2


def test_show_fails_when_a_chunk_cannot_be_rebuilt(tmp_path) -> None:
    traces, lake, cid = make(tmp_path)
    (lake / "lake" / "docs" / "rules" / "2026-06" / "chunks.jsonl").write_text(
        json.dumps({"chunk_id": cid, "text": "different text now"}) + "\n")
    assert show.main(["t0", "--traces", str(traces), "--lake", str(lake)]) == 6


def test_summary_counts_and_percentiles(tmp_path, capsys) -> None:
    traces, _, _ = make(tmp_path)
    rows = summary.load(traces, None, None)
    s = summary.summarise(rows)
    assert s["requests"] == 3 and s["by_status"] == {"ok": 2, "abstained": 1}
    assert s["abstention_rate"] == round(1 / 3, 4) and s["cache_hit_rate"] == round(1 / 3, 4)
    assert s["guardrail_actions"] == {"injection:neutralised": 1}
    assert len(summary.load(traces, "2026-11-26T10:01:00Z", None)) == 2
    assert len(summary.load(traces, None, None, None, "2026-11-26T10:01:00Z")) == 1
    assert summary.main(["--traces", str(traces)]) == 0
    assert summary.main(["--traces", str(traces), "--route", "/nope"]) == 3


def test_summary_reports_the_top1_similarity_distribution_and_filters_by_release(tmp_path) -> None:
    """D3 asks for the top-1 retrieval similarity distribution; the first summary tool omitted it."""
    traces, _, _ = make(tmp_path)
    rows = summary.load(traces, None, None)
    # give the three traces known top-1 scores
    for r, score in zip(rows, (0.9, 0.7, 0.5)):
        r["retrieval"] = {"candidates": [{"score": score}, {"score": 0.1}]}
    t1 = summary.summarise(rows)["top1_similarity"]
    assert t1["n"] == 3 and t1["min"] == 0.5 and t1["max"] == 0.9 and t1["p50"] == 0.7
    release = rows[0].get("release_id")
    assert len(summary.load(traces, None, None, release)) >= 1
    assert summary.load(traces, None, None, "no-such-release") == []
    assert summary.main(["--traces", str(traces)]) == 0       # the CLI runs end to end on these traces


def test_show_prints_the_exact_prompt_and_context(tmp_path, capsys) -> None:
    """D2: the tool must print the exact context and prompt that produced the answer, not only their hash."""
    traces, lake, _ = make(tmp_path)
    assert show.main(["t0", "--traces", str(traces), "--lake", str(lake)]) == 0
    out = capsys.readouterr().out
    assert "PROMPT (exactly what the model received" in out
    assert "--- SYSTEM MESSAGE ---" in out and "--- USER MESSAGE ---" in out
    assert "<evidence>Students need a CGPA of 2.00.</evidence>" in out          # the retrieved context, verbatim
    assert show.main(["t0", "--traces", str(traces), "--no-prompt"]) == 0
    assert "PROMPT (exactly" not in capsys.readouterr().out
    assert show.main(["t0", "--traces", str(traces), "--json"]) == 0
    assert "prompt_messages" in capsys.readouterr().out
