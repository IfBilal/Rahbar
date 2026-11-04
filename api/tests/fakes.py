"""Test doubles: no Chroma, Redis, Ollama or network anywhere in the unit tests."""

from __future__ import annotations

import fnmatch
from typing import Any

from app.schemas import Answer, Citation, Passage


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.ttl: dict[str, int] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("redis down")

    def ping(self) -> bool:
        self._check()
        return True

    def get(self, key: str) -> Any:
        self._check()
        return self.kv.get(key)

    def set(self, key: str, value: Any) -> None:
        self.kv[key] = value

    def scan_iter(self, match: str = "*"):
        return [k for k in list(self.kv) if fnmatch.fnmatch(k, match)]

    def delete(self, *keys: str) -> None:
        for k in keys:
            self.kv.pop(k, None)

    def lpush(self, key: str, value: str) -> None:
        self.kv.setdefault(key, []).insert(0, value)

    def ltrim(self, key: str, start: int, end: int) -> None:
        self.kv[key] = self.kv.get(key, [])[start:end + 1]

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        self._check()
        return self.kv.get(key, [])[start:end + 1]

    def expire(self, key: str, seconds: int) -> None:
        self.ttl[key] = seconds


def passage(n: int, score: float = 0.8, source: str = "rules.pdf", section: str | None = None,
            page: int = 1, text: str | None = None, superseded: bool = False) -> Passage:
    return Passage(chunk_id=f"c{n}", text=text or f"Passage {n} text.", source=source,
                   section=section or f"Section {n}", page=page, score=score,
                   doc_version="2023-08" if superseded else "2026-06", superseded=superseded)


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage], generation: str = "g1") -> None:
        self.passages = passages
        self.generation = generation
        self.calls = 0
        self.fail: Exception | None = None

    def retrieve(self, question: str, k: int) -> list[Passage]:
        self.calls += 1
        if self.fail:
            raise self.fail
        return self.passages[:k]

    def embed_query(self, question: str) -> list[float]:
        # deterministic toy embedding: similar wording -> similar vector
        words = question.lower().replace("?", "").split()
        return [float(sum(1 for w in words if w.startswith(c))) for c in "abcdefghijklmnopqrstuvwxyz"]


class ScriptedProvider:
    """Returns the queued answers (or raises the queued exceptions) in order."""

    name = "scripted"

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[str | None] = []

    def generate(self, question: str, passages: list[Passage],
                 retry_reason: str | None = None) -> Answer:
        self.calls.append(retry_reason)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def grounded(p: Passage, text: str = "The rule is X [1].") -> Answer:
    return Answer(reasoning="secret chain of thought", answer=text,
                  citations=[Citation(source=p.source, section=p.section, page=p.page)],
                  answered_from_context=True, confidence="high")


def declined() -> Answer:
    return Answer(reasoning="nothing relevant", answer="The documents do not cover this.",
                  citations=[], answered_from_context=False, confidence="low")
