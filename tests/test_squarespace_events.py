"""WS12 Squarespace events connector — Lake Havasu Museum of History (C5)."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.contrib.approval_service import (
    _DEFAULT_AUTO_APPROVE_EVENT_SOURCES,
    _SCRAPE_EVENT_SOURCES,
)
from app.events.scrapers.squarespace_events import HavasuMuseumClient

_PHX = ZoneInfo("America/Phoenix")


def _phx_ms(y: int, mo: int, d: int, h: int, mi: int) -> int:
    """Epoch milliseconds for a Lake Havasu wall-clock datetime (Squarespace form)."""
    return int(datetime(y, mo, d, h, mi, tzinfo=_PHX).timestamp() * 1000)


def _feed(items: list[dict]) -> str:
    return json.dumps({"collection": {"typeName": "events-stacked"}, "items": items})


UPCOMING_FEED = _feed(
    [
        {
            "title": "McCulloch In The Air — Grand Opening",
            "startDate": _phx_ms(2026, 8, 15, 18, 0),
            "endDate": _phx_ms(2026, 8, 15, 20, 0),
            "fullUrl": "/upcoming-events/mcculloch-in-the-air",
            "excerpt": "The J-2 Gyroplane on display in the museum parking lot.",
            "location": {
                "addressLine1": "320 London Bridge Rd",
                "addressLine2": "Lake Havasu City, AZ 86403",
            },
        },
        {
            # No location block -> falls back to the museum default venue.
            "title": "Founders' Day Talk",
            "startDate": _phx_ms(2026, 9, 1, 10, 30),
            "endDate": None,
            "fullUrl": "/upcoming-events/founders-day",
            "excerpt": "A morning history talk.",
            "location": None,
        },
        {
            # Past event -> must be dropped even if the feed lists it.
            "title": "Last Year's Gala",
            "startDate": _phx_ms(2025, 12, 1, 18, 0),
            "endDate": _phx_ms(2025, 12, 1, 21, 0),
            "fullUrl": "/upcoming-events/gala-2025",
            "excerpt": "",
            "location": None,
        },
    ]
)


def _client(feed: str) -> HavasuMuseumClient:
    c = HavasuMuseumClient()
    c.fetch_text = lambda url, **kw: feed  # type: ignore[method-assign]
    return c


def test_museum_parses_upcoming_local_times() -> None:
    payloads = {p.name: p for p in _client(UPCOMING_FEED).run({"today": date(2026, 7, 9)})}

    grand = payloads["McCulloch In The Air — Grand Opening"]
    assert grand.start_date == date(2026, 8, 15)
    assert grand.start_time == time(18, 0)  # America/Phoenix wall time round-trips
    assert grand.end_time == time(20, 0)
    assert grand.event_url == "https://www.havasumuseum.com/upcoming-events/mcculloch-in-the-air"
    # location block -> event's own address; venue shape is honored.
    assert grand.venue_name == "320 London Bridge Rd, Lake Havasu City, AZ 86403"

    talk = payloads["Founders' Day Talk"]
    assert talk.start_time == time(10, 30)
    assert talk.end_time is None
    # no location -> museum default venue.
    assert talk.venue_name == "Lake Havasu Museum of History"


def test_museum_drops_past_events() -> None:
    payloads = _client(UPCOMING_FEED).run({"today": date(2026, 7, 9)})
    assert not any(p.name == "Last Year's Gala" for p in payloads)


def test_museum_empty_collection_is_graceful() -> None:
    """The live collection is currently empty; that must yield [] not a crash."""
    payloads = _client(_feed([])).run({"today": date(2026, 7, 9)})
    assert payloads == []


def test_museum_is_review_queue_first() -> None:
    assert "havasu_museum" not in _DEFAULT_AUTO_APPROVE_EVENT_SOURCES
    assert "havasu_museum" in _SCRAPE_EVENT_SOURCES
