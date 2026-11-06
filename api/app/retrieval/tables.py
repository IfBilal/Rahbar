"""Identify numeric table rows that directly match a quantitative question.

This is a narrow lexical assist to dense retrieval, not a source of answers. A match
requires a meaningful word in the section heading and a complete row label in the
question. The retriever still computes the real cosine score and applies its usual floor.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
_NUMBER = re.compile(r"\d")
_QUANTITY = re.compile(r"\b(?:how many|how much|number of|total number|count of)\b", re.I)
_YEAR = re.compile(r"\b((?:19|20)\d{2})(?:\s*[-/]\s*(\d{2,4}))?\b")
_GENERIC = frozenset({"about", "according", "academic", "campus", "count", "data", "details",
                      "information", "members", "other", "others", "report", "rules",
                      "student", "students", "summary", "table", "total", "university"})


def quantitative(question: str) -> bool:
    return bool(_QUANTITY.search(question))


def _words(text: str) -> set[str]:
    return {x for x in _WORD.findall(text.lower()) if len(x) >= 4 and x not in _GENERIC}


def _years(text: str) -> set[str]:
    return {year for start, end in _YEAR.findall(text)
            for year in (start, start[:2] + end if len(end) == 2 else end) if year}


def matching_rows(question: str, text: str, section: str, version: str,
                  source: str) -> list[str]:
    """Return numeric rows whose label, topic and edition match the question."""
    if not quantitative(question):
        return []
    question_words = _words(question)
    if not (_words(section.rsplit(">", 1)[-1]) & question_words):
        return []
    requested_years = _years(question)
    if requested_years and not requested_years <= _years(version + " " + source):
        return []
    rows: list[str] = []
    for line in text.splitlines():
        cells = line.split("|")
        if len(cells) < 3 or sum(bool(_NUMBER.search(c)) for c in cells[1:]) < 2:
            continue
        label = _words(cells[0])
        if label and label <= question_words:
            rows.append(line)
    return rows


def matches(question: str, text: str, section: str, version: str, source: str) -> bool:
    """True only for a matching heading, numeric row label and explicit edition, if any."""
    return bool(matching_rows(question, text, section, version, source))
