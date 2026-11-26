"""Verification and ingest reports (docs/a3-ragops/05 section 5, schema in 14 section 3).

One JSON file per run, plus a Markdown rendering sized for a terminal screenshot: a table
with four status columns per document, then the code and full reason of each check. Screenshot A1 is this output.
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


def render_markdown(report: dict[str, Any]) -> str:
    """Summary table, then per document one line per check: PASS/FAIL, code and the full reason."""
    rows = [f"# Verification report {report['run_id']}", "",
            f"embedding `{report['embed_model']}` · documents {report['summary']['documents']} · "
            f"unchanged {report['summary']['unchanged']}", "",
            "| document | quality | complete | recency | unique | outcome |",
            "| --- | --- | --- | --- | --- | --- |"]
    detail = ["", "## Reason for each check", ""]
    for d in report["documents"]:
        checks = d["checks"]
        rows.append(f"| {d['file']} | " + " | ".join(_cell(checks[c]) for c in CHECKS)
                    + f" | {d['outcome']} |")
        detail += [f"**{d['file']}** ({d['outcome']})"]
        detail += [f"- {c}: {_cell(checks[c])} {checks[c]['code']}: {checks[c]['reason']}" for c in CHECKS]
        detail.append("")
    for r in report["reevaluated"]:
        rows.append(f"| {r['doc']} (already indexed) | – | – | FAIL | – | {r['outcome']} |")
        detail += [f"**{r['doc']}** (already indexed, {r['outcome']})",
                   f"- recency: FAIL {r['code']}: {r['reason']}", ""]
    rows += detail
    s = report["summary"]
    fb = s["failures_by_check"]
    rows += ["", f"**accepted {s['accepted']} · quarantined {s['quarantined']} · archived "
                 f"{s['archived']} · unchanged {s['unchanged']}**",
             f"failures by check: quality {fb['quality']} · completeness {fb['completeness']} · "
             f"recency {fb['recency']} · uniqueness {fb['uniqueness']}"]
    return "\n".join(rows) + "\n"
