"""Lake Havasu Chamber GrowthZone community calendar (Phase 9b)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

CHAMBER_LIST_URL = (
    "https://business.havasuchamber.com/community-event-calendar/"
    "Search?showpastevents=false"
)
CHAMBER_BASE = "https://business.havasuchamber.com"


class ChamberClient(EventIngestClient):
    source_name = "chamber"
    scrape_source = "chamber"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        html = self.fetch_text(CHAMBER_LIST_URL)
        soup = BeautifulSoup(html, "html.parser")
        hits: list[RawHit] = []
        seen: set[str] = set()
        for a in soup.select('a.gz-event-card-title[itemprop="url"], a[itemprop="url"].gz-event-card-title'):
            href = (a.get("href") or "").strip()
            if not href or "Details/" not in href:
                continue
            url = urljoin(CHAMBER_BASE, href)
            if url in seen:
                continue
            seen.add(url)
            name = (a.get_text() or "").strip()
            card = a.find_parent(class_=re.compile(r"gz-events-card"))
            start_meta = card.find("meta", itemprop="startDate") if card else None
            start_raw = start_meta.get("content") if start_meta else None
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=url,
                    name=name or url,
                    raw={"list_url": url, "start_raw": start_raw},
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        html = self.fetch_text(hit.source_stable_id)
        soup = BeautifulSoup(html, "html.parser")
        enriched: dict[str, Any] = {"html": html}

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") in ("Event", "http://schema.org/Event"):
                    enriched["json_ld"] = item
                    break
            if "json_ld" in enriched:
                break

        title_el = soup.select_one('h1.gz-pagetitle[itemprop="name"], h1[itemprop="name"]')
        if title_el:
            enriched["title"] = title_el.get_text(strip=True)
        sub = soup.select_one("h5.gz-subtitle")
        if sub:
            enriched["subtitle"] = sub.get_text(" ", strip=True)
        about = soup.select_one('.gz-event-description[itemprop="about"], [itemprop="about"]')
        if about:
            enriched["description"] = about.get_text(" ", strip=True)
        for meta in soup.find_all("meta", itemprop=True):
            prop = meta.get("itemprop")
            if prop in ("startDate", "endDate", "eventStatus"):
                enriched[str(prop)] = meta.get("content")

        return EnrichedHit(raw_hit=hit, enriched=enriched)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        data = hit.enriched
        jld = data.get("json_ld") if isinstance(data.get("json_ld"), dict) else {}
        title = (
            (jld.get("name") if jld else None)
            or data.get("title")
            or hit.raw_hit.name
        )
        title = str(title).strip()
        start_raw = jld.get("startDate") if jld else data.get("startDate") or hit.raw_hit.raw.get("start_raw")
        end_raw = jld.get("endDate") if jld else data.get("endDate")
        start_dt = dateutil_parser.parse(str(start_raw)) if start_raw else None
        end_dt = dateutil_parser.parse(str(end_raw)) if end_raw else None
        if start_dt is None:
            raise ValueError(f"chamber event missing start: {hit.raw_hit.source_stable_id}")
        desc = str(data.get("description") or jld.get("description") or "")
        loc = jld.get("location") if jld else None
        venue = None
        if isinstance(loc, dict):
            venue = loc.get("name") or loc.get("address")
        elif isinstance(loc, str):
            venue = loc
        url = str(jld.get("url") if jld else hit.raw_hit.source_stable_id)
        return EventPayload(
            name=title,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_dt.date(),
            end_date=end_dt.date() if end_dt else None,
            start_time=start_dt.time().replace(tzinfo=None),
            end_time=end_dt.time().replace(tzinfo=None) if end_dt else None,
            venue_name=str(venue).strip() if venue else None,
            description=desc,
            event_url=url,
            source_stable_url=hit.raw_hit.source_stable_id,
            category_slug="events",
        )


def parse_chamber_list_card_html(html: str) -> list[dict[str, str]]:
    """Test helper: extract list-card fields from Chamber HTML."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for a in soup.select('a.gz-event-card-title[itemprop="url"]'):
        card = a.find_parent(class_=re.compile(r"gz-events-card"))
        start_meta = card.find("meta", itemprop="startDate") if card else None
        out.append(
            {
                "title": a.get_text(strip=True),
                "url": a.get("href") or "",
                "startDate": (start_meta.get("content") if start_meta else "") or "",
            }
        )
    return out
