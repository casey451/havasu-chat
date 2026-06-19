"""Movie showtime store: fetch Star Cinemas + upsert/prune MovieShowtime rows.

Star Cinemas' public site is a React app backed by a PUBLIC Supabase REST API;
one request to ``sessions`` (joined to films/screens/sites) returns every
upcoming showtime. We map each session to a :class:`MovieShowtime` and upsert on
``(source, source_stable_id)`` so the twice-daily scrape is idempotent. Movies
never touch the events/contributions pipeline — this is the whole point of the
dedicated table: they can't leak into the general events feed.

The Supabase anon key is the site's own public, read-only frontend key (designed
to ship in the browser bundle, RLS-gated). Both values are env-overridable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.contrib.river_scene import USER_AGENT
from app.core.timezone import now_lake_havasu
from app.db.models import MovieShowtime

STAR_CINEMAS_SUPABASE_URL = (
    os.getenv("STAR_CINEMAS_SUPABASE_URL")
    or "https://kfwmdbjaovxyvxpfokcr.supabase.co"
).rstrip("/")
STAR_CINEMAS_SUPABASE_ANON_KEY = os.getenv("STAR_CINEMAS_SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtmd21kYmphb3Z4eXZ4cGZva2NyIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NDI5NDI0NjksImV4cCI6MjA1ODUxODQ2OX0."
    "ktAlKbkJ-WjZnpkZkXMAHrBvjNlz4Axuw2r921QlZLU"
)

SHOWTIME_WINDOW_DAYS = 14

STAR_CINEMAS_SOURCE = "star_cinemas"
STAR_CINEMAS_THEATER_SLUG = "star-cinemas"
STAR_CINEMAS_THEATER_NAME = "Star Cinemas"

_SELECT = (
    "id,session_datetime,show_start,status,show_type,seating_type,is_sold_out,"
    "web_session_url,"
    "film:films(id,title,rating,genre,runtime,director,synopsis,poster_url,release_date),"
    "screen:screens(screen_name),"
    "site:sites(name,address,city,state,timezone)"
)
_DEAD_STATUSES = {"cancelled", "canceled", "deleted", "closed", "hidden"}


@dataclass
class ShowtimeRecord:
    """Source-agnostic showtime ready to upsert into ``movie_showtimes``."""

    source: str
    source_stable_id: str
    theater_slug: str
    theater_name: str
    film_title: str
    show_date: date
    show_time: time
    rating: str | None = None
    genre: str | None = None
    runtime_minutes: int | None = None
    director: str | None = None
    synopsis: str | None = None
    poster_url: str | None = None
    screen: str | None = None
    booking_url: str | None = None
    is_sold_out: bool = False
    is_free: bool = False
    tags: list[str] = field(default_factory=list)


def _parse_session_dt(value: str) -> datetime:
    """Veezi serializes the local Arizona show time with a ``+00:00`` suffix; the
    wall-clock components are what the theater displays, so drop the tzinfo."""
    s = (value or "").strip().replace("Z", "+00:00")
    return datetime.fromisoformat(s).replace(tzinfo=None)


def _int_or_none(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _fetch_json(url: str, *, timeout: float = 60.0) -> Any:
    """GET a Supabase REST URL with the anon key, behind the retry envelope."""

    def _inner() -> Any:
        from app.contrib.url_fetcher import is_blocked_target

        blocked, reason = is_blocked_target(url)
        if blocked:
            raise RuntimeError(f"blocked_ssrf:{reason}:{url}")
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "apikey": STAR_CINEMAS_SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {STAR_CINEMAS_SUPABASE_ANON_KEY}",
        }
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as c:
            r = c.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()

    from app.core.background import with_retry

    result = with_retry(_inner, max_attempts=3)
    if result is None:
        raise RuntimeError(f"fetch failed for {url}")
    return result


def fetch_star_cinemas(
    *, today: date | None = None, window_days: int = SHOWTIME_WINDOW_DAYS
) -> list[ShowtimeRecord]:
    """Fetch Star Cinemas showtimes for [today, today+window_days] as records."""
    today = today or now_lake_havasu().date()
    frm = f"{today.isoformat()}T00:00:00"
    to = f"{(today + timedelta(days=window_days)).isoformat()}T23:59:59"
    url = (
        f"{STAR_CINEMAS_SUPABASE_URL}/rest/v1/sessions"
        f"?select={_SELECT}"
        f"&session_datetime=gte.{frm}"
        f"&session_datetime=lte.{to}"
        f"&order=session_datetime.asc"
    )
    rows = _fetch_json(url)
    out: list[ShowtimeRecord] = []
    for row in rows if isinstance(rows, list) else []:
        film = row.get("film") or {}
        title = (film.get("title") or "").strip()
        if not title or not row.get("session_datetime"):
            continue
        if (row.get("status") or "").strip().lower() in _DEAD_STATUSES:
            continue
        sid = str(row.get("id") or "").strip()
        if not sid:
            continue
        start = _parse_session_dt(str(row["session_datetime"]))
        site = row.get("site") or {}
        screen = (row.get("screen") or {}).get("screen_name")
        show_type = (row.get("show_type") or "").strip()
        tags: list[str] = []
        if show_type and show_type.lower() != "public":
            tags.append(show_type.lower())
        if row.get("is_sold_out"):
            tags.append("sold-out")
        out.append(
            ShowtimeRecord(
                source=STAR_CINEMAS_SOURCE,
                source_stable_id=sid,
                theater_slug=STAR_CINEMAS_THEATER_SLUG,
                theater_name=(site.get("name") or STAR_CINEMAS_THEATER_NAME).strip()
                or STAR_CINEMAS_THEATER_NAME,
                film_title=title,
                show_date=start.date(),
                show_time=start.time().replace(tzinfo=None),
                rating=(film.get("rating") or "").strip() or None,
                genre=(film.get("genre") or "").strip() or None,
                runtime_minutes=_int_or_none(film.get("runtime")),
                director=(film.get("director") or "").strip() or None,
                synopsis=(film.get("synopsis") or "").strip() or None,
                poster_url=(film.get("poster_url") or "").strip() or None,
                screen=screen,
                booking_url=(row.get("web_session_url") or "").strip() or None,
                is_sold_out=bool(row.get("is_sold_out")),
                is_free=False,
                tags=tags,
            )
        )
    return out


_MUTABLE_FIELDS = (
    "theater_slug",
    "theater_name",
    "film_title",
    "show_date",
    "show_time",
    "rating",
    "genre",
    "runtime_minutes",
    "director",
    "synopsis",
    "poster_url",
    "screen",
    "booking_url",
    "is_sold_out",
    "is_free",
    "tags",
)


def upsert_showtimes(db: Session, records: list[ShowtimeRecord]) -> dict[str, int]:
    """Idempotent upsert on ``(source, source_stable_id)``. Returns counts."""
    if not records:
        return {"created": 0, "updated": 0}
    sources = {r.source for r in records}
    stable_ids = {r.source_stable_id for r in records}
    existing = {
        (m.source, m.source_stable_id): m
        for m in db.scalars(
            select(MovieShowtime).where(
                MovieShowtime.source.in_(sources),
                MovieShowtime.source_stable_id.in_(stable_ids),
            )
        ).all()
    }
    now = now_lake_havasu()
    created = updated = 0
    for r in records:
        row = existing.get((r.source, r.source_stable_id))
        if row is None:
            row = MovieShowtime(source=r.source, source_stable_id=r.source_stable_id)
            for fld in _MUTABLE_FIELDS:
                setattr(row, fld, getattr(r, fld))
            row.scraped_at = now
            db.add(row)
            created += 1
        else:
            for fld in _MUTABLE_FIELDS:
                setattr(row, fld, getattr(r, fld))
            row.scraped_at = now
            updated += 1
    db.commit()
    return {"created": created, "updated": updated}


def prune_past(db: Session, *, before: date | None = None) -> int:
    """Delete showtimes whose date is strictly before ``before`` (default today).

    Keeps the table bounded to current/upcoming showings."""
    before = before or now_lake_havasu().date()
    result = db.execute(delete(MovieShowtime).where(MovieShowtime.show_date < before))
    db.commit()
    return int(result.rowcount or 0)
