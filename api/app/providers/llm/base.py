"""The LLM provider interface (section 3.5). Swapping providers is one file."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol

from ...schemas import Answer, Passage

# (tokens in, tokens out) of the last generation in this request, for /metrics (4.8).
# A ContextVar, not an attribute: requests run concurrently in the thread pool.
usage_var: ContextVar[tuple[int, int]] = ContextVar("llm_usage", default=(0, 0))


class LLMProvider(Protocol):
    name: str

    def generate(self, question: str, passages: list[Passage],
                 retry_reason: str | None = None) -> Answer:
        """Answer the question from the passages, as an `Answer`. `retry_reason` is set
        on the one retry after a rejected reply (3.4) and is fed back to the model."""
        ...
