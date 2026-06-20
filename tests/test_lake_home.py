"""Phase 1 — the Lake Ink & Brass home (/home?theme=lake).

Verifies the flag swaps in `home_lake.html` (the v10 layout wired to the SAME
real `serve_home` context), that desert stays the default surface, that the
home's structured data is present + valid, and that the page clears the same
WCAG 2.1 AA structural contract as every other page.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

# Reuse the exact structural WCAG checker the desert suite runs (pytest puts the
# tests/ dir on sys.path, so this imports as a top-level module).
from test_ada_compliance import _A11yChecker

from app.main import app


def _lake_home() -> str:
    # Fresh client per call so the QA theme cookie never bleeds across tests.
    return TestClient(app).get("/home?theme=lake").text


def test_desert_home_is_the_default() -> None:
    r = TestClient(app).get("/home")
    assert r.status_code == 200
    assert 'data-theme="lake"' not in r.text
    # Still the desert home (its own stylesheet / hero), unchanged by the flag.
    assert "desert_home.css" in r.text or "home-hero" in r.text


def test_lake_home_renders_with_flag() -> None:
    r = TestClient(app).get("/home?theme=lake")
    assert r.status_code == 200
    b = r.text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_home.css" in b
    assert b.count("<h1") == 1
    assert 'role="search"' in b  # the ask bar
    assert "Find a place or service" in b  # slim directory section
    # Phase 1 hero copy: the H1 + the "search engine" sub-line under the ask box.
    assert "Search like a local." in b
    assert "Lake Havasu's only search engine." in b
    # Phase 1 removed the second month-calendar block from the home (the month
    # grid lives on /events-ui now) — the home strip links out to it instead.
    assert 'class="mcal"' not in b


def _sample_week() -> dict:
    days = [
        {
            "iso": "2026-06-18", "md": "Jun 18", "label": "Thu", "has": True,
            "event_count": 3, "class_count": 12,
            "events": [
                {"time": "6:00 PM", "title": "Sunset Paddle", "type": "water", "recurrence_label": None},
                {"time": "7:30 PM", "title": "Live Music on the Channel", "type": "music", "recurrence_label": None},
            ],
            "categories": [{"key": "music", "label": "Music", "count": 2}],
        }
    ]
    for n in range(19, 25):
        days.append({
            "iso": f"2026-06-{n}", "md": f"Jun {n}", "label": "Fri", "has": n % 2 == 1,
            "event_count": 1 if n % 2 else 0, "class_count": 4, "events": [], "categories": [],
        })
    return {"has_any": True, "days": days}


def _sample_calendar() -> dict:
    cell = {
        "in_month": True, "has": True, "is_today": True, "day": 18, "iso": "2026-06-18",
        "count": 3, "class_count": 12,
        "events": [{"type": "water", "title": "Sunset Paddle"}], "overflow": 2,
    }
    empty = {"in_month": False, "has": False, "is_today": False, "day": None, "iso": None,
             "count": 0, "class_count": 0, "events": [], "overflow": 0}
    return {"label": "June 2026", "prev": "2026-05", "next": "2026-07",
            "has_any": True, "weeks": [[empty] * 4 + [cell] + [empty] * 2]}


def test_lake_home_week_and_calendar_bindings() -> None:
    from unittest.mock import patch

    from app.home import sandstone

    with (
        patch.object(sandstone, "week_strip", return_value=_sample_week()),
        patch.object(sandstone, "calendar_month", return_value=_sample_calendar()),
    ):
        r = TestClient(app).get("/home?theme=lake")
    assert r.status_code == 200
    b = r.text
    # Real week strip + today's events render from the bound data.
    assert 'class="daystrip"' in b
    assert ">18<" in b  # today's day number, derived from iso
    assert "Sunset Paddle" in b  # today's event (emitted in the events JSON-LD)
    # Phase 1 removed the in-home month grid — no month cells render on the home.
    assert 'class="mcal"' not in b
    # Still structurally accessible with the data populated.
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


def _sample_feed() -> dict:
    return {
        "summary": "1 event · 1 class · 1 movie",
        "groups": [
            {"key": "events", "label": "Events", "count": 1, "open": True, "rows": [
                {"time_label": "8 AM", "title": "ZZ Farmers Market", "venue": "Visitor Center",
                 "url": "/events/1", "recurring": False, "tags": ["Kids"]},
            ]},
            {"key": "classes", "label": "Classes & fitness", "count": 1, "open": False, "rows": [
                {"time_label": "6 PM", "title": "ZZ Sunrise Yoga", "venue": "Eight Lotus",
                 "url": "/events/2", "recurring": True, "tags": []},
            ]},
            {"key": "movies", "label": "At the movies", "count": 1, "open": False, "films": [
                {"title": "ZZ Robin Hood", "tags": ["Kids"], "summary": "Star Cinemas · next 6:30 PM",
                 "url": "https://x/book", "theaters": [{"name": "Star Cinemas", "times": ["6:30 PM"]}]},
            ]},
        ],
    }


def test_lake_home_today_feed_renders() -> None:
    """The home renders the four-group unified feed: Events open by default, the
    rest collapsed, audience tags, and per-theater movie showtimes."""
    from unittest.mock import patch

    from app.home import router as home_router

    with patch.object(home_router, "today_feed", return_value=_sample_feed()):
        b = TestClient(app).get("/home?theme=lake").text

    # Four-group feed present; Events open, others collapsed.
    assert 'class="today-groups tfeed"' in b
    assert 'data-group="events" open' in b
    assert 'data-group="classes"' in b and 'data-group="classes" open' not in b
    assert 'data-group="movies"' in b
    # Rows + audience tag + per-theater movie showtime render.
    assert "ZZ Farmers Market" in b
    assert "ZZ Sunrise Yoga" in b
    assert "ZZ Robin Hood" in b
    assert '<span class="rtag kids">Kids</span>' in b
    assert "6:30 PM" in b
    # The single lightweight filter control is present.
    assert 'id="feed-filter"' in b
    # Still structurally accessible with the feed populated.
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


def test_lake_nav_unified_across_breakpoints() -> None:
    """The lean primary destinations appear in BOTH the desktop header nav and
    the mobile drawer, so no front-door vanishes on mobile (Phase 1 nav fix)."""
    b = _lake_home()
    assert 'id="lk-menu-btn"' in b  # the hamburger toggle exists

    # Isolate the desktop primary nav and the mobile drawer markup.
    desktop = re.search(r'<nav class="nav"[^>]*>(.*?)</nav>', b, re.S)
    drawer = re.search(r'<nav class="drawer"[^>]*>(.*?)</nav>', b, re.S)
    assert desktop and drawer, "both the desktop nav and mobile drawer must render"

    lean = ('href="/events-ui"', 'href="/categories"', 'href="/map"',
            'href="/portal"', 'href="/login"')
    for href in lean:
        assert href in desktop.group(1), f"{href} missing from desktop nav"
        assert href in drawer.group(1), f"{href} missing from mobile drawer"
    # Category front-doors were trimmed out of the header (they live in the
    # directory zone now), so the heavy nav is genuinely lean.
    assert 'href="/categories/eat-and-drink"' not in desktop.group(1)


def test_lake_home_slim_directory() -> None:
    """Phase 3: the home directory is one slim block — a keyword search into
    /search, six high-traffic front doors, and a single "see all" line. The old
    15-tile grid + duplicate "Need something done?" strip are gone."""
    b = _lake_home()
    # Keyword search field wired to the real /search results page.
    assert 'class="dirsearch"' in b
    assert 'action="/search"' in b
    # The six curated front doors (curated nav — present even on an empty DB).
    for label in ("Eat &amp; Drink", "Home Services", "Health", "Auto &amp; Boat"):
        assert label in b
    # One line to the rest of the taxonomy.
    assert 'class="dmore"' in b
    assert 'href="/categories"' in b
    # The duplicate service strip is gone from the slim directory.
    assert "Need something done?" not in b


def test_lake_home_structural_a11y() -> None:
    checker = _A11yChecker()
    checker.feed(_lake_home())
    issues = checker.finish()
    assert not issues, "; ".join(sorted(set(issues)))


def test_lake_home_jsonld_is_present_and_valid() -> None:
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', _lake_home(), re.S
    )
    assert blocks, "lake home emits no JSON-LD"
    types = set()
    for blk in blocks:
        data = json.loads(blk)  # must parse as valid JSON
        types.add(data.get("@type"))
    # Site-wide brand + search schema the home is the canonical page for.
    assert "Organization" in types
    assert "WebSite" in types


def test_lake_home_search_action_targets_chat() -> None:
    b = _lake_home()
    assert "SearchAction" in b
    assert "/chat?q={search_term_string}" in b
