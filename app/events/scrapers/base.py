"""Event ingest clients extending Phase 4 BaseIngestClient (Phase 9b)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time

import httpx

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload
from app.contrib.river_scene import USER_AGENT
from app.db import contribution_store as cs
from app.schemas.contribution import ContributionCreate, ContributionSource


@dataclass
class EventPayload(EntityPayload):
    """EntityPayload specialized for entity_type='event' ingest."""

    entity_type: str = "event"
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_entity_id: str | None = None
    rrule: str | None = None
    tags: list[str] = field(default_factory=list)
    event_url: str | None = None
    description: str = ""
    source_stable_url: str | None = None
    image_url: str | None = None


class EventIngestClient(BaseIngestClient):
    """Event-source scraper base."""

    scrape_source: str = "operator_backfill"

    def to_entity_payload(self, hit: EnrichedHit) -> EventPayload:  # type: ignore[override]
        return self.to_event_payload(hit)

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raise NotImplementedError

    def fetch_text(
        self,
        url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> str:
        """GET URL as text with with_retry envelope."""

        def _inner() -> str:
            c = client
            owns = False
            if c is None:
                c = httpx.Client(
                    timeout=timeout,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
                owns = True
            try:
                r = c.get(url, timeout=timeout)
                r.raise_for_status()
                return r.text
            finally:
                if owns:
                    c.close()

        from app.core.background import with_retry

        result = with_retry(_inner, max_attempts=3)
        if result is None:
            raise RuntimeError(f"fetch failed for {url}")
        return result


def normalize_event_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def event_payload_to_contribution(
    payload: EventPayload,
    *,
    scrape_source: str,
) -> ContributionCreate:
    """Map :class:`EventPayload` to contributions queue row."""
    url = (payload.event_url or payload.source_stable_url or "").strip()
    if not url:
        raise ValueError("event payload requires event_url or source_stable_url")
    if not payload.start_date or not payload.start_time:
        raise ValueError("event payload requires start_date and start_time")
    name = (payload.name or "").strip()
    if not name:
        raise ValueError("event payload requires name")
    notes = (payload.description or "").strip()
    if payload.venue_name:
        notes = f"Venue: {payload.venue_name}\n\n{notes}".strip()
    src: ContributionSource = scrape_source  # type: ignore[assignment]
    return ContributionCreate(
        entity_type="event",
        submission_name=name,
        submission_url=url,
        source_url=cs.normalize_submission_url(url),
        submission_category_hint=scrape_source,
        submission_notes=notes or None,
        event_date=payload.start_date,
        event_end_date=payload.end_date,
        event_time_start=payload.start_time,
        event_time_end=payload.end_time,
        source=src,
    )


__all__ = [
    "EventIngestClient",
    "EventPayload",
    "event_payload_to_contribution",
    "normalize_event_title",
]
