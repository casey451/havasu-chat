"""Phase 9b — EventIngestClient + EventPayload."""

from __future__ import annotations

from datetime import date, time

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import (
    EventIngestClient,
    EventPayload,
    event_payload_to_contribution,
    normalize_event_title,
)


class _StubClient(EventIngestClient):
    source_name = "stub"

    def discover(self, query):
        return [
            RawHit(
                source="stub",
                source_stable_id="https://example.com/e/1",
                name="Stub Event",
                raw={},
            )
        ]

    def enrich(self, hit):
        return EnrichedHit(raw_hit=hit, enriched={})

    def dedupe_key(self, hit):
        return hit.source_stable_id

    def to_event_payload(self, hit):
        return EventPayload(
            name="Stub Event",
            start_date=date(2026, 6, 1),
            start_time=time(18, 0),
            event_url="https://example.com/e/1",
            source_stable_url="https://example.com/e/1",
            venue_name="Park",
        )


def test_event_payload_roundtrip_fields() -> None:
    p = EventPayload(
        name="Yoga",
        start_date=date(2026, 6, 2),
        end_date=date(2026, 6, 2),
        start_time=time(6, 0),
        end_time=time(7, 0),
        venue_name="Studio",
        tags=["wellness"],
        event_url="https://example.com/yoga",
        source_stable_url="https://example.com/yoga",
    )
    c = event_payload_to_contribution(p, scrape_source="chamber")
    assert c.entity_type == "event"
    assert c.event_date == date(2026, 6, 2)
    assert c.source == "chamber"


def test_normalize_event_title_strips_punctuation() -> None:
    assert normalize_event_title("AMI Trivia!!!") == "ami trivia"


def test_stub_client_run_isolated() -> None:
    payloads = _StubClient().run({})
    assert len(payloads) == 1
    assert payloads[0].name == "Stub Event"


def test_source_registry_keys() -> None:
    from app.events.scrapers import SOURCE_REGISTRY

    assert set(SOURCE_REGISTRY) == {
        "chamber",
        "go_lake_havasu",
        "river_scene",
        "lhc_library",
        "lhc_parks_rec",
        "star_cinemas",
    }
