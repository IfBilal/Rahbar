"""The LLM judge and the deterministic faithfulness proxy (docs/a3-ragops/06 sections 6.2-6.3).

The judge is a small local model, so every call is defensive: malformed output is counted as
`unparseable`, never raised. The proxy is a cheap second opinion that does not depend on a
small model's honesty: an answer sentence passes when most of its content words, and every
number in it, appear in the context the model was given.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .clients import Judge

LABELS = ("supported", "partial", "unsupported")
STOP = set("""a an and are as at be been but by can could did do does for from had has have he her
his how i if in into is it its may might more most must no not of on or our shall she should so
such than that the their them then there these they this those to was we were what when where
which who whom why will with would you your also any all each other only own same some very""".split())

PROMPT = """You are checking whether an ANSWER is supported by the CONTEXT only.
Use no outside knowledge. Reply with JSON: {{"label": "supported|partial|unsupported",
"unsupported_claims": ["..."]}}.
supported = every factual statement in the answer is backed by the context.
partial = some statements are backed, some are not.
unsupported = the main statements are not backed by the context.

CONTEXT:
{context}

QUESTION: {question}

ANSWER: {answer}
"""


def parse_judgement(raw: str) -> dict[str, Any] | None:
    """The first JSON object in the reply with a valid label, else None."""
    for m in re.finditer(r"\{.*\}", raw or "", flags=re.S):
        try:
            obj = json.loads(m.group())
        except ValueError:
            continue
        label = str(obj.get("label", "")).strip().lower()
        if label in LABELS:
            claims = obj.get("unsupported_claims") or []
            return {"label": label, "unsupported_claims": [str(c) for c in claims][:5]}
    return None


def judge_answer(judge: Judge, question: str, answer: str, context: str, seed: int,
                 max_chars: int) -> dict[str, Any]:
    truncated = len(context) > max_chars
    prompt = PROMPT.format(context=context[:max_chars], question=question, answer=answer)
    parsed = parse_judgement(judge.generate_json(prompt, seed))
    if parsed is None:
        return {"label": None, "unparseable": True, "truncated": truncated}
    return {**parsed, "unparseable": False, "truncated": truncated}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*", text.lower())
            if w not in STOP and len(w) > 1]


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def faithfulness_proxy(answer: str, context: str, min_overlap: float = 0.70) -> float | None:
    """Share of answer sentences whose content words are >= `min_overlap` present in the
    context and whose every number occurs in the context. None when there is nothing to check."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", answer or "") if _words(s)]
    if not sentences:
        return None
    ctx_words, ctx_nums = set(_words(context)), _numbers(context)
    ok = 0
    for s in sentences:
        words = _words(s)
        overlap = sum(1 for w in words if w in ctx_words) / len(words)
        if overlap >= min_overlap and _numbers(s) <= ctx_nums:
            ok += 1
    return round(ok / len(sentences), 4)
