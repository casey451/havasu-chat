"""/events-ui surfaces "At the Movies" as a first-class Calendar category on the
today/day views (two-surface spec §2; promoted 2026-06-25 from the old collapsed
side strip).

serve_events_ui inserts a ``movies`` render group (``is_movies``) into the
today + day groups (not week or month), and the events template renders it as a
first-class accordion (``data-k="movies"``). This pins that wiring
end-to-end: a showtime seeded for the mocked "today" renders in the accordion on
the today view and is absent from the week view.

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
# The promoted first-class accordion (was the side-strip's aria-label marker).
_MOVIES_MARKER = 'data-k="movies"'


def _seed_showtime(film_title: str, sid: str, *, booking_url: str | None = "https://example.com/book") -> str:
    with SessionLocal() as db:
        row = MovieShowtime(
            source="test_movies_ui",
            source_stable_id=sid,
            theater_slug="star-cinemas",
            theater_name="Star Cinemas",
            film_title=film_title,
            show_date=_NOW.date(),
            show_time=time(18, 30),
            booking_url=booking_url,
        )
        db.add(row)
        db.commit()
        return row.id


def _cleanup(ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(ids)))
        db.commit()


def test_events_ui_today_shows_movies_category_week_does_not(
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
        # The first-class "At the Movies" accordion renders on the today view,
        # carrying the category label, the seeded film, and a /movies link.
        assert _MOVIES_MARKER in today.text
        assert "At the Movies" in today.text
        assert film in today.text
        assert 'href="/movies"' in today.text
        # The week view has no movies group (only today/day get one).
        assert week.status_code == 200
        assert _MOVIES_MARKER not in week.text
        assert film not in week.text
    finally:
        _cleanup(ids)


def test_movie_tile_with_no_booking_url_is_not_a_dead_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A showtime whose booking_url is blank must NOT render a dead ``href=""`` on
    # the movies surface — it falls back to /movies. (Star Cinemas' live feed now
    # backfills a booking landing in the store, but the template guard is the
    # belt-and-suspenders for any url-less row.)
    suffix = uuid.uuid4().hex[:6]
    film = f"ZZ Linkless Film {suffix}"
    ids = [_seed_showtime(film, f"nolink-{suffix}", booking_url=None)]
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _NOW)
        with TestClient(app) as client:
            today = client.get("/events-ui")
        assert today.status_code == 200
        assert film in today.text
        # No dead href anywhere on the rendered movies surface.
        assert 'href=""' not in today.text
    finally:
        _cleanup(ids)
