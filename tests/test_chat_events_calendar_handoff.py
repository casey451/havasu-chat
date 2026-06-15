"""A4 (Phase E build half) — chat events answers carry a deep-link to the
interactive filtered /events-ui calendar.

Covers the pure link logic the unified router calls via attach_calendar_link:
the window→view mapping, the family toggle, and the gate that leaves every
non-events answer untouched.
"""

from __future__ import annotations

from app.events.calendar_links import (
    EVENTS_CALENDAR_COMPONENTS,
    attach_calendar_link,
    events_calendar_url,
    is_family_query,
)


def test_calendar_url_window_mapping() -> None:
    assert events_calendar_url("today") == "/events-ui"
    assert events_calendar_url("tonight") == "/events-ui"
    assert events_calendar_url(None) == "/events-ui"
    assert events_calendar_url("tomorrow") == "/events-ui?view=week"
    assert events_calendar_url("this_weekend") == "/events-ui?view=week"
    assert events_calendar_url("this_week") == "/events-ui?view=week"
    assert events_calendar_url("month") == "/events-ui?view=month"


def test_calendar_url_family_toggle() -> None:
    assert events_calendar_url("today", family=True) == "/events-ui?family=1"
    assert events_calendar_url("this_weekend", family=True) == "/events-ui?view=week&family=1"


def test_is_family_query() -> None:
    assert is_family_query("anything fun for kids this weekend") is True
    assert is_family_query("family events tonight") is True
    assert is_family_query("live music tonight") is False
    assert is_family_query(None) is False


def test_attach_calendar_link_adds_url_for_events_components() -> None:
    for ctype in EVENTS_CALENDAR_COMPONENTS:
        data = {"days": [], "total_count": 0}
        out = attach_calendar_link(ctype, data, when="this_weekend")
        assert out["calendar_url"] == "/events-ui?view=week"
        # Original keys preserved; input dict not mutated.
        assert out["total_count"] == 0
        assert "calendar_url" not in data


def test_attach_calendar_link_family_query() -> None:
    out = attach_calendar_link(
        "day_agenda", {"agenda": []}, when="today", query="kids stuff today"
    )
    assert out["calendar_url"] == "/events-ui?family=1"


def test_attach_calendar_link_noop_without_events_intent_or_component() -> None:
    # No events `when` → unchanged (same object).
    data = {"items": []}
    assert attach_calendar_link("day_agenda", data, when=None) is data
    # Non-events component → unchanged even with a `when`.
    biz = {"items": []}
    assert attach_calendar_link("business_list", biz, when="this_weekend") is biz
    assert "calendar_url" not in biz
