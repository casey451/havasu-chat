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
    assert "Find your spot" in b  # explore section
    # The month calendar always renders (grid or honest empty state); the
    # "Happening" week strip is omitted when there are no events (empty DB).
    assert 'class="mcal"' in b


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
    assert "Sunset Paddle" in b  # today's event title
    # Month grid renders the bound cell with its overflow + class counts.
    assert "+2 more" in b
    assert "12 classes" in b
    # Still structurally accessible with the data populated.
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


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
