"""Lane 4 UI-logic behaviors: month totals (1.1), time consistency (1.4),
aggregate recurrence cards + recurrence_label (4.2).

Real Event rows on the project's shared test DB session, wiped per test —
same harness as ``test_week_strip``. No HTTP.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event
from app.events.series import schedule_label
from app.home import sandstone

_TODAY = date(2026, 6, 1)  # a Monday
_MONTH = (2026, 6)


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
    start: time | None = time(10, 0),
    end: time | None = None,
    tags: list[str] | None = None,
    featured: bool = False,
    recurring: bool = False,
    rrule: str | None = None,
) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        end_time=end,
        location_name="Test Venue",
        location_normalized="test venue",
        description="An event",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source="test_lane4",
        verified=True,
        featured=featured,
        is_recurring=recurring,
        rrule=rrule,
    )
    db.add(ev)
    db.commit()
    return ev


# --- 1.1 month totals --------------------------------------------------------


def test_calendar_month_exposes_oneoff_and_class_totals(db: Session) -> None:
    # Two one-off events + one daily-recurring class across the month.
    _add(db, title="Street Fair", on_date=date(2026, 6, 3), start=time(17, 0))
    _add(db, title="Boat Show", on_date=date(2026, 6, 10), start=time(11, 0))
    _add(
        db,
        title="Sunrise Yoga",
        on_date=date(2026, 6, 1),
        start=time(6, 0),
        recurring=True,
        rrule="FREQ=DAILY;COUNT=30",
    )
    cal = sandstone.calendar_month(db, year=_MONTH[0], month=_MONTH[1], today=_TODAY)
    assert "month_oneoff_total" in cal and "month_class_total" in cal
    assert cal["month_oneoff_total"] == 2  # the two one-offs
    assert cal["month_class_total"] >= 30  # daily class occurrences across June

    # The totals must equal the sum of the per-cell counts the grid renders.
    grid_oneoff = sum(
        c.get("count", 0) for week in cal["weeks"] for c in week if c.get("in_month")
    )
    grid_class = sum(
        c.get("class_count", 0) for week in cal["weeks"] for c in week if c.get("in_month")
    )
    assert cal["month_oneoff_total"] == grid_oneoff
    assert cal["month_class_total"] == grid_class


def test_calendar_month_totals_zero_on_empty_month(db: Session) -> None:
    cal = sandstone.calendar_month(db, year=2030, month=1, today=date(2030, 1, 1))
    assert cal["month_oneoff_total"] == 0
    assert cal["month_class_total"] == 0


# --- 1.4 time consistency (single source of truth) ---------------------------


def test_week_strip_headline_time_matches_detail_page_resolution(db: Session) -> None:
    # The home week headline time and the detail-page time must resolve from the
    # same start_time via the shared time-labels contract (no divergent format).
    from app.main import _format_event_datetime

    ev = _add(db, title="Planning & Zoning Meeting", start=time(9, 0), tags=["civic"])
    strip = sandstone.week_strip(db, today=_TODAY)
    today = strip["days"][0]
    headline = next(e for e in today["events"] if "Planning" in e["title"])
    # Detail page renders "..., 9:00 AM"; the week strip renders "9 AM" — both
    # read the SAME 9:00 start (no fabricated/offset time). The detail string
    # ends with the same clock the strip's short label describes.
    detail = _format_event_datetime(ev)
    assert detail.endswith("9:00 AM")
    assert headline["time"] == "9 AM"


def test_planning_zoning_oneoff_reachable_on_day_view(db: Session) -> None:
    # 1.4 + P1: a civic one-off must appear on the per-day view (not vanish), now
    # in its own "City & Government" group rather than the leisure "Around town".
    from app.home import events_views

    _add(db, title="Planning & Zoning Meeting", start=time(9, 0), tags=["civic"])
    groups = events_views.day_groups(db, day=_TODAY)
    civic = next((g for g in groups if g["key"] == "civic"), None)
    assert civic is not None
    titles = [r["title"] for r in civic["rows"]]
    assert any("Planning" in t for t in titles)
    # It must NOT also sit in the leisure "Happening today" bucket.
    around_town = next((g for g in groups if g["key"] == "events"), None)
    around_titles = [r["title"] for r in (around_town["rows"] if around_town else [])]
    assert not any("Planning" in t for t in around_titles)


# --- 4.2 aggregate recurrence cards ------------------------------------------


def test_recurrence_label_helper() -> None:
    assert sandstone.recurrence_label({0, 1, 2, 3, 4}, "9 AM") == "Mon–Fri, 9 AM"
    assert sandstone.recurrence_label(set(range(7))) == "Daily"
    assert sandstone.recurrence_label(set()) is None  # non-recurring -> None
    # Cadence phrasing is shared with the events feed.
    assert sandstone.recurrence_label({1, 3}) == schedule_label({1, 3})


def test_aggregate_cards_collapse_recurring_class_to_one_card(db: Session) -> None:
    # A class recurring every day across the week renders as ONE card with a
    # recurrence_label, not one card per occurrence.
    _add(
        db,
        title="Aqua Aerobics",
        on_date=_TODAY,
        start=time(6, 0),
        end=time(7, 0),
        recurring=True,
        rrule="FREQ=DAILY;COUNT=10",
    )
    end = date(2026, 6, 7)
    cards = sandstone.aggregate_event_cards(db, window_start=_TODAY, window_end=end)
    aqua = [c for c in cards if "Aqua" in c["title"]]
    assert len(aqua) == 1  # collapsed
    card = aqua[0]
    assert card["recurring"] is True
    # short_time_label renders the start clock ("6 AM"); cadence + time.
    assert card["recurrence_label"] == "Daily, 6 AM"
    assert card["occurrence_count"] >= 7  # daily over the 7-day window


def test_aggregate_card_oneoff_has_no_recurrence_label(db: Session) -> None:
    _add(db, title="Boat Show", on_date=date(2026, 6, 3), start=time(11, 0))
    cards = sandstone.aggregate_event_cards(
        db, window_start=_TODAY, window_end=date(2026, 6, 7)
    )
    show = next(c for c in cards if "Boat Show" in c["title"])
    assert show["recurring"] is False
    assert show["recurrence_label"] is None
    assert show["occurrence_count"] == 1


def test_aggregate_card_passes_through_optional_fields(db: Session) -> None:
    ev = _add(db, title="Charity Gala", on_date=date(2026, 6, 5), start=time(18, 0))
    # Optional fields populated by another lane; the card must pass them through.
    ev.cost = "$25"
    ev.host = "Rotary Club"
    ev.image_url = "https://example.com/gala.jpg"
    db.commit()
    cards = sandstone.aggregate_event_cards(
        db, window_start=_TODAY, window_end=date(2026, 6, 7)
    )
    gala = next(c for c in cards if "Charity Gala" in c["title"])
    assert gala["cost"] == "$25"
    assert gala["host"] == "Rotary Club"
    assert gala["image_url"] == "https://example.com/gala.jpg"
