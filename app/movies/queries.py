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
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import to_lake_naive
from app.db.models import MovieShowtime
from app.events.time_labels import short_time_label, time_sort_key
from app.movies.posters import proxied_poster_url

# A showtime drops off "today" this many minutes after it starts (the same
# start-based cutoff the events calendar uses): once a movie has been running an
# hour it's too late to catch it, so it stops showing.
_SHOWTIME_GRACE_MINUTES = 60


def _showtime_expired(
    show_date: date, show_time: time | None, now: datetime | None
) -> bool:
    """True if a showtime on ``show_date`` started >1h ago relative to ``now``.

    No-op (False) unless ``now`` is given and ``show_date`` is the current day, so
    only *today's* already-started showtimes are trimmed; other days are untouched.
    """
    if now is None or show_time is None:
        return False
    now_local = to_lake_naive(now)
    if now_local.date() != show_date:
        return False
    start_dt = datetime.combine(show_date, show_time)
    return now_local > start_dt + timedelta(minutes=_SHOWTIME_GRACE_MINUTES)

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


def _canonical_titles(
    rows: list["MovieShowtime"], *, day: date | None
) -> dict[str, str]:
    """One canonical *display* spelling per film, keyed by :func:`normalize_film_title`.

    The two sources spell the same film with different capitalization ("Masters
    of the Universe" at Star Cinemas vs "Masters Of The Universe" at Movies
    Havasu), so the same film read inconsistently across the per-theater
    sections. We pick a single display form per film by source priority — the
    earliest theater in :data:`THEATER_ORDER` (Star Cinemas) wins — so every
    section, the home "At the movies" feed, and the strip render it identically.
    Ties (same theater, or two unknown theaters) keep the first-seen spelling.
    """
    best: dict[str, tuple[int, str]] = {}
    for r in rows:
        if day is not None and r.show_date != day:
            continue
        title = (r.film_title or "").strip()
        if not title:
            continue
        slug = r.theater_slug or "theater"
        idx = THEATER_ORDER.index(slug) if slug in THEATER_ORDER else len(THEATER_ORDER)
        fkey = normalize_film_title(title)
        cur = best.get(fkey)
        if cur is None or idx < cur[0]:
            best[fkey] = (idx, title)
    return {k: v[1] for k, v in best.items()}


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


def _meta_str(genre: str, runtime_minutes: int | None) -> str:
    bits = [b for b in [(genre or "").strip(), _runtime_label(runtime_minutes)] if b]
    return " · ".join(bits)


@dataclass(frozen=True)
class _FilmMeta:
    rating: str
    genre: str
    runtime_minutes: int | None


def _canonical_film_meta(
    rows: list["MovieShowtime"], *, day: date | None
) -> dict[str, _FilmMeta]:
    """One canonical ``(rating, genre, runtime)`` per film across theaters (Item
    2.3), keyed by :func:`normalize_film_title`.

    The two sources disagree on a film's metadata — runtime "2h 3m" vs "2h 2m",
    different genre lists — so the same film read inconsistently between the
    per-theater sections (first row per theater won). One canonical set per film,
    by an explicit, documented rule:

      • **genre** → the LONGEST non-empty genre string (the most complete list).
      • **runtime** → the canonical-source theater's runtime (earliest in
        :data:`THEATER_ORDER`, then first-seen), falling back to any non-zero
        runtime — so a film reads ONE runtime everywhere.
      • **rating** → same priority as runtime (first non-empty by theater order).

    Mirrors :func:`_canonical_titles` so a film's title and its metadata agree on
    source spelling.
    """
    best_genre: dict[str, str] = {}
    best_rt: dict[str, tuple[int, int]] = {}      # fkey -> (theater_idx, minutes)
    best_rating: dict[str, tuple[int, str]] = {}  # fkey -> (theater_idx, rating)
    for r in rows:
        if day is not None and r.show_date != day:
            continue
        title = (r.film_title or "").strip()
        if not title:
            continue
        fkey = normalize_film_title(title)
        slug = r.theater_slug or "theater"
        idx = THEATER_ORDER.index(slug) if slug in THEATER_ORDER else len(THEATER_ORDER)
        genre = (r.genre or "").strip()
        if genre and len(genre) > len(best_genre.get(fkey, "")):
            best_genre[fkey] = genre
        rt = int(r.runtime_minutes or 0)
        if rt > 0 and (fkey not in best_rt or idx < best_rt[fkey][0]):
            best_rt[fkey] = (idx, rt)
        rating = (r.rating or "").strip()
        if rating and (fkey not in best_rating or idx < best_rating[fkey][0]):
            best_rating[fkey] = (idx, rating)
    keys = set(best_genre) | set(best_rt) | set(best_rating)
    return {
        k: _FilmMeta(
            rating=best_rating.get(k, (0, ""))[1],
            genre=best_genre.get(k, ""),
            runtime_minutes=best_rt[k][1] if k in best_rt else None,
        )
        for k in keys
    }


def group_showtimes(
    rows: list[MovieShowtime], *, day: date | None = None, now: datetime | None = None
) -> list[TheaterGroup]:
    """Pure grouping: showtime rows -> theater -> film -> showtimes.

    Films with no displayable showtime are dropped. Showtimes sort
    chronologically; films sort by their earliest showtime; theaters follow
    :data:`THEATER_ORDER` then alphabetical.

    When ``now`` is given (and ``day`` is the current day), showtimes that started
    more than an hour ago are skipped, and a film whose showtimes have all started
    drops out entirely — the same start-based cutoff the events calendar uses.
    """
    # One canonical display spelling per film, shared across theaters, so the
    # same film never reads "X of the Y" in one section and "X Of The Y" in
    # another (Item 1).
    canon = _canonical_titles(rows, day=day)
    # One canonical (rating, genre, runtime) per film, shared across theaters, so
    # the same film never reads "2h 3m · Action" in one section and "2h 2m ·
    # Adventure" in another (Item 2.3).
    canon_meta = _canonical_film_meta(rows, day=day)
    theaters: dict[str, dict] = {}
    for r in rows:
        if day is not None and r.show_date != day:
            continue
        if _showtime_expired(r.show_date, r.show_time, now):
            continue
        slug = r.theater_slug or "theater"
        tg = theaters.setdefault(
            slug, {"name": r.theater_name or "Theater", "slug": slug, "films": {}}
        )
        fkey = normalize_film_title(r.film_title)
        film = tg["films"].get(fkey)
        if film is None:
            cm = canon_meta.get(fkey)
            film = {
                "title": canon.get(fkey, r.film_title),  # canonical display spelling
                # Canonical, theater-independent rating + meta (Item 2.3).
                "rating": cm.rating if cm else (r.rating or "").strip(),
                "meta": _meta_str(cm.genre, cm.runtime_minutes) if cm else "",
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
            # De-duplicate identical showtimes. Some feeds (notably Movies
            # Havasu / internet-ticketing.com) return the same start time more
            # than once, which rendered as "10 AM, 10 AM, 12 PM". Keep one entry
            # per time label, preferring one that carries a booking URL.
            _seen: dict[str, Showtime] = {}
            for _s in f["times"]:
                _kept = _seen.get(_s.label)
                if _kept is None or (not _kept.url and _s.url):
                    _seen[_s.label] = _s
            f["times"] = list(_seen.values())
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


def showtimes_for_day(
    db: Session, *, day: date, now: datetime | None = None
) -> list[TheaterGroup]:
    """Theater -> film -> showtime groups for the /movies page.

    Pass ``now`` to hide showtimes that started >1h ago when ``day`` is today.
    """
    return group_showtimes(_load_day(db, day), day=day, now=now)


def has_free_kids(db: Session, *, day: date) -> bool:
    """True when any free showing (the summer kids series) is on ``day``."""
    stmt = (
        select(MovieShowtime.id)
        .where(MovieShowtime.show_date == day, MovieShowtime.is_free.is_(True))
        .limit(1)
    )
    return db.scalar(stmt) is not None


def movies_today(
    db: Session, *, day: date, now: datetime | None = None, limit: int = 6
) -> list[dict]:
    """Flat, compact list for the home "At the movies today" strip.

    Pass ``now`` to hide showtimes that started >1h ago when ``day`` is today.
    """
    flat: list[dict] = []
    for group in showtimes_for_day(db, day=day, now=now):
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
