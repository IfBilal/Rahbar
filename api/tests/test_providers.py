"""Providers: constrained decoding requested, temperature passed, output validated."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.providers.llm import get_provider
from app.providers.llm.base import usage_var
from app.providers.llm.hosted import HostedProvider
from app.providers.llm.ollama import OllamaProvider
from app.schemas import Answer

from .fakes import passage

GOOD = {"reasoning": "r", "answer": "80% [1].", "answered_from_context": True,
        "confidence": "high", "citations": [{"source": "rules.pdf", "section": "Section 1", "page": 1}]}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_sends_schema_temperature_and_messages() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": json.dumps(GOOD)},
                                         "prompt_eval_count": 900, "eval_count": 60})

    s = Settings(temperature=0.2, llm_model="llama3.2:3b", ollama_url="http://ollama:11434")
    out = OllamaProvider(s, client=_client(handler)).generate("q?", [passage(1)])
    assert isinstance(out, Answer) and out.answer == "80% [1]."
    assert seen["url"] == "http://ollama:11434/api/chat"
    body = seen["body"]
    assert body["format"] == Answer.model_json_schema() and body["stream"] is False
    assert body["options"]["temperature"] == 0.2 and body["model"] == "llama3.2:3b"
    assert body["messages"][0]["role"] == "system"
    assert usage_var.get() == (900, 60)


def test_ollama_prose_instead_of_json_is_a_validation_error() -> None:
    handler = lambda r: httpx.Response(200, json={"message": {"content": "Sure! Attendance is 80%."}})  # noqa: E731
    with pytest.raises(ValidationError):
        OllamaProvider(Settings(), client=_client(handler)).generate("q?", [passage(1)])


def test_ollama_http_error_propagates_for_the_retry_logic() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        OllamaProvider(Settings(), client=_client(lambda r: httpx.Response(500))).generate(
            "q?", [passage(1)])


def test_hosted_uses_bearer_key_and_json_mode() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 7}})

    s = Settings(llm_provider="hosted", hosted_base_url="https://api.example/v1/",
                 llm_api_key="test-key", temperature=0.1)
    out = HostedProvider(s, client=_client(handler)).generate("q?", [passage(1)])
    assert out.answered_from_context and seen["auth"] == "Bearer test-key"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["temperature"] == 0.1 and usage_var.get() == (5, 7)


def test_hosted_needs_a_base_url() -> None:
    with pytest.raises(ValueError, match="HOSTED_BASE_URL"):
        HostedProvider(Settings(llm_provider="hosted"))


def test_provider_selection_is_one_config_key() -> None:
    assert get_provider(Settings(llm_provider="stub")).name == "stub"
    assert get_provider(Settings(llm_provider="ollama-host")).name == "ollama"
    assert get_provider(Settings(llm_provider="ollama-incluster")).name == "ollama"
    with pytest.raises(ValueError):
        get_provider(Settings(llm_provider="gpt-9"))
