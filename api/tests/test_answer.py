"""The eight-step pipeline: floor, retry, fallback, cache, logging. No network."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.routes import metrics as m
from app.schemas import Answer, Citation
from app.services.answer import ABSTAIN_TEXT, FALLBACK_TEXT, answer_question
from app.services.cache import SemanticCache

from .fakes import FakeRedis, FakeRetriever, ScriptedProvider, declined, grounded, passage

S = Settings(relevance_floor=0.5, top_k=5, cache_threshold=0.95)
P = [passage(1, 0.82), passage(2, 0.71), passage(3, 0.40)]


def _bad_citation() -> Answer:
    return Answer(reasoning="r", answer="Attendance is optional.", answered_from_context=True,
                  confidence="high",
                  citations=[Citation(source="attendance-policy-2099.pdf", section="1", page=1)])


def _count(metric, **labels) -> float:
    return (metric.labels(**labels) if labels else metric)._value.get()


def test_grounded_answer_never_exposes_reasoning() -> None:
    r = answer_question("What is the rule?", FakeRetriever(P), ScriptedProvider(grounded(P[0])), S)
    assert r.answered_from_context and r.citations[0].source == "rules.pdf"
    assert "reasoning" not in r.model_dump() and "secret" not in r.model_dump_json()
    assert [x.chunk_id for x in r.retrieved] == ["c1", "c2", "c3"]


def test_below_the_relevance_floor_abstains_without_calling_the_model() -> None:
    weak = [passage(1, 0.31), passage(2, 0.22)]
    provider = ScriptedProvider()
    before = _count(m.ABSTENTIONS, reason="below_relevance_floor")
    r = answer_question("Hostel curfew?", FakeRetriever(weak), provider, S)
    assert not r.answered_from_context and r.citations == [] and r.answer == ABSTAIN_TEXT
    assert provider.calls == []
    assert _count(m.ABSTENTIONS, reason="below_relevance_floor") == before + 1


def test_only_passages_above_the_floor_reach_the_model() -> None:
    seen = {}

    class Spy(ScriptedProvider):
        def generate(self, question, passages, retry_reason=None):
            seen["ids"] = [p.chunk_id for p in passages]
            return grounded(passages[0])

    answer_question("q?", FakeRetriever(P), Spy(), S)
    assert seen["ids"] == ["c1", "c2"]
    many = [passage(i, 0.9 - i / 100) for i in range(1, 6)]
    answer_question("q?", FakeRetriever(many), Spy(), Settings(relevance_floor=0.5, max_context_passages=3))
    assert seen["ids"] == ["c1", "c2", "c3"]                    # best three reach the model


def test_fabricated_citation_is_retried_once_then_succeeds() -> None:
    provider = ScriptedProvider(_bad_citation(), grounded(P[0]))
    r = answer_question("q?", FakeRetriever(P), provider, S)
    assert r.answered_from_context and len(provider.calls) == 2
    assert provider.calls[0] is None and "does not match" in provider.calls[1]


@pytest.mark.parametrize("first,second", [
    (_bad_citation(), _bad_citation()),
    (ValidationError.from_exception_data("Answer", []), ValueError("prose, not JSON")),
    (httpx.ReadTimeout("model too slow"), httpx.ConnectError("host down")),
])
def test_two_failures_give_a_safe_canned_answer_not_a_500(first, second) -> None:
    before = _count(m.FALLBACKS, reason="invalid_output")
    r = answer_question("q?", FakeRetriever(P), ScriptedProvider(first, second), S)
    assert r.answer == FALLBACK_TEXT and not r.answered_from_context and r.citations == []
    assert _count(m.FALLBACKS, reason="invalid_output") == before + 1


def test_retrieval_failure_is_a_fallback_too() -> None:
    retriever = FakeRetriever(P)
    retriever.fail = ConnectionError("chroma down")
    r = answer_question("q?", retriever, ScriptedProvider(), S)
    assert r.answer == FALLBACK_TEXT and r.retrieved == []


def _cached_stack():
    redis = FakeRedis()
    return redis, SemanticCache(redis, threshold=0.95)


def test_a_repeated_question_is_served_from_the_cache() -> None:
    redis, cache = _cached_stack()
    provider = ScriptedProvider(grounded(P[0]))
    first = answer_question("What is the withdrawal deadline?", FakeRetriever(P), provider, S, cache)
    again = answer_question("What is the withdrawal deadline?", FakeRetriever(P), provider, S, cache)
    assert not first.cached and again.cached and len(provider.calls) == 1
    assert again.answer == first.answer and again.citations == first.citations


@pytest.mark.parametrize("question,reply", [
    ("And what about it?", None),                     # follow-up: never cached
    ("Hostel fee?", declined()),                      # abstention: never cached
])
def test_unsafe_answers_are_not_cached(question, reply) -> None:
    redis, cache = _cached_stack()
    answer_question(question, FakeRetriever(P), ScriptedProvider(reply or grounded(P[0])), S, cache)
    assert not [k for k in redis.kv if k.endswith(":entries") and redis.kv[k]]


def test_fallbacks_are_not_cached() -> None:
    redis, cache = _cached_stack()
    answer_question("q?", FakeRetriever(P), ScriptedProvider(_bad_citation(), _bad_citation()),
                    S, cache)
    assert not [k for k in redis.kv if k.endswith(":entries")]


def test_reindex_expires_the_cache() -> None:
    redis, cache = _cached_stack()
    provider = ScriptedProvider(grounded(P[0]), grounded(P[0]))
    answer_question("What is the rule?", FakeRetriever(P, generation="g1"), provider, S, cache)
    r = answer_question("What is the rule?", FakeRetriever(P, generation="g2"), provider, S, cache)
    assert not r.cached and len(provider.calls) == 2
    assert not [k for k in redis.kv if ":g1:" in k]


def test_a_broken_cache_does_not_break_answers() -> None:
    redis, cache = _cached_stack()
    redis.down = True
    r = answer_question("q?", FakeRetriever(P), ScriptedProvider(grounded(P[0])), S, cache)
    assert r.answered_from_context


def test_one_log_line_per_turn_with_ids_scores_and_no_text(caplog) -> None:
    caplog.set_level(logging.INFO, logger="rahbar.answer")
    answer_question("Secret question text?", FakeRetriever(P), ScriptedProvider(grounded(P[0])), S)
    rec = [r for r in caplog.records if r.getMessage() == "answered"][-1]
    assert rec.chunk_ids == ["c1", "c2", "c3"] and rec.scores == [0.82, 0.71, 0.4]
    assert rec.top_k == 5 and rec.abstained is False
    assert "Secret question" not in json.dumps(vars(rec), default=str)


def test_a_settings_change_starts_a_fresh_cache_scope() -> None:
    """Found on the cluster: answers cached under the old floor and another provider were
    served after a ConfigMap change. Every answer-shaping knob is now part of the key."""
    from dataclasses import replace

    from app.services.answer import cache_scope

    base = cache_scope("g1", "ollama", S)
    assert cache_scope("g1", "stub", S) != base
    for change in ({"relevance_floor": 0.6}, {"top_k": 3}, {"temperature": 0.1},
                   {"max_context_passages": 2}, {"llm_model": "llama3.2:1b"},
                   {"embed_model": "other"}, {"superseded_filter": False}):
        assert cache_scope("g1", "ollama", replace(S, **change)) != base, change
    assert cache_scope("g1", "ollama", S) == base


def test_answers_from_a_different_provider_are_not_reused() -> None:
    redis, cache = _cached_stack()
    first = ScriptedProvider(grounded(P[0]))
    answer_question("What is the rule?", FakeRetriever(P), first, S, cache)

    class Other(ScriptedProvider):
        name = "ollama"

    second = Other(grounded(P[0]))
    r = answer_question("What is the rule?", FakeRetriever(P), second, S, cache)
    assert not r.cached and len(second.calls) == 1
