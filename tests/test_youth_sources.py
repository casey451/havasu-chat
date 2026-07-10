"""WS12 youth/family connectors — USA BMX live scraper, recurring fixtures,
family filter, and the review-queue-first ("training wheels") rollout guarantee.

Salvaged + adapted from closed PR #302: the Toptracer "Family Night Golf"
fixtures were dropped (WS6 venue-hours-not-events), and the auto-approve
assertions were flipped — WS12 §4 mandates every connector row land PENDING for
review, not auto-publish (which is what #302 did).
"""

from __future__ import annotations

import json
from datetime import date, time
from types import SimpleNamespace

from app.contrib.approval_service import (
    _DEFAULT_AUTO_APPROVE_EVENT_SOURCES,
    _SCRAPE_EVENT_SOURCES,
    should_auto_approve_event,
)
from app.events.family_filter import is_family_event
from app.events.scrapers.havasu_youth import HavasuYouthClient
from app.events.scrapers.lhc_bmx import LhcBmxClient

TODAY = date(2026, 6, 12)  # a Friday (June 1 2026 is a Monday)

BMX_JSON = json.dumps(
    {
        "thisWeekEvent": [
            {
                "name": "Local Race SINGLE",
                "race_start_time": "ASAP",
                "race_begins_on": "2026-06-09T00:00:00.000Z",
                "signup_start_time": "6pm",
                "signup_end_time": "7pm",
                "series_race_type": "Local Race",
                "description": "<p>Tuesday Single Points</p>",
                "status": "RESULT",
                "track_id": 136,
                "race_id": 1,
            },
            {
                "name": "Clinic",
                "race_start_time": "6:30 PM",
                "race_begins_on": "2026-06-12T00:00:00.000Z",
                "signup_start_time": None,
                "series_race_type": "Clinic",
                "description": "",
                "status": "ACTIVE",
                "track_id": 136,
                "race_id": 2,
            },
        ],
        "upcomingEvent": [
            {
                "name": "Local Race",
                "race_start_time": "ASAP",
                "race_begins_on": "2026-06-16T00:00:00.000Z",
                "signup_start_time": "6pm",
                "signup_end_time": "7pm",
                "series_race_type": "Local Race",
                "description": "<p>Tuesday Racing</p>",
                "status": "ACTIVE",
                "track_id": 136,
                "race_id": 3,
            },
        ],
    }
)


def test_bmx_excludes_results_and_past(monkeypatch) -> None:
    client = LhcBmxClient()
    monkeypatch.setattr(client, "fetch_text", lambda url, **kw: BMX_JSON)
    hits = client.discover({"today": TODAY})
    # RESULT row (race_id 1, also in the past) is dropped; clinic + race remain.
    assert {h.raw["race_id"] for h in hits} == {2, 3}


def test_bmx_payload_times_and_title(monkeypatch) -> None:
    client = LhcBmxClient()
    monkeypatch.setattr(client, "fetch_text", lambda url, **kw: BMX_JSON)
    payloads = {p.name: p for p in client.run({"today": TODAY})}

    clinic = payloads["BMX Clinic"]
    assert clinic.start_time == time(18, 30)  # feed's explicit 6:30 PM kept
    assert clinic.start_date == date(2026, 6, 12)
    assert clinic.venue_name == "Lake Havasu City BMX"
    assert "bmx" in clinic.tags

    race = payloads["BMX Local Race"]
    assert race.start_time == time(19, 0)  # "ASAP" -> operator 7 PM default
    assert "Racing 8 PM" in race.description


def test_havasu_youth_idempotent_distinct_urls() -> None:
    hits = HavasuYouthClient().discover({"today": TODAY})
    assert hits
    # Every occurrence must carry a unique URL so each lands as its own row.
    urls = [h.source_stable_id for h in hits]
    assert len(urls) == len(set(urls))


def test_havasu_youth_known_occurrences() -> None:
    client = HavasuYouthClient()
    payloads = client.run({"today": TODAY})
    by_key = {(p.name, p.start_date): p for p in payloads}

    # 2026-06-12 is a Friday -> Rock & Bowl glow night.
    rb = by_key[("Rock & Bowl — Family Glow Bowling", date(2026, 6, 12))]
    assert rb.start_time == time(18, 0)
    assert rb.end_time == time(23, 0)
    assert rb.venue_name == "Havasu Lanes"

    # No payload may ship without a start time (ingest requires it).
    assert all(p.start_time is not None for p in payloads)


def test_havasu_youth_dropped_toptracer() -> None:
    """The Toptracer 'Family Night Golf' fixtures were removed (WS6: venue
    hours, not events). No payload may reference them."""
    payloads = HavasuYouthClient().run({"today": TODAY})
    assert not any("Toptracer" in (p.venue_name or "") for p in payloads)
    assert not any("Night Golf" in p.name for p in payloads)


def test_family_filter_keeps_youth_venues() -> None:
    for title in (
        "BMX Local Race",
        "Rock & Bowl — Family Glow Bowling",
        "Glow in the Park — All Ages",
        "Junior Jump Time (Ages 6 & Under)",
        "Cosmic Bowling",
        "Arcade Night at The Spot",
    ):
        assert is_family_event(title), title


def test_family_filter_still_vetoes_adult() -> None:
    assert not is_family_event("Sippin' with the Somm")
    assert not is_family_event("Adults Only Wine Tasting")
    assert not is_family_event("21+ Bar Crawl")
    assert not is_family_event(None)


def _fake_contribution(source: str) -> SimpleNamespace:
    """Minimal Contribution shape for should_auto_approve_event()."""
    return SimpleNamespace(
        entity_type="event",
        source=source,
        submission_name="BMX Local Race",
        event_date=date(2026, 6, 16),
        event_time_start=time(19, 0),
    )


def test_youth_connectors_are_review_queue_first(monkeypatch) -> None:
    """WS12 §4 rollout discipline: youth connectors NEVER auto-approve — every
    row lands pending for review (the opposite of PR #302's decision)."""
    monkeypatch.delenv("EVENT_AUTO_APPROVE_SOURCES", raising=False)
    for source in ("lhc_bmx", "havasu_youth"):
        assert source not in _DEFAULT_AUTO_APPROVE_EVENT_SOURCES
        assert not should_auto_approve_event(_fake_contribution(source))


def test_youth_connectors_stamp_provenance() -> None:
    """Approved youth rows still carry their source (dedup + analytics +
    per-connector freshness), even though they are review-gated."""
    assert "lhc_bmx" in _SCRAPE_EVENT_SOURCES
    assert "havasu_youth" in _SCRAPE_EVENT_SOURCES
