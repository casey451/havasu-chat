"""eventbrite_orgs — Eventbrite organizer events (the public search API is dead).

source-expansion #12. The public Eventbrite search API was retired in 2020, but
``GET /v3/organizations/{id}/events/`` still works with a token. Seeded with
local organizers (Havasu Community Health Foundation, org 40584556073); add more
org IDs discovered during build.

Recurring worship-service listings are excluded (see ``WORSHIP_KEYWORDS``).
RELEVANCE GATE: the dry-run surfaces samples so Casey can judge Havasu-relevance;
the module is trivially removable.

Key handling (rule 5): the token is read from ``EVENTBRITE_API_TOKEN``. With no
token the fetcher logs once and returns ``[]`` (no HTTP). Never types/fetches a
real key value. Inert build-only module: fetch + parse only, no DB writes, no
orchestrator registration.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.contrib.event_record import EventRecord, dedupe_within, parse_dt
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "eventbrite_orgs"
API_BASE = "https://www.eventbriteapi.com/v3"
SEED_ORG_IDS: tuple[str, ...] = ("40584556073",)  # Havasu Community Health Foundation
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
WORSHIP_KEYWORDS = (
    "worship",
    "sunday service",
    "church service",
    "sabbath",
    "mass ",
    "holy mass",
    "bible study",
)
_LIMITER = SourceLimiter("eventbrite_orgs", qps=0.5)


def _token() -> str:
    return (os.environ.get("EVENTBRITE_API_TOKEN") or "").strip()


def _is_worship(name: str, description: str) -> bool:
    blob = f"{name} {description}".lower()
    return any(kw in blob for kw in WORSHIP_KEYWORDS)


def parse_events(payload: Any, *, org_id: str | None = None) -> list[EventRecord]:
    """Map an Eventbrite ``events`` array (expand=venue) to EventRecords."""
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return []
    records: list[EventRecord] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = ((ev.get("name") or {}).get("text") or "").strip()
        if not name:
            continue
        description = ((ev.get("description") or {}).get("text") or "").strip()
        if _is_worship(name, description):
            continue
        start = parse_dt((ev.get("start") or {}).get("local") or (ev.get("start") or {}).get("utc"))
        end = parse_dt((ev.get("end") or {}).get("local"))
        venue = ev.get("venue") or {}
        venue_name = (venue.get("name") or "").strip() or None if isinstance(venue, dict) else None
        addr_obj = venue.get("address") if isinstance(venue, dict) else None
        venue_addr = (addr_obj.get("localized_address_display") if isinstance(addr_obj, dict) else None)
        records.append(
            EventRecord(
                source=SOURCE,
                title=name,
                start_date=start.date() if start else None,
                start_time=start.time().replace(tzinfo=None) if start else None,
                end_date=end.date() if end else None,
                end_time=end.time().replace(tzinfo=None) if end else None,
                venue_name=venue_name,
                venue_address=venue_addr,
                url=(ev.get("url") or "").strip() or None,
                description=description or None,
                tags=["eventbrite", f"org:{org_id}"] if org_id else ["eventbrite"],
                raw={"id": ev.get("id")},
            )
        )
    return records


def fetch_org_events(org_id: str, *, client: httpx.Client) -> list[EventRecord]:
    token = _token()
    params = {"token": token, "expand": "venue", "status": "live", "order_by": "start_asc"}
    resp = _LIMITER.call_with_retry(
        lambda: client.get(f"{API_BASE}/organizations/{org_id}/events/", params=params, timeout=30.0)
    )
    if resp is None:
        raise RuntimeError(f"eventbrite org {org_id} fetch failed")
    resp.raise_for_status()
    return parse_events(resp.json(), org_id=org_id)


def fetch_events(*, org_ids: tuple[str, ...] | None = None, client: httpx.Client | None = None) -> list[EventRecord]:
    if not _token():
        logger.info("eventbrite_orgs.no_token — skipping (set EVENTBRITE_API_TOKEN)")
        return []
    org_ids = org_ids or SEED_ORG_IDS
    owns = client is None
    c = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, follow_redirects=True
    )
    records: list[EventRecord] = []
    try:
        for org_id in org_ids:
            records += fetch_org_events(org_id, client=c)
    finally:
        if owns:
            c.close()
    return dedupe_within(records)
