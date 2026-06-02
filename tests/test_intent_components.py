"""Pure tests for the intent-layer card wiring (no DB).

Verifies that provider results build a ``business_list`` component and event
results build ``day_agenda`` (single day) / ``week_strip`` (multi-day), reusing
the existing app.chat.component_builders.
"""

from __future__ import annotations

from datetime import date

from app.chat.intents.queries import QueryResult
from app.chat.intents.runtime import _build_events, _build_providers


def _provider_row(name, rating=4.5):
    return {
        "type": "provider",
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "phone": "(928) 555-0100",
        "address": "100 Main St",
        "category": "home_services",
        "google_primary_category": "plumber",
        "google_rating": rating,
        "google_review_count": 40,
        "hours_structured": None,
        "description": "",
        "tier": "free",
        "sponsored_until": None,
        "thumb_url": None,
    }


def _event_row(name, day, start, venue="The Pier", tags=None):
    return {
        "type": "event",
        "name": name,
        "date": day,
        "end_date": None,
        "start_time": start,
        "end_time": None,
        "location_name": venue,
        "tags": tags or [],
        "event_url": "",
    }


def test_providers_build_business_list():
    qr = QueryResult(
        "find_service",
        "providers",
        [_provider_row("Ace Plumbing", 4.8), _provider_row("Bay Plumbing", 4.2)],
        "services",
        "Here's who can help:",
        label="plumber",
    )
    voice, ctype, data = _build_providers(qr)
    assert ctype == "business_list"
    names = [it["name"] for it in data["items"]]
    assert "Ace Plumbing" in names
    # Higher-rated first.
    assert names[0] == "Ace Plumbing"
    assert voice and "?" not in voice


def test_events_single_day_builds_day_agenda():
    today = date(2026, 6, 1)  # Monday
    rows = [
        _event_row("Taco Night", "2026-06-01", "18:00", tags=["food"]),
        _event_row("Live Band", "2026-06-01", "20:00", tags=["music"]),
    ]
    qr = QueryResult("events_today", "events", rows, "events", "", window="today")
    voice, ctype, data = _build_events(qr, today=today)
    assert ctype == "day_agenda"
    assert len(data["events"]) == 2
    assert voice


def test_events_week_builds_week_strip():
    today = date(2026, 6, 1)  # Monday
    rows = [_event_row(f"Event {i}", "2026-06-03", "10:00") for i in range(3)]
    qr = QueryResult("events_this_week", "events", rows, "events", "", window="this_week")
    voice, ctype, data = _build_events(qr, today=today)
    assert ctype == "week_strip"
    assert "days" in data and len(data["days"]) == 7
    assert voice
