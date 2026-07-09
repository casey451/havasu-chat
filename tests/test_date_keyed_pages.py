"""v4.4 PR-2 — date-scoped pages must reflect the CURRENT local day/month.

The June/July symptom: on 2026-07-02 bare ``/home`` served July 1's page and bare
``/calendar`` served a June-26 grid, while the ``?date=``/``?cal=`` variants were
fresh — a stale render pinned to a past date. These tests freeze the Lake-Havasu
clock, render, advance the clock, and assert the page rolls over (heading, grid
month, and the day-scoped feed/count), so a future date-blind cache can't
reintroduce the bug. They also pin that every date-scoped HTML route ships
``no-cache`` (the header that stops a shared/edge cache from replaying a past
day — the actual production mechanism, since the app resolves the date fresh per
request and holds no cross-request render cache).
"""

from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import app

TZ = ZoneInfo("America/Phoenix")


def _at(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 10, 0, 0, tzinfo=TZ)


def _home(client, dt: datetime) -> str:
    with patch("app.home.router.now_lake_havasu", return_value=dt):
        return client.get("/home").text


def _events_ui(client, dt: datetime) -> str:
    with patch("app.home.router.now_lake_havasu", return_value=dt):
        return client.get("/events-ui").text


def _calendar(client, dt: datetime) -> str:
    with patch("app.home.calendar_route.now_lake_havasu", return_value=dt):
        return client.get("/calendar").text


def test_home_heading_rolls_over_to_current_day() -> None:
    with TestClient(app) as client:
        d1 = _home(client, _at(2026, 7, 3))  # Friday
        d2 = _home(client, _at(2026, 7, 4))  # Saturday
    assert "Friday, July 3" in d1
    assert "Saturday, July 4" not in d1
    assert "Saturday, July 4" in d2
    assert "Friday, July 3" not in d2


def test_events_ui_rolls_over_to_current_day() -> None:
    with TestClient(app) as client:
        d1 = _events_ui(client, _at(2026, 7, 3))
        d2 = _events_ui(client, _at(2026, 7, 4))
    assert "July 3" in d1 and "July 4" not in d1
    assert "July 4" in d2 and "July 3" not in d2


def test_calendar_grid_rolls_over_to_current_month() -> None:
    with TestClient(app) as client:
        c1 = _calendar(client, _at(2026, 7, 31))  # last day of July
        c2 = _calendar(client, _at(2026, 8, 1))  # first day of August
    assert "July" in c1 and "August" not in c1
    assert "August" in c2 and "July" not in c2


def test_home_feed_is_day_scoped_not_a_stale_snapshot() -> None:
    """The day's feed (and thus its count) follows the resolved date: an event on
    D shows on D's home, not on D-1's."""
    day = date(2026, 9, 15)
    title = "ZZ Unique Rollover Probe Event"
    ev_id = ""
    ent_id = None
    with SessionLocal() as db:
        ev = Event(
            title=title, normalized_title=title.lower(), date=day,
            start_time=time(18, 0), end_time=None, location_name="Rotary Park",
            location_normalized="rotary park", description="probe",
            event_url="https://example.com/e", source_url="", tags=[],
            status="live", source="test", verified=True, is_recurring=False,
        )
        db.add(ev)
        db.commit()
        ev_id, ent_id = ev.id, ev.entity_id
    try:
        with TestClient(app) as client:
            on_day = _home(client, _at(2026, 9, 15))
            day_before = _home(client, _at(2026, 9, 14))
        assert title in on_day  # event surfaces on its own day
        assert title not in day_before  # not on the prior day's feed
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.id == ev_id))
            if ent_id:
                db.execute(delete(Entity).where(Entity.id == ent_id))
            db.commit()


def test_date_scoped_html_routes_send_no_cache() -> None:
    """Every date-scoped HTML surface must forbid shared/edge caching so a past
    day can't be replayed (the production stale-page mechanism)."""
    with TestClient(app) as client:
        for path in ("/home", "/calendar", "/events-ui", "/events-ui?view=week"):
            resp = client.get(path)
            assert resp.status_code == 200
            cc = (resp.headers.get("cache-control") or "").lower()
            assert "no-cache" in cc or "no-store" in cc, f"{path} -> {cc!r}"
