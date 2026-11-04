#!/usr/bin/env python3
"""Smoke test through the Ingress (cd.yml deploy, and by hand after `make apply`).

Standard library only. Checks the UI is served, the API answers a covered question with
citations that all name retrieved passages, and declines an absent topic.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def call(base: str, host: str, path: str, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 headers={"Host": host, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status, r.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--host", default="rahbar.local")
    ap.add_argument("--question", default="What minimum CGPA does an undergraduate need to avoid academic warning?")
    ap.add_argument("--absent", default="What are the hostel curfew timings for female students?")
    a = ap.parse_args()
    failures = []

    status, page = call(a.api, a.host, "/")
    print(f"GET / -> {status}, {len(page)} bytes")
    if status != 200 or "<html" not in page.lower():
        failures.append("the UI is not served at /")

    status, body = call(a.api, a.host, "/api/ask", {"question": a.question})
    r = json.loads(body)
    retrieved = {(x["source"], x["section"], x["page"]) for x in r["retrieved"]}
    print(f"POST /api/ask (covered) -> {status}, answered_from_context={r['answered_from_context']}, "
          f"{len(r['citations'])} citations, {len(r['retrieved'])} retrieved")
    if status != 200 or not r["retrieved"]:
        failures.append("the covered question retrieved nothing")
    if r["answered_from_context"] and not r["citations"]:
        failures.append("a grounded answer without citations")
    bad = [c for c in r["citations"] if (c["source"], c["section"], c["page"]) not in retrieved]
    if bad:
        failures.append(f"citations that were never retrieved: {bad}")
    if "reasoning" in r:
        failures.append("the model's reasoning leaked into the response")

    status, body = call(a.api, a.host, "/api/ask", {"question": a.absent})
    r = json.loads(body)
    print(f"POST /api/ask (absent)  -> {status}, answered_from_context={r['answered_from_context']}")
    if r["answered_from_context"]:
        failures.append("the absent topic was answered from context")

    for f in failures:
        print("FAIL:", f)
    print("smoke test passed" if not failures else "smoke test FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
