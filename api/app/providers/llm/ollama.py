"""Ollama provider: ollama-host or ollama-incluster (section 3.5).

Enforce, then validate (3.4): the Answer JSON schema is passed as Ollama's `format`, so
decoding is constrained to it, and the reply is still parsed with Answer.model_validate_json.
Temperature comes from the ConfigMap. The call has a timeout: a hung model must not hold
a worker thread forever.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from .base import usage_var


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.http = client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout, connect=5.0))

    def generate(self, question: str, passages: list[Passage],
                 retry_reason: str | None = None) -> Answer:
        payload = {
            "model": self.settings.llm_model,
            "messages": build_messages(question, passages, retry_reason),
            "stream": False,
            "format": Answer.model_json_schema(),
            "options": {"temperature": self.settings.temperature, "num_ctx": 4096},
        }
        r = self.http.post(f"{self.settings.ollama_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        usage_var.set((int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0)))
        return Answer.model_validate_json(data["message"]["content"])
