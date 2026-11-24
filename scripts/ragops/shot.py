#!/usr/bin/env python3
"""Render a saved terminal transcript as a terminal-style PNG for the report appendix.

    python scripts/ragops/shot.py --label A1 --transcript docs/a3-evidence/A1.txt --out docs/a3-evidence/screenshots/A1.png

The picture is drawn FROM the saved transcript of a real run (scripts/ragops/capture.sh writes the
transcript at the moment the command runs); it is a rendering, not a live screen grab, and says so
in its title bar. Long output is wrapped at 150 columns and split across pages, never cropped.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BG, FG, DIM, BAR, PROMPT = (24, 26, 31), (226, 229, 234), (135, 142, 153), (45, 49, 58), (120, 200, 140)
COLS, MAX_LINES, SIZE, PAD, BAR_H = 150, 70, 15, 16, 34


def wrap(text: str) -> list[str]:
    out: list[str] = []
    for line in text.expandtabs(4).splitlines():
        out.extend(textwrap.wrap(line, COLS, replace_whitespace=False, drop_whitespace=False,
                                 subsequent_indent="    ") or [""])
    return out


def render(label: str, lines: list[str], page: int, pages: int, out: Path) -> None:
    font = ImageFont.truetype(FONT, SIZE)
    lh = SIZE + 5
    cw = int(font.getlength("M"))
    width = PAD * 2 + cw * COLS
    height = BAR_H + PAD * 2 + lh * len(lines)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, width, BAR_H), fill=BAR)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((12 + i * 22, 11, 24 + i * 22, 23), fill=c)
    title = f"{label}  -  terminal transcript of a real run, rendered" + (f"  (page {page}/{pages})" if pages > 1 else "")
    d.text((90, 8), title, font=font, fill=DIM)
    y = BAR_H + PAD
    for line in lines:
        color = PROMPT if line.startswith("$ ") else FG
        d.text((PAD, y), line, font=font, fill=color)
        y += lh
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--transcript", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    lines = wrap(a.transcript.read_text(encoding="utf-8", errors="replace"))
    chunks = [lines[i:i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)] or [[""]]
    for n, chunk in enumerate(chunks, 1):
        out = a.out if len(chunks) == 1 else a.out.with_name(f"{a.out.stem}-{n}{a.out.suffix}")
        render(a.label, chunk, n, len(chunks), out)
        print(out)


if __name__ == "__main__":
    main()
