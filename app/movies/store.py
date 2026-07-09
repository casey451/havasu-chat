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

import logging
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
from app.events.lint import is_kids_series, suspect_showtime

logger = logging.getLogger(__name__)

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
# Star Cinemas' Veezi booking landing — the site's own "Show Times" page, listing
# every upcoming session with per-show ticket links. We fall back to it when a
# session's per-show ``web_session_url`` is empty (Veezi leaves it blank for some
# sessions), so a Star Cinemas showtime still links to its bookable destination
# instead of a dead/bouncing href. The siteToken is the public token in the
# working per-show URLs. (Confirmed 2026-06-26: title "Star Cinemas Show Times".)
STAR_CINEMAS_SITE_TOKEN = "3vydq3bssmr057q5b2h3b8caqr"
STAR_CINEMAS_BOOKING_LANDING = (
    f"https://ticketing.uswest.veezi.com/sessions/?siteToken={STAR_CINEMAS_SITE_TOKEN}"
)

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
                # Per-show Veezi URL when present, else the theater's booking
                # landing so the showtime still links somewhere bookable (Veezi
                # leaves ``web_session_url`` blank for some sessions). Free
                # showings are handled by a separate loader and aren't booked
                # here, so this feed's rows always get a real link.
                booking_url=(row.get("web_session_url") or "").strip()
                or STAR_CINEMAS_BOOKING_LANDING,
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


# Theaters whose backend systematically flips PM matinees to AM. Verified Jul 2026:
# Movies Havasu's marketing site AND its internet-ticketing booking system BOTH
# list Moana at "4:00 AM (ends 5:55 AM)" for a show that is really 4:00 PM (it
# fills the 2 PM→5 PM slate gap; Star Cinemas lists Moana only in the afternoon).
# The booking system is NOT an independent check here — it shares the flipped
# backend — so for these sources an implausible <9 AM showtime is AUTO-CORRECTED
# +12h and tagged, and the real matinee shows instead of being hidden. Every other
# source keeps the quarantine behavior (Star Cinemas + its 9:30 AM kids whitelist).
AUTO_CORRECT_SOURCES: frozenset[str] = frozenset({"movies_havasu"})
AUTO_CORRECTED_TAG = "auto_corrected"
# The theater's observed operating window — first show ~10 AM, last ~10 PM. A +12h
# flip is only trusted when the corrected time lands inside it; anything else is a
# sign the row isn't a simple PM-typed-as-AM matinee, so it quarantines instead.
OPERATING_OPEN = time(10, 0)
OPERATING_CLOSE = time(22, 0)


def _shift_12h(t: time) -> time:
    return (datetime.combine(datetime(2000, 1, 1), t) + timedelta(hours=12)).time()


def _autocorrect_target(t: time) -> time | None:
    """The +12h-corrected time for an implausibly-early auto-flip source's
    showtime, or ``None`` to quarantine instead. Two guards (Casey 2026-07-08):

    1. **Never flip the midnight hour** (12:00–12:59 AM): a real midnight premiere
       is legitimate, so it goes to review rather than becoming a noon show.
    2. **Sanity-bound the result** to the theater's operating window (~10 AM–10 PM):
       if +12h lands outside it, the row isn't a plain PM-matinee flip — quarantine.
    """
    if t.hour == 0:  # 12:00–12:59 AM — a legit midnight premiere, not a flip
        return None
    flipped = _shift_12h(t)
    if OPERATING_OPEN <= flipped <= OPERATING_CLOSE:
        return flipped
    return None


def showtime_record_is_suspect(r: ShowtimeRecord) -> bool:
    """A showtime too early to be real (before 9 AM) and not a whitelisted kids
    series — almost always a PM time entered as AM. The free summer kids series
    (``is_free``) is treated as a kids series regardless of title/tags. Public so
    the scraper's dry-run can report candidates before any write."""
    kids = r.is_free or is_kids_series(r.film_title, r.tags)
    return suspect_showtime(r.show_time, kids_series=kids)


def upsert_showtimes(db: Session, records: list[ShowtimeRecord]) -> dict[str, int]:
    """Idempotent upsert on ``(source, source_stable_id)``. Returns counts.

    Early-AM lint (WS6, extended to showtimes): a record before 9 AM is almost
    always an AM/PM flip (a 4 PM show typed "4 AM"). For a known-flipping source
    (:data:`AUTO_CORRECT_SOURCES`) it is AUTO-CORRECTED +12h in place, tagged
    ``auto_corrected`` and logged, so the real matinee still shows. For every
    other source it is QUARANTINED — dropped here, never written — so a flip can't
    reach /movies. The kids-series matinee is whitelisted from both; the midnight
    hour and out-of-operating-window flips also quarantine (see _autocorrect_target)."""
    kept: list[ShowtimeRecord] = []
    corrected: list[ShowtimeRecord] = []
    quarantined: list[ShowtimeRecord] = []
    for r in records:
        if not showtime_record_is_suspect(r):
            kept.append(r)
            continue
        target = _autocorrect_target(r.show_time) if r.source in AUTO_CORRECT_SOURCES else None
        if target is not None:
            old = r.show_time
            r.show_time = target
            if AUTO_CORRECTED_TAG not in r.tags:
                r.tags = [*r.tags, AUTO_CORRECTED_TAG]
            logger.warning(
                "auto-corrected AM/PM-flipped showtime (+12h): %r %s %s->%s @ %s",
                r.film_title, r.show_date.isoformat(), old.isoformat(),
                r.show_time.isoformat(), r.theater_name,
            )
            corrected.append(r)
            kept.append(r)
        else:
            logger.warning(
                "quarantined implausible showtime (before 9 AM — likely AM/PM flip): "
                "%r %s %s @ %s",
                r.film_title, r.show_date.isoformat(), r.show_time.isoformat(), r.theater_name,
            )
            quarantined.append(r)
    records = kept
    _counts_extra = {"quarantined": len(quarantined), "auto_corrected": len(corrected)}
    if not records:
        return {"created": 0, "updated": 0, **_counts_extra}
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
    return {"created": created, "updated": updated, **_counts_extra}


def prune_past(db: Session, *, before: date | None = None) -> int:
    """Delete showtimes whose date is strictly before ``before`` (default today).

    Keeps the table bounded to current/upcoming showings."""
    before = before or now_lake_havasu().date()
    result = db.execute(delete(MovieShowtime).where(MovieShowtime.show_date < before))
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def _hours(t: time) -> float:
    return t.hour + t.minute / 60.0


def cross_check_autocorrected(db: Session, *, tolerance_hours: float = 3.0) -> list[str]:
    """The free cross-check (Casey 2026-07-08): for each auto-corrected Movies
    Havasu showtime, if Star Cinemas shows the SAME film at a wildly different time
    pattern — the corrected time lands outside Star Cinemas' showtime window for
    that film, ± ``tolerance_hours`` — flag it. Star Cinemas has independent,
    unflipped Veezi data, so a mismatch means our +12h may be wrong. Returns
    human-readable flag lines for the nightly canary output (empty = all consistent).

    Only films Star Cinemas also carries are checkable; the rest can't be
    cross-checked and are silently skipped (never a false flag)."""
    from app.movies.queries import normalize_film_title

    auto = [
        r
        for r in db.scalars(
            select(MovieShowtime).where(MovieShowtime.theater_slug == "movies-havasu")
        ).all()
        if AUTO_CORRECTED_TAG in (r.tags or [])
    ]
    sc_by_film: dict[str, list[time]] = {}
    for s in db.scalars(
        select(MovieShowtime).where(MovieShowtime.theater_slug == "star-cinemas")
    ).all():
        sc_by_film.setdefault(normalize_film_title(s.film_title), []).append(s.show_time)

    flags: list[str] = []
    for r in auto:
        sc_times = sc_by_film.get(normalize_film_title(r.film_title))
        if not sc_times:
            continue  # not showing at Star Cinemas — no cross-check available
        lo, hi = min(_hours(t) for t in sc_times), max(_hours(t) for t in sc_times)
        if not (lo - tolerance_hours <= _hours(r.show_time) <= hi + tolerance_hours):
            flags.append(
                f"auto_corrected mismatch: {r.film_title!r} {r.show_date.isoformat()} "
                f"Movies Havasu -> {r.show_time.isoformat()} but Star Cinemas shows it "
                f"{min(sc_times).isoformat()}–{max(sc_times).isoformat()}"
            )
    return flags
