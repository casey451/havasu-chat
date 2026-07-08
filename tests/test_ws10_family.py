"""WS10 — the /family hub + /family/camps.

Acceptance (§10): zero chat-deflection tiles; today's kids feed (the ?family=1
narrow); a camps index built from the events DB. Seeding mirrors
tests/test_events_ui_views (Event auto-creates its Entity on flush; far-future
dates; uuid suffixes + targeted cleanup; membership assertions).
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import family_hub
from app.main import app

_FUTURE = date(2099, 7, 13)  # a far-future Monday


def _add_event(
    db, *, title, on, end=None, start=time(9, 0), loc="Rotary Park", tags=None, recurring=False
):
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        end_date=end,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source="test-ws10-family",
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids):
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


# --- page-level acceptance ---------------------------------------------------


def test_family_hub_has_no_chat_tiles() -> None:
    with TestClient(app) as client:
        body = client.get("/family").text
    assert "chat?q=" not in body


def test_family_tiles_link_real_leaves() -> None:
    with TestClient(app) as client:
        body = client.get("/family").text
    for t in family_hub.family_tiles():
        assert t["url"] in body
    assert "/family/camps" in body


def test_family_keeps_heading_and_events_link() -> None:
    with TestClient(app) as client:
        body = client.get("/family").text
    assert "Plenty to do with the kids" in body
    assert 'href="/events-ui"' in body


def test_family_camps_page_renders() -> None:
    with TestClient(app) as client:
        r = client.get("/family/camps")
    assert r.status_code == 200
    assert "Summer camps" in r.text
    assert "chat?q=" not in r.text


# --- camps_index -------------------------------------------------------------


def test_camps_index_selects_camps_excludes_lookalikes() -> None:
    suf = uuid.uuid4().hex[:8]
    camp = f"ZZ Rainforest Rush Kids Camp {suf}"
    clinic = f"ZZ Split Finger Baseball Clinic {suf}"
    campaign = f"ZZ Voter Campaign Rally {suf}"  # 'campaign' must NOT read as camp
    ground = f"ZZ Havasu Campground Cleanup {suf}"  # 'campground' must NOT match
    with SessionLocal() as db:
        eids = [
            _add_event(db, title=camp, on=_FUTURE, end=_FUTURE + timedelta(days=4)),
            _add_event(db, title=clinic, on=_FUTURE),
            _add_event(db, title=campaign, on=_FUTURE),
            _add_event(db, title=ground, on=_FUTURE),
        ]
        db.commit()
    try:
        with SessionLocal() as db:
            got = {r["title"] for r in family_hub.camps_index(db, today=_FUTURE)}
        assert camp in got
        assert clinic in got
        assert campaign not in got
        assert ground not in got
    finally:
        _cleanup(eids)


def test_camps_index_dedupes_by_title_with_date_range() -> None:
    suf = uuid.uuid4().hex[:8]
    title = f"ZZ Camp I Wanna Go {suf}"
    with SessionLocal() as db:
        eids = [
            _add_event(db, title=title, on=_FUTURE, end=_FUTURE + timedelta(days=4)),
            _add_event(db, title=title, on=_FUTURE + timedelta(days=14)),  # 2nd session
        ]
        db.commit()
    try:
        with SessionLocal() as db:
            rows = [r for r in family_hub.camps_index(db, today=_FUTURE) if r["title"] == title]
        assert len(rows) == 1  # one card per camp
        assert "Jul 13" in rows[0]["when"]  # earliest occurrence, date-range label
    finally:
        _cleanup(eids)


def test_kids_today_rows_lists_kid_event() -> None:
    suf = uuid.uuid4().hex[:8]
    title = f"ZZ Kids Story Time {suf}"
    with SessionLocal() as db:
        eid = _add_event(db, title=title, on=_FUTURE, start=time(10, 0), loc="Library")
        db.commit()
    try:
        with SessionLocal() as db:
            got = family_hub.kids_today_rows(db, day=_FUTURE)
        match = next((r for r in got if r["title"].startswith("ZZ Kids Story Time")), None)
        assert match is not None
        assert match["url"].startswith("/events/")
    finally:
        _cleanup([eid])
