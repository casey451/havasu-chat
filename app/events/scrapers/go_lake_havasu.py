"""Go Lake Havasu Simpleview events (JSON-LD per detail page; Phase 9b)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

GO_LAKE_LIST_URL = "https://www.golakehavasu.com/events/"
GO_LAKE_BASE = "https://www.golakehavasu.com"


class GoLakeHavasuClient(EventIngestClient):
    source_name = "go_lake_havasu"
    scrape_source = "go_lake_havasu"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        html = self.fetch_text(GO_LAKE_LIST_URL)
        soup = BeautifulSoup(html, "html.parser")
        hits: list[RawHit] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not re.match(r"^/events/[^/]+/?$", href):
                continue
            url = urljoin(GO_LAKE_BASE, href)
            if url in seen:
                continue
            seen.add(url)
            name = a.get_text(strip=True) or href.rstrip("/").split("/")[-1]
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=url,
                    name=name,
                    raw={"list_url": url},
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        html = self.fetch_text(hit.source_stable_id)
        soup = BeautifulSoup(html, "html.parser")
        jld: dict[str, Any] | None = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Event":
                    jld = item
                    break
            if jld:
                break
        return EnrichedHit(raw_hit=hit, enriched={"json_ld": jld, "html": html})

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        jld = hit.enriched.get("json_ld")
        if not isinstance(jld, dict):
            raise ValueError(f"go_lake_havasu missing JSON-LD: {hit.raw_hit.source_stable_id}")
        title = str(jld.get("name") or hit.raw_hit.name).strip()
        start_raw = jld.get("startDate")
        end_raw = jld.get("endDate")
        start_dt = dateutil_parser.parse(str(start_raw)) if start_raw else None
        end_dt = dateutil_parser.parse(str(end_raw)) if end_raw else None
        if start_dt is None:
            raise ValueError(f"go_lake_havasu missing startDate: {hit.raw_hit.source_stable_id}")
        loc = jld.get("location")
        venue = None
        if isinstance(loc, dict):
            venue = loc.get("name") or loc.get("address")
        desc = str(jld.get("description") or "")
        url = str(jld.get("url") or hit.raw_hit.source_stable_id)
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
