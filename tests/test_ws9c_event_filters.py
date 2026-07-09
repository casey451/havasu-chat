"""WS9c — feed quick filters (Free / Indoor / Tonight / This weekend).

Layers:
* pure occurrence predicates (``_event_is_free`` / ``_event_is_evening`` /
  ``_event_is_indoor``) and the weekend-date helpers — no DB;
* the route — chips render, ``?free=1`` / ``?tonight=1`` narrow the day feed
  server-side, ``?weekend=1`` renders the This-weekend span, and a Fri–Sun clock
  makes the bare page default to that weekend span.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from datetime import time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_EVENT
from app.db.models import Entity, Event
from app.home import events_views as ev
from app.home.router import _is_weekend_default_day, _weekend_dates

_LHC = ZoneInfo("America/Phoenix")


class _Ev:
    """Minimal duck for the pure predicates (they read attributes only)."""

    def __init__(self, *, cost=None, start_time=None, end_time=None, tags=None,
                 location_name="", location_normalized=""):
        self.cost = cost
        self.start_time = start_time
        self.end_time = end_time
        self.tags = tags or []
        self.location_name = location_name
        self.location_normalized = location_normalized


# --- pure predicates --------------------------------------------------------


def test_is_free_only_on_positive_signal() -> None:
    assert ev._event_is_free(_Ev(cost="Free")) is True
    assert ev._event_is_free(_Ev(cost="$0")) is True
    assert ev._event_is_free(_Ev(cost="Free with RSVP")) is True
    assert ev._event_is_free(_Ev(cost="$20")) is False
    assert ev._event_is_free(_Ev(cost=None)) is False  # unknown is NOT free
    assert ev._event_is_free(_Ev(cost="")) is False


def test_is_evening_at_or_after_5pm_only() -> None:
    assert ev._event_is_evening(_Ev(start_time=time(17, 0))) is True
    assert ev._event_is_evening(_Ev(start_time=time(19, 30))) is True
    assert ev._event_is_evening(_Ev(start_time=time(9, 0))) is False
    assert ev._event_is_evening(_Ev(start_time=None)) is False
    # All-day sentinel (00:00 / no end) is not "tonight".
    assert ev._event_is_evening(_Ev(start_time=time(0, 0), end_time=None)) is False


def test_is_indoor_by_activity_tag_or_venue_attribute() -> None:
    assert ev._event_is_indoor(_Ev(tags=["activity:bowling"]), set()) is True
    assert ev._event_is_indoor(_Ev(tags=["activity:festival"]), set()) is False
    keys = {"the cooler club"}
    assert ev._event_is_indoor(_Ev(location_normalized="the cooler club"), keys) is True
    assert ev._event_is_indoor(_Ev(location_normalized="sunny beach"), keys) is False


def test_weekend_dates_span() -> None:
    # Wed → the coming Fri/Sat/Sun; Sat → [Sat, Sun]; Sun → [Sun].
    assert _weekend_dates(dt.date(2026, 7, 8)) == [
        dt.date(2026, 7, 10), dt.date(2026, 7, 11), dt.date(2026, 7, 12)
    ]
    assert _weekend_dates(dt.date(2026, 7, 11)) == [dt.date(2026, 7, 11), dt.date(2026, 7, 12)]
    assert _weekend_dates(dt.date(2026, 7, 12)) == [dt.date(2026, 7, 12)]


def test_is_weekend_default_day() -> None:
    assert _is_weekend_default_day(dt.date(2026, 7, 8)) is False  # Wed
    assert _is_weekend_default_day(dt.date(2026, 7, 10)) is True  # Fri
    assert _is_weekend_default_day(dt.date(2026, 7, 12)) is True  # Sun


# --- route integration ------------------------------------------------------

_DAY = dt.date(2099, 3, 11)  # a Wednesday, far future (no auto-expiry)


@pytest.fixture
def db() -> Iterator[Session]:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_event(db: Session, *, title: str, start: time, cost: str | None, tags=None) -> None:
    ent = Entity(id=str(uuid.uuid4()), entity_type=ENTITY_TYPE_EVENT,
                 slug=f"ws9c-{uuid.uuid4().hex[:10]}", name=title, source="test-ws9c")
    db.add(ent)
    db.add(Event(
        id=str(uuid.uuid4()), title=title, normalized_title=title.lower(), date=_DAY,
        start_time=start, location_name="Plaza", location_normalized="plaza",
        description=title, status="live", source="test-ws9c", entity_id=ent.id,
        cost=cost, tags=tags or ["festival"],
    ))
    db.commit()


def test_free_filter_narrows_day_feed(client, db: Session) -> None:
    suf = uuid.uuid4().hex[:6]
    free_t, paid_t = f"ZZ Free Concert {suf}", f"ZZ Paid Gala {suf}"
    _seed_event(db, title=free_t, start=time(18, 0), cost="Free")
    _seed_event(db, title=paid_t, start=time(18, 0), cost="$25")
    both = client.get(f"/events-ui?date={_DAY.isoformat()}").text
    assert free_t in both and paid_t in both  # unfiltered shows both
    only_free = client.get(f"/events-ui?date={_DAY.isoformat()}&free=1").text
    assert free_t in only_free
    assert paid_t not in only_free


def test_tonight_filter_narrows_to_evening(client, db: Session) -> None:
    suf = uuid.uuid4().hex[:6]
    eve_t, morn_t = f"ZZ Evening Show {suf}", f"ZZ Morning Market {suf}"
    _seed_event(db, title=eve_t, start=time(19, 0), cost=None)
    _seed_event(db, title=morn_t, start=time(9, 0), cost=None)
    only_eve = client.get(f"/events-ui?date={_DAY.isoformat()}&tonight=1").text
    assert eve_t in only_eve
    assert morn_t not in only_eve


def test_quick_filter_chips_render_with_toggle_urls(client) -> None:
    body = client.get("/events-ui?view=today").text
    for label in ("Free", "Indoor", "Tonight", "This weekend"):
        assert f'<span class="cl">{label}</span>' in body
    # An active filter is reflected + toggles preserve it.
    active = client.get("/events-ui?view=today&free=1").text
    assert 'aria-pressed="true"><span class="cl">Free</span>' in active


def test_weekend_param_renders_weekend_span(client) -> None:
    body = client.get("/events-ui?weekend=1").text
    assert "This weekend" in body  # H1 + active chip


def test_bare_page_defaults_to_weekend_on_friday(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    friday = dt.datetime(2099, 3, 13, 9, 0, tzinfo=_LHC)  # a Friday
    monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: friday)
    body = client.get("/events-ui").text
    assert "This weekend" in body
    assert '<h1 class="serif" id="feedTitle">This weekend</h1>' in body


def test_bare_page_defaults_to_today_on_weekday(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    wednesday = dt.datetime(2099, 3, 11, 9, 0, tzinfo=_LHC)
    monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: wednesday)
    body = client.get("/events-ui").text
    assert '<h1 class="serif" id="feedTitle">Happening today</h1>' in body
