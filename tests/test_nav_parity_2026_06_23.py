"""Nav shape — desktop bar is the six primary links; the drawer is complete.

v4.4 §7 (2026-07-02) deliberately split the shared header: the desktop ``.navlinks``
shows only the six primary destinations, while the mobile ``.navdrawer-menu`` keeps
the FULL list so a phone user never loses a destination. (Before v4.4 both carried
the same set; that parity was replaced by this primary/complete split.)
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

#: The six primary destinations on the desktop bar (For Business = /portal).
DESKTOP_HREFS = {
    "/home",
    "/events-ui",
    "/lake",
    "/categories/eat-and-drink",
    "/categories#search",
    "/portal",
}

#: The complete destination set the mobile drawer must still expose (nothing
#: becomes unreachable when it leaves the desktop bar).
COMPLETE_HREFS = DESKTOP_HREFS | {
    "/calendar",
    "/news",
    "/movies",
    "/family",
    "/seniors",
    "/gas",
    "/ask",
}

#: Secondary destinations that must NOT clutter the desktop bar.
SECONDARY_HREFS = {"/calendar", "/news", "/movies", "/gas", "/family", "/seniors", "/ask"}


def _block(html: str, cls: str) -> str:
    m = re.search(rf'<(span|div|nav) class="{cls}\b[^>]*>(.*?)</\1>', html, re.DOTALL)
    assert m, f"no element with class \"{cls}\" found in page"
    return m.group(2)


def _hrefs(block: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', block))


def test_desktop_bar_is_the_six_primary_links() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    desktop = _hrefs(_block(html, "navlinks"))
    assert DESKTOP_HREFS <= desktop, f"desktop nav missing {DESKTOP_HREFS - desktop}"
    assert not (SECONDARY_HREFS & desktop), (
        f"secondary destinations should not be on the desktop bar: {SECONDARY_HREFS & desktop}"
    )


def test_drawer_keeps_the_complete_menu() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    drawer = _hrefs(_block(html, "navdrawer-menu"))
    assert COMPLETE_HREFS <= drawer, f"mobile drawer missing {COMPLETE_HREFS - drawer}"


def test_for_kids_and_ask_reachable_via_drawer() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    drawer = _hrefs(_block(html, "navdrawer-menu"))
    assert "/family" in drawer, "For Kids (/family) must stay reachable in the drawer"
    assert "/ask" in drawer, "Ask (/ask) must stay reachable in the drawer"
