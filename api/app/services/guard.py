"""Validate (3.2 step 7): structure is guaranteed by the schema; this checks what the
schema cannot. Every citation must name a passage retrieved for THIS request (3.4), an
answer that claims grounding must cite something, and evidence markers in the text must
point at real passages. A failure raises GuardError, and the caller retries once."""

from __future__ import annotations

import re

from ..schemas import Answer, Citation, Passage

_MARKER = re.compile(r"\[([A-Z])\]")            # evidence letters, see prompt.evidence_id
_NUMBER = re.compile(r"\s*\[\d{1,3}\]")          # a bracketed number is never a citation


class GuardError(ValueError):
    pass


def _norm(text: str | None) -> str:
    return " ".join((text or "").replace("’", "'").lower().split())


def match_passage(citation: Citation, passages: list[Passage]) -> Passage | None:
    """The retrieved passage a citation refers to, or None if it names none of them.
    A model that shortens the section path ('Withdrawal from a Course' for '4. Registration >
    Withdrawal from a Course') still points at a real chunk, so a suffix match counts; the
    citation is then rewritten to the passage's exact labels."""
    same_source = [p for p in passages if _norm(p.source) == _norm(citation.source)]
    want = _norm(citation.section)
    hits = [p for p in same_source if want and (_norm(p.section) == want
                                                or _norm(p.section).endswith(want))]
    if citation.page is not None:
        hits = [p for p in hits if p.page == citation.page] or []
    return hits[0] if hits else None


def check_answer(answer: Answer, passages: list[Passage]) -> Answer:
    """Return a cleaned copy of `answer`, or raise GuardError."""
    letters = _MARKER.findall(answer.answer)
    bad = [x for x in letters if ord(x) - ord("A") >= len(passages)]
    if bad:
        raise GuardError(f"evidence marker(s) {bad} do not exist; the evidence ids are "
                         f"A to {chr(ord('A') + len(passages) - 1)}")
    numbers = [ord(x) - ord("A") + 1 for x in letters]
    answer = answer.model_copy(update={"answer": _NUMBER.sub("", answer.answer)})
    if not answer.answered_from_context:
        if numbers:
            raise GuardError("answered_from_context is false but the answer cites evidence "
                             f"{sorted(set(numbers))}; set it to true if the evidence answers "
                             "the question, otherwise give no evidence numbers")
        text = answer.answer.strip()
        return answer.model_copy(update={"answer": text, "citations": []})

    cited: list[Passage] = []
    for c in answer.citations:
        p = match_passage(c, passages)
        if p is None:
            raise GuardError(f"citation {c.source} / {c.section} / page {c.page} does not "
                             "match any retrieved passage")
        cited.append(p)
    cited += [passages[n - 1] for n in numbers]       # markers are citations too
    unique = list({p.chunk_id: p for p in cited}.values())
    if not unique:
        raise GuardError("answered_from_context is true but nothing is cited")
    def readable(m: re.Match[str]) -> str:
        p = passages[ord(m.group(1)) - ord("A")]
        return f"[{p.source} / {p.section}]"

    text = _MARKER.sub(readable, answer.answer)
    if not letters:     # 3.4: the answer text itself must show its sources, not only the list
        text = text.rstrip() + " " + " ".join(f"[{p.source} / {p.section}]" for p in unique)
    return answer.model_copy(update={
        "answer": text,
        "citations": [Citation(source=p.source, section=p.section, page=p.page) for p in unique],
    })


_FOLLOW_UP = re.compile(
    r"^\s*(and|but|also|so|then|what about|how about|same)\b"
    r"|\b(it|its|that one|this one|those|these|they|them|above|previous answer|you said|"
    r"the same|what you)\b", re.I)


def is_follow_up(question: str) -> bool:
    """The API has no conversation state, so this is conservative: anything that leans on
    an earlier turn is answered as asked but never cached (3.3)."""
    return bool(_FOLLOW_UP.search(question))
