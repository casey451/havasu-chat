"""v4.4 PR-8 — six-link shell + footer/email consistency (Δ9).

The desktop header shows six primary links; the mobile drawer keeps the FULL
destination list so nothing becomes unreachable. Footer is single-sourced with
brass For Business / Advertise; /sponsor is indexable; no havasuchat.com anywhere
in the templates.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

_TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


def _home() -> str:
    with TestClient(app) as client:
        return client.get("/home").text


def _desktop_nav(html: str) -> str:
    i = html.find('class="navlinks')
    return html[i : html.find("</span>", i)] if i >= 0 else ""


def _drawer(html: str) -> str:
    i = html.find("navdrawer-menu")
    return html[i : html.find("</details>", i)] if i >= 0 else ""


def test_desktop_nav_is_the_six_primary_links() -> None:
    nav = _desktop_nav(_home())
    for label in ("Today", "Events", "Lake", "Eat &amp; Drink", "Explore", "For Business"):
        assert label in nav, f"desktop nav missing {label!r}"
    # The secondary destinations are NOT in the desktop bar (they live in pills,
    # cards, footer, and the drawer).
    for label in ("News", "Movies", "Gas", "Calendar", "For Kids", "For Seniors"):
        assert label not in nav, f"desktop nav should not carry {label!r}"


def test_drawer_keeps_every_destination() -> None:
    drawer = _drawer(_home())
    for label in (
        "Today", "Events", "Calendar", "News", "Movies", "For Kids",
        "For Seniors", "Lake", "Eat &amp; Drink", "Gas", "Explore", "For Business",
    ):
        assert label in drawer, f"drawer missing {label!r} (nothing may become unreachable)"


def test_footer_business_links_are_brass() -> None:
    html = _home()
    assert '<a class="biz" href="/portal">For Business</a>' in html
    assert '<a class="biz" href="/sponsor">Advertise</a>' in html
    # Trust line verbatim.
    assert "Real public reviews" in html
    assert "Sponsored clearly labeled" in html
    assert "Built in Lake Havasu" in html


def test_sponsor_is_indexable() -> None:
    with TestClient(app) as client:
        sponsor = client.get("/sponsor").text
    assert 'content="noindex"' not in sponsor


def test_no_havasuchat_com_in_templates() -> None:
    hits = []
    for path in _TEMPLATES.rglob("*.html"):
        if "havasuchat.com" in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path))
    assert not hits, f"havasuchat.com found in templates: {hits}"
