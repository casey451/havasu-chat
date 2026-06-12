"""Youth/family sources — USA BMX live scraper, recurring fixtures, family filter."""

from __future__ import annotations

import json
from datetime import date, time

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

    # 2026-06-15 is a Monday -> Toptracer night.
    tt = by_key[("Toptracer Range — Family Night Golf", date(2026, 6, 15))]
    assert tt.start_time == time(17, 0)
    assert "Toptracer" in tt.venue_name

    # No payload may ship without a start time (ingest requires it).
    assert all(p.start_time is not None for p in payloads)


def test_family_filter_keeps_youth_venues() -> None:
    for title in (
        "BMX Local Race",
        "Rock & Bowl — Family Glow Bowling",
        "Glow in the Park — All Ages",
        "Toptracer Range — Family Night Golf",
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
