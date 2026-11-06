"""Semantic cache in Redis (3.3, ADR 0003).

A hit is a stored question whose embedding has cosine similarity >= CACHE_THRESHOLD with
the new question's embedding. Entries live in one Redis list per *scope*:

    rahbar:cache:<generation>:<embed model>:<llm model>:entries

so an answer can only be reused by the same index generation, embedding model and
generator that produced it. Invalidation on re-index: the indexer publishes a new
generation (it never talks to Redis; NetworkPolicy allows Redis from the API only), the
API sees the new generation id on its next request, and `observe()` deletes every key of
the old scope. Even before that delete lands, old entries are unreachable because the
scope in the key has changed.

shortcut: lookup scans the newest CACHE_MAX_ENTRIES vectors in Python (O(n), ~1 ms per 500
x 768 floats); move to RediSearch vector search if the cache ever needs to hold more.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

log = logging.getLogger("rahbar.cache")

PREFIX = "rahbar:cache:"
SCOPE_KEY = PREFIX + "current-scope"
TURNS_KEY = "rahbar:turns"          # outside PREFIX: a re-index must not erase the turn history


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else -1.0


class SemanticCache:
    def __init__(self, redis: Any, threshold: float, max_entries: int = 500,
                 ttl_seconds: int = 7 * 24 * 3600) -> None:
        self.redis = redis
        self.threshold = threshold
        self.max_entries = max_entries
        self.ttl = ttl_seconds

    @classmethod
    def from_url(cls, url: str, threshold: float, max_entries: int, ttl: int) -> SemanticCache:
        import redis

        client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2,
                                      decode_responses=True)
        return cls(client, threshold, max_entries, ttl)

    @staticmethod
    def entries_key(scope: str) -> str:
        return f"{PREFIX}{scope}:entries"

    def ping(self) -> bool:
        return bool(self.redis.ping())

    def observe(self, scope: str) -> int:
        """Invalidate on re-index: when the scope changed, delete the old scope's keys."""
        if self.redis.get(SCOPE_KEY) == scope:
            return 0
        stale = [k for k in self.redis.scan_iter(match=PREFIX + "*:entries")
                 if k != self.entries_key(scope)]
        if stale:
            self.redis.delete(*stale)
        self.redis.set(SCOPE_KEY, scope)
        log.info("cache scope changed; old entries expired",
                 extra={"scope": scope, "deleted_keys": len(stale)})
        return len(stale)

    def lookup(self, scope: str, vector: list[float]) -> tuple[dict | None, float]:
        """Best match at or above the threshold, as (stored response, similarity)."""
        best, best_score = None, -1.0
        for raw in self.redis.lrange(self.entries_key(scope), 0, self.max_entries - 1):
            entry = json.loads(raw)
            score = cosine(vector, entry["vector"])
            if score > best_score:
                best, best_score = entry, score
        if best is not None and best_score >= self.threshold:
            return best["response"], best_score
        return None, best_score

    def record_turn(self, turn: dict) -> None:
        """Step 8 of 3.2: keep every turn (question, answer, evidence ids), newest first,
        bounded by max_entries and expiring after ttl like the cache entries."""
        self.redis.lpush(TURNS_KEY, json.dumps(turn))
        self.redis.ltrim(TURNS_KEY, 0, self.max_entries - 1)
        self.redis.expire(TURNS_KEY, self.ttl)

    def store(self, scope: str, question: str, vector: list[float], response: dict) -> None:
        key = self.entries_key(scope)
        entry = {"question": question, "vector": vector, "response": response,
                 "stored_at": int(time.time())}
        self.redis.lpush(key, json.dumps(entry))
        self.redis.ltrim(key, 0, self.max_entries - 1)
        self.redis.expire(key, self.ttl)
