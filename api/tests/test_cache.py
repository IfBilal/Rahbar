"""The semantic cache: threshold, bounds, scope invalidation."""

from __future__ import annotations

import json

from app.services.cache import SCOPE_KEY, SemanticCache, cosine

from .fakes import FakeRedis


def test_cosine_edges() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0
    assert abs(cosine([1, 0], [0, 1])) < 1e-12
    assert cosine([0, 0], [1, 0]) == -1.0 and cosine([1], [1, 0]) == -1.0


def test_hit_at_threshold_miss_below() -> None:
    cache = SemanticCache(FakeRedis(), threshold=0.9)
    cache.store("s", "q", [1.0, 0.0], {"answer": "A"})
    hit, score = cache.lookup("s", [1.0, 0.1])                 # cos ~ 0.995
    assert hit == {"answer": "A"} and score > 0.99
    miss, score = cache.lookup("s", [1.0, 1.0])                # cos ~ 0.707
    assert miss is None and 0.7 < score < 0.71


def test_scopes_do_not_share_answers() -> None:
    cache = SemanticCache(FakeRedis(), threshold=0.5)
    cache.store("g1:model", "q", [1.0], {"answer": "old"})
    assert cache.lookup("g2:model", [1.0])[0] is None


def test_observe_deletes_the_old_scope_once() -> None:
    redis = FakeRedis()
    cache = SemanticCache(redis, threshold=0.5)
    cache.observe("g1")
    cache.store("g1", "q", [1.0], {"answer": "old"})
    assert cache.observe("g1") == 0
    assert cache.observe("g2") == 1
    assert redis.get(SCOPE_KEY) == "g2" and cache.entries_key("g1") not in redis.kv


def test_store_is_bounded_and_expires() -> None:
    redis = FakeRedis()
    cache = SemanticCache(redis, threshold=0.5, max_entries=3, ttl_seconds=60)
    for i in range(5):
        cache.store("s", f"q{i}", [float(i)], {"n": i})
    key = cache.entries_key("s")
    assert [json.loads(x)["question"] for x in redis.kv[key]] == ["q4", "q3", "q2"]
    assert redis.ttl[key] == 60
