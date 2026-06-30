"""Nav parity — desktop top-nav and mobile drawer expose the same destinations.

Phase 1.2 (FIX_SPEC_2026-06-23 / UX review §P0 §2). The canonical Lake header
(``_partials/site_header.html``) drives both the desktop ``.nav`` and the mobile
``.drawer``; this asserts they list the SAME primary items, including the two
front doors restored in Phase 1.2 — **For Kids** (``/family``) and **Ask**
(``/ask`` → ``/chat``). A regression here means a phone user lost a destination
the desktop has (the exact bug the UX review flagged: "For Kids disappears on
phones", "chat is a nav item on one breakpoint and invisible on the other").
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

#: Primary destinations that MUST appear on both breakpoints, by href.
SHARED_HREFS = {
    "/home",
    "/events-ui",
    "/calendar",  # F10: Calendar restored to the menu
    "/news",
    "/movies",
    "/family",
    "/seniors",
    "/gas",  # F10: Gas restored to the menu
    "/categories#search",
    "/ask",
    "/portal",
    "/login",
}


def _nav_block(html: str, cls: str) -> str:
    """Return the inner HTML of ``<nav class="{cls} …">…</nav>`` (first match)."""
    m = re.search(rf'<nav class="{cls}\b[^>]*>(.*?)</nav>', html, re.DOTALL)
    assert m, f"no <nav class=\"{cls}\"> block found in page"
    return m.group(1)


def _hrefs(block: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', block))


def test_desktop_nav_and_mobile_drawer_expose_same_destinations() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    desktop = _hrefs(_nav_block(html, "nav"))
    drawer = _hrefs(_nav_block(html, "drawer"))
    # Both surfaces carry the full shared set …
    assert SHARED_HREFS <= desktop, f"desktop nav missing {SHARED_HREFS - desktop}"
    assert SHARED_HREFS <= drawer, f"mobile drawer missing {SHARED_HREFS - drawer}"
    # … and they agree (no destination on one breakpoint but not the other).
    assert desktop == drawer, f"nav/drawer diverge: {desktop ^ drawer}"


def test_for_kids_and_ask_front_doors_present() -> None:
    """The two specifically-named restorations (FIX_SPEC 1.2 acceptance)."""
    html = TestClient(app).get("/home?theme=lake").text
    for cls in ("nav", "drawer"):
        hrefs = _hrefs(_nav_block(html, cls))
        assert "/family" in hrefs, f"For Kids (/family) missing from .{cls}"
        assert "/ask" in hrefs, f"Ask (/ask) missing from .{cls}"
