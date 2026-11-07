"""Validate (3.2 step 7): structure is guaranteed by the schema; this checks what the
schema cannot. Every citation must name a passage retrieved for THIS request (3.4), an
answer that claims grounding must cite something, and evidence markers in the text must
point at real passages. A failure raises GuardError, and the caller retries once."""

from __future__ import annotations

import re

from ..schemas import Answer, Citation, Passage

_MARKER = re.compile(r"\[([A-Z])\]")            # evidence letters, see prompt.evidence_id
_CLAUSE = re.compile(r"\d{1,2}(\.\d{1,2}){1,2}")    # '1.2', '4.25', '6.4.1'
_NUMBER = re.compile(r"\s*\[\d{1,3}\]")          # a bracketed number is never a citation
# A sentence ends at . ! or ? followed by a space and a capital or quote: "2.00", "1.21" and
# "Rs. 500" (digit after the space) never end one.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


class GuardError(ValueError):
    pass


def _norm(text: str | None) -> str:
    return " ".join((text or "").replace("’", "'").lower().split())


def match_passage(citation: Citation, passages: list[Passage]) -> Passage | None:
    """The retrieved passage a citation refers to, or None if it names none of them.

    The model often gets a label slightly wrong while pointing at a real chunk: a shortened
    section path ('Withdrawal from a Course'), a clause number instead of the heading
    ('1.2'), or a page copied from the section number ('6. Rules for Summer Semester',
    page 6). Each still identifies a passage retrieved for this request, so it is matched
    and then rewritten to that passage's exact source, section and page. The page decides
    between passages of the same section; it never makes a real passage unmatchable.
    A citation naming no retrieved passage at all is rejected."""
    same_source = [p for p in passages if _norm(p.source) == _norm(citation.source)]
    want = _norm(citation.section)
    if not want:
        return None
    hits = [p for p in same_source if _norm(p.section) == want or _norm(p.section).endswith(want)]
    if not hits and _CLAUSE.fullmatch(want):        # a clause number found in the passage
        hits = [p for p in same_source if re.search(rf"(?<![\d.]){re.escape(want)}(?![\d])", p.text)]
    on_page = [p for p in hits if citation.page is not None and p.page == citation.page]
    best = on_page or hits
    return best[0] if best else None


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

    every = [chr(ord("A") + passages.index(p)) for p in unique]
    text = _MARKER.sub(readable, _cite_every_sentence(answer.answer, every))
    return answer.model_copy(update={
        "answer": text,
        "citations": [Citation(source=p.source, section=p.section, page=p.page) for p in unique],
    })


def _cite_every_sentence(text: str, every: list[str]) -> str:
    """3.4: every claim-bearing sentence carries a [source / section] tag. A sentence the model
    left uncited takes the evidence letters of the next cited sentence (models often cite once
    at the end of a run of sentences), else of the previous one, else every cited passage."""
    sentences = [x for x in _SENTENCE.split(text.strip()) if x]
    found = [_MARKER.findall(x) for x in sentences]
    out = []
    for i, (sentence, letters) in enumerate(zip(sentences, found)):
        if not letters:
            later = [f for f in found[i + 1:] if f]
            earlier = [f for f in found[:i] if f]
            letters = later[0] if later else earlier[-1] if earlier else every
            tag = "".join(f"[{x}]" for x in dict.fromkeys(letters))
            body = sentence.rstrip()
            end = body[-1] if body[-1:] in ".!?" else ""
            sentence = f"{body[:len(body) - len(end)]} {tag}{end}"   # "... classes [A]."
        out.append(sentence)
    return " ".join(out)


_FOLLOW_UP = re.compile(
    r"^\s*(and|but|also|so|then|what about|how about|same)\b"
    r"|\b(it|its|that one|this one|those|these|they|them|above|previous answer|you said|"
    r"the same|what you)\b", re.I)


def is_follow_up(question: str) -> bool:
    """The API has no conversation state, so this is conservative: anything that leans on
    an earlier turn is answered as asked but never cached (3.3)."""
    return bool(_FOLLOW_UP.search(question))
