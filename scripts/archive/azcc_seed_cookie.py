#!/usr/bin/env python3
"""One-shot operator helper: capture AZCC session cookies after manual captcha solve.

Launches a headed Playwright browser, waits for the operator to complete a
successful business search (including captcha), then prints an AZCC_SESSION_COOKIE
line suitable for pasting into .env.
"""

from __future__ import annotations

import json
import sys
import time

DEFAULT_SEARCH_URL = "https://arizonabusinesscenter.azcc.gov/businesssearch"
PUBLIC_SEARCH_API_FRAGMENT = "publicsearch/public-search"
WAIT_TIMEOUT_MS = 600_000  # 10 minutes


def main() -> int:
    from playwright.sync_api import sync_playwright

    captured: dict | None = None

    def _on_response(response) -> None:
        nonlocal captured
        if PUBLIC_SEARCH_API_FRAGMENT not in response.url:
            return
        if response.status != 200:
            return
        try:
            body = response.json()
        except Exception:
            return
        if isinstance(body, dict) and body.get("succeeded") and body.get("data"):
            captured = body

    print(
        "Opening AZCC Business Search in a browser window.\n"
        "Type a business name, click Business Search, solve the captcha, click Verify.\n"
        "This script will detect the successful API call and emit the cookie line.\n"
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.on("response", _on_response)
                page.set_default_navigation_timeout(120_000)
                page.set_default_timeout(WAIT_TIMEOUT_MS)
                page.goto(DEFAULT_SEARCH_URL, wait_until="networkidle", timeout=120_000)

                deadline = time.monotonic() + (WAIT_TIMEOUT_MS / 1000.0)
                while captured is None:
                    page.wait_for_timeout(1_000)
                    if time.monotonic() >= deadline:
                        print(
                            "Timed out waiting for successful public-search response.",
                            file=sys.stderr,
                        )
                        return 1

                cookies = context.cookies()
                line = "AZCC_SESSION_COOKIE=" + json.dumps(cookies, separators=(",", ":"))
                print(line)
                return 0
            finally:
                browser.close()
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
