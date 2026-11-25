#!/usr/bin/env python3
"""Turn `kubectl top pods --containers` samples into peak and steady usage per workload (F5).

    python scripts/ragops/top_summary.py docs/a3-evidence/top-ingest.txt [more files ...]

Input: a file written by a sampler loop, `date -u +%FT%TZ` followed by the `kubectl top` rows of that
moment, repeated. Each row is `POD CONTAINER CPU(cores) MEMORY(bytes)`. Pods are grouped by workload
(the pod name without its hash suffix). Steady = median of the samples where the workload was busy
(CPU above 5 percent of its own peak, so idle seconds before and after a Job do not dilute it);
peak = maximum. CPU in millicores, memory in MiB.
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def parse(text: str) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4 or not re.fullmatch(r"\d+m|\d+", parts[2]) or not parts[3].endswith(("Mi", "Gi", "Ki")):
            continue
        pod, container, cpu, mem = parts
        workload = re.sub(r"(-[a-f0-9]{8,10})?-[a-z0-9]{5}$|-\d+$", "", pod)
        workload = re.sub(r"-\d{10}.*$", "", workload)         # ingest-sync-1124173342-q8c89 -> ingest-sync
        c = float(cpu[:-1]) if cpu.endswith("m") else float(cpu) * 1000
        unit = {"Ki": 1 / 1024, "Mi": 1.0, "Gi": 1024.0}[mem[-2:]]
        series[f"{workload}/{container}"].append((c, float(mem[:-2]) * unit))
    return series


def summarise(series: dict[str, list[tuple[float, float]]]) -> list[dict[str, object]]:
    rows = []
    for name, samples in sorted(series.items()):
        cpu = [s[0] for s in samples]
        mem = [s[1] for s in samples]
        peak_cpu = max(cpu)
        busy = [s for s in samples if s[0] > 0.05 * peak_cpu] or samples
        rows.append({"workload": name, "samples": len(samples), "peak_cpu_m": round(peak_cpu),
                     "steady_cpu_m": round(statistics.median(s[0] for s in busy)),
                     "peak_mem_mi": round(max(mem)), "steady_mem_mi": round(statistics.median(s[1] for s in busy))})
    return rows


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for f in argv:
        for k, v in parse(Path(f).read_text(encoding="utf-8", errors="replace")).items():
            series[k].extend(v)
    print(f"{'workload/container':<28}{'samples':>8}{'peak CPU m':>12}{'steady CPU m':>14}{'peak Mi':>9}{'steady Mi':>11}")
    for r in summarise(series):
        print(f"{r['workload']:<28}{r['samples']:>8}{r['peak_cpu_m']:>12}{r['steady_cpu_m']:>14}"
              f"{r['peak_mem_mi']:>9}{r['steady_mem_mi']:>11}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
