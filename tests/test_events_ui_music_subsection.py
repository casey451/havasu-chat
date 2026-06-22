"""P2: the Music & nightlife group splits into Live Music / Comedy & Theater on
the /events-ui day view, and event rows carry a scannable type label."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Event
from app.home import events_views
from app.main import app

_SRC = "_p2_music_probe"


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe(db: Session):
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()
    yield
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()


def _add(db: Session, *, title: str, on: date, venue: str = "Lighthouse Lounge", tags=None) -> None:
    db.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=on,
            start_time=time(20, 0),
            end_time=time(23, 0),
            location_name=venue,
            location_normalized=venue.lower(),
            description="x",
            event_url="https://example.com/e",
            tags=tags or [],
            status="live",
            source=_SRC,
            verified=True,
        )
    )
    db.commit()


def test_music_group_splits_into_live_music_and_comedy(db: Session) -> None:
    d = now_lake_havasu().date() + timedelta(days=3)
    _add(db, title="Sacred Stone", on=d, tags=["music"])  # live music
    _add(db, title="Top Goons: A Night of Comedy", on=d)  # comedy
    _add(db, title="DJ Spinz Late Night", on=d, tags=["music"])  # residual

    groups = {g["key"]: g for g in events_views.day_groups(db, day=d, now=now_lake_havasu())}
    assert "music" in groups, list(groups)
    subs = {s["label"]: s["count"] for s in groups["music"].get("subgroups", [])}
    assert subs.get("Live Music") == 1
    assert subs.get("Comedy & Theater") == 1
    assert subs.get("More music & nightlife") == 1


def test_day_view_rows_carry_type_label(db: Session) -> None:
    d = now_lake_havasu().date() + timedelta(days=3)
    _add(db, title="Sacred Stone", on=d, tags=["music"])
    body = TestClient(app).get(f"/events-ui?date={d.isoformat()}&theme=lake").text
    assert "Live Music" in body
    assert "Sacred Stone" in body  # the real title is never mangled
    # The type rides as a distinct badge, not folded into the title text.
    assert 'class="rtype">Live Music' in body
