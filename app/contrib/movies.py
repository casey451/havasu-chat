"""movies — showtimes for the two Lake Havasu theaters.

source-expansion #11. Movies Havasu (movieshavasu.com) runs the Webedia /
BoxOffice CMS (theater id ``X0QCN``, circuit ``101364``) and is JS-rendered, so
the path is its underlying webediamovies.pro JSON XHR rather than the HTML. Star
Cinemas (starcinemashavasu.com) is the second screen; if the Webedia JSON proves
unworkable from prod, the fallback is a showtimes aggregator
(showtimes.com / cinemaclock.com) covering BOTH theaters.

Kids' free summer movies: the schedule is confirmed on the Movies Havasu
**Facebook** page; the website may mirror it. If it is website-visible it is
parsed here and family-tagged (see ``tag_family_if_kids``). If it is
Facebook-only, it must NOT be scraped here — route it through the OpenClaw
facebook_scrape pipeline instead (Facebook is out of scope for this repo).

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the Webedia XHR endpoint + response shape are
parsed defensively (the JS-rendered XHR could not be sniffed from the sandbox);
confirm against a captured payload, or switch to the aggregator fallback.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.contrib.event_record import EventRecord, dedupe_within, parse_dt
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "movies"
MOVIES_HAVASU = {"name": "Movies Havasu", "theater_id": "X0QCN", "circuit": "101364"}
STAR_CINEMAS = {"name": "Star Cinemas Havasu 10", "theater_id": None, "circuit": None}

# Best-known Webedia BoxOffice showtimes JSON endpoint; override via env once the
# real XHR is captured from prod. NEEDS_PROD_VERIFY.
WEBEDIA_API_URL = os.environ.get(
    "MOVIES_WEBEDIA_API_URL",
    "https://www.webediamovies.pro/api/v1/theaters/X0QCN/showtimes",
)
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_KIDS_KEYWORDS = ("summer movie", "kids", "free family", "family film", "summer kids", "summer series")
_LIMITER = SourceLimiter("movies", qps=0.5)


def tag_family_if_kids(title: str, extra: str = "") -> list[str]:
    blob = f"{title} {extra}".lower()
    tags = ["movie", "showtime"]
    if any(kw in blob for kw in _KIDS_KEYWORDS):
        tags += ["family", "free-summer-movie"]
    return tags


def _iter_showtimes(movie: dict) -> list[dict]:
    for key in ("showtimes", "sessions", "times", "schedules"):
        v = movie.get(key)
        if isinstance(v, list):
            return [s for s in v if isinstance(s, dict)]
    return []


def parse_webedia_showtimes(payload: Any, *, theater_name: str) -> list[EventRecord]:
    """Map a Webedia-style showtimes payload to EventRecords (one per movie/day).

    Defensive about container + field names. Groups showtimes by movie + date and
    lists the individual times in the description.
    """
    if isinstance(payload, dict):
        movies = payload.get("movies") or payload.get("films") or payload.get("data") or []
    elif isinstance(payload, list):
        movies = payload
    else:
        movies = []

    by_movie_day: dict[tuple[str, Any], list[str]] = {}
    meta: dict[tuple[str, Any], dict] = {}
    for movie in movies:
        if not isinstance(movie, dict):
            continue
        title = (movie.get("title") or movie.get("name") or "").strip()
        if not title:
            continue
        for st in _iter_showtimes(movie):
            dt = parse_dt(st.get("datetime") or st.get("startsAt") or st.get("date_time"))
            if dt is None:
                d = st.get("date")
                t = st.get("time") or st.get("startTime")
                dt = parse_dt(f"{d} {t}") if d and t else parse_dt(d)
            if dt is None:
                continue
            key = (title, dt.date())
            by_movie_day.setdefault(key, []).append(dt.strftime("%I:%M %p").lstrip("0"))
            meta.setdefault(key, {"first": dt, "url": movie.get("url") or movie.get("link")})

    records: list[EventRecord] = []
    for (title, day), times in by_movie_day.items():
        info = meta[(title, day)]
        first = info["first"]
        records.append(
            EventRecord(
                source=SOURCE,
                title=title,
                start_date=day,
                start_time=first.time().replace(tzinfo=None),
                venue_name=theater_name,
                url=(info.get("url") or "").strip() or None,
                description="Showtimes: " + ", ".join(sorted(set(times))),
                tags=tag_family_if_kids(title),
            )
        )
    return dedupe_within(records)


def fetch_movies_havasu(*, client: httpx.Client | None = None) -> list[EventRecord]:
    """Fetch Movies Havasu showtimes via the Webedia JSON XHR."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(WEBEDIA_API_URL, timeout=30.0))
        if resp is None:
            raise RuntimeError("movies webedia fetch failed")
        resp.raise_for_status()
        return parse_webedia_showtimes(resp.json(), theater_name=MOVIES_HAVASU["name"])
    finally:
        if owns:
            c.close()
