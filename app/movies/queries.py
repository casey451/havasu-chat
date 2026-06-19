"""Movie-showtime queries for the /movies page and the home movie strip.

Showtimes are stored as ``Event`` rows tagged ``movie`` plus a per-theater tag
(``star-cinemas``, ``movies-havasu``). This module loads them for a day and
shapes them into theater -> film -> showtime groups for the templates.

Tag filtering is done in Python (not a DB JSON operator) so it's identical on
SQLite and Postgres — the day window keeps the row count tiny.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Event
from app.events.time_labels import short_time_label, time_sort_key

MOVIE_TAG = "movie"
FREE_KIDS_TAGS = {"free", "kids", "summer-series"}
_RATINGS = {"G", "PG", "PG-13", "R", "NC-17", "NR"}

# Display order for known theaters; unknown theaters sort after, alphabetically.
THEATER_ORDER = ["star-cinemas", "movies-havasu"]
_KNOWN_THEATER_SLUGS = set(THEATER_ORDER)


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


@dataclass
class TheaterGroup:
    name: str
    slug: str
    films: list[FilmCard]


def _slugify(value: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in (value or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "theater"


def _theater_slug(ev: Event) -> str:
    for tag in ev.tags or []:
        if tag in _KNOWN_THEATER_SLUGS:
            return tag
    return _slugify(ev.location_name or "theater")


def _split_rating(meta_line: str) -> tuple[str, str]:
    """Split a "PG · Drama · 2h" meta line into (rating, "Drama · 2h")."""
    parts = [p.strip() for p in meta_line.split("·") if p.strip()]
    if parts and parts[0] in _RATINGS:
        return parts[0], " · ".join(parts[1:])
    return "", meta_line


def _meta_line(description: str | None) -> str:
    """Return the leading meta line ("PG - Drama - 2h 25m"), if present.

    The scraper writes ``"<meta>\\n\\n<synopsis>"``; the meta line is short and
    uses the " · " separator. Anything that doesn't look like that is treated
    as plain synopsis and no meta is shown.
    """
    head = (description or "").split("\n\n", 1)[0].strip()
    if head and len(head) <= 90 and "·" in head:
        return head
    return ""


def group_showtimes(events: list[Event], *, day: date) -> list[TheaterGroup]:
    """Pure grouping: movie events on ``day`` -> theater -> film -> showtimes.

    Films with no displayable showtime are dropped. Showtimes sort
    chronologically; films sort by their earliest showtime; theaters follow
    :data:`THEATER_ORDER` then alphabetical.
    """
    movies = [
        e
        for e in events
        if e.date == day and MOVIE_TAG in (e.tags or [])
    ]
    theaters: dict[str, dict] = {}
    for e in movies:
        slug = _theater_slug(e)
        tg = theaters.setdefault(
            slug,
            {"name": e.location_name or "Theater", "slug": slug, "films": {}},
        )
        if e.title not in tg["films"]:
            rating, meta = _split_rating(_meta_line(e.description))
            tg["films"][e.title] = {
                "title": e.title, "rating": rating, "meta": meta,
                "poster": e.image_url, "times": [],
            }
        film = tg["films"][e.title]
        if not film["poster"] and e.image_url:
            film["poster"] = e.image_url
        label = short_time_label(e.start_time, e.end_time)
        if label:
            film["times"].append(
                Showtime(
                    label=label,
                    url=(e.event_url or ""),
                    sort=time_sort_key(e.start_time, e.end_time),
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
                    poster=f["poster"], showtimes=f["times"],
                )
            )
        if not films:
            continue
        films.sort(key=lambda fc: fc.showtimes[0].sort)
        groups.append(TheaterGroup(name=tg["name"], slug=slug, films=films))
    return groups


def _load_live_events_for_day(db: Session, day: date) -> list[Event]:
    stmt = select(Event).where(Event.date == day, Event.status == "live")
    return list(db.execute(stmt).scalars().all())


def showtimes_for_day(db: Session, *, day: date) -> list[TheaterGroup]:
    """Theater -> film -> showtime groups for the /movies page."""
    return group_showtimes(_load_live_events_for_day(db, day), day=day)


def has_free_kids(db: Session, *, day: date) -> bool:
    """True when any free/kids/summer-series movie is showing on ``day``."""
    for e in _load_live_events_for_day(db, day):
        tags = set(e.tags or [])
        if MOVIE_TAG in tags and FREE_KIDS_TAGS & tags:
            return True
    return False


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
