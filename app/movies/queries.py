"""Read movie showtimes for the /movies page and the home "At the movies today"
strip, from the dedicated ``movie_showtimes`` table.

No ``Event`` rows are involved — movie showtimes live in their own table so they
can't leak into the general events feed. The public API (``showtimes_for_day``,
``has_free_kids``, ``movies_today``) is unchanged from the events-backed version,
so the router and templates need no edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MovieShowtime
from app.events.time_labels import short_time_label, time_sort_key
from app.movies.posters import proxied_poster_url

# Display order for known theaters; unknown theaters sort after, alphabetically.
THEATER_ORDER = ["star-cinemas", "movies-havasu"]

# Trailing punctuation/whitespace trimmed when comparing film titles for de-dup.
_FILM_TRAILING = " \t.,!?;:·-–—\"'`’"
_WS_RE = re.compile(r"\s+")


def normalize_film_title(title: str | None) -> str:
    """Case/space-insensitive de-dup key for a film title.

    Two theaters spell the same film differently — "The Death of Robin Hood" vs
    "The Death Of Robin Hood", "Masters of the Universe" vs "Masters Of The
    Universe" — and an exact-string de-dup showed both. Casefold, collapse
    internal whitespace, and trim trailing punctuation so the variants merge.
    Articles are deliberately KEPT (no "the"/"a" stripping) so genuinely
    different films are never collapsed.
    """
    t = _WS_RE.sub(" ", (title or "").casefold()).strip()
    return t.rstrip(_FILM_TRAILING)


@dataclass
class Showtime:
    label: str
    url: str
    sort: tuple[int, time]


@dataclass
class FilmCard:
    title: str
    rating: str
    meta: str
    poster: str | None
    showtimes: list[Showtime]
    # True when ANY of this film's showtimes today is free (the summer kids
    # series). Trailing default keeps positional construction backward-compatible.
    is_free: bool = False


@dataclass
class TheaterGroup:
    name: str
    slug: str
    films: list[FilmCard]


def _runtime_label(minutes: int | None) -> str:
    if not minutes or minutes <= 0:
        return ""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h" if hours else f"{mins}m"


def _meta(row: MovieShowtime) -> str:
    bits = [b for b in [(row.genre or "").strip(), _runtime_label(row.runtime_minutes)] if b]
    return " · ".join(bits)


def group_showtimes(
    rows: list[MovieShowtime], *, day: date | None = None
) -> list[TheaterGroup]:
    """Pure grouping: showtime rows -> theater -> film -> showtimes.

    Films with no displayable showtime are dropped. Showtimes sort
    chronologically; films sort by their earliest showtime; theaters follow
    :data:`THEATER_ORDER` then alphabetical.
    """
    theaters: dict[str, dict] = {}
    for r in rows:
        if day is not None and r.show_date != day:
            continue
        slug = r.theater_slug or "theater"
        tg = theaters.setdefault(
            slug, {"name": r.theater_name or "Theater", "slug": slug, "films": {}}
        )
        fkey = normalize_film_title(r.film_title)
        film = tg["films"].get(fkey)
        if film is None:
            film = {
                "title": r.film_title,  # first-seen spelling is the display title
                "rating": (r.rating or "").strip(),
                "meta": _meta(r),
                # Proxy Veezi posters through our own origin so referrer-based
                # hotlink protection can't blank them (see app.movies.posters).
                "poster": proxied_poster_url(r.poster_url),
                "free": False,
                "times": [],
            }
            tg["films"][fkey] = film
        if not film["poster"] and r.poster_url:
            film["poster"] = proxied_poster_url(r.poster_url)
        if getattr(r, "is_free", False):
            film["free"] = True
        label = short_time_label(r.show_time, None)
        if label:
            film["times"].append(
                Showtime(
                    label=label,
                    url=(r.booking_url or ""),
                    sort=time_sort_key(r.show_time, None),
                )
            )

    def theater_key(slug: str) -> tuple[int, str]:
        idx = THEATER_ORDER.index(slug) if slug in THEATER_ORDER else len(THEATER_ORDER)
        return (idx, slug)

    groups: list[TheaterGroup] = []
    for slug in sorted(theaters, key=theater_key):
        tg = theaters[slug]
        films: list[FilmCard] = []
        for f in tg["films"].values():
            if not f["times"]:
                continue
            f["times"].sort(key=lambda s: s.sort)
            films.append(
                FilmCard(
                    title=f["title"], rating=f["rating"], meta=f["meta"],
                    poster=f["poster"], showtimes=f["times"], is_free=f["free"],
                )
            )
        if not films:
            continue
        films.sort(key=lambda fc: fc.showtimes[0].sort)
        groups.append(TheaterGroup(name=tg["name"], slug=slug, films=films))
    return groups


def _load_day(db: Session, day: date) -> list[MovieShowtime]:
    return list(db.scalars(select(MovieShowtime).where(MovieShowtime.show_date == day)).all())


def showtimes_for_day(db: Session, *, day: date) -> list[TheaterGroup]:
    """Theater -> film -> showtime groups for the /movies page."""
    return group_showtimes(_load_day(db, day), day=day)


def has_free_kids(db: Session, *, day: date) -> bool:
    """True when any free showing (the summer kids series) is on ``day``."""
    stmt = (
        select(MovieShowtime.id)
        .where(MovieShowtime.show_date == day, MovieShowtime.is_free.is_(True))
        .limit(1)
    )
    return db.scalar(stmt) is not None


def movies_today(db: Session, *, day: date, limit: int = 6) -> list[dict]:
    """Flat, compact list for the home "At the movies today" strip."""
    flat: list[dict] = []
    for group in showtimes_for_day(db, day=day):
        for film in group.films:
            flat.append(
                {
                    "title": film.title,
                    "poster": film.poster,
                    "theater": group.name,
                    "times": [s.label for s in film.showtimes[:3]],
                    "url": film.showtimes[0].url,
                    "sort": film.showtimes[0].sort,
                }
            )
    flat.sort(key=lambda x: x["sort"])
    return flat[:limit]
