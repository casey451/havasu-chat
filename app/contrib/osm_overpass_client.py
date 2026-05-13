"""OpenStreetMap Overpass-QL Layer-2 client.

Lake Havasu bounding box per strategy memo §3.2:
  south=34.43, west=-114.41, north=34.59, east=-114.30

Phase 4.3 ships a single-category proof (default: leisure=dog_park).
Phase 5 fills additional categories per the strategy memo §3.2 category table.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

OSM_OVERPASS_LIMITER: Final = SourceLimiter("osm_overpass", qps=0.5)
OSM_OVERPASS_ENDPOINT: Final = "https://overpass-api.de/api/interpreter"
LHC_BOUNDING_BOX: Final = (34.43, -114.41, 34.59, -114.30)  # (south, west, north, east)


def build_query(tag: str, value: str) -> str:
    s, w, n, e = LHC_BOUNDING_BOX
    return f"""[out:json][timeout:60];
(
  node["{tag}"="{value}"]({s:.2f},{w:.2f},{n:.2f},{e:.2f});
  way["{tag}"="{value}"]({s:.2f},{w:.2f},{n:.2f},{e:.2f});
);
out body geom;
"""


class OsmOverpassClient(BaseIngestClient):
    """Layer-2 OSM Overpass discovery; enrichment is a no-op (full detail in discovery)."""

    source_name = "osm"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        tag = str(query.get("tag", "leisure"))
        value = str(query.get("value", "dog_park"))
        q = build_query(tag, value)
        try:
            with httpx.Client(timeout=90.0) as http:
                response = OSM_OVERPASS_LIMITER.call_with_retry(
                    lambda: http.post(OSM_OVERPASS_ENDPOINT, data={"data": q})
                )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning("osm_overpass.transport_error", extra={"error": str(exc)})
            return []
        if response.status_code != 200:
            return []
        try:
            elements = response.json().get("elements", [])
        except ValueError:
            return []
        out: list[RawHit] = []
        for el in elements:
            tags = el.get("tags") or {}
            if not tags.get("name"):
                continue
            hit = self._element_to_raw_hit(el)
            out.append(hit)
        return out

    def _element_to_raw_hit(self, el: dict[str, Any]) -> RawHit:
        tags = el.get("tags") or {}
        center = el.get("center") or {}
        lat = el.get("lat") or center.get("lat")
        lng = el.get("lon") or center.get("lon")
        return RawHit(
            source=self.source_name,
            source_stable_id=f"osm_{el.get('type')}_{el.get('id')}",
            name=str(tags.get("name", "")),
            lat=float(lat) if lat is not None else None,
            lng=float(lng) if lng is not None else None,
            raw={"element": el, "tags": tags},
        )

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        tags = hit.raw_hit.raw.get("tags") or {}
        category_slug = "outdoors-parks-trails"
        extensions: dict[str, Any] = {}
        wheelchair = tags.get("wheelchair")
        if wheelchair in ("yes", "limited"):
            extensions["ada_accessible"] = True
        elif wheelchair == "no":
            extensions["ada_accessible"] = False
        fee = tags.get("fee")
        if fee == "no":
            extensions["free"] = True
        elif fee == "yes":
            extensions["free"] = False
        return EntityPayload(
            name=hit.raw_hit.name,
            entity_type="place",
            lat=hit.raw_hit.lat,
            lng=hit.raw_hit.lng,
            category_slug=category_slug,
            source=self.source_name,
            extension_payloads=extensions,
        )
