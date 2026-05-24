"""RiverScene adapter wrapping Phase 4.x river_scene module (Phase 9b)."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.contrib.river_scene import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    fetch_and_parse_event,
    fetch_sitemap_urls,
)
from app.events.scrapers.base import EventIngestClient, EventPayload


class RiverSceneV2Client(EventIngestClient):
    """Thin EventIngestClient over existing RiverScene pull parsers."""

    source_name = "river_scene"
    scrape_source = "river_scene"

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today")
        if not isinstance(today, date):
            today = date.today()

        def _run(client: httpx.Client) -> list[RawHit]:
            urls = fetch_sitemap_urls(client=client)
            return [
                RawHit(
                    source=self.source_name,
                    source_stable_id=u.strip(),
                    name=u.rstrip("/").split("/")[-1],
                    raw={"url": u},
                )
                for u in urls
                if u and u.strip()
            ]

        if self._client is not None:
            return _run(self._client)
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            return _run(client)

    def enrich(self, hit: RawHit) -> EnrichedHit:
        today = date.today()

        def _run(client: httpx.Client) -> EnrichedHit:
            rse = fetch_and_parse_event(
                hit.source_stable_id, client=client, today=today
            )
            return EnrichedHit(raw_hit=hit, enriched={"rse": rse})

        if self._client is not None:
            return _run(self._client)
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            return _run(client)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        rse = hit.enriched.get("rse")
        if rse is None:
            raise ValueError(f"river_scene unparseable: {hit.raw_hit.source_stable_id}")
        from app.contrib.river_scene import _submission_public_url

        pub_url = _submission_public_url(rse)
        return EventPayload(
            name=rse.title,
            entity_type="event",
            source=self.scrape_source,
            start_date=rse.start_date,
            end_date=rse.end_date,
            start_time=rse.start_time,
            end_time=rse.end_time,
            venue_name=rse.venue_name,
            description=rse.description_html,
            event_url=pub_url,
            source_stable_url=hit.raw_hit.source_stable_id,
            tags=list(rse.category_slugs or []),
            category_slug="events",
        )
