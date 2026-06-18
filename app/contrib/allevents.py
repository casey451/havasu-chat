"""allevents — AllEvents.in Lake Havasu events via schema.org JSON-LD.

source-expansion #9. ~130 rolling events including bar/nightlife events no other
source has (Flying X Saloon, Sky Lounge, The Office). The city + this-weekend
pages carry schema.org Event JSON-LD.

High overlap with golakehavasu/RiverScene on marquee events, so records are
deduped on the normalised (title, start date, venue) key WITHIN the batch here,
and at ingestion route through the event contribution flow + events.dedup
(cross-source guard). Inert build-only module: fetch + parse only, no DB writes,
no orchestrator registration.
"""

from __future__ import annotations

import logging

import httpx

from app.contrib.event_record import EventRecord, dedupe_within, parse_jsonld_events
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "allevents"
CITY_URL = "https://allevents.in/lake-havasu-city"
WEEKEND_URL = "https://allevents.in/lake-havasu-city/this-weekend"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("allevents", qps=0.5)


def _decode_response(resp: httpx.Response) -> str:
    """Decode an httpx response as text, defaulting to UTF-8 (not latin-1).

    When the server declares an explicit charset in its Content-Type header we
    honor it. When it does not, httpx falls back to a guessed codec that
    corrupts multibyte/emoji characters (e.g. "💋" -> "?"), so we force UTF-8
    with replacement decoding instead.
    """
    if not resp.charset_encoding:
        return resp.content.decode("utf-8", errors="replace")
    return resp.text


def _fetch_html(url: str, client: httpx.Client) -> str:
    resp = _LIMITER.call_with_retry(lambda: client.get(url, timeout=30.0))
    if resp is None:
        raise RuntimeError(f"allevents fetch failed: {url}")
    resp.raise_for_status()
    return _decode_response(resp)


def fetch_events(
    *,
    include_weekend: bool = True,
    client: httpx.Client | None = None,
    enrich: bool = True,
) -> list[EventRecord]:
    """Fetch the city (+ this-weekend) pages and parse their JSON-LD events.

    When ``enrich`` is set (default), events that arrive with an empty or
    placeholder body have their real description pulled from the event's own
    AllEvents.in detail page (rate-limited via the shared source limiter), so
    listings such as "A-Z" or "Motor Madness" land with genuine text instead of a
    generic placeholder. Pass ``enrich=False`` for a pure index-only dry run."""
    owns = client is None
    c = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, follow_redirects=True
    )
    try:
        records = parse_jsonld_events(_fetch_html(CITY_URL, c), source=SOURCE)
        if include_weekend:
            records += parse_jsonld_events(_fetch_html(WEEKEND_URL, c), source=SOURCE)
        records = dedupe_within(records)
        if enrich:
            from app.contrib.event_enrich import enrich_event_records

            enrich_event_records(records, fetch_text=lambda u: _fetch_html(u, c), source=SOURCE)
    finally:
        if owns:
            c.close()
    return records
