"""Go Lake Havasu Simpleview events (JSON-LD per detail page; Phase 9b)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.field_recovery import recover_event_fields
from app.events.scrapers.base import EventIngestClient, EventPayload, is_valid_venue_shape

GO_LAKE_LIST_URL = "https://www.golakehavasu.com/events/"
GO_LAKE_BASE = "https://www.golakehavasu.com"

# Tracking params that must be stripped from URLs at ingest (B-08): the Facebook
# click id and the full UTM family. They corrupt the canonical-URL identity used
# for cross-source dedup and add nothing for users.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})

# A streetAddress that leads with a number is a real street, not a venue label.
_STREET_NUMBER_LEAD = re.compile(r"^\d+\s")


def strip_tracking_params(url: str | None) -> str | None:
    """Drop fbclid / UTM (and friends) query params from a URL, preserving the rest.

    Returns the cleaned URL; a URL with no tracking params is returned unchanged
    (modulo normalization by urlsplit/urlunsplit). ``None``/empty -> ``None``.
    """
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    parts = urlsplit(s)
    if not parts.query:
        return s
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAM_EXACT
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


def _postal_address_parts(addr: Any) -> tuple[str | None, str | None]:
    """Split a JSON-LD ``location.address`` into ``(street, city)``.

    Accepts a ``PostalAddress`` dict or a plain string. For a dict, ``street`` is
    the ``streetAddress`` and ``city`` joins locality/region/postal. For a string
    there is no reliable split, so the whole value is returned as ``street``.
    """
    if isinstance(addr, str):
        s = addr.strip()
        return (s or None, None)
    if isinstance(addr, dict):
        street = str(addr.get("streetAddress")).strip() if addr.get("streetAddress") else None
        city_parts = [
            str(addr.get(k)).strip()
            for k in ("addressLocality", "addressRegion", "postalCode")
            if addr.get(k)
        ]
        city = ", ".join(city_parts) or None
        return (street or None, city)
    return (None, None)


def _postal_address_to_str(addr: Any) -> str | None:
    """Flatten a JSON-LD ``PostalAddress`` dict into a clean one-line string.

    Guards the ED-1 corruption: ``str(dict)`` previously dumped ``{'@type': ...}``
    into the venue field. A plain string address passes through unchanged.
    """
    street, city = _postal_address_parts(addr)
    parts = [p for p in (street, city) if p]
    return ", ".join(parts) or None


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
        ld_street = None
        if isinstance(loc, dict):
            # Parse the JSON-LD ``location`` into a structured venue + street/city.
            # NEVER fall back to the organizer block or the page footer -- only the
            # structured ``location`` (its ``name`` / ``address``) is authoritative.
            raw_venue = loc.get("name")
            # A description-shaped / dict-leaked ``location.name`` is rejected here
            # so it never reaches the venue field (B-08 / E-4).
            ld_desc = str(jld.get("description") or "")
            venue = (
                str(raw_venue).strip()
                if raw_venue and is_valid_venue_shape(str(raw_venue), description=ld_desc)
                else None
            )
            ld_street, _ = _postal_address_parts(loc.get("address"))
            ld_address = _postal_address_to_str(loc.get("address"))
            if not venue and ld_street and not _STREET_NUMBER_LEAD.match(ld_street):
                # A non-numeric streetAddress is often the venue label itself.
                venue = ld_street
        desc = str(jld.get("description") or "")
        url = strip_tracking_params(str(jld.get("url") or hit.raw_hit.source_stable_id))

        # ED-1: the authoritative venue/address often sits on a ``LOCATION:`` line
        # inside the description, and the description carries ingest noise. Run the
        # shared recovery pass so new rows land clean (and match the backfill).
        recovered = recover_event_fields(
            location_name=str(venue).strip() if venue else "",
            description=desc,
        )
        recovered_venue = (
            recovered.location_name if recovered.location_name != "Location TBD" else None
        )
        # Final shape gate: a recovered venue that is still description-shaped is
        # dropped to NULL rather than stored (never fabricate a venue).
        venue_name = (
            recovered_venue
            if recovered_venue and is_valid_venue_shape(recovered_venue, description=desc)
            else None
        )
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
            source_stable_url=strip_tracking_params(hit.raw_hit.source_stable_id),
            image_url=image_url,
            category_slug="events",
        )
