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


def test_turns_are_stored_bounded_and_survive_a_reindex() -> None:
    from app.services.cache import TURNS_KEY

    redis = FakeRedis()
    cache = SemanticCache(redis, threshold=0.9, max_entries=2, ttl_seconds=60)
    for i in range(3):
        cache.record_turn({"request_id": f"r{i}", "question": f"q{i}"})
    kept = [json.loads(x)["request_id"] for x in redis.lrange(TURNS_KEY, 0, 9)]
    assert kept == ["r2", "r1"] and redis.ttl[TURNS_KEY] == 60
    cache.observe("new-generation")                     # a re-index expires answers, not turns
    assert len(redis.lrange(TURNS_KEY, 0, 9)) == 2


def test_the_ask_route_stores_the_turn_and_survives_redis_failure() -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.cache import TURNS_KEY

    redis = FakeRedis()
    with TestClient(app) as client:
        app.state.cache = SemanticCache(redis, threshold=0.99)
        r = client.post("/api/ask", json={"question": "What is the attendance rule?"}).json()
        turn = json.loads(redis.lrange(TURNS_KEY, 0, 0)[0])
        assert turn["request_id"] == r["request_id"] and turn["question"].startswith("What")
        assert turn["answer"] == r["answer"]
        redis.down = True
        redis.lpush = lambda *a: (_ for _ in ()).throw(ConnectionError("down"))  # type: ignore[method-assign]
        assert client.post("/api/ask", json={"question": "What is the attendance rule?"}).status_code == 200
