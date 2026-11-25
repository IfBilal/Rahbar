#!/usr/bin/env python3
"""Draw the two report figures from committed result files (no matplotlib needed; PIL only).

    python scripts/ragops/charts.py          # writes docs/a3-report/fig-candidates.png and fig-coverage.png

fig-candidates.png: recall@5, faithfulness and abstention correctness for the baseline and the three candidates,
read from eval/results/*.json, with the gate's recall@5 floor (baseline minus 0.02) and faithfulness minimum (0.89).
fig-coverage.png: coverage share before, after round 1 and after round 2 of the E4 questions against the 0.85 minimum,
read from the coverage transcripts under docs/a3-evidence/E/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
INK, GRID = (30, 33, 40), (210, 214, 220)
COLORS = [(70, 110, 190), (60, 160, 120), (230, 150, 50), (200, 80, 80)]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else FONT, size)


def metric(path: str, *keys: str) -> float:
    cur = json.loads((ROOT / "eval/results" / path).read_text())["levels"]
    for k in keys:
        cur = cur[k]
    return float(cur)


def candidates() -> Image.Image:
    runs = [("baseline (nomic)", "20261124T174636Z_baseline.json"), ("cand-minilm", "20261125T054522Z_cand-minilm.json"),
            ("cand-mxbai", "20261125T083132Z_cand-mxbai.json"), ("cand-llama1b", "20261125T074817Z_cand-llama1b.json")]
    groups = [("recall@5", ("component", "clean", "recall@5")), ("faithfulness", ("endpoint", "faithfulness")),
              ("abstention correctness", ("endpoint", "abstention_correctness"))]
    w, h, left, top, bottom = 1500, 760, 90, 110, 160
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((left, 20), "Part C: baseline and three candidates (golden v1, Batch A: 20 answerable, 6 unanswerable)", font=font(21, True), fill=INK)
    plot_h = h - top - bottom
    for i in range(0, 11, 2):
        y = top + plot_h - plot_h * i / 10 * 0.92
        d.line((left, y, w - 30, y), fill=GRID)
        d.text((left - 48, y - 10), f"{i / 10:.1f}", font=font(18), fill=INK)
    gw = (w - left - 40) / len(groups)
    bw = gw / (len(runs) + 1.5)
    for gi, (gname, keys) in enumerate(groups):
        x0 = left + gi * gw + bw * 0.5
        for ri, (rname, f) in enumerate(runs):
            v = metric(f, *keys)
            x = x0 + ri * bw
            y = top + plot_h - plot_h * v * 0.92
            d.rectangle((x, y, x + bw * 0.85, top + plot_h), fill=COLORS[ri])
            d.text((x, y - 24), f"{v:.3f}", font=font(17), fill=INK)
        d.text((x0, h - bottom + 12), gname, font=font(21, True), fill=INK)
    base_r5 = metric(runs[0][1], "component", "clean", "recall@5")
    for val, gi in ((base_r5 - 0.02, 0), (0.89, 1)):
        y = top + plot_h - plot_h * val * 0.92
        d.line((left + gi * gw, y, left + (gi + 1) * gw - 10, y), fill=(120, 0, 0), width=3)
    d.text((left, 74), "dark red line = gate limit: recall@5 baseline - 0.02 = 0.78; faithfulness minimum 0.89",
           font=font(17, True), fill=(120, 0, 0))
    lx = left
    for ri, (rname, _) in enumerate(runs):
        d.rectangle((lx, h - 60, lx + 22, h - 38), fill=COLORS[ri])
        d.text((lx + 30, h - 62), rname, font=font(19), fill=INK)
        lx += 330
    return img


def coverage() -> Image.Image:
    def share(name: str) -> float:
        text = (ROOT / "docs/a3-evidence/E" / name).read_text()
        return float(re.search(r"share ([0-9.]+)", text).group(1))
    bars = [("before E4", share("E1-coverage-before.txt")), ("after round 1\n(8 questions)", share("E2-coverage-after.txt")),
            ("after round 2\n(15 questions)", share("E2-coverage-after-round2.txt"))]
    w, h, left, top, bottom = 1000, 640, 90, 70, 130
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((left, 18), "Part E: query coverage of 42 live queries (tau 0.6448)", font=font(22, True), fill=INK)
    plot_h = h - top - bottom
    for i in range(0, 11, 2):
        y = top + plot_h - plot_h * i / 10
        d.line((left, y, w - 30, y), fill=GRID)
        d.text((left - 48, y - 10), f"{i / 10:.1f}", font=font(18), fill=INK)
    y85 = top + plot_h - plot_h * 0.85
    d.line((left, y85, w - 30, y85), fill=(120, 0, 0), width=3)
    d.text((left + 6, y85 - 24), "min share 0.85", font=font(16, True), fill=(120, 0, 0))
    bw = 170
    for i, (name, v) in enumerate(bars):
        x = left + 80 + i * 260
        y = top + plot_h - plot_h * v
        d.rectangle((x, y, x + bw, top + plot_h), fill=COLORS[i if v < 0.85 else 1])
        d.text((x + 40, y - 26), f"{v:.3f}", font=font(20, True), fill=INK)
        for li, line in enumerate(name.split("\n")):
            d.text((x, h - bottom + 14 + li * 24), line, font=font(19), fill=INK)
    return img


if __name__ == "__main__":
    out = ROOT / "docs/a3-report"
    candidates().save(out / "fig-candidates.png")
    coverage().save(out / "fig-coverage.png")
    print("wrote", out / "fig-candidates.png", out / "fig-coverage.png")
