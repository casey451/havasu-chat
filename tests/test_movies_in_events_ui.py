"""/events-ui surfaces the "At the movies today" strip on the today/day views.

serve_events_ui adds ``movies_today`` to the today + day contexts (not week or
month), and the events templates include ``_partials/movies_today.html`` there.
This pins that wiring end-to-end: a showtime seeded for the mocked "today"
renders in the strip on the today view and is absent from the week view.

Mirrors tests/test_events_ui_views.py: far-future 2099 date + the
``app.home.router.now_lake_havasu`` monkeypatch so the view is anchored on a
deterministic "today".
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import MovieShowtime
from app.main import app

_LHC = ZoneInfo("America/Phoenix")
_NOW = datetime(2099, 7, 13, 9, 0, tzinfo=_LHC)
_STRIP_MARKER = 'aria-label="At the movies today"'


def _seed_showtime(film_title: str, sid: str) -> str:
    with SessionLocal() as db:
        row = MovieShowtime(
            source="test_movies_ui",
            source_stable_id=sid,
            theater_slug="star-cinemas",
            theater_name="Star Cinemas",
            film_title=film_title,
            show_date=_NOW.date(),
            show_time=time(18, 30),
            booking_url="https://example.com/book",
        )
        db.add(row)
        db.commit()
        return row.id


def _cleanup(ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(ids)))
        db.commit()


def test_events_ui_today_shows_movies_strip_week_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:6]
    film = f"ZZ Showtime Film {suffix}"
    ids = [_seed_showtime(film, f"sc-{suffix}")]
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _NOW)
        with TestClient(app) as client:
            today = client.get("/events-ui")
            week = client.get("/events-ui?view=week")
        assert today.status_code == 200
        # The strip renders on the today view, carrying the seeded film + a
        # /movies link.
        assert _STRIP_MARKER in today.text
        assert film in today.text
        assert 'href="/movies"' in today.text
        # The week view never includes the strip (no movies_today context there).
        assert week.status_code == 200
        assert _STRIP_MARKER not in week.text
        assert film not in week.text
    finally:
        _cleanup(ids)
