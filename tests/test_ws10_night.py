"""WS10 — the /night hub renders real, server-rendered content (no chat tiles).

Acceptance (§10): zero ``href="/chat?q="`` on the hub; the bar tiles land on the
bars-and-breweries subcategory; "Live music tonight" surfaces real events from
the events "music" bucket (``redesign.night_music_rows``); a happy-hour card is
an honest "coming soon" placeholder, not a chat deep-link.

Seeding mirrors tests/test_events_ui_views: an ``Event`` auto-creates its
``Entity`` on flush, far-future dates keep the row out of any live window, uuid
suffixes + targeted cleanup keep the suite isolated, and assertions key on
membership (never global counts).
"""

from __future__ import annotations

import uuid
from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import redesign
from app.main import app

# 2099-07-13 is a Monday; far enough out that no real event shares the day.
_FUTURE_DAY = date(2099, 7, 13)


def _add_event(db, *, title: str, on: date, start: time, loc: str, tags=None) -> str:
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
        tags=tags or [],
        status="live",
        source="test-ws10-night",
        verified=True,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


# --- page-level acceptance (no seeding needed) -------------------------------


def test_night_has_no_chat_query_tiles() -> None:
    """The headline WS10 acceptance: zero /chat?q= deep-links on the /night hub."""
    with TestClient(app) as client:
        body = client.get("/night").text
    assert "chat?q=" not in body
    assert "/chat?q=" not in body


def test_night_bar_tiles_point_to_bars_subcategory() -> None:
    with TestClient(app) as client:
        body = client.get("/night").text
    assert "/categories/eat-and-drink/bars-and-breweries" in body
    # The old unfiltered Eat & Drink deep-link is gone from the drink tiles.
    assert "live+music+tonight" not in body
    assert "happy+hour+now" not in body
    assert "taxi+or+rideshare" not in body


def test_night_happy_hours_is_coming_soon_not_chat() -> None:
    with TestClient(app) as client:
        body = client.get("/night").text
    assert "Coming soon" in body
    assert "Happy hours" in body


# --- night_music_rows: real events from the "music" bucket -------------------


def test_night_music_rows_lists_real_music_event() -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"ZZ Live Music Night {suf}"
    with SessionLocal() as db:
        eid = _add_event(db, title=name, on=_FUTURE_DAY, start=time(20, 0), loc="Barley Bros")
        db.commit()
    try:
        with SessionLocal() as db:
            rows = redesign.night_music_rows(db, day=_FUTURE_DAY)
        match = next((r for r in rows if r["title"].startswith("ZZ Live Music Night")), None)
        assert match is not None
        assert match["url"].startswith("/events/")
        assert match["time_label"]  # a real clock time, not blank
    finally:
        _cleanup([eid])


def test_night_music_rows_omits_when_none() -> None:
    """Honest-omit: a day with no music returns [] (the card is hidden, not faked).
    Uses a far-future day that carries no seeded music."""
    with SessionLocal() as db:
        rows = redesign.night_music_rows(db, day=date(2099, 12, 25))
    assert rows == []
