"""Recurrence badge on the LIVE week-view headline + home today-card items.

4.2 wiring: ``app.home.sandstone.event_recurrence_label`` populates
``recurrence_label`` on the two context objects the templates already read —
the events-page week headline (``d.headline.recurrence_label`` in
``events_sandstone.html``) and the home today-card chips
(``ev.recurrence_label`` on ``week.days[0].events`` in ``home_sandstone.html``).

A recurring (rrule/rdate-carrying) event yields a non-None cadence label; a
one-off yields ``None``; malformed/empty recurrence data never raises. The
per-day lists are NOT collapsed — each surface still shows the occurrence once,
only labelled. No HTTP; real Event rows on the shared test DB, wiped per test.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event
from app.home import events_views, sandstone

_TODAY = date(2026, 6, 5)  # a Friday
_END = date(2026, 6, 11)  # +6 days (the default 7-day window)


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
    recurring: bool = False,
    rrule: str | None = None,
    rdate: list[str] | None = None,
) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name="Test Venue",
        location_normalized="test venue",
        description="An event",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test_recurrence_label",
        verified=True,
        is_recurring=recurring,
        rrule=rrule,
        rdate=rdate,
    )
    db.add(ev)
    db.commit()
    return ev


# --- the helper, in isolation ----------------------------------------------


def test_helper_labels_weekly_rrule() -> None:
    ev = Event(
        title="Monday Yoga",
        normalized_title="monday yoga",
        date=date(2026, 5, 4),  # a Monday, before the window
        start_time=time(9, 0),
        is_recurring=True,
        rrule="FREQ=WEEKLY;BYDAY=MO",
    )
    label = sandstone.event_recurrence_label(
        ev, window_start=_TODAY, window_end=_END, time_label="9 AM"
    )
    # One Monday (6/8) falls in the Fri 6/5..Thu 6/11 window → single-weekday
    # cadence with the time appended.
    assert label == "Mon, 9 AM"


def test_helper_labels_mon_fri_rrule() -> None:
    ev = Event(
        title="Daily Bootcamp",
        normalized_title="daily bootcamp",
        date=date(2026, 6, 1),
        start_time=time(6, 0),
        is_recurring=True,
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    label = sandstone.event_recurrence_label(
        ev, window_start=_TODAY, window_end=_END, time_label="6 AM"
    )
    assert label == "Mon–Fri, 6 AM"


def test_helper_oneoff_yields_none() -> None:
    ev = Event(
        title="Grand Opening",
        normalized_title="grand opening",
        date=_TODAY,
        start_time=time(18, 0),
        is_recurring=False,
        rrule=None,
        rdate=None,
    )
    assert (
        sandstone.event_recurrence_label(
            ev, window_start=_TODAY, window_end=_END, time_label="6 PM"
        )
        is None
    )


def test_helper_malformed_rrule_does_not_raise() -> None:
    ev = Event(
        title="Broken Series",
        normalized_title="broken series",
        date=_TODAY,
        start_time=time(8, 0),
        is_recurring=True,
        rrule="THIS=IS;NOT=A;VALID=RRULE",
    )
    # Must not raise; flagged-recurring falls back to the stored weekday (Friday).
    label = sandstone.event_recurrence_label(
        ev, window_start=_TODAY, window_end=_END, time_label="8 AM"
    )
    assert label is not None  # falls back to a single-weekday cadence
    assert "Fri" in label


def test_helper_empty_recurrence_data_does_not_raise() -> None:
    ev = Event(
        title="No Schedule",
        normalized_title="no schedule",
        date=_TODAY,
        start_time=time(8, 0),
        is_recurring=False,
        rrule="",
        rdate=[],
    )
    assert (
        sandstone.event_recurrence_label(
            ev, window_start=_TODAY, window_end=_END
        )
        is None
    )


# --- home today-card items (week_strip → days[0].events[*].recurrence_label) -


def test_home_today_card_recurring_oneoff_gets_label(db: Session) -> None:
    # A row that recurs via rrule but is NOT is_recurring still headlines on the
    # home today card (it is a "one-off" for headline purposes), and now carries
    # a cadence badge.
    _add(
        db,
        title="Sunset Social",
        start=time(17, 0),
        recurring=False,
        rrule="FREQ=WEEKLY;BYDAY=FR",
    )
    strip = sandstone.week_strip(db, today=_TODAY)
    today = strip["days"][0]
    assert len(today["events"]) == 1
    item = today["events"][0]
    assert item["recurrence_label"] is not None
    assert "Fri" in item["recurrence_label"]


def test_home_today_card_true_oneoff_label_is_none(db: Session) -> None:
    _add(db, title="One-Time Gala", start=time(19, 0))
    strip = sandstone.week_strip(db, today=_TODAY)
    item = strip["days"][0]["events"][0]
    assert item["recurrence_label"] is None


def test_home_today_card_rdate_series_gets_label(db: Session) -> None:
    # Two explicit rdates inside the window → a multi-day cadence label.
    _add(
        db,
        title="Pop-up Market",
        start=time(9, 0),
        recurring=False,
        rdate=["2026-06-05", "2026-06-07"],
    )
    strip = sandstone.week_strip(db, today=_TODAY)
    item = strip["days"][0]["events"][0]
    assert item["recurrence_label"] is not None


# --- events-page week headline (week_rows → headline.recurrence_label) -------


def test_week_headline_recurring_oneoff_gets_label(db: Session) -> None:
    _add(
        db,
        title="Friday Wine Down",
        start=time(17, 0),
        recurring=False,
        rrule="FREQ=WEEKLY;BYDAY=FR",
    )
    rows = events_views.week_rows(db, start=_TODAY)
    today = rows[0]
    assert today["headline"] is not None
    assert today["headline"]["recurrence_label"] is not None
    assert "Fri" in today["headline"]["recurrence_label"]


def test_week_headline_true_oneoff_label_is_none(db: Session) -> None:
    _add(db, title="Single Concert", start=time(19, 0))
    rows = events_views.week_rows(db, start=_TODAY)
    today = rows[0]
    assert today["headline"] is not None
    assert today["headline"]["recurrence_label"] is None


def test_week_headline_absent_when_no_oneoff(db: Session) -> None:
    """A class-only day still has no headline (recurring never headlines), so
    there is simply no recurrence_label to render — the template guards on
    ``d.headline``."""
    _add(db, title="Lap Swim", start=time(5, 0), recurring=True)
    rows = events_views.week_rows(db, start=_TODAY)
    assert rows[0]["headline"] is None
