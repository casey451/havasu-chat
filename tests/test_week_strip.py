"""This-week strip — next 7 days, events ranked by importance.

Replaces the old "Today around the lake" card pair. Verifies the 7-day shape,
the importance tiering (festival/special > water > music > community > class),
and that recurring aquatic-center classes sink into the "+N more" overflow
rather than crowding out a one-off. No HTTP; real Event rows on an in-memory-ish
SQLite session (the project's shared test DB), wiped per test.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event
from app.home import sandstone

_TODAY = date(2026, 6, 5)  # a Friday


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe_events(db: Session):
    db.query(Event).delete()
    db.commit()
    yield
    db.query(Event).delete()
    db.commit()


def _add(
    db: Session,
    *,
    title: str,
    on_date: date = _TODAY,
    start: time = time(10, 0),
    tags: list[str] | None = None,
    featured: bool = False,
    recurring: bool = False,
) -> None:
    db.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=on_date,
            start_time=start,
            location_name="Test Venue",
            location_normalized="test venue",
            description="An event",
            event_url="https://example.com/e",
            tags=tags or [],
            status="live",
            source="test_week_strip",
            verified=True,
            featured=featured,
            is_recurring=recurring,
        )
    )
    db.commit()


# --- tiering (pure) ---------------------------------------------------------


@pytest.mark.parametrize(
    "title,tags,featured,recurring,expected",
    [
        ("London Bridge Days Festival", [], False, False, sandstone._TIER_SPECIAL),
        ("Spring Concert", [], True, False, sandstone._TIER_SPECIAL),  # featured wins
        ("Sunset Kayak Tour", ["kayak"], False, False, sandstone._TIER_WATER),
        ("Live Music at The Nautical", [], False, False, sandstone._TIER_MUSIC),
        ("Downtown Farmers Market", [], False, False, sandstone._TIER_COMMUNITY),
        ("Aqua Aerobics", [], False, True, sandstone._TIER_CLASS),
        ("Lap Swim", [], False, True, sandstone._TIER_CLASS),
        ("Mystery Pop-up", [], False, False, sandstone._TIER_COMMUNITY),  # one-off default
        ("Standing Group", [], False, True, sandstone._TIER_CLASS),  # recurring default
    ],
)
def test_event_tier(title, tags, featured, recurring, expected) -> None:
    assert (
        sandstone._event_tier(title=title, tags=tags, featured=featured, recurring=recurring)
        == expected
    )


@pytest.mark.parametrize(
    "t,expected",
    [
        (time(8, 0), "8 AM"),
        (time(18, 30), "6:30 PM"),
        (time(12, 0), "12 PM"),  # noon, not "2 PM"
        (time(0, 15), "12:15 AM"),  # midnight, not ":15 AM"
        (time(0, 0), "12 AM"),
    ],
)
def test_short_time(t, expected) -> None:
    assert sandstone._short_time(t) == expected


# --- strip assembly ---------------------------------------------------------


def test_week_strip_has_seven_days_today_first(db: Session) -> None:
    strip = sandstone.week_strip(db, today=_TODAY)
    assert len(strip["days"]) == 7
    assert strip["days"][0]["label"] == "Today"
    assert strip["days"][0]["is_today"] is True
    assert strip["days"][1]["label"] == "Tomorrow"
    assert strip["days"][0]["iso"] == "2026-06-05"
    assert strip["days"][6]["iso"] == "2026-06-11"
    assert strip["has_any"] is False  # no events seeded


def test_week_strip_ranks_special_over_class_and_overflows(db: Session) -> None:
    _add(db, title="Aqua Aerobics", start=time(6, 0), recurring=True)
    _add(db, title="Lap Swim", start=time(7, 0), recurring=True)
    _add(db, title="London Bridge Days Festival", start=time(18, 0))
    strip = sandstone.week_strip(db, today=_TODAY, per_day=2)
    today = strip["days"][0]
    assert today["count"] == 3
    titles = [e["title"] for e in today["events"]]
    # Festival leads the two visible slots; the two recurring classes overflow.
    assert titles[0] == "London Bridge Days Festival"
    assert today["events"][0]["type"] == "special"
    assert today["overflow"] == 1
    assert "Lap Swim" not in titles  # a class fell into the overflow count


def test_week_strip_empty_day_is_omittable(db: Session) -> None:
    _add(db, title="Kayak Meetup", on_date=date(2026, 6, 7), tags=["kayak"])
    strip = sandstone.week_strip(db, today=_TODAY)
    assert strip["has_any"] is True
    assert strip["days"][0]["has"] is False  # today empty
    assert strip["days"][0]["events"] == []
    sunday = strip["days"][2]  # 2026-06-07
    assert sunday["has"] is True
    assert sunday["events"][0]["type"] == "water"
    assert sunday["events"][0]["time"] == "10 AM"
