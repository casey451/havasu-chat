"""Go Lake Havasu Simpleview events (JSON-LD per detail page; Phase 9b)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.field_recovery import recover_event_fields
from app.events.scrapers.base import EventIngestClient, EventPayload

GO_LAKE_LIST_URL = "https://www.golakehavasu.com/events/"
GO_LAKE_BASE = "https://www.golakehavasu.com"


def _postal_address_to_str(addr: Any) -> str | None:
    """Flatten a JSON-LD ``PostalAddress`` dict into a clean one-line string.

    Guards the ED-1 corruption: ``str(dict)`` previously dumped ``{'@type': …}``
    into the venue field. A plain string address passes through unchanged.
    """
    if isinstance(addr, str):
        return addr.strip() or None
    if isinstance(addr, dict):
        parts = [
            str(addr.get(k)).strip()
            for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")
            if addr.get(k)
        ]
        return ", ".join(parts) or None
    return None


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
        ld_address = None
        if isinstance(loc, dict):
            # Prefer a real venue name; fall back to a *flattened* address string,
            # never str(dict) (the ED-1 PostalAddress dump).
            venue = loc.get("name")
            ld_address = _postal_address_to_str(loc.get("address"))
            if not venue:
                venue = ld_address
        desc = str(jld.get("description") or "")
        url = str(jld.get("url") or hit.raw_hit.source_stable_id)

        # ED-1: the authoritative venue/address often sits on a ``LOCATION:`` line
        # inside the description, and the description carries ingest noise. Run the
        # shared recovery pass so new rows land clean (and match the backfill).
        recovered = recover_event_fields(
            location_name=str(venue).strip() if venue else "",
            description=desc,
        )
        venue_name = recovered.location_name if recovered.location_name != "Location TBD" else None
        address = recovered.address or ld_address

        # ED-3: capture an event image — from a recovered ``Image:`` line, else the
        # JSON-LD ``image`` (string or {url}).
        ld_image = jld.get("image")
        if isinstance(ld_image, dict):
            ld_image = ld_image.get("url")
        image_url = recovered.image_url or (str(ld_image).strip() if ld_image else None)

        return EventPayload(
            name=title,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_dt.date(),
            end_date=end_dt.date() if end_dt else None,
            start_time=start_dt.time().replace(tzinfo=None),
            end_time=end_dt.time().replace(tzinfo=None) if end_dt else None,
            venue_name=venue_name,
            address=address,
            description=recovered.description,
            event_url=url,
            source_stable_url=hit.raw_hit.source_stable_id,
            image_url=image_url,
            category_slug="events",
        )
