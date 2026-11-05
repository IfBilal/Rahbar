"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter): any OpenAI-compatible
POST {hosted_base_url}/chat/completions.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command line. It
never appears in a file we commit, and never in a log line. JSON mode is requested with
response_format, and the reply is still validated against Answer.
"""

from __future__ import annotations

import json

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from .base import usage_var


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.hosted_base_url:
            raise ValueError("LLM_PROVIDER=hosted needs HOSTED_BASE_URL in the ConfigMap")
        self.settings = settings
        self.http = client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout, connect=5.0))

    def generate(self, question: str, passages: list[Passage],
                 retry_reason: str | None = None) -> Answer:
        messages = build_messages(question, passages, retry_reason)
        # JSON mode guarantees an object; the schema text tells the model which object.
        messages[0]["content"] += "\nJSON schema:\n" + json.dumps(Answer.model_json_schema())
        r = self.http.post(
            f"{self.settings.hosted_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={"model": self.settings.llm_model, "messages": messages,
                  "temperature": self.settings.temperature,
                  "response_format": {"type": "json_object"}})
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        usage_var.set((int(usage.get("prompt_tokens") or 0),
                       int(usage.get("completion_tokens") or 0)))
        return Answer.model_validate_json(data["choices"][0]["message"]["content"])
