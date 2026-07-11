"""WS12 Split Finger Athletics (RunSwift) connector.

Camps -> multi-day events with a "camp" title keyword; classes -> one event per
session occurrence, bounded by the horizon; review-queue-first. Fixtures are
trimmed real shapes from the 2026-07-10 RunSwift public-API capture (16:00Z ==
9:00 AM America/Phoenix, UTC-7).
"""

from __future__ import annotations

import json
from datetime import date, time

from app.contrib.approval_service import (
    _DEFAULT_AUTO_APPROVE_EVENT_SOURCES,
    _SCRAPE_EVENT_SOURCES,
)
from app.events.scrapers import SOURCE_REGISTRY
from app.events.scrapers.split_finger import (
    CAMP_URL,
    SplitFingerClient,
    _camp_title,
)

CAMPS = json.dumps(
    [
        {
            "campId": 14860,
            "name": "Softball Summer Session #1 (Ages 7-12)",
            "active": True,
            "previewText": "Fundamentals: Proper hitting mechanics, fielding techniques",
            "minAgeLimit": 7,
            "maxAgeLimit": 12,
            "prices": {"basePrice": {"cost": 70}},
            "service": {
                "type": "CAMP",
                "bookingGroups": [
                    {
                        "bookings": [
                            {"startTime": "2026-07-13T16:00:00.000Z", "endTime": "2026-07-13T18:00:00.000Z"},
                            {"startTime": "2026-07-15T16:00:00.000Z", "endTime": "2026-07-15T18:00:00.000Z"},
                            {"startTime": "2026-07-14T16:00:00.000Z", "endTime": "2026-07-14T18:00:00.000Z"},
                        ]
                    }
                ],
            },
        },
        {
            # Fully past -> must be dropped.
            "campId": 14000,
            "name": "Spring Break Camp",
            "active": True,
            "prices": {"basePrice": {"cost": 70}},
            "service": {
                "type": "CAMP",
                "bookingGroups": [
                    {"bookings": [{"startTime": "2026-03-10T16:00:00.000Z", "endTime": "2026-03-10T18:00:00.000Z"}]}
                ],
            },
        },
    ]
)

CLASSES = json.dumps(
    [
        {
            "classId": 15635,
            "name": "Team Speed & Agility",
            "active": True,
            "previewText": "Speed and agility work for teams",
            "minAgeLimit": 9,
            "maxAgeLimit": None,
            "prices": {"basePrice": {"cost": 10}},
            "service": {
                "type": "CLASS",
                "bookingGroups": [
                    {
                        "bookings": [
                            {"startTime": "2026-06-04T17:00:00.000Z", "endTime": "2026-06-04T18:00:00.000Z"},  # past
                            {"startTime": "2026-07-16T17:00:00.000Z", "endTime": "2026-07-16T18:00:00.000Z"},  # Thu 10 AM
                            {"startTime": "2026-07-23T17:00:00.000Z", "endTime": "2026-07-23T18:00:00.000Z"},
                            {"startTime": "2026-07-23T17:00:00.000Z", "endTime": "2026-07-23T18:00:00.000Z"},  # dup -> collapse
                            {"startTime": "2026-07-30T17:00:00.000Z", "endTime": "2026-07-30T18:00:00.000Z"},
                            {"startTime": "2026-12-01T17:00:00.000Z", "endTime": "2026-12-01T18:00:00.000Z"},  # beyond horizon
                        ]
                    }
                ],
            },
        },
        {
            "classId": 15696,
            "name": "Mom's Softball Night",
            "active": True,
            "prices": {"basePrice": {"cost": 35}},
            "service": {
                "type": "CLASS",
                "bookingGroups": [
                    # 01:00Z -> 18:00 (6 PM) the PREVIOUS Phoenix day (crosses midnight).
                    {"bookings": [{"startTime": "2026-07-25T01:00:00.000Z", "endTime": "2026-07-25T04:00:00.000Z"}]}
                ],
            },
        },
    ]
)


def _client() -> SplitFingerClient:
    c = SplitFingerClient()

    def fake_fetch(url, **kw):  # noqa: ANN001, ANN202
        return CAMPS if "/camp?" in url else CLASSES

    c.fetch_text = fake_fetch  # type: ignore[method-assign]
    return c


def _run(today=date(2026, 7, 10)):
    return _client().run({"today": today})


def test_registered() -> None:
    assert SOURCE_REGISTRY["split_finger"] is SplitFingerClient


def test_camp_becomes_one_multiday_event() -> None:
    camps = [p for p in _run() if "Camp" in p.name and p.end_date]
    assert len(camps) == 1  # the past Spring Break camp is dropped
    c = camps[0]
    assert c.start_date == date(2026, 7, 13)
    assert c.end_date == date(2026, 7, 15)
    assert c.start_time == time(9, 0)
    assert c.end_time == time(11, 0)
    assert c.venue_name == "Split Finger Athletics"
    # /family/camps title-keyword gate + card detail parsing.
    assert "Camp" in c.name
    assert "Ages 7–12" in c.description
    assert "From $70" in c.description
    assert "campId=14860" in (c.event_url or "")


def test_camp_title_only_suffixed_when_missing_keyword() -> None:
    assert _camp_title("Softball Summer Session #1") == "Softball Summer Session #1 — Camp"
    assert _camp_title("Youth Baseball Camp") == "Youth Baseball Camp"
    assert _camp_title("Pitching Clinic") == "Pitching Clinic"


def test_class_occurrences_bounded_and_deduped() -> None:
    team = [p for p in _run() if p.name == "Team Speed & Agility"]
    dates = sorted(p.start_date for p in team)
    # June (past) + December (beyond 45d horizon) dropped; the duplicate 07-23
    # collapses; leaves 3 upcoming Thursdays.
    assert dates == [date(2026, 7, 16), date(2026, 7, 23), date(2026, 7, 30)]
    p = team[0]
    assert p.end_date is None  # single-day occurrence, not a range
    assert p.start_time == time(10, 0)
    assert "From $10 per session" in p.description
    # Distinct booking URL per occurrence (so each lands as its own contribution).
    assert len({p.event_url for p in team}) == 3
    assert "classId=15635" in (p.event_url or "")


def test_class_timezone_crosses_midnight() -> None:
    mom = [p for p in _run() if p.name == "Mom's Softball Night"]
    assert len(mom) == 1
    assert mom[0].start_date == date(2026, 7, 24)  # 01:00Z -> prev Phoenix day
    assert mom[0].start_time == time(18, 0)


def test_lessons_and_rentals_are_not_events() -> None:
    # The connector only reads /camp and /class; private lessons + cage rentals
    # are intentionally never emitted as events.
    names = {p.name for p in _run()}
    assert not any("private lesson" in n.lower() or "cage" in n.lower() for n in names)


def test_review_queue_first() -> None:
    assert "split_finger" not in _DEFAULT_AUTO_APPROVE_EVENT_SOURCES
    assert "split_finger" in _SCRAPE_EVENT_SOURCES


def test_camp_url_is_pure_http_public() -> None:
    # No auth key/secret in the endpoint — pure-HTTP public API.
    assert CAMP_URL.startswith("https://book.runswiftapp.com/api/public/camp?")
    assert "facilityId=760" in CAMP_URL
