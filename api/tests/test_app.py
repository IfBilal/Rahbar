"""App-level wiring: config, metrics, contract additions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_settings_read_the_configmap_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {"RELEVANCE_FLOOR": "0.61", "CACHE_THRESHOLD": "0.97", "TOP_K": "4",
                       "TEMPERATURE": "0.1", "EXACT_TERM_ASSIST": "false",
                       "REDIS_URL": "redis://redis:6379/0", "LLM_TIMEOUT_SECONDS": "30"}.items():
        monkeypatch.setenv(key, value)
    s = get_settings()
    assert (s.relevance_floor, s.cache_threshold, s.top_k, s.temperature) == (0.61, 0.97, 4, 0.1)
    assert s.exact_term_assist is False and s.redis_url.startswith("redis://")
    assert "test" not in repr(s.llm_api_key) or s.llm_api_key == ""


def test_api_key_is_never_in_the_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "super-secret-value")
    assert "super-secret-value" not in repr(get_settings())


def test_response_carries_cached_flag(client: TestClient) -> None:
    r = client.post("/api/ask", json={"question": "What is the attendance requirement?"}).json()
    assert r["cached"] is False and "reasoning" not in r


def test_rag_metrics_are_exposed(client: TestClient) -> None:
    client.post("/api/ask", json={"question": "What is the attendance requirement?"})
    text = client.get("/metrics").text
    for name in ("rahbar_retrieval_seconds", "rahbar_generation_seconds",
                 "rahbar_cache_hit_ratio", "rahbar_cache_lookups_total",
                 "rahbar_abstentions_total", "rahbar_fallbacks_total",
                 "rahbar_tokens_total", "rahbar_tokens_per_request", "rahbar_request_seconds"):
        assert name in text, name


def test_every_response_names_the_running_version(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.json() == {"status": "alive"}                 # the body stays as the starter pins it
    assert r.headers["X-Rahbar-Version"]


def test_abstention_and_fallback_series_exist_before_any_happen() -> None:
    from prometheus_client import generate_latest

    text = generate_latest().decode()
    for series in ('rahbar_abstentions_total{reason="below_relevance_floor"}',
                   'rahbar_abstentions_total{reason="model_declined"}',
                   'rahbar_fallbacks_total{reason="retrieval_error"}',
                   'rahbar_fallbacks_total{reason="invalid_output"}',
                   'rahbar_tokens_total{direction="in"}'):
        assert series in text, series
