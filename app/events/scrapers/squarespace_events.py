"""Squarespace events-collection connector (WS12 C5).

Squarespace exposes any page's data as JSON by appending ``?format=json`` — no
API key. An *events* collection (``collection.typeName == "events-stacked"``)
returns its **upcoming** events in ``items``, each carrying ``startDate`` /
``endDate`` as epoch **milliseconds**, a ``fullUrl`` path, an ``excerpt`` /
``body``, and a ``location`` block. That is a clean, durable contract, so we
parse the JSON directly rather than hash-diffing the rendered page.

This module is generic on purpose: :class:`SquarespaceEventsClient` is the reusable
base (many Lake Havasu venues run on Squarespace — the History Museum, Grace Arts
Live), and each concrete venue is a tiny subclass that sets the events URL, the
default venue name/address, and the ``source_name``. First target: the Lake
Havasu Museum of History (:class:`HavasuMuseumClient`).

Timezone: Squarespace emits ``startDate`` as a UTC epoch; we convert to naive
America/Phoenix wall time, matching the ical-parse convention every other event
source uses. (Arizona has no DST, so this is unambiguous.) Rows are review-queue
gated regardless, so a mis-set site timezone is caught before publish.

Rollout (WS12 §4): NOT auto-approved — every row lands PENDING for review.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.core.timezone import LAKE_HAVASU_TZ
from app.events.scrapers.base import EventIngestClient, EventPayload, clean_venue_shape


def _epoch_ms_to_local(ms: Any) -> datetime | None:
    """UTC epoch-milliseconds -> naive America/Phoenix wall time, or None."""
    if not isinstance(ms, (int, float)):
        return None
    return (
        datetime.fromtimestamp(ms / 1000.0, tz=UTC)
        .astimezone(LAKE_HAVASU_TZ)
        .replace(tzinfo=None)
    )


def _squarespace_location(loc: dict[str, Any] | None) -> str | None:
    """Best single-line address from a Squarespace ``location`` block."""
    if not isinstance(loc, dict):
        return None
    parts = [
        str(loc.get(k)).strip()
        for k in ("addressLine1", "addressLine2")
        if str(loc.get(k) or "").strip()
    ]
    return ", ".join(parts) or None


class SquarespaceEventsClient(EventIngestClient):
    """Base for any Squarespace ``events-stacked`` collection.

    Subclasses set: :attr:`source_name`, :attr:`scrape_source`,
    :attr:`events_json_url`, :attr:`site_root`, :attr:`default_venue_name`, and
    optionally :attr:`default_address`.
    """

    events_json_url: str = ""
    site_root: str = ""
    default_venue_name: str = ""
    default_address: str | None = None

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today")
        if not isinstance(today, date):
            today = date.today()
        raw = json.loads(self.fetch_text(self.events_json_url, timeout=60.0))
        items = raw.get("items") if isinstance(raw, dict) else None
        hits: list[RawHit] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            start = _epoch_ms_to_local(it.get("startDate"))
            end = _epoch_ms_to_local(it.get("endDate"))
            if start is None:
                continue
            # An events collection returns upcoming items, but guard anyway: an
            # event whose (end or start) is already past must not be re-created.
            eff_end = end or start
            if eff_end.date() < today:
                continue
            full = str(it.get("fullUrl") or "").strip()
            link = urljoin(self.site_root, full) if full else self.site_root
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=link,
                    name=str(it.get("title") or "").strip(),
                    raw={
                        "title": str(it.get("title") or "").strip(),
                        "start_iso": start.isoformat(),
                        "end_iso": end.isoformat() if end else None,
                        "link": link,
                        "excerpt": str(it.get("excerpt") or ""),
                        "location": it.get("location"),
                    },
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        title = str(raw.get("title") or "").strip()
        if not title:
            raise ValueError(f"squarespace event missing title: {hit.raw_hit.source_stable_id}")
        start_dt = datetime.fromisoformat(str(raw["start_iso"]))
        end_iso = raw.get("end_iso")
        end_dt = datetime.fromisoformat(str(end_iso)) if end_iso else None
        link = str(raw.get("link") or hit.raw_hit.source_stable_id)
        venue = clean_venue_shape(
            _squarespace_location(raw.get("location")) or self.default_venue_name,
            description=str(raw.get("excerpt") or ""),
        ) or self.default_venue_name
        return EventPayload(
            name=title,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_dt.date(),
            end_date=end_dt.date() if end_dt else None,
            start_time=start_dt.time().replace(tzinfo=None),
            end_time=end_dt.time().replace(tzinfo=None) if end_dt else None,
            venue_name=venue,
            address=self.default_address,
            description=str(raw.get("excerpt") or ""),
            event_url=link,
            source_stable_url=link,
            category_slug="events",
        )


class HavasuMuseumClient(SquarespaceEventsClient):
    """Lake Havasu Museum of History — Squarespace events collection."""

    source_name = "havasu_museum"
    scrape_source = "havasu_museum"
    events_json_url = "https://www.havasumuseum.com/upcoming-events?format=json"
    site_root = "https://www.havasumuseum.com"
    default_venue_name = "Lake Havasu Museum of History"
    default_address = "320 London Bridge Rd, Lake Havasu City, AZ 86403"
