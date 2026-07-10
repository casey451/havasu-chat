"""Phase 2 — the Lake Ink & Brass events surface (/events-ui?theme=lake).

Verifies the flag swaps in `events_lake.html` (the v10/lake idiom over the SAME
real serve_events_ui context), that desert stays the default, that all three
view modes render, BreadcrumbList JSON-LD is valid, and the page clears the
structural WCAG contract.
"""

from __future__ import annotations

import json
import re
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app


def _get(path: str) -> str:
    return TestClient(app).get(path).text


def test_lake_events_renders_all_views() -> None:
    for path in ("/events-ui?theme=lake", "/events-ui?theme=lake&view=week",
                 "/events-ui?theme=lake&view=month"):
        b = _get(path)
        assert 'data-theme="lake"' in b
        assert "/static/styles/lake_redesign.css" in b
        assert b.count("<h1") == 1
        assert 'aria-label="Breadcrumb"' in b
        assert 'aria-label="Calendar view"' in b
    assert 'class="calmonth"' in _get("/events-ui?theme=lake&view=month")


def test_lake_events_breadcrumb_jsonld_valid() -> None:
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        _get("/events-ui?theme=lake"), re.S,
    )
    assert blocks
    types = {json.loads(b).get("@type") for b in blocks}
    assert "BreadcrumbList" in types


def test_lake_events_structural_a11y() -> None:
    for path in ("/events-ui?theme=lake", "/events-ui?theme=lake&view=week",
                 "/events-ui?theme=lake&view=month"):
        checker = _A11yChecker()
        checker.feed(_get(path))
        issues = checker.finish()
        assert not issues, f"{path}: " + "; ".join(sorted(set(issues)))


def _sample_groups() -> list[dict]:
    return [
        {
            "key": "events", "label": "Around town", "icon": "", "count": 2, "open": True,
            "rows": [
                {"time_label": "6:00 PM", "title": "Sunset Paddle", "venue": "London Bridge Beach", "url": "/events/1", "recurring": False},
                {"time_label": "All day", "title": "Farmers Market", "venue": "Main Street", "url": "/events/2", "recurring": True},
            ],
        },
        {
            "key": "classes", "label": "Fitness & classes", "icon": "", "count": 3, "open": False,
            "subgroups": [
                {"label": "Yoga", "count": 2, "rows": [
                    {"time_label": "6 AM", "title": "Sunrise Flow", "venue": "The Studio", "url": "/events/3", "recurring": True},
                ]},
            ],
        },
    ]


def test_lake_events_day_bindings() -> None:
    # Pin the day view: WS9c makes "weekend" the default landing Fri–Sun
    # (app/home/router.py::_is_weekend_default_day), which renders a different
    # path and bypasses the patched day_groups — so a bare "/events-ui" made this
    # assertion date-rot (green Mon–Thu, red Fri–Sun). ?view=today forces the
    # single-day render on any weekday.
    with patch("app.home.events_views.day_groups", return_value=_sample_groups()):
        b = TestClient(app).get("/events-ui?theme=lake&view=today").text
    assert 'class="sec' in b
    assert "Around town" in b and "Sunset Paddle" in b
    assert "Fitness &amp; classes" in b and "Sunrise Flow" in b  # subgroup row
    # P1: the inconsistent "recurring" row banner is removed across all views.
    assert "Recurring ↻" not in b
    # ItemList of the day's events emitted.
    assert '"@type": "ItemList"' in b
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()
