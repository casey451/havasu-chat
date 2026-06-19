"""Star Cinemas (Lake Havasu City) showtimes — Veezi/Supabase feed (Phase 9b).

Star Cinemas' public site (https://starcinemashavasu.com) is a client-rendered
React app backed by a **public** Supabase REST API. A single request to the
``sessions`` table — joined to ``films``, ``screens`` and ``sites`` — returns
every upcoming showtime with full film metadata and a Veezi booking URL, so we
never have to render the page or scrape HTML.

Endpoint (anon key is the site's own public, read-only frontend key; RLS-gated):
    GET {SUPABASE_URL}/rest/v1/sessions?select=...&session_datetime=gte.<from>
        &order=session_datetime.asc
    headers: apikey / Authorization: Bearer <anon key>

Each session maps to one event (a single showtime). ``session_datetime`` is the
local Arizona wall-clock time (serialized with a ``+00:00`` suffix by Veezi); we
treat the naive components as the local show date/time, matching how the theater
renders it. Verified live 2026-06-19: 230 sessions / 8 films / 6-day window.

NOTE ON VOLUME: one theater emits ~200+ showtimes per refresh. These are tagged
``movie``/``showtime``/``star-cinemas`` and given ``category_slug="movies"`` so
the movies surface can filter them in and the general events feed can filter them
out. If the volume proves heavy for the contributions/events pipeline, the
follow-up is a dedicated ``movie_showtimes`` table (see the PR notes).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.contrib.river_scene import USER_AGENT
from app.events.scrapers.base import EventIngestClient, EventPayload

# Public Supabase project that backs starcinemashavasu.com. Both values are the
# site's own client-side configuration (the anon key is designed to ship in the
# browser bundle and is read-only behind row-level security). Overridable via env
# so we never hard-depend on a value that the theater might rotate.
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

# Default look-ahead window. The feed only carries the current play range
# anyway; we bound it defensively so a backfill of advance tickets can't balloon.
SHOWTIME_WINDOW_DAYS = 14

_SELECT = (
    "id,session_datetime,show_start,status,show_type,seating_type,is_sold_out,"
    "web_session_url,"
    "film:films(id,title,rating,genre,runtime,director,synopsis,poster_url,release_date),"
    "screen:screens(screen_name),"
    "site:sites(name,address,city,state,timezone)"
)

# Statuses that mean "do not publish this showtime".
_DEAD_STATUSES = {"cancelled", "canceled", "deleted", "closed", "hidden"}

STAR_CINEMAS_VENUE = "Star Cinemas"


def _parse_session_dt(value: str) -> datetime:
    """Parse ``session_datetime`` as a naive local datetime.

    Veezi serializes the local Arizona show time with a ``+00:00`` suffix; the
    wall-clock components are what the theater displays, so we drop the tzinfo
    rather than converting (which would shift every time by the UTC offset).
    """
    s = (value or "").strip().replace("Z", "+00:00")
    return datetime.fromisoformat(s).replace(tzinfo=None)


def _runtime_label(minutes: Any) -> str | None:
    try:
        mins = int(minutes)
    except (TypeError, ValueError):
        return None
    if mins <= 0:
        return None
    hours, rem = divmod(mins, 60)
    return f"{hours} hr {rem} min" if hours else f"{rem} min"


def _build_description(film: dict[str, Any], *, screen: str | None, show_type: str | None) -> str:
    rating = (film.get("rating") or "").strip()
    genre = (film.get("genre") or "").strip()
    runtime = _runtime_label(film.get("runtime"))
    meta_bits = [b for b in (rating, genre, runtime) if b]
    if show_type and show_type.strip().lower() not in {"public", ""}:
        meta_bits.append(show_type.strip())
    if screen:
        meta_bits.append(screen)
    meta = " · ".join(meta_bits)
    synopsis = (film.get("synopsis") or "").strip()
    return (f"{meta}\n\n{synopsis}" if meta and synopsis else (meta or synopsis)).strip()


class StarCinemasClient(EventIngestClient):
    """Star Cinemas showtimes via the theater's public Supabase ``sessions`` feed."""

    source_name = "star_cinemas"
    scrape_source = "star_cinemas"

    def _fetch_json(self, url: str, *, timeout: float = 60.0) -> Any:
        """GET a Supabase REST URL with the anon key, behind the retry envelope.

        Mirrors :meth:`EventIngestClient.fetch_text` (SSRF guard + ``with_retry``)
        but sends the Supabase auth headers and decodes JSON.
        """

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

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today: date = query.get("today") or date.today()
        window_days = int(query.get("window_days") or SHOWTIME_WINDOW_DAYS)
        frm = f"{today.isoformat()}T00:00:00"
        to = f"{(today + timedelta(days=window_days)).isoformat()}T23:59:59"
        url = (
            f"{STAR_CINEMAS_SUPABASE_URL}/rest/v1/sessions"
            f"?select={_SELECT}"
            f"&session_datetime=gte.{frm}"
            f"&session_datetime=lte.{to}"
            f"&order=session_datetime.asc"
        )
        rows = self._fetch_json(url)
        hits: list[RawHit] = []
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
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=sid,
                    name=title,
                    raw=row,
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        film = raw.get("film") or {}
        site = raw.get("site") or {}
        screen = (raw.get("screen") or {}).get("screen_name")
        start = _parse_session_dt(str(raw["session_datetime"]))
        venue = (site.get("name") or STAR_CINEMAS_VENUE).strip() or STAR_CINEMAS_VENUE
        booking_url = (raw.get("web_session_url") or "").strip()
        poster = (film.get("poster_url") or "").strip() or None

        tags = ["movie", "showtime", "star-cinemas"]
        show_type = (raw.get("show_type") or "").strip()
        if show_type and show_type.lower() != "public":
            tags.append(show_type.lower())
        if raw.get("is_sold_out"):
            tags.append("sold-out")

        return EventPayload(
            name=hit.raw_hit.name,
            entity_type="event",
            source=self.scrape_source,
            start_date=start.date(),
            start_time=start.time().replace(tzinfo=None),
            venue_name=venue,
            description=_build_description(film, screen=screen, show_type=show_type),
            event_url=booking_url or None,
            source_stable_url=booking_url or None,
            image_url=poster,
            tags=tags,
            category_slug="movies",
        )
