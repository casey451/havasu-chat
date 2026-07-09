"""Shared movie-event tag helper.

Kept deliberately dependency-light (only ``app.db.models`` + SQLAlchemy) so both
``app.events.queries`` and ``app.home.queries`` can import it without creating a
circular import (events.queries -> providers.queries -> home.queries).

Movie showtimes are ``Event`` rows carrying ``"movie"`` in ``Event.tags``. They
have their own surface (``/movies`` + the home "At the movies today" strip) and
are excluded from every general events feed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, cast

from app.db.models import Event

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

MOVIE_EVENT_TAG = "movie"


def not_movie_event_clause() -> ColumnElement[bool]:
    """SQL filter excluding movie-tagged events from general event queries.

    ``Event.tags`` is a non-null JSON list. The quoted-token match is exact
    (``"movies"`` / ``"movie-night"`` won't match) and portable across SQLite
    (tags stored as TEXT) and Postgres (JSON) since both cast to the JSON string.
    Use this on any query that LIMITs in SQL, so movie rows don't consume the
    limit before a Python filter could run.
    """
    return cast(Event.tags, String).notlike(f'%"{MOVIE_EVENT_TAG}"%')
