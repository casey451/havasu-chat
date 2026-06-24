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
    # P3 directory-first hero copy: the "search engine" / "search like a local"
    # framing is gone; the H1 + sub-line lead with the directory promise (§2.7).
    assert "Everything in Lake Havasu, in one place." in b
    assert "The local directory for Lake Havasu City" in b
    assert "Search like a local." not in b
    assert "only search engine" not in b
    # Phase 1 removed the second month-calendar block from the home (the month
    # grid lives on /events-ui now) — the home strip links out to it instead.
    assert 'class="mcal"' not in b


def _sample_week() -> dict:
    days = [
        {
            "iso": "2026-06-18", "md": "Jun 18", "label": "Thu", "dow": "Thu", "has": True,
            "event_count": 3, "class_count": 12,
            "events": [
                {"time": "6:00 PM", "title": "Sunset Paddle", "type": "water", "recurrence_label": None},
                {"time": "7:30 PM", "title": "Live Music on the Channel", "type": "music", "recurrence_label": None},
            ],
            "categories": [{"key": "music", "label": "Music", "count": 2}],
        }
    ]
    _dow = {19: "Fri", 20: "Sat", 21: "Sun", 22: "Mon", 23: "Tue", 24: "Wed"}
    for n in range(19, 25):
        days.append({
            "iso": f"2026-06-{n}", "md": f"Jun {n}", "label": "Fri", "dow": _dow[n],
            "has": n % 2 == 1,
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


def _sample_groups() -> list:
    # day_groups-shaped (the /events-ui organized structure the home now reuses).
    return [
        {"key": "events", "label": "Happening today", "icon": "", "count": 1, "open": True,
         "rows": [{"time_label": "12 PM", "title": "ZZ Bridge Days", "venue": "The Bridge",
                   "url": "/events/1", "type_label": None}]},
        {"key": "classes", "label": "Fitness & classes", "icon": "", "count": 2, "open": False,
         "rows": [], "subgroups": [
            {"label": "Yoga", "count": 1, "rows": [
                {"time_label": "6 AM", "title": "ZZ Inferno", "venue": "Amalaya Yoga",
                 "url": "/provider/amalaya", "type_label": None}]},
            {"label": "Martial Arts", "count": 1, "rows": [
                {"time_label": "7 PM", "title": "ZZ MMA", "venue": "The Tap Room",
                 "url": "/provider/tap-room", "type_label": None}]},
         ]},
    ]


def _sample_movies_feed() -> dict:
    # Only the "At the movies" group is consumed from today_feed now (day_groups
    # builds everything else); it's the collapsed per-film showtime rollup.
    return {
        "summary": "", "groups": [
            {"key": "movies", "label": "At the movies", "count": 1, "open": False, "films": [
                {"title": "ZZ Robin Hood", "tags": ["Kids"], "summary": "Star Cinemas · next 6:30 PM",
                 "url": "https://x/book", "theaters": [{"name": "Star Cinemas", "times": ["6:30 PM"]}]},
            ]},
        ],
    }


def test_lake_home_today_feed_renders() -> None:
    """The home now renders the SAME organized day-group structure as /events-ui
    (typed subsections, real group keys), plus the collapsed "At the movies"
    group from today_feed. "Happening today" opens by default, the rest collapse."""
    from unittest.mock import patch

    from app.home import router as home_router

    with (
        patch.object(home_router.events_views, "day_groups", return_value=_sample_groups()),
        patch.object(home_router, "today_feed", return_value=_sample_movies_feed()),
    ):
        b = TestClient(app).get("/home?theme=lake").text

    # Feed present; "Happening today" open, others collapsed.
    assert 'class="today-groups tfeed"' in b
    assert 'data-group="events" open' in b
    assert 'data-group="classes"' in b and 'data-group="classes" open' not in b
    assert 'data-group="movies"' in b
    # Rows + typed Fitness subsections + the movie showtime (from today_feed).
    assert "ZZ Bridge Days" in b
    assert "ZZ Inferno" in b and "ZZ MMA" in b
    assert 'class="tg-subhead"' in b
    assert ">Yoga<" in b and ">Martial Arts<" in b
    assert "ZZ Robin Hood" in b
    assert "6:30 PM" in b
    # No per-row green KIDS pill, no audience rtag in the feed.
    assert 'class="rtag kids"' not in b
    assert ">Kids</span>" not in b
    # The dropped controls stay gone: no "Show" filter, no Try-chips, no big heading.
    assert 'id="feed-filter"' not in b
    assert 'class="tryrow"' not in b
    assert "Today in Lake Havasu" not in b
    # The day picker is a grid (no scroll) with a Full-calendar button; the old
    # top "Full calendar" link in the feed header is gone (FIX_DAYPICKER 2–3).
    assert 'class="daystrip-wrap"' in b
    assert 'class="day daycal"' in b
    assert 'class="full"' not in b
    # Still structurally accessible with the feed populated.
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


def test_lake_home_daypicker_is_weekday_grid_linking_home() -> None:
    """FIX_DAYPICKER items 1–3: every tile is labelled by weekday abbreviation,
    the tiles re-render the HOME feed for the day (``/home?date=``, not the
    separate ``/events-ui?date=`` page), and a Full-calendar button stands in for
    the removed top link."""
    from unittest.mock import patch

    from app.home import sandstone

    with patch.object(sandstone, "week_strip", return_value=_sample_week()):
        b = TestClient(app).get("/home?theme=lake").text

    # Grid, not a scroll container; every weekday abbreviation appears as a label.
    assert 'class="daystrip"' in b
    for dow in ("Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"):
        assert f'<span class="dow">{dow}</span>' in b
    # Tiles re-render the home feed for the day (no jump to the /events-ui page).
    assert 'href="/home?date=2026-06-20#today"' in b
    assert 'href="/events-ui?date=' not in b
    # The Full-calendar button (spanning the last two cells) opens the week view
    # of the calendar (FIX_POSTERS_AND_CALENDAR item 2).
    assert 'class="day daycal" href="/events-ui?view=week"' in b
    assert ">Full calendar</span>" in b
    # The old top "Full calendar" link in the feed header is removed (item 3).
    assert 'class="full"' not in b


def test_lake_home_daychip_binds_event_count_not_class_inflated_total() -> None:
    """Finding 30: the day-picker chip's trailing number is the per-day EVENT
    count (``event_count``), never the events+recurring-classes total
    (``count``). The total balloons to 40-60 on a weekday (dominated by recurring
    class occurrences) and rendered as a meaningless number ("Mon 22 64"). Give a
    day where the two diverge sharply and pin that the chip uses the event count.
    """
    from unittest.mock import patch

    from app.home import sandstone

    week = {
        "has_any": True,
        "days": [
            {
                "iso": "2026-06-21", "md": "Jun 21", "label": "Sun", "dow": "Sun",
                "has": True, "event_count": 3, "class_count": 47, "count": 50,
                "events": [], "categories": [],
            }
        ],
    }
    with (
        patch.object(sandstone, "week_strip", return_value=week),
        patch.object(sandstone, "calendar_month", return_value=_sample_calendar()),
    ):
        b = TestClient(app).get("/home?theme=lake").text

    # The chip + its aria-label carry the event count, not the class-inflated total.
    assert 'aria-label="3 events on Sun Jun 21"' in b
    assert "50 events on Sun Jun 21" not in b
    assert ">50<" not in b  # the events+classes total is never the chip figure


def test_lake_home_date_param_renders_selected_day() -> None:
    """FIX_DAYPICKER item 4: ``?date=`` re-renders the home feed for a non-today
    day with the correct long date label and that day's tile highlighted — no
    "Happening today" heading and no separate page (same template = no font jump)."""
    from unittest.mock import patch

    from app.home import sandstone

    with patch.object(sandstone, "week_strip", return_value=_sample_week()):
        b = TestClient(app).get("/home?theme=lake&date=2026-06-21").text

    # The feed's small date label reflects the selected day, not "today".
    assert "Sunday, June 21" in b
    assert "Happening today" not in b
    # The selected tile (Sun 21) carries the highlight + aria-current.
    assert 'class="day today"' in b
    assert 'href="/home?date=2026-06-21#today"' in b
    assert 'aria-current="date"' in b


def test_lake_nav_unified_across_breakpoints() -> None:
    """The lean primary destinations appear in BOTH the desktop header nav and
    the mobile drawer, so no front-door vanishes on mobile (Phase 1 nav fix)."""
    b = _lake_home()
    assert 'id="lk-menu-btn"' in b  # the hamburger toggle exists

    # Isolate the desktop primary nav and the mobile drawer markup.
    desktop = re.search(r'<nav class="nav"[^>]*>(.*?)</nav>', b, re.S)
    drawer = re.search(r'<nav class="drawer"[^>]*>(.*?)</nav>', b, re.S)
    assert desktop and drawer, "both the desktop nav and mobile drawer must render"

    # P3 canonical six: Home · Events · Movies · Explore · For Business · Sign in.
    lean = ('href="/home"', 'href="/events-ui"', 'href="/movies"',
            'href="/categories#search"', 'href="/portal"', 'href="/login"')
    for href in lean:
        assert href in desktop.group(1), f"{href} missing from desktop nav"
        assert href in drawer.group(1), f"{href} missing from mobile drawer"
    # Map and Ask were removed from the nav (P3): Map route stays live but
    # unlinked; chat is no longer an identity front door.
    for gone in ('href="/map"', 'href="/chat"'):
        assert gone not in desktop.group(1), f"{gone} should be gone from desktop nav"
        assert gone not in drawer.group(1), f"{gone} should be gone from mobile drawer"
    # Category front-doors were trimmed out of the header (they live in the
    # directory zone now), so the heavy nav is genuinely lean.
    assert 'href="/categories/eat-and-drink"' not in desktop.group(1)


def test_lake_home_slim_directory() -> None:
    """P3: the home directory zone is browse-first — top front doors + one "see
    all" line. The keyword search lives only in the hero (one search bar per the
    home brief); the duplicate lower /search box was removed."""
    b = _lake_home()
    # The second/bottom search bar is gone; only the hero search remains.
    assert 'class="dirsearch"' not in b
    assert b.count('role="search"') == 1
    # The curated front doors (curated nav — present even on an empty DB).
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
