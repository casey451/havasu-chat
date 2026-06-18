"""LHCPBA scraper: parse + payload + calendar grouping + decide_ingest funnel.

Run: python -m pytest tests/test_lakehavasu_pickleball_load.py -q

Mirrors tests/test_usapickleball_load.py: fixture-driven pure-parse tests, an
injected httpx.MockTransport client, and decide_ingest routing on a rollback
session. The JS open-play calendar's grouping is unit-tested as a pure function
(no browser); the Playwright render layer is exercised only via workflow_dispatch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

import scripts.lakehavasu_pickleball_load as loader
from app.contrib import lakehavasu_pickleball as lhc
from app.contrib.lakehavasu_pickleball_calendar import (
    Occurrence,
    _match_venue,
    group_open_play,
    parse_clock,
)
from app.db.database import SessionLocal

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db_session():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _mock_client() -> httpx.Client:
    routes = {
        "/places-to-play": _fixture("lhcpba_places_to_play.html"),
        "/round-robin": _fixture("lhcpba_round_robin.html"),
        "/beginner-novice-pickleball-instruct-1": _fixture("lhcpba_beginner.html"),
        "/tournaments": _fixture("lhcpba_tournaments.html"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        for path, html in routes.items():
            if request.url.path == path:
                return httpx.Response(200, text=html)
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# --- facilities -------------------------------------------------------------
def test_parse_facilities_three_venues() -> None:
    facilities = lhc.parse_facilities(_fixture("lhcpba_places_to_play.html"))
    by_name = {f.name: f for f in facilities}
    assert set(by_name) == {
        "Mike Delaney Pickleball Complex at Dick Samp Park",
        "Lake Havasu City Aquatic Center",
        "The Ark Center",
    }

    delaney = by_name["Mike Delaney Pickleball Complex at Dick Samp Park"]
    assert delaney.lat == pytest.approx(34.523536)
    assert delaney.lng == pytest.approx(-114.3368359)
    assert "1628 Avalon Ave" in (delaney.address or "")
    assert delaney.address.endswith("AZ 86404")
    assert delaney.cost == "Free"
    assert delaney.outdoor_courts == 16
    assert delaney.indoor_courts is None

    aquatic = by_name["Lake Havasu City Aquatic Center"]
    assert aquatic.lat == pytest.approx(34.4660072)
    assert aquatic.cost == "$3 per session"
    assert "100 Park Ave" in (aquatic.address or "")

    ark = by_name["The Ark Center"]
    assert ark.lat == pytest.approx(34.4654605)
    assert ark.cost == "$5 per session"
    assert ark.indoor_courts == 3
    assert "2700 Jamaica Blvd" in (ark.address or "")


def test_facility_payload_source_category_legacy() -> None:
    facilities = lhc.parse_facilities(_fixture("lhcpba_places_to_play.html"))
    payload = lhc.facility_to_entity_payload(facilities[0])
    assert payload.source == "lakehavasu_pickleball"
    assert payload.entity_type == "place"
    assert payload.category_slug == "classes-sports-recreation"
    assert payload.legacy_category == "pickleball"
    assert payload.website == lhc.FACILITIES_URL
    assert "16 outdoor" in payload.description
    assert "Free" in payload.description


# --- activities -------------------------------------------------------------
def test_parse_round_robin_single_program() -> None:
    specs = lhc.parse_round_robin(_fixture("lhcpba_round_robin.html"))
    assert len(specs) == 1
    assert specs[0].title == "LHCPBA Round Robins"
    assert specs[0].cost == "Member-only event"
    assert specs[0].activity_category == "sports"
    assert len(specs[0].description) >= 20  # ProgramApprovalFields min


def test_parse_instruction_beginner_and_novice() -> None:
    specs = lhc.parse_instruction(_fixture("lhcpba_beginner.html"))
    titles = {s.title for s in specs}
    assert titles == {
        "LHCPBA Beginner Pickleball Lessons",
        "LHCPBA Novice Pickleball Clinics",
    }
    novice = next(s for s in specs if "Novice" in s.title)
    assert novice.cost == "$5 per session"
    assert novice.location_name == "The Ark Center"


# --- tournaments ------------------------------------------------------------
def test_parse_tournaments_future_picklefest() -> None:
    specs = lhc.parse_tournaments(
        _fixture("lhcpba_tournaments.html"), today=date(2026, 6, 18)
    )
    assert len(specs) == 1
    ev = specs[0]
    assert ev.title == "PickleFest 2027"
    assert ev.date == date(2027, 2, 26)
    assert ev.end_date == date(2027, 2, 28)
    assert ev.source_anchor == "picklefest-2027-02-26"


def test_parse_tournaments_skips_past_event() -> None:
    specs = lhc.parse_tournaments(
        _fixture("lhcpba_tournaments.html"), today=date(2027, 6, 1)
    )
    assert specs == []


# --- calendar grouping (pure) -----------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("8:00am", "08:00"),
        ("8 am", "08:00"),
        ("12:30 pm", "12:30"),
        ("6:30pm", "18:30"),
        ("12 am", "00:00"),
        ("noon-ish", None),
    ],
)
def test_parse_clock(text: str, expected: str | None) -> None:
    assert parse_clock(text) == expected


def test_match_venue_word_boundary() -> None:
    assert _match_venue("12:30 pm AC Round Robin")[0] == "Lake Havasu City Aquatic Center"
    assert _match_venue("8:00 am ARK Center")[0] == "The Ark Center"
    # "Park" must NOT match the "ark" keyword; "dick samp" should win.
    assert _match_venue("Dick Samp Park open play")[0].startswith("Mike Delaney")
    # "ac" inside "Isaac" must not produce a false Aquatic Center match.
    assert _match_venue("Isaac memorial gathering") is None


def test_group_open_play_collapses_recurring() -> None:
    occ = [
        Occurrence(title="8:00 am ARK Center", date=date(2026, 6, 1),
                   start_time="08:00", end_time="11:00", cost="$5 per session"),
        Occurrence(title="8:00 am ARK Center", date=date(2026, 6, 2), start_time="08:00"),
        Occurrence(title="9:00 am Aquatic Center", date=date(2026, 6, 2), start_time="09:00"),
    ]
    specs = group_open_play(occ)
    ark = next(s for s in specs if "Ark" in s.location_name and s.start_time == "08:00")
    assert ark.schedule_days == ["Monday", "Tuesday"]
    assert ark.cost == "$5 per session"
    assert ark.end_time == "11:00"
    assert "2700 Jamaica Blvd" in (ark.location_address or "")
    assert "open-play" in ark.tags
    aquatic = next(s for s in specs if "Aquatic" in s.location_name)
    assert aquatic.schedule_days == ["Tuesday"]
    assert aquatic.cost == "$3 per session"


# --- fetch via mock transport -----------------------------------------------
def test_fetch_facilities_via_mock() -> None:
    with _mock_client() as client:
        facilities = lhc.fetch_facilities(client=client)
    assert len(facilities) == 3


def test_fetch_activities_via_mock() -> None:
    with _mock_client() as client:
        specs = lhc.fetch_activities(client=client)
    assert len(specs) == 3  # 1 round robin + beginner + novice


# --- decide_ingest funnel ---------------------------------------------------
def test_facility_decide_insert_when_no_match(db_session) -> None:
    from app.contrib.scraper_ingest import decide_ingest

    payload = lhc.facility_to_entity_payload(
        lhc.Facility(name="Brand New Pickleball Barn ZZZ", lat=41.234567, lng=-120.876543)
    )
    d = decide_ingest(db_session, payload)
    assert d.action == "insert"
    assert d.should_hide is False


def test_ingest_facilities_unknown_category_raises(db_session) -> None:
    facilities = [lhc.Facility(name="Nowhere Courts ZZZ", lat=41.5, lng=-119.9)]
    with pytest.raises(ValueError):
        loader.ingest_facilities(
            facilities, db=db_session, category_slug="totally-bogus-slug-zzz", dry_run=False
        )


# --- schedule window (no fabricated midnight end) ---------------------------
@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("08:00", "11:00", ("08:00", "11:00")),
        ("08:00", None, ("08:00", "10:00")),  # derive +2h, not midnight
        (None, None, ("00:00", "00:00")),  # placeholder, zero-length
        ("23:30", None, ("23:30", "01:30")),  # wraps past midnight
        (None, "09:00", ("00:00", "09:00")),
    ],
)
def test_schedule_window_no_midnight_fabrication(start, end, expected) -> None:
    assert loader._schedule_window(start, end) == expected


# --- dry-run end-to-end smoke (parse + schema validation, no writes) --------
def test_run_dry_run_validates_all_sections() -> None:
    with _mock_client() as client:
        results = loader.run(
            dry_run=True, skip_calendar=True, http_client=client, today=date(2026, 6, 18)
        )
    assert results["facilities"]["found"] == 3
    assert results["programs"]["found"] == 3
    assert results["programs"]["imported"] == 3  # all specs build valid schemas
    assert results["events"]["found"] == 1
    assert results["events"]["imported"] == 1
