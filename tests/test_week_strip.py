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


def _add_weekly(db: Session, *, title: str, byday: str, start: date) -> None:
    db.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=start,
            start_time=time(9, 0),
            location_name="Studio",
            location_normalized="studio",
            description="A weekly class",
            event_url="https://example.com/e",
            tags=[],
            status="live",
            source="test_week_strip",
            verified=True,
            is_recurring=True,
            rrule=f"FREQ=WEEKLY;BYDAY={byday}",
        )
    )
    db.commit()


def test_week_strip_expands_weekly_recurring_into_window(db: Session) -> None:
    """A weekly Monday class whose stored start is a month before the window still
    tiles on the in-window Monday occurrence (rrule expansion), not just its start."""
    _add_weekly(db, title="Monday Yoga", byday="MO", start=date(2026, 5, 4))
    strip = sandstone.week_strip(db, today=_TODAY)  # Fri 6/5 .. Thu 6/11
    monday = next(d for d in strip["days"] if d["iso"] == "2026-06-08")
    assert monday["count"] == 1
    assert monday["events"][0]["title"] == "Monday Yoga"
    # Not shown on Friday (its stored start weekday is Monday; today is Friday).
    assert strip["days"][0]["count"] == 0


def test_calendar_month_expands_weekly_recurring_on_every_occurrence(db: Session) -> None:
    """A weekly Monday class appears on every Monday cell of the month grid."""
    _add_weekly(db, title="Monday Yoga", byday="MO", start=date(2026, 5, 4))
    cal = sandstone.calendar_month(db, year=2026, month=6, today=_TODAY)
    days_with_event = {
        cell["day"]
        for week in cal["weeks"]
        for cell in week
        if cell.get("in_month") and cell.get("count")
    }
    # June 2026 Mondays: 1, 8, 15, 22, 29.
    assert days_with_event == {1, 8, 15, 22, 29}


# ----- midnight-fallback time suppression (aggregator "no time" rows) --------


def _mk_event(**kw):
    from datetime import datetime

    defaults = dict(
        title="Midnight Fallback Test", normalized_title="midnight fallback test",
        date=date(2026, 12, 5), start_time=time(0, 0), end_time=None,
        location_name="Test Venue", location_normalized="test venue",
        description="A test event with no real source time component provided.",
        source="allevents", tags=["community"],
    )
    defaults.update(kw)
    ev = Event(**defaults)
    ev.created_at = getattr(ev, "created_at", None) or datetime(2026, 12, 1)
    return ev


def test_midnight_fallback_hides_time_label() -> None:
    from app.home.router import _window_event_dict

    d = _window_event_dict(_mk_event(), recurring=False, schedule_label="")
    assert d["time_label"] == ""


def test_real_midnight_span_keeps_label() -> None:
    """An explicit end time means the midnight start is real, not a fallback."""
    from app.home.router import _window_event_dict

    d = _window_event_dict(
        _mk_event(end_time=time(2, 0)), recurring=False, schedule_label=""
    )
    assert d["time_label"] == "12:00 AM - 2:00 AM"


def test_nonmidnight_time_label_unchanged() -> None:
    from app.home.router import _window_event_dict

    d = _window_event_dict(
        _mk_event(start_time=time(19, 0)), recurring=False, schedule_label=""
    )
    assert d["time_label"] == "7:00 PM"


def test_permalink_datetime_midnight_fallback_is_date_only() -> None:
    from app.main import _format_event_datetime

    assert _format_event_datetime(_mk_event()) == "Saturday, December 5"
    assert (
        _format_event_datetime(_mk_event(start_time=time(19, 30)))
        == "Saturday, December 5, 7:30 PM"
    )


def test_midnight_zero_span_also_hidden() -> None:
    """allevents often fills endDate with midnight too — a 00:00-00:00 zero
    span is still 'time unknown', not a midnight event."""
    from app.home.router import _window_event_dict
    from app.main import _format_event_datetime

    ev = _mk_event(end_time=time(0, 0))
    d = _window_event_dict(ev, recurring=False, schedule_label="")
    assert d["time_label"] == ""
    assert _format_event_datetime(ev) == "Saturday, December 5"
