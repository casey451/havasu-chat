"""Phase 2b — the /calendar discovery page + the concierge intent-router.

Covers the deterministic intent parser, the server-rendered /calendar page
(real per-day data, removable "Hava understood" chips, a11y, noindex), and the
FLAG-GATED concierge router: lake routes (discovery → /calendar, else → search)
while desert keeps the conversational fallback unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.categories import leaf_query
from app.home.calendar_view import is_discovery_query, parse_calendar_query
from app.main import app

# ── intent parser (pure) ────────────────────────────────────────────────────

def test_parse_extracts_day_time_audience_age() -> None:
    f = parse_calendar_query("things for my 8 year old tuesday and thursday afternoons")
    assert f["aud"] == "kids" and f["age"] == "8" and f["part"] == "afternoon"
    assert "Tue" in f["days"] and "Thu" in f["days"]


def test_parse_type_and_weekend() -> None:
    f = parse_calendar_query("live music this weekend")
    assert f["type"] == "music"
    assert set(f["days"]) == {"Sat", "Sun"}


def test_parse_tonight_is_today_evening() -> None:
    f = parse_calendar_query("what's happening tonight")
    assert f["part"] == "evening" and f["days"] == ["Today"]


def test_is_discovery_query() -> None:
    assert is_discovery_query("what's happening tonight")
    assert is_discovery_query("live music this weekend")
    assert is_discovery_query("kids stuff today")
    assert not is_discovery_query("best sushi spot downtown")
    assert not is_discovery_query("a plumber for a leak")


# ── /calendar page ──────────────────────────────────────────────────────────

def test_calendar_renders_lake_and_noindex() -> None:
    r = TestClient(app).get("/calendar")
    assert r.status_code == 200
    b = r.text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_calendar.css" in b
    assert 'name="robots" content="noindex' in b
    assert "noindex" in (r.headers.get("x-robots-tag") or "")
    assert b.count("<h1") == 1
    assert 'role="search"' in b  # the refine form
    assert 'aria-label="Time of day"' in b  # segmented controls


def test_calendar_understood_chips_from_query() -> None:
    b = TestClient(app).get("/calendar?q=live+music+this+weekend").text
    assert "Hava understood" in b
    assert "Live music" in b  # derived title
    assert "Music" in b  # type chip
    assert "“live music this weekend”" in b  # readback


def test_calendar_structural_a11y() -> None:
    for path in ("/calendar", "/calendar?q=kids+tomorrow", "/calendar?q=live+music+tonight"):
        checker = _A11yChecker()
        checker.feed(TestClient(app).get(path).text)
        issues = checker.finish()
        assert not issues, f"{path}: " + "; ".join(sorted(set(issues)))


def _sample_groups() -> list[dict]:
    return [{
        "key": "events", "label": "Around town", "icon": "", "count": 1, "open": True,
        "rows": [{"time_label": "6:00 PM", "title": "Sunset Paddle", "venue": "Site Six", "url": "/events/1", "recurring": False}],
    }]


def test_calendar_columns_bind_real_rows() -> None:
    with patch("app.home.events_views.day_groups", return_value=_sample_groups()):
        b = TestClient(app).get("/calendar?days=Today").text
    assert 'class="col"' in b
    assert "Sunset Paddle" in b and "Site Six" in b


# ── concierge intent-router (flag-gated) ────────────────────────────────────

class _FakeLeaf:
    department_slug = "home-property-services"
    slug = "plumbers"


def test_chat_desert_still_chats() -> None:
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get("/chat?q=live music tonight", follow_redirects=False)
    assert r.status_code == 200  # conversational scaffold, NOT routed


def test_chat_lake_routes_discovery_to_calendar() -> None:
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get("/chat?q=live music tonight&theme=lake", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/calendar?q=")


def test_chat_lake_unplaced_falls_back_to_search() -> None:
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get("/chat?q=best sushi spot downtown&theme=lake", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/search?q=")


def test_chat_service_leaf_routes_in_both_themes() -> None:
    with patch.object(leaf_query, "match_leaf_query", return_value=_FakeLeaf()):
        for suffix in ("", "&theme=lake"):
            r = TestClient(app).get(f"/chat?q=plumbers{suffix}", follow_redirects=False)
            assert r.status_code == 302
            assert r.headers["location"] == "/categories/home-property-services/plumbers"
