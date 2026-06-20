"""Movies feature renders under the lake theme (nav, home strip, /movies page).

The #445 nav + home strip and the /movies page were desert-only; lake is the
live default, so they must render through base_lake too. Seeds one showtime for
"today" and, with THEME_DEFAULT=lake (as prod sets it), asserts the lake base
renders and the movies content shows on /movies, /home, and /events-ui.
"""

from __future__ import annotations

import uuid
from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import MovieShowtime
from app.main import app

_LAKE_MARKER = 'data-theme="lake"'
_STRIP_MARKER = 'aria-label="At the movies today"'


def _seed(film_title: str, sid: str) -> str:
    with SessionLocal() as db:
        row = MovieShowtime(
            source="test_movies_lake",
            source_stable_id=sid,
            theater_slug="star-cinemas",
            theater_name="Star Cinemas",
            film_title=film_title,
            show_date=now_lake_havasu().date(),
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


def test_movies_feature_renders_under_lake_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEME_DEFAULT", "lake")
    suffix = uuid.uuid4().hex[:6]
    film = f"ZZ Lake Showtime {suffix}"
    ids = [_seed(film, f"sc-{suffix}")]
    try:
        with TestClient(app) as client:
            movies = client.get("/movies")
            home = client.get("/home")
            events = client.get("/events-ui")

        # /movies: lake base + lake nav Movies link + the film grid body.
        assert movies.status_code == 200
        assert _LAKE_MARKER in movies.text
        assert 'href="/movies"' in movies.text  # nav parity link
        assert "Movies around the lake" in movies.text
        assert film in movies.text

        # /home: lake base + movies now live INSIDE the unified feed's
        # "At the movies" group (Phase 2), not the standalone strip.
        assert home.status_code == 200
        assert _LAKE_MARKER in home.text
        assert 'data-group="movies"' in home.text
        assert film in home.text

        # /events-ui (today): lake base + the strip.
        assert events.status_code == 200
        assert _LAKE_MARKER in events.text
        assert _STRIP_MARKER in events.text
        assert film in events.text
    finally:
        _cleanup(ids)
