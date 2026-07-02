"""City of LHC CivicPlus calendar RSS/iCal (Phase 9b)."""

from __future__ import annotations

from datetime import date, time
from typing import Any

import feedparser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload
from app.events.scrapers.ical_parse import parse_ical_events

CIVIC_ICAL_URL = (
    "https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?catID=23&feed=calendar"
)
CIVIC_RSS_URL = "https://www.lhcaz.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml"
CIVIC_EVENT_BASE = "https://www.lhcaz.gov/Calendar.aspx"


class LhcParksRecClient(EventIngestClient):
    """CivicPlus city calendar (meetings + public events; weekly cadence)."""

    source_name = "lhc_parks_rec"
    scrape_source = "lhc_parks_rec"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        prefer_ical = bool(query.get("prefer_ical", True))
        today = date.today()
        hits: list[RawHit] = []
        if prefer_ical:
            try:
                text = self.fetch_text(CIVIC_ICAL_URL, timeout=90.0)
                for ev in parse_ical_events(text):
                    if ev.start.date() < today:
                        continue
                    eid = ev.uid.strip()
                    link = f"{CIVIC_EVENT_BASE}?EID={eid}"
                    hits.append(
                        RawHit(
                            source=self.source_name,
                            source_stable_id=link,
                            name=ev.summary,
                            raw={
                                "eid": eid,
                                "start_iso": ev.start.isoformat(),
                                "end_iso": ev.end.isoformat() if ev.end else None,
                                "location": ev.location,
                                "description": ev.description,
                                "link": link,
                            },
                        )
                    )
                if hits:
                    return hits
            except Exception:
                pass
        return self._discover_rss(today=today)

    def _discover_rss(self, *, today: date) -> list[RawHit]:
        text = self.fetch_text(CIVIC_RSS_URL, timeout=90.0)
        feed = feedparser.parse(text)
        hits: list[RawHit] = []
        for entry in feed.entries:
            link = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not link or not title:
                continue
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=link,
                    name=title,
                    raw={"rss": dict(entry)},
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        if "start_iso" in hit.raw:
            return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))
        return self._enrich_rss(hit)

    def _enrich_rss(self, hit: RawHit) -> EnrichedHit:
        import re

        from dateutil import parser as dateutil_parser

        entry = hit.raw.get("rss") or {}
        desc = entry.get("description") or ""
        date_m = re.search(r"Event date:</strong>\s*([^<]+)", desc, re.I)
        time_m = re.search(r"Event Time:\s*</strong>\s*([^<]+)", desc, re.I)
        loc_m = re.search(r"Location:</strong>\s*([^<]+)", desc, re.I)
        start_date = dateutil_parser.parse(date_m.group(1)).date() if date_m else None
        # No "Event Time" in the RSS description -> the 00:00 midnight sentinel
        # (is_time_tbd renders it as "Time TBD"). Never fabricate a 9 AM start —
        # the WP-4 contract is real times or an honest TBD.
        start_time = time(0, 0)
        end_iso = None
        if time_m:
            parts = time_m.group(1).split("-")
            if parts:
                start_time = dateutil_parser.parse(parts[0].strip()).time()
            if len(parts) > 1 and start_date:
                end_t = dateutil_parser.parse(parts[1].strip()).time()
                end_iso = f"{start_date.isoformat()}T{end_t.isoformat()}"
        enriched = {
            "start_iso": f"{start_date.isoformat()}T{start_time.isoformat()}"
            if start_date
            else None,
            "end_iso": end_iso,
            "location": loc_m.group(1).strip() if loc_m else "Lake Havasu City",
            "description": desc,
            "link": hit.source_stable_id,
            # ``hit`` IS the RawHit here (the enriched wrapper has .raw_hit;
            # this raw one has .name directly) — .raw_hit.name crashed every
            # RSS-fallback enrich with AttributeError.
            "cancelled": "(Canceled)" in hit.name,
        }
        return EnrichedHit(raw_hit=hit, enriched=enriched)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        from dateutil import parser as dateutil_parser

        raw = hit.enriched
        start_iso = raw.get("start_iso")
        if not start_iso:
            raise ValueError(f"lhc_parks_rec missing dates: {hit.raw_hit.source_stable_id}")
        start_dt = dateutil_parser.parse(str(start_iso))
        end_iso = raw.get("end_iso")
        end_dt = dateutil_parser.parse(str(end_iso)) if end_iso else None
        title = hit.raw_hit.name.replace("(Canceled)", "").strip()
        link = str(raw.get("link") or hit.raw_hit.source_stable_id)
        loc = str(raw.get("location") or "Lake Havasu City").strip()
        if loc.startswith(" - "):
            loc = loc[3:].strip()
        return EventPayload(
            name=title,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_dt.date(),
            end_date=end_dt.date() if end_dt else None,
            start_time=start_dt.time().replace(tzinfo=None),
            end_time=end_dt.time().replace(tzinfo=None) if end_dt else None,
            venue_name=loc,
            description=str(raw.get("description") or ""),
            event_url=link,
            source_stable_url=link,
            category_slug="events",
        )
