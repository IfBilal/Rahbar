#!/usr/bin/env python3
"""Screenshot the chat UI through the Ingress with real questions (README image).

Needs Playwright and a Chrome install:  pip install playwright==1.55.0
    python scripts/screenshot.py --ip $(minikube ip) --out docs/evidence/ui-screenshot.png
Chrome resolves rahbar.local to the Ingress IP itself, so /etc/hosts is untouched.
"""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright

QUESTIONS = [
    "What is the deadline to withdraw from a course?",
    "What is the monthly hostel fee and how do I apply for a hostel room?",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=[f"--host-resolver-rules=MAP rahbar.local {a.ip}"])
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        page.goto("http://rahbar.local/", wait_until="networkidle")
        for i, question in enumerate(QUESTIONS, start=1):
            page.fill("#question", question)
            page.click("#send")
            # the UI shows a .pending bubble until the answer (or an .err) replaces it;
            # CPU generation can take minutes
            page.wait_for_function(
                f"document.querySelectorAll('#thread .q').length >= {i} && "
                "!document.querySelector('#thread .pending')", timeout=600_000)
            page.wait_for_timeout(500)
        page.screenshot(path=a.out, full_page=True)
        browser.close()
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
