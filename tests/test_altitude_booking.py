"""WS12 Altitude ROLLER booking connector — camp filter, dates, review-queue-first."""

from __future__ import annotations

import json
from datetime import date, time

from app.contrib.approval_service import (
    _DEFAULT_AUTO_APPROVE_EVENT_SOURCES,
    _SCRAPE_EVENT_SOURCES,
)
from app.events.scrapers.altitude_booking import (
    AltitudeBookingClient,
    _is_camp,
    _min_cost,
)

# Trimmed real shapes from the 2026-07-10 ROLLER capture.
PRODUCTS = json.dumps(
    [
        {"id": "765285", "name": "High Flyer Membership", "type": "membership",
         "products": [{"id": "1", "cost": 19.99}]},
        {"id": "765248", "name": "Jump Grip Socks", "type": "addon",
         "products": [{"id": "2", "cost": 3.5}]},
        {"id": "810570", "name": "Activity Camp- Full Day", "type": "session",
         "shortDescription": "Full-Day Activity Day Camp! 9:00 am- 4:00 pm",
         "products": [
             {"id": "810571", "name": "Activity Day Camp", "cost": 36.99},
             {"id": "810572", "name": "Member: Activity Camp", "cost": 26.99},
         ]},
        {"id": "1592720", "name": "90 Day Pass", "type": "membership",
         "products": [{"id": "3", "cost": 99.0}]},
    ]
)
# 2026-07-13 is a Monday; include a weekend day that must be dropped.
AVAIL = json.dumps(
    [
        {"date": "2026-07-13", "availability": "available"},  # Mon
        {"date": "2026-07-14", "availability": "available"},  # Tue
        {"date": "2026-07-18", "availability": "available"},  # Sat -> dropped
        {"date": "2026-07-20", "availability": "soldOut"},    # Mon but not available
    ]
)


def _client() -> AltitudeBookingClient:
    c = AltitudeBookingClient()

    def fake_fetch(url, **kw):  # noqa: ANN001, ANN202
        return PRODUCTS if url.endswith("/products") else AVAIL

    c.fetch_text = fake_fetch  # type: ignore[method-assign]
    return c


def test_camp_filter() -> None:
    assert _is_camp({"name": "Activity Camp- Full Day", "type": "session"})
    assert not _is_camp({"name": "High Flyer Membership", "type": "membership"})
    assert not _is_camp({"name": "Jump Grip Socks", "type": "addon"})
    assert not _is_camp({"name": "90 Day Pass", "type": "membership"})


def test_min_cost_is_from_price() -> None:
    prod = {"products": [{"cost": 36.99}, {"cost": 26.99}]}
    assert _min_cost(prod) == 26.99  # "From $26.99"


def test_discover_only_weekday_available_camp_dates() -> None:
    payloads = _client().run({"today": date(2026, 7, 13)})
    # Only the Mon + Tue available camp dates survive (Sat dropped, soldOut dropped).
    dates = sorted(p.start_date for p in payloads)
    assert dates == [date(2026, 7, 13), date(2026, 7, 14)]
    p = payloads[0]
    assert p.start_time == time(9, 0)
    assert p.end_time == time(16, 0)
    assert p.venue_name == "Altitude Trampoline Park"
    assert "Camp" in p.name
    assert "From $26.99" in p.description
    assert "date=2026-07-13" in (p.event_url or "")


def test_review_queue_first() -> None:
    assert "altitude_booking" not in _DEFAULT_AUTO_APPROVE_EVENT_SOURCES
    assert "altitude_booking" in _SCRAPE_EVENT_SOURCES
