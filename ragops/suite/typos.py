"""Seeded typo noise for the component noise test (docs/a3-ragops/06 section 5.4).

Same seed, same text, same output. Digits, clause numbers and quoted strings are never
touched: they carry the exact-term signal, and perturbing them would measure the wrong thing.
"""

from __future__ import annotations

import random
import re

KEYBOARD = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij",
    "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "awdx", "d": "serfcx", "f": "drtgvc",
    "g": "ftyhbv", "h": "gyujnb", "j": "huikmn", "k": "jiolm", "l": "kop", "z": "asx",
    "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}
WORD = re.compile(r"[A-Za-z]+")


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans = [m.span() for m in re.finditer(r"\"[^\"]*\"|'[^']{2,}'", text)]
    spans += [m.span() for m in re.finditer(r"\S*\d\S*", text)]  # any token with a digit
    return spans


def _perturb(word: str, kind: str, rng: random.Random) -> str:
    i = rng.randrange(1, len(word) - 1) if len(word) > 2 else 0
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:] if i + 1 < len(word) else word
    if kind == "drop":
        return word[:i] + word[i + 1:]
    if kind == "dup":
        return word[:i + 1] + word[i] + word[i + 1:]
    near = KEYBOARD.get(word[i].lower())
    if not near:
        return word
    sub = rng.choice(near)
    return word[:i] + (sub.upper() if word[i].isupper() else sub) + word[i + 1:]


def add_typos(text: str, rate: float, kinds: list[str], min_word_len: int,
              seed: int, key: str = "") -> str:
    """Perturb about `rate` of the eligible letters' worth of words, deterministically."""
    rng = random.Random(f"{seed}:{key}:{text}")
    protected = _protected_spans(text)
    candidates = [m for m in WORD.finditer(text)
                  if len(m.group()) >= min_word_len
                  and not any(s <= m.start() < e for s, e in protected)]
    if not candidates:
        return text
    n = max(1, round(rate * sum(len(m.group()) for m in candidates)))
    n = min(n, len(candidates))
    chosen = sorted(rng.sample(range(len(candidates)), n))
    out, last = [], 0
    for idx in chosen:
        m = candidates[idx]
        out.append(text[last:m.start()])
        out.append(_perturb(m.group(), rng.choice(kinds), rng))
        last = m.end()
    out.append(text[last:])
    return "".join(out)
