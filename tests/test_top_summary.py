"""The F5 resource summariser (scripts/ragops/top_summary.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "top_summary", Path(__file__).resolve().parents[1] / "scripts" / "ragops" / "top_summary.py")
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

SAMPLE = """2026-11-24T17:00:00Z
api-6c8bc44955-hgbzk    api       3m    70Mi
ingest-f4zgx            indexer   10m   100Mi
2026-11-24T17:00:10Z
api-6c8bc44955-hgbzk    api       5m    72Mi
ingest-f4zgx            indexer   1000m 900Mi
2026-11-24T17:00:20Z
ingest-f4zgx            indexer   1200m 910Mi
garbage line
"""


def test_samples_are_grouped_by_workload_and_summarised() -> None:
    rows = {r["workload"]: r for r in ts.summarise(ts.parse(SAMPLE))}
    assert set(rows) == {"api/api", "ingest/indexer"}
    api = rows["api/api"]
    assert api["peak_cpu_m"] == 5 and api["peak_mem_mi"] == 72 and api["samples"] == 2
    ing = rows["ingest/indexer"]
    assert ing["peak_cpu_m"] == 1200 and ing["peak_mem_mi"] == 910
    assert ing["steady_cpu_m"] == 1100          # the idle 10m sample (below 5% of the peak) is excluded
