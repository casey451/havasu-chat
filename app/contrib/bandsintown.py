"""bandsintown — regional live-music events via the Bandsintown Events API.

source-expansion #10. Catches concerts nothing else covers: BlueWater (Parker)
and Laughlin casino shows. Events are tagged ``regional`` since they are outside
Lake Havasu City proper.

Key handling (rule 5): the app_id is read from ``BANDSINTOWN_APP_ID``. With no
app_id the fetcher logs once and returns ``[]`` (no HTTP), so a cron can call it
unconditionally. Never types/fetches a real key value.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the location-search response shape is parsed
defensively (sandbox could not exercise the API with a real app_id).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.contrib.event_record import EventRecord, dedupe_within, parse_dt
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "bandsintown"
SEARCH_URL = "https://rest.bandsintown.com/events/search"
DEFAULT_LOCATION = "lake havasu city, az"
DEFAULT_RADIUS_MI = 75
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("bandsintown", qps=0.5)


def _app_id() -> str:
    return (os.environ.get("BANDSINTOWN_APP_ID") or "").strip()


def parse_events(payload: Any) -> list[EventRecord]:
    """Map a Bandsintown events array to regional-tagged EventRecords."""
    if not isinstance(payload, list):
        return []
    records: list[EventRecord] = []
    for ev in payload:
        if not isinstance(ev, dict):
            continue
        lineup = ev.get("lineup")
        title = ev.get("title") or (lineup[0] if isinstance(lineup, list) and lineup else None)
        start = parse_dt(ev.get("datetime") or ev.get("starts_at"))
        if not title or start is None:
            continue
        venue = ev.get("venue") or {}
        venue_name = (venue.get("name") or "").strip() or None if isinstance(venue, dict) else None
        city = venue.get("city") if isinstance(venue, dict) else None
        region = venue.get("region") if isinstance(venue, dict) else None
        addr = ", ".join(p for p in (city, region) if p) or None
        url = ev.get("url") or ev.get("event_url")
        records.append(
            EventRecord(
                source=SOURCE,
                title=str(title).strip(),
                start_date=start.date(),
                start_time=start.time().replace(tzinfo=None),
                venue_name=venue_name,
                venue_address=addr,
                url=(url or "").strip() or None,
                description=(ev.get("description") or "").strip() or None,
                tags=["regional", "live-music"],
                raw={"id": ev.get("id")},
            )
        )
    return dedupe_within(records)


def fetch_events(
    *,
    location: str = DEFAULT_LOCATION,
    radius_mi: int = DEFAULT_RADIUS_MI,
    client: httpx.Client | None = None,
) -> list[EventRecord]:
    app_id = _app_id()
    if not app_id:
        logger.info("bandsintown.no_app_id — skipping (set BANDSINTOWN_APP_ID)")
        return []
    params = {"app_id": app_id, "location": location, "radius": str(radius_mi)}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(SEARCH_URL, params=params, timeout=30.0))
        if resp is None:
            raise RuntimeError("bandsintown fetch failed")
        resp.raise_for_status()
        return parse_events(resp.json())
    finally:
        if owns:
            c.close()
