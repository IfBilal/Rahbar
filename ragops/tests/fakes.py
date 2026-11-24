"""Fakes for the suite's two services, with the same methods as the real clients."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FakeEmbedder:
    """Deterministic bag-of-words vectors: shared words => higher cosine."""

    def __init__(self, model: str = "nomic-embed-text", noise: float = 0.0) -> None:
        self.model, self.noise, self.calls = model, noise, 0
        self.vocab = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            self.calls += 1
            v = [0.0] * self.vocab
            for w in t.lower().replace("search_query:", "").split():
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.vocab] += 1.0
            if self.noise:
                v[0] += self.noise * (self.calls % 7)
            out.append(v)
        return out


class FakeJudge:
    model = "fake-judge"

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = replies or ['{"label": "supported", "unsupported_claims": []}']
        self.n = 0

    def generate_json(self, prompt: str, seed: int) -> str:
        r = self.replies[self.n % len(self.replies)]
        self.n += 1
        return r


class FakeApi:
    """A tiny RAG: every question has a table of (source, page) it retrieves."""

    def __init__(self, retrieval: dict[str, list[tuple[str, int]]] | None = None,
                 trace_dir: Path | None = None, abstain_all: bool = False) -> None:
        self.retrieval = retrieval or {}
        self.trace_dir = trace_dir
        self.abstain_all = abstain_all
        self.asks = 0

    def target_info(self) -> dict[str, Any]:
        return {"url": "http://fake", "release_id": "R1-nomic", "collection": "rahbar",
                "revision": "r0001", "embed_model": "nomic-embed-text", "embed_version": "x",
                "app_version": "t"}

    def retrieve(self, question: str, k: int) -> dict[str, Any]:
        pairs = self.retrieval.get(question.lower(), [("other.pdf", 1)] * k)
        return {"trace_id": "t-r", "_seconds": 0.01,
                "candidates": [{"rank": i + 1, "chunk_id": f"c{i}", "source": s, "page": p,
                                "score": 0.9 - 0.1 * i, "superseded": False}
                               for i, (s, p) in enumerate(pairs[:k])]}

    def ask(self, question: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        self.asks += 1
        pairs = self.retrieval.get(question.lower(), [])
        answered = bool(pairs) and not self.abstain_all
        tid = f"trace-{self.asks}"
        if self.trace_dir is not None and answered:
            self._write_trace(tid, pairs)
        return {"answer": "The minimum CGPA is 2.00." if answered else "not in the documents",
                "citations": [{"source": s, "section": "x", "page": p} for s, p in pairs[:1]]
                if answered else [],
                "answered_from_context": answered, "confidence": "high",
                "retrieved": [{"chunk_id": "c", "source": s, "section": "x", "page": p, "score": 0.9}
                              for s, p in pairs], "provider": "fake", "cached": False,
                "trace_id": tid, "tokens": {"in": 100, "out": 10},
                "_seconds": 1.0 + 0.1 * self.asks, "_headers": {"x-trace-id": tid}}

    def _write_trace(self, tid: str, pairs: list[tuple[str, int]]) -> None:
        assert self.trace_dir is not None
        (self.trace_dir / "prompts").mkdir(parents=True, exist_ok=True)
        messages = [{"role": "system", "content": "rules"},
                    {"role": "user", "content": "Passage: the minimum CGPA is 2.00 to avoid warning"}]
        sha = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        (self.trace_dir / "prompts" / f"{sha}.json").write_text(
            json.dumps({"sha256": sha, "messages": messages}), encoding="utf-8")
        with (self.trace_dir / "pod.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "trace", "trace_id": tid, "prompt": {"sha256": sha}}) + "\n")


def golden_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(1, 7):
        rows.append({"id": f"g{i:03d}", "question": f"question number {i} about rules",
                     "category": "answerable", "answerable": True, "origin": "human",
                     "gold": [{"doc": "rules.pdf", "page": i}], "must_not": []})
    rows.append({"id": "g007", "question": "what is the hostel fee", "category": "unanswerable",
                 "answerable": False, "origin": "human", "gold": []})
    rows.append({"id": "g008", "question": "bus timing zeta", "category": "hard",
                 "hard_kind": "batch_b", "answerable": True, "origin": "human",
                 "gold": [{"doc": "transport.html", "page": 1}], "requires_batch": ["B"]})
    return rows


def good_retrieval() -> dict[str, list[tuple[str, int]]]:
    return {r["question"].lower(): [(g["doc"], g["page"]) for g in r["gold"]]
            for r in golden_rows() if r["gold"]}
