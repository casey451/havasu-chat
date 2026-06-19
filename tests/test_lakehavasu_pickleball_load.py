"""LHCPBA scraper: parse + payload + open-play events + decide_ingest funnel.

Run: python -m pytest tests/test_lakehavasu_pickleball_load.py -q

Mirrors tests/test_usapickleball_load.py: fixture-driven pure-parse tests, an
injected httpx.MockTransport client, and decide_ingest routing on a rollback
session. Open play is published as all-day events derived from the facility list
(no browser), so it is fully unit-testable.
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import httpx
import pytest

import scripts.lakehavasu_pickleball_load as loader
from app.contrib import lakehavasu_pickleball as lhc
from app.db.database import SessionLocal
from app.db.models import Event, Provider

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
    assert ev.all_day is False  # PickleFest is a timed event


def test_parse_tournaments_skips_past_event() -> None:
    specs = lhc.parse_tournaments(
        _fixture("lhcpba_tournaments.html"), today=date(2027, 6, 1)
    )
    assert specs == []


# --- open play -> all-day events --------------------------------------------
def test_open_play_event_specs_all_day_window() -> None:
    facs = [
        lhc.Facility(name="Mike Delaney Pickleball Complex at Dick Samp Park", cost="Free"),
        lhc.Facility(name="The Ark Center", cost="$5 per session"),
    ]
    specs = lhc.open_play_event_specs(facs, today=date(2026, 6, 18), window_days=3)
    assert len(specs) == 6  # 2 venues x 3 days
    assert all(s.all_day for s in specs)
    assert all(s.title.startswith("Pickleball Open Play") for s in specs)
    assert all(s.event_url == lhc.CALENDAR_URL for s in specs)
    assert all(s.source_anchor.startswith("openplay|") for s in specs)

    delaney_dates = sorted(
        s.date for s in specs if "Delaney" in s.location_name
    )
    assert delaney_dates == [date(2026, 6, 18), date(2026, 6, 19), date(2026, 6, 20)]
    # cost is surfaced in the description
    ark = next(s for s in specs if s.location_name == "The Ark Center")
    assert "$5 per session" in ark.description


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


# --- Aquatic-style merge into an existing row -------------------------------
def test_same_venue_matches_on_name_or_address() -> None:
    payload = lhc.facility_to_entity_payload(
        lhc.Facility(
            name="Lake Havasu City Aquatic Center",
            address="100 Park Ave, Lake Havasu City, AZ 86403",
        )
    )
    same = Provider(
        provider_name="Lake Havasu City Aquatic Center",
        address="100 Park Ave, Lake Havasu City, AZ 86403",
    )
    assert loader._same_venue(same, payload) is True
    other = Provider(provider_name="Unrelated Spot", address="999 Nowhere Rd")
    assert loader._same_venue(other, payload) is False


def test_merge_pickleball_into_is_additive_and_idempotent() -> None:
    payload = lhc.facility_to_entity_payload(
        lhc.Facility(name="Lake Havasu City Aquatic Center")
    )
    prov = Provider(provider_name="Lake Havasu City Aquatic Center")
    prov.description = "Public aquatic center with lap pool."
    loader._merge_pickleball_into(prov, payload)
    assert "pickleball" in prov.description.lower()
    assert prov.description.startswith("Public aquatic center")  # never clobbered
    once = prov.description
    loader._merge_pickleball_into(prov, payload)  # no double-append
    assert prov.description == once


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
        results = loader.run(dry_run=True, http_client=client, today=date(2026, 6, 18))
    assert results["facilities"]["found"] == 3
    assert results["programs"]["found"] == 3
    assert results["programs"]["imported"] == 3  # all specs build valid schemas
    # 1 PickleFest + (3 venues x 7-day open-play window) = 22 events
    assert results["events"]["found"] == 22
    assert results["events"]["imported"] == 22


def _evt(anchor: str, start: time, end: time | None = None) -> Event:
    return Event(
        title="Pickleball Open Play",
        normalized_title="pickleball open play",
        date=date(2026, 6, 20),
        start_time=start,
        end_time=end,
        location_name="Lake Havasu City Aquatic Center",
        location_normalized="lake havasu city aquatic center",
        description="x",
        source_url=f"https://www.lakehavasupickleball.com/calendar#{anchor}",
        tags=[],
    )


def test_prune_aquatic_allday_removes_legacy_rows_only(db_session) -> None:
    db = db_session
    db.add(_evt("openplay|Lake Havasu City Aquatic Center|2026-06-20", time(0, 0)))
    db.add(_evt("openplay|aquatic|2026-06-20|12:30", time(12, 30), time(15, 30)))
    db.add(_evt("openplay|The Ark Center|2026-06-20", time(0, 0)))
    db.commit()

    # dry-run reports the would-delete count but writes nothing
    assert loader.prune_aquatic_allday(db=db, dry_run=True) == 1
    assert db.query(Event).count() == 3

    # real run deletes only the legacy all-day Aquatic row
    assert loader.prune_aquatic_allday(db=db, dry_run=False) == 1
    remaining = {e.source_url.split("#", 1)[1] for e in db.query(Event).all()}
    assert "openplay|aquatic|2026-06-20|12:30" in remaining
    assert "openplay|The Ark Center|2026-06-20" in remaining
    assert all("openplay|Lake Havasu City Aquatic Center|" not in u for u in remaining)
