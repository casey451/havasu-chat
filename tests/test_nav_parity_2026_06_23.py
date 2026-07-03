"""Nav parity — the desktop nav and the mobile hamburger menu expose the same
primary destinations.

The unified v4 masthead (``_partials/site_header.html``, F11) drives both the
desktop ``.navlinks`` inline nav and the mobile ``.navdrawer-menu`` (the
hamburger menu). This asserts both carry the SAME primary set — so a phone user
never loses a destination the desktop has. The hamburger menu is the COMPLETE
menu (it additionally carries Account + Sign in); the desktop keeps those as the
right-side Sign-in button, so they are not required inside ``.navlinks``.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

#: Primary destinations that MUST appear on both the desktop nav and the menu.
SHARED_HREFS = {
    "/home",
    "/events-ui",
    "/calendar",  # F10: Calendar in the menu
    "/news",
    "/movies",
    "/family",
    "/seniors",
    "/lake",  # F10/F11: Lake added to the menu
    "/gas",  # F10: Gas in the menu
    "/categories#search",
    "/ask",
    "/portal",
}


def _block(html: str, cls: str) -> str:
    """Inner HTML of the first ``<tag class="{cls} …">…</tag>`` (span/div/nav)."""
    m = re.search(rf'<(span|div|nav) class="{cls}\b[^>]*>(.*?)</\1>', html, re.DOTALL)
    assert m, f"no element with class \"{cls}\" found in page"
    return m.group(2)


def _hrefs(block: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', block))


def test_desktop_nav_and_mobile_menu_expose_same_destinations() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    desktop = _hrefs(_block(html, "navlinks"))
    drawer = _hrefs(_block(html, "navdrawer-menu"))
    assert SHARED_HREFS <= desktop, f"desktop nav missing {SHARED_HREFS - desktop}"
    assert SHARED_HREFS <= drawer, f"mobile menu missing {SHARED_HREFS - drawer}"


def test_for_kids_and_ask_front_doors_present() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    for cls in ("navlinks", "navdrawer-menu"):
        hrefs = _hrefs(_block(html, cls))
        assert "/family" in hrefs, f"For Kids (/family) missing from .{cls}"
        assert "/ask" in hrefs, f"Ask (/ask) missing from .{cls}"
