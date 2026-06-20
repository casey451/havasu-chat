"""Phase 4 — Seniors parity: filter, /events-ui toggle, and chat senior intent.

Mirrors tests/test_events_ui_views.py seeding (far-future 2099 Monday, uuid
suffixes, ``app.home.router.now_lake_havasu`` monkeypatch, targeted cleanup).
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
from app.events.senior_filter import is_senior_event
from app.home import calendar_view, events_views
from app.main import app

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


def _add_event(db, *, title, start, loc, tags=None) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url="https://example.com/e", tags=tags or [],
        status="live", source="test-seniors-p4", verified=True, is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


# --- senior_filter -----------------------------------------------------------


def test_is_senior_event_tag_and_keywords() -> None:
    assert is_senior_event("Exercise Class", ["senior"]) is True
    assert is_senior_event("Tai Chi for Balance") is True       # new keyword
    assert is_senior_event("Bunco Night") is True               # new keyword
    assert is_senior_event("Low-Impact Aerobics") is True       # new keyword
    # Lake-Havasu-ambiguous terms must NOT imply seniors on their own.
    assert is_senior_event("London Bridge Days") is False
    assert is_senior_event("Live Music at the Brewery") is False


# --- day_groups seniors narrow ----------------------------------------------


def test_day_groups_seniors_narrows() -> None:
    s = uuid.uuid4().hex[:6]
    senior = f"ZZ Senior Stretch {s}"
    music = f"ZZ Live Band Night {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=senior, start=time(20, 0), loc="Senior Center",
                               tags=["senior"]))
        eids.append(_add_event(db, title=music, start=time(20, 30), loc="Bar", tags=["music"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), seniors=True, now=_MONDAY)
        titles = {r["title"] for g in groups for r in g["rows"]}
        assert any(senior in t for t in titles)
        assert not any(music in t for t in titles)
        # The narrowed view does not also build the cross-cutting overlays.
        assert not any(g["key"] in ("family", "seniors") for g in groups)
    finally:
        _cleanup(eids)


# --- /events-ui ?seniors=1 toggle -------------------------------------------


def test_events_ui_seniors_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    s = uuid.uuid4().hex[:6]
    senior = f"ZZ Senior Social {s}"
    music = f"ZZ Karaoke Night {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=senior, start=time(20, 0), loc="Senior Center",
                               tags=["senior"]))
        eids.append(_add_event(db, title=music, start=time(20, 30), loc="Bar", tags=["music"]))
        db.commit()
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _MONDAY)
        with TestClient(app) as client:
            body = client.get("/events-ui?theme=lake&seniors=1").text
        # The Seniors toggle renders pressed; the narrow keeps senior items only.
        assert 'class="ev-fam ev-sen on"' in body
        assert 'aria-pressed="true"' in body
        assert senior in body
        assert music not in body
    finally:
        _cleanup(eids)


# --- chat senior intent (calendar_view) -------------------------------------


def test_calendar_parses_senior_intent() -> None:
    assert calendar_view.parse_calendar_query("what is there for seniors this week")["aud"] == "seniors"
    assert calendar_view.parse_calendar_query("older adults activities")["aud"] == "seniors"
    # A senior ask is a discovery query (routes to /calendar, not a directory leaf).
    assert calendar_view.is_discovery_query("things for seniors tonight") is True
    # Kids intent still resolves to kids (not regressed).
    assert calendar_view.parse_calendar_query("toddler story time")["aud"] == "kids"


def test_calendar_seniors_segment_and_narrow() -> None:
    s = uuid.uuid4().hex[:6]
    senior = f"ZZ Senior Bingo {s}"
    music = f"ZZ DJ Night {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=senior, start=time(20, 0), loc="Senior Center",
                               tags=["senior"]))
        eids.append(_add_event(db, title=music, start=time(20, 30), loc="Bar", tags=["music"]))
        db.commit()
    try:
        with SessionLocal() as db:
            vm = calendar_view.build_calendar(
                db, q="for seniors", today=_MONDAY.date(), now=_MONDAY
            )
        # Senior segment offered; narrowed columns hold the senior item only.
        assert any(o["label"] == "Seniors" and o["active"] for o in vm["seg_aud"])
        all_titles = {it["title"] for col in vm["columns"] for it in col["entries"]}
        assert any(senior in t for t in all_titles)
        assert not any(music in t for t in all_titles)
    finally:
        _cleanup(eids)
