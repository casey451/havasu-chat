"""Capture the agreed-design reference screenshots from the v4 mockup.

Reads ``design-exploration/ask-hava-premium-v4.html`` (the literal visual source
of truth) and writes reference PNGs into ``tests/visual/refs/`` at the two gate
sizes — 390x844 (mobile) and 1280x1024 (desktop) — plus a calendar variant of
each. These refs are the committed "this is what we agreed to" baseline that the
visual-regression test (``test_home_redesign_visual.py``) and human review check
the production reskin against.

Run manually after a mockup change (browsers required):

    python tests/visual/capture_refs.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

_ROOT = Path(__file__).resolve().parents[2]
_MOCKUP = _ROOT / "design-exploration" / "ask-hava-premium-v4.html"
_REFS = Path(__file__).resolve().parent / "refs"

_SIZES = {"mobile": (390, 844), "desktop": (1280, 1024)}


def capture() -> None:
    _REFS.mkdir(parents=True, exist_ok=True)
    url = _MOCKUP.as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (w, h) in _SIZES.items():
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(url)
            if name == "desktop":
                page.click('.toggle button[data-w="d"]')
            page.wait_for_timeout(700)  # let the entrance + sheen settle
            page.screenshot(path=str(_REFS / f"home_{name}.png"))
            # calendar variant — flip to the calendar view
            page.click("#calBtn")
            page.wait_for_timeout(500)
            page.screenshot(path=str(_REFS / f"calendar_{name}.png"))
            page.close()
        browser.close()
    print(f"wrote refs to {_REFS}")


if __name__ == "__main__":
    capture()
