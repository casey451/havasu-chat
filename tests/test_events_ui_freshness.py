"""P0 regression — /events-ui and /home must never serve a previous day's render.

Live repro (2026-06-07): /events-ui showed "Today: 2 events" dated June 2 while
/home was fresh at the same moment. The routes themselves recompute every
bucket from ``now_lake_havasu()`` per request — there is deliberately NO
in-process cache of the event sections — so these tests pin both halves of
the freshness contract:

* **Day rollover:** a process that rendered the page on day N must render
  day-N+1 data on the next request. If anyone ever introduces a module-level
  snapshot/cache of the rendered sections (or freezes ``now`` at import
  time), the rollover tests below fail.
* **Transport:** the HTML responses must carry an explicit ``no-cache``
  directive so no browser/proxy/edge cache may replay an old render (the
  mechanism behind the live June 2 page; see SecurityHeadersMiddleware).

Dates use far-future 2099 (xdist isolation, same pattern as
tests/test_wp3_events_surfaces.py). 2099-06-02 is a Tuesday and 2099-06-07 a
Sunday — the same weekday shape as the 2026 incident.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import app

_LHC = ZoneInfo("America/Phoenix")

# Tuesday — the day the stale render was minted in the live incident.
_JUNE_2 = datetime(2099, 6, 2, 9, 0, tzinfo=_LHC)
# Sunday five days later — the day the stale render was still being served.
_JUNE_7 = datetime(2099, 6, 7, 9, 0, tzinfo=_LHC)

_EXPECTED_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"


def _add_event(db, *, title: str, on, start: time, loc: str) -> tuple[str, str]:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test-freshness",
        verified=True,
        is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.id, ev.entity_id


def _seed_rollover_events(suffix: str) -> tuple[str, str, list[str]]:
    """One event on the stale day, one on the fresh day. Returns titles + eids."""
    stale_title = f"ZZ StaleFest {suffix}"
    fresh_title = f"ZZ FreshFest {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        _id, eid = _add_event(
            db, title=stale_title, on=_JUNE_2.date(), start=time(18, 0), loc="Bridge"
        )
        eids.append(eid)
        _id, eid = _add_event(
            db, title=fresh_title, on=_JUNE_7.date(), start=time(18, 0), loc="Marina"
        )
        eids.append(eid)
        db.commit()
    return stale_title, fresh_title, eids


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_events_ui_day_rollover_serves_fresh_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached-at-June-2 world, request on June 7 → June 7 data, zero June 2 leakage.

    The same process renders both requests, so any module-level snapshot of
    the sections (or an import-time ``now``) would replay the June 2 render
    on the second request — exactly the live P0.
    """
    suffix = uuid.uuid4().hex[:6]
    stale_title, fresh_title, eids = _seed_rollover_events(suffix)
    try:
        with TestClient(app) as client:
            # Day N: mint a render with the June 2 event under "Today".
            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_2)
            body_day_n = client.get("/events-ui").text
            assert stale_title in body_day_n

            # Day N+5, same process: the old "Today" must be gone, the new
            # day's event present.
            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_7)
            resp = client.get("/events-ui")
            body_day_n5 = resp.text
            assert fresh_title in body_day_n5
            assert stale_title not in body_day_n5
            # Transport half of the fix: the dated page must demand
            # revalidation so no HTTP cache can replay the June 2 render.
            assert resp.headers.get("cache-control") == _EXPECTED_CACHE_CONTROL
    finally:
        _cleanup(eids)


def test_events_ui_when_chip_windows_follow_day_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ?when=today chip must re-anchor to the current lake-local date."""
    suffix = uuid.uuid4().hex[:6]
    stale_title, fresh_title, eids = _seed_rollover_events(suffix)
    try:
        with TestClient(app) as client:
            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_2)
            assert stale_title in client.get("/events-ui?when=today").text

            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_7)
            body = client.get("/events-ui?when=today").text
            assert fresh_title in body
            assert stale_title not in body
    finally:
        _cleanup(eids)


def test_home_day_rollover_updates_today_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """/home's date stamp and week strip must follow the lake-local date."""
    # The hero eyebrow renders "Your lake · {{ today_label }}" only when no
    # env override is set; clear it so the date stamp is assertable.
    monkeypatch.delenv("HOME_HERO_EYEBROW", raising=False)
    # The week strip renders only when the window has events (has_any gate in
    # home_sandstone.html), so seed one on each anchor day.
    suffix = uuid.uuid4().hex[:6]
    _stale_title, _fresh_title, eids = _seed_rollover_events(suffix)
    try:
        with TestClient(app) as client:
            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_2)
            body_day_n = client.get("/home").text
            assert "Tuesday, June 2" in body_day_n

            monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _JUNE_7)
            resp = client.get("/home")
            body_day_n5 = resp.text
            assert "Sunday, June 7" in body_day_n5
            assert "Tuesday, June 2" not in body_day_n5
            # Week strip re-anchors: today's tap-through link is the new date.
            assert "/events-ui?date=2099-06-07" in body_day_n5
            assert resp.headers.get("cache-control") == _EXPECTED_CACHE_CONTROL
    finally:
        _cleanup(eids)
