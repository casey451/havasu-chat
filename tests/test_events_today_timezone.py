"""Regression: chat "today" event windows must follow the lake clock, not UTC.

Bug: ``tier2_db_query._today()`` returned ``date.today()`` -- the *server-local*
date, which is the UTC date on the production host. After 5 PM in Lake Havasu
(America/Phoenix, no DST) UTC has already rolled to tomorrow, so an evening
"what's happening today" chat query fetched *tomorrow's* events while the
day_agenda component (``resolve_target_date``, lake-time) labeled the answer
with today's date -- the header count and the rendered list disagreed, and the
events the user actually asked about were silently excluded.

These tests freeze the lake clock to an evening hour where the UTC date is
already the next day and assert the query window, the component date, and the
rendered item count all agree.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.chat import component_builders, tier2_db_query
from app.chat.tier2_db_query import query as tier2_query
from app.chat.tier2_schema import Tier2Filters
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Event

# Thursday 2099-04-09 7 PM in Lake Havasu == Friday 2099-04-10 02:00 UTC.
# Far-future date keeps seeded rows clear of real catalog data.
_EVENING_LAKE = datetime(2099, 4, 9, 19, 0, tzinfo=LAKE_HAVASU_TZ)
_LAKE_TODAY = _EVENING_LAKE.date()  # 2099-04-09


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _add_event(db: Session, *, title: str, on_date: date, start: time) -> Event:
    e = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name="Test Venue",
        location_normalized="test venue",
        description=f"{title} description",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="tz-regression-test",
        verified=True,
        is_recurring=False,
    )
    db.add(e)
    db.flush()
    return e


@pytest.fixture
def frozen_evening(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Freeze the lake clock to an evening hour where UTC is tomorrow."""
    monkeypatch.setattr(tier2_db_query, "_now_lake_havasu", lambda: _EVENING_LAKE)
    monkeypatch.setattr(component_builders, "now_lake_havasu", lambda: _EVENING_LAKE)
    return _EVENING_LAKE


@pytest.fixture
def seeded(frozen_evening: datetime):
    """One event tonight (lake-today) and one tomorrow; cleaned up after."""
    suf = _suffix()
    with SessionLocal() as db:
        tonight = _add_event(
            db, title=f"ZZ Tonight Concert {suf}", on_date=_LAKE_TODAY, start=time(20, 0)
        )
        tomorrow = _add_event(
            db,
            title=f"ZZ Tomorrow Market {suf}",
            on_date=_LAKE_TODAY + timedelta(days=1),
            start=time(9, 0),
        )
        ids = [tonight.id, tomorrow.id]
        db.commit()
    yield suf
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.id.in_(ids)))
        db.commit()


def test_today_is_lake_date_not_utc_date(frozen_evening: datetime) -> None:
    # The whole point: at this instant the UTC calendar already says tomorrow.
    assert frozen_evening.astimezone(UTC).date() == _LAKE_TODAY + timedelta(days=1)
    assert tier2_db_query._today() == _LAKE_TODAY


def test_evening_today_query_returns_tonights_events(seeded: str) -> None:
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="today"))
    mine = [r for r in rows if r["type"] == "event" and seeded in r["name"]]
    assert [r["name"] for r in mine] == [f"ZZ Tonight Concert {seeded}"]
    assert all(r["date"] == _LAKE_TODAY.isoformat() for r in mine)


def test_evening_today_total_matches_rendered_agenda(seeded: str) -> None:
    """The day_agenda built from a "today" query renders every queried row,
    all dated the lake-time today the header announces."""
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="today"))
    event_rows = [r for r in rows if r["type"] == "event"]
    filters = Tier2Filters(parser_confidence=0.9, time_window="today")
    data = component_builders.build_day_agenda(filters, event_rows)
    # total == rendered: every fetched row shows up in the component...
    assert len(data["events"]) == len(event_rows)
    # ...and the component's date is the same lake-time day the rows were
    # fetched for (pre-fix: header said lake-today, rows were UTC-tomorrow's).
    assert data["date"] == _LAKE_TODAY.isoformat()
    assert all(r["date"] == data["date"] for r in event_rows)
    assert any(seeded in e["title"] for e in data["events"])


def test_evening_tomorrow_query_anchors_to_lake_tomorrow(seeded: str) -> None:
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="tomorrow"))
    mine = [r for r in rows if r["type"] == "event" and seeded in r["name"]]
    assert [r["name"] for r in mine] == [f"ZZ Tomorrow Market {seeded}"]


def test_evening_weekend_window_anchors_to_lake_today(frozen_evening: datetime) -> None:
    # Thursday evening lake-time: this_weekend is Friday Apr 10 .. Sunday Apr 12.
    # A UTC anchor (already Friday) would also start Apr 10 -- the giveaway is
    # "today": (ref, ref) must be Apr 9, and tomorrow Apr 10, per lake time.
    ref = tier2_db_query._today()
    assert tier2_db_query._resolve_time_window("this_weekend", ref) == (
        date(2099, 4, 10),
        date(2099, 4, 12),
    )
    assert tier2_db_query._resolve_time_window("today", ref) == (_LAKE_TODAY, _LAKE_TODAY)
    assert tier2_db_query._resolve_time_window("tomorrow", ref) == (
        _LAKE_TODAY + timedelta(days=1),
        _LAKE_TODAY + timedelta(days=1),
    )
