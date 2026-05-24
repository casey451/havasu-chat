"""Mohave County Library Trumba iCal feed (Phase 9b)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload
from app.events.scrapers.ical_parse import parse_ical_events

TRUMBA_ICAL_URL = "https://www.trumba.com/calendars/havasu.ics"


class LhcLibraryClient(EventIngestClient):
    source_name = "lhc_library"
    scrape_source = "lhc_library"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        text = self.fetch_text(TRUMBA_ICAL_URL, timeout=90.0)
        today = date.today()
        hits: list[RawHit] = []
        for ev in parse_ical_events(text):
            if ev.start.date() < today:
                continue
            uid = ev.uid.strip()
            link = ev.url or f"https://www.trumba.com/event/{uid}"
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=uid,
                    name=ev.summary,
                    raw={
                        "ical_uid": uid,
                        "link": link,
                        "location": ev.location,
                        "description": ev.description,
                        "start_iso": ev.start.isoformat(),
                        "end_iso": ev.end.isoformat() if ev.end else None,
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
        from dateutil import parser as dateutil_parser

        start_dt = dateutil_parser.parse(str(raw["start_iso"]))
        end_iso = raw.get("end_iso")
        end_dt = dateutil_parser.parse(str(end_iso)) if end_iso else None
        link = str(raw.get("link") or hit.raw_hit.source_stable_id)
        loc = str(raw.get("location") or "Lake Havasu City Library").strip()
        if loc.startswith(" - "):
            loc = loc[3:].strip()
        return EventPayload(
            name=hit.raw_hit.name,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_dt.date(),
            end_date=end_dt.date() if end_dt else None,
            start_time=start_dt.time().replace(tzinfo=None),
            end_time=end_dt.time().replace(tzinfo=None) if end_dt else None,
            venue_name=loc or "Mohave County Library — LHC Branch",
            description=str(raw.get("description") or ""),
            event_url=link,
            source_stable_url=link,
            category_slug="events",
        )
