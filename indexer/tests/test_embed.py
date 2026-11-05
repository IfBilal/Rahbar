"""Stage 4 (embed): batched, pinned, prefixed, checked."""

from __future__ import annotations

import json

import httpx
import pytest

from pipeline import embed as emb
from pipeline.config import get_settings
from pipeline.embed import check_vectors, document_prefix, embed


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_batches_use_the_pinned_model_and_the_document_prefix(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]] * len(body["input"])})

    vectors = embed([f"t{i}" for i in range(70)], get_settings(), client=_client(handler))
    assert len(vectors) == 70 and [len(b["input"]) for b in seen] == [32, 32, 6]
    assert all(b["model"] == "nomic-embed-text" for b in seen)
    assert seen[0]["input"][0] == "search_document: t0"


def test_uncased_model_input_is_lowercased() -> None:
    """Regression: Ollama sent 'Rector' and 'Dean' to an uncased vocabulary unchanged and
    both became [UNK]. Lowercasing restores what the reference tokenizer does."""
    from pipeline.embed import prepare_document
    assert prepare_document("nomic-embed-text", "Rector's List, BS") == \
        "search_document: rector's list, bs"
    assert prepare_document("mxbai-embed-large", "Rector") == "Rector"


def test_prefix_only_for_models_that_use_one() -> None:
    assert document_prefix("nomic-embed-text:latest") == "search_document: "
    assert document_prefix("mxbai-embed-large") == ""


def test_transient_failure_is_retried(monkeypatch) -> None:
    monkeypatch.setattr(emb.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    assert embed(["x"], get_settings(), client=_client(handler)) == [[1.0, 0.0]]
    assert calls["n"] == 2


def test_persistent_failure_fails_the_job(monkeypatch) -> None:
    monkeypatch.setattr(emb.time, "sleep", lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        embed(["x"], get_settings(), client=_client(lambda r: httpx.Response(500)))


def test_wrong_vector_count_is_an_error(monkeypatch) -> None:
    monkeypatch.setattr(emb.time, "sleep", lambda s: None)
    handler = lambda r: httpx.Response(200, json={"embeddings": [[1.0]]})  # noqa: E731
    with pytest.raises(ValueError, match="asked for 2"):
        embed(["a", "b"], get_settings(), client=_client(handler))


def test_no_texts_no_calls() -> None:
    assert embed([], get_settings(), client=_client(lambda r: pytest.fail("called"))) == []


@pytest.mark.parametrize("vectors,expected,match", [
    ([[1.0, 2.0], [1.0]], 2, "mixed dimensions"),
    ([[float("nan"), 1.0]], 1, "NaN"),
    ([[1.0]], 2, "2 chunks but 1 vectors"),
])
def test_bad_vectors_are_rejected(vectors, expected, match) -> None:
    with pytest.raises(ValueError, match=match):
        check_vectors(vectors, expected)


def test_good_vectors_report_their_dimension() -> None:
    assert check_vectors([[0.0] * 768, [1.0] * 768], 2) == 768
