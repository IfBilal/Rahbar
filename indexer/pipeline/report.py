"""Verification and ingest reports (docs/a3-ragops/05 section 5, schema in 14 section 3).

One JSON file per run, plus a Markdown rendering sized for a terminal screenshot: one table,
one row per document, four status columns, a reason column. Screenshot A1 is this output.
"""

from __future__ import annotations

import time
from typing import Any

CHECKS = ("quality", "completeness", "recency", "uniqueness")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_verification_report(run_id: str, embed_model: str, embed_version: str,
                              thresholds: dict[str, float], documents: list[dict[str, Any]],
                              reevaluated: list[dict[str, Any]], unchanged: list[str],
                              git_sha: str = "", image: str = "") -> dict[str, Any]:
    failures = {c: 0 for c in CHECKS}
    outcomes: dict[str, int] = {}
    for d in documents:
        outcomes[d["outcome"]] = outcomes.get(d["outcome"], 0) + 1
        for name, rec in d["checks"].items():
            if rec["status"] == "fail":
                failures[name] += 1
    for r in reevaluated:
        failures[r["check"]] += 1
    return {
        "schema": 1, "run_id": run_id, "started_at": _now(), "git_sha": git_sha, "image": image,
        "embed_model": embed_model, "embed_version": embed_version, "thresholds": thresholds,
        "documents": documents, "reevaluated": reevaluated, "unchanged": unchanged,
        "summary": {"documents": len(documents), "accepted": outcomes.get("accepted", 0),
                    "quarantined": outcomes.get("quarantined", 0),
                    "archived": len(reevaluated), "unchanged": len(unchanged),
                    "failures_by_check": failures},
    }


def _cell(rec: dict[str, Any]) -> str:
    return "PASS" if rec["status"] == "pass" else "FAIL"


def render_markdown(report: dict[str, Any], reason_width: int = 60) -> str:
    rows = [f"# Verification report {report['run_id']}", "",
            f"embedding `{report['embed_model']}` · documents {report['summary']['documents']} · "
            f"unchanged {report['summary']['unchanged']}", "",
            "| document | quality | complete | recency | unique | outcome | reason |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for d in report["documents"]:
        checks = d["checks"]
        failing = [c for c in CHECKS if checks[c]["status"] == "fail"]
        reason = (f"{checks[failing[0]]['code']}: {checks[failing[0]]['reason']}" if failing
                  else checks["recency"]["reason"] if checks["recency"]["code"] == "R-SUPERSEDES"
                  else "all four checks passed")
        reason = reason if len(reason) <= reason_width else reason[:reason_width - 1] + "…"
        rows.append(f"| {d['file']} | " + " | ".join(_cell(checks[c]) for c in CHECKS)
                    + f" | {d['outcome']} | {reason} |")
    for r in report["reevaluated"]:
        reason = f"{r['code']}: {r['reason']}"
        reason = reason if len(reason) <= reason_width else reason[:reason_width - 1] + "…"
        rows.append(f"| {r['doc']} (already indexed) | – | – | FAIL | – | {r['outcome']} | {reason} |")
    s = report["summary"]
    fb = s["failures_by_check"]
    rows += ["", f"**accepted {s['accepted']} · quarantined {s['quarantined']} · archived "
                 f"{s['archived']} · unchanged {s['unchanged']}**",
             f"failures by check: quality {fb['quality']} · completeness {fb['completeness']} · "
             f"recency {fb['recency']} · uniqueness {fb['uniqueness']}"]
    return "\n".join(rows) + "\n"
