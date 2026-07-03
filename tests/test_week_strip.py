"""This-week strip — next 7 days, one-off headlines + collapsed class rollup.

Replaces the old "Today around the lake" card pair. Verifies the 7-day shape,
the headline tiering (special > music > community > water > other one-off),
that recurring classes NEVER headline (they collapse into the "N classes"
rollup), and that time-unknown rows never render a fake "12 AM". No HTTP; real
Event rows on an in-memory-ish SQLite session (the project's shared test DB),
wiped per test.
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


# --- F6/F9 canonical happenings count ---------------------------------------


def test_real_happenings_counts_events_excludes_movies(db: Session) -> None:
    _add(db, title="One-off Concert")
    _add(db, title="Weekly Farmers Market", recurring=True)
    _add(db, title="Matinee Showtime", tags=["movie"])
    counts = sandstone.real_happenings_by_day(db, window_start=_TODAY, window_end=_TODAY)
    # The one-off + the recurring EVENT count; the movie showtime does not.
    assert counts.get(_TODAY) == 2


def test_real_happenings_empty_day_is_absent(db: Session) -> None:
    _add(db, title="Only Today")
    counts = sandstone.real_happenings_by_day(db, window_start=_TODAY, window_end=_TODAY)
    other = date(2026, 6, 6)
    counts2 = sandstone.real_happenings_by_day(db, window_start=other, window_end=other)
    assert counts.get(_TODAY) == 1
    # An honest empty day reads as 0 (no fabricated "busy"), not a flat roster.
    assert counts2.get(other, 0) == 0


def test_week_strip_day_carries_happenings(db: Session) -> None:
    _add(db, title="A")
    _add(db, title="B")
    strip = sandstone.week_strip(db, today=_TODAY)
    assert strip["days"][0]["happenings"] == 2


# --- F9: the strip follows a far selection, with a Today anchor back ---------


def test_week_strip_today_anchored_by_default(db: Session) -> None:
    strip = sandstone.week_strip(db, today=_TODAY)
    assert strip["days"][0]["iso"] == _TODAY.isoformat()
    assert strip["days"][0]["is_today"] is True
    assert strip["includes_today"] is True
    assert strip["today_iso"] == _TODAY.isoformat()


def test_week_strip_near_selection_stays_today_anchored(db: Session) -> None:
    # A selection within the next 7 days keeps the today-first window.
    strip = sandstone.week_strip(db, today=_TODAY, selected=_TODAY + __import__("datetime").timedelta(days=2))
    assert strip["days"][0]["iso"] == _TODAY.isoformat()
    assert strip["includes_today"] is True


def test_week_strip_follows_far_selection(db: Session) -> None:
    far = date(2027, 2, 15)
    strip = sandstone.week_strip(db, today=_TODAY, selected=far)
    isos = [d["iso"] for d in strip["days"]]
    assert far.isoformat() in isos  # the selected day is visible in the strip
    assert isos[len(isos) // 2] == far.isoformat()  # centered
    assert strip["includes_today"] is False  # today fell out of the window…
    assert strip["today_iso"] == _TODAY.isoformat()  # …so the anchor back is exposed
    # No card is mislabeled "Today" when today isn't in the window.
    assert all(d["is_today"] is False for d in strip["days"])


# --- tiering (pure) ---------------------------------------------------------


@pytest.mark.parametrize(
    "title,tags,featured,recurring,expected",
    [
        ("London Bridge Days Festival", [], False, False, sandstone._TIER_SPECIAL),
        ("Spring Concert", [], True, False, sandstone._TIER_SPECIAL),  # featured wins
        ("Sunset Kayak Tour", ["kayak"], False, False, sandstone._TIER_WATER),
        ("Live Music at The Nautical", [], False, False, sandstone._TIER_MUSIC),
        ("Downtown Farmers Market", [], False, False, sandstone._TIER_COMMUNITY),
        # Pool activities are Aquatic Center, not on-the-water and not generic
        # class — the pool/lake split (2026-06). Both happen in the pool.
        ("Aqua Aerobics", [], False, True, sandstone._TIER_AQUATIC),
        ("Lap Swim", [], False, True, sandstone._TIER_AQUATIC),
        ("Mystery Pop-up", [], False, False, sandstone._TIER_OTHER),  # one-off default
        ("Standing Group", [], False, True, sandstone._TIER_CLASS),  # recurring default
    ],
)
def test_event_tier(title, tags, featured, recurring, expected) -> None:
    assert (
        sandstone._event_tier(title=title, tags=tags, featured=featured, recurring=recurring)
        == expected
    )


def test_tier_rank_order_is_owner_approved() -> None:
    """Headline ranking: special > music/nightlife > community > water > other."""
    assert (
        sandstone._TIER_SPECIAL
        < sandstone._TIER_MUSIC
        < sandstone._TIER_COMMUNITY
        < sandstone._TIER_WATER
        < sandstone._TIER_OTHER
        < sandstone._TIER_CLASS
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


def test_week_strip_headlines_oneoffs_and_collapses_classes(db: Session) -> None:
    _add(db, title="Aqua Aerobics", start=time(6, 0), recurring=True)
    _add(db, title="Lap Swim", start=time(7, 0), recurring=True)
    _add(db, title="London Bridge Days Festival", start=time(18, 0))
    strip = sandstone.week_strip(db, today=_TODAY, per_day=2)
    today = strip["days"][0]
    assert today["count"] == 3
    # Only the one-off headlines; recurring classes are NEVER a headline —
    # they collapse into the rollup line instead.
    assert [e["title"] for e in today["events"]] == ["London Bridge Days Festival"]
    # Slice C: the week strip now buckets like /events-ui (app.home.event_buckets).
    # There is no separate "Special" bucket there — a special-tier festival
    # collects in "Around town" (key "events"; still the orange pill and still
    # ranked first by _event_tier, so it keeps its prominence).
    assert today["events"][0]["type"] == "events"
    assert today["event_count"] == 1
    assert today["class_count"] == 2
    assert today["summary"] == "1 event · 2 classes"
    assert today["overflow"] == 0  # no one-off was pushed out


def test_week_strip_never_headlines_recurring_class(db: Session) -> None:
    """A class-only day shows no headline, just the honest rollup count."""
    _add(db, title="Lap Swim", start=time(5, 0), recurring=True)
    strip = sandstone.week_strip(db, today=_TODAY)
    today = strip["days"][0]
    assert today["events"] == []
    assert today["class_count"] == 1
    assert today["summary"] == "1 class"
    assert today["has"] is True  # the day still links through to /events-ui


def test_week_strip_no_12am_and_tbd_sorts_after_timed(db: Session) -> None:
    """Midnight-fallback rows show no time (never "12 AM") and sort last."""
    _add(db, title="Craft Fair", start=time(0, 0))  # aggregator "no time" fallback
    _add(db, title="Farmers Market", start=time(8, 0))
    strip = sandstone.week_strip(db, today=_TODAY)
    today = strip["days"][0]
    # Same tier (community): the timed event leads, the TBD one trails.
    assert [e["title"] for e in today["events"]] == ["Farmers Market", "Craft Fair"]
    assert today["events"][0]["time"] == "8 AM"
    assert today["events"][1]["time"] is None  # omitted — never "12 AM"


def test_week_strip_empty_day_is_omittable(db: Session) -> None:
    _add(db, title="Kayak Meetup", on_date=date(2026, 6, 7), tags=["kayak"])
    strip = sandstone.week_strip(db, today=_TODAY)
    assert strip["has_any"] is True
    assert strip["days"][0]["has"] is False  # today empty
    assert strip["days"][0]["events"] == []
    sunday = strip["days"][2]  # 2026-06-07
    assert sunday["has"] is True
    # Slice F: only TODAY headlines individual events; the other days are trimmed
    # to counts-only cards, so a non-today day carries an empty events list and is
    # represented by its event_count / class_count instead.
    assert sunday["events"] == []
    assert sunday["event_count"] == 1
    assert sunday["count"] == 1


def test_week_strip_day_categories_breakdown(db: Session) -> None:
    """Phase 7: each day carries a recurring-occurrence ``categories`` breakdown
    (bucketed by the shared Slice C definition, ordered by GROUP_DEFS). One-off
    events are NOT in it — they are the headlines / event_count."""
    _add(db, title="Street Fair", start=time(17, 0))  # one-off → not a category
    _add(db, title="Vinyasa Yoga", start=time(9, 0), recurring=True)  # → classes
    _add(db, title="Lap Swim", start=time(6, 0), recurring=True)  # pool class → classes
    strip = sandstone.week_strip(db, today=_TODAY)
    today = strip["days"][0]
    cats = {c["key"]: c["count"] for c in today["categories"]}
    # No separate Aquatic Center bucket: pool classes fold into Fitness & classes.
    assert cats == {"classes": 2}  # recurring only; one-off excluded
    assert [c["key"] for c in today["categories"]] == ["classes"]
    assert all(c["label"] for c in today["categories"])
    assert today["event_count"] == 1  # the one-off Street Fair


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
    counts on the in-window Monday occurrence (rrule expansion), not just its
    start — in the class rollup, never as a headline."""
    _add_weekly(db, title="Monday Yoga", byday="MO", start=date(2026, 5, 4))
    strip = sandstone.week_strip(db, today=_TODAY)  # Fri 6/5 .. Thu 6/11
    monday = next(d for d in strip["days"] if d["iso"] == "2026-06-08")
    assert monday["count"] == 1
    assert monday["events"] == []  # recurring class never headlines
    assert monday["class_count"] == 1
    assert monday["summary"] == "1 class"
    # Not shown on Friday (its stored start weekday is Monday; today is Friday).
    assert strip["days"][0]["count"] == 0


def test_calendar_month_expands_weekly_recurring_on_every_occurrence(db: Session) -> None:
    """A weekly Monday class lands on every Monday cell's class badge."""
    _add_weekly(db, title="Monday Yoga", byday="MO", start=date(2026, 5, 4))
    cal = sandstone.calendar_month(db, year=2026, month=6, today=_TODAY)
    days_with_class = {
        cell["day"]
        for week in cal["weeks"]
        for cell in week
        if cell.get("in_month") and cell.get("class_count")
    }
    # June 2026 Mondays: 1, 8, 15, 22, 29.
    assert days_with_class == {1, 8, 15, 22, 29}


def test_calendar_month_cell_collapses_classes_to_badge(db: Session) -> None:
    """Day cells show one-off titles + a class badge, not a flood of classes."""
    for i in range(3):
        _add(
            db,
            title=f"Aqua Class {i}",
            on_date=date(2026, 6, 9),
            start=time(5 + i, 0),
            recurring=True,
        )
    _add(db, title="Street Fair", on_date=date(2026, 6, 9), start=time(17, 0))
    cal = sandstone.calendar_month(db, year=2026, month=6, today=_TODAY)
    cell = next(
        c for week in cal["weeks"] for c in week if c.get("in_month") and c.get("day") == 9
    )
    assert [e["title"] for e in cell["events"]] == ["Street Fair"]
    assert cell["count"] == 1  # one-off events only — not class instances
    assert cell["class_count"] == 3  # classes collapse into the badge
    assert cell["overflow"] == 0  # no "+44" dump


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





# (The _windowevent_dict midnight-TBD label tests were deleted 2026-07-02 with
# the pre-v4 window feed; the same contract is covered by the is_time_tbd unit
# tests and the live week-strip/permalink assertions below.)


def test_permalink_datetime_midnight_fallback_is_date_only() -> None:
    from app.main import _format_event_datetime

    assert _format_event_datetime(_mk_event()) == "Saturday, December 5"
    assert (
        _format_event_datetime(_mk_event(start_time=time(19, 30)))
        == "Saturday, December 5, 7:30 PM"
    )



