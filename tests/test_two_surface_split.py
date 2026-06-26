"""Two-surface calendar split (CALENDAR_TWO_SURFACE_SPEC_2026-06-25.md, Phase 2).

Surface routing is ``events_views._row_is_event``: True → Calendar (dated
happenings + themed specials + showtimes + civic), False → Places & Ongoing
(venue hours + recurring class rosters, browsed once). These tests pin the §7
worked examples on both surfaces.

* Calendar (``day_groups(events_only=True)``): a golf-course-hours row and a
  recurring class do NOT appear; a themed special (Cosmic / Rock & Bowl) lands
  in the new "Special sessions" group; a one-off market lands in Events; a civic
  meeting lands in Local Government; a senior special stays gated under Seniors.
* Places (``places_groups``): every row is ``_row_is_event`` False, de-duplicated
  to one per venue, grouped into Things to Do / Sports & Fitness / Seniors.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event
from app.home import events_views as ev
from app.main import app

_SRC = "_two_surface_probe"
_DAY = date(2099, 8, 17)  # far-future, deterministic; no auto-expiry


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe(db: Session):
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()
    yield
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()


def _add(
    db: Session,
    *,
    title: str,
    tags: list[str],
    recurring: bool = False,
    on: date = _DAY,
) -> None:
    db.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=on,
            start_time=time(18, 0),
            end_time=time(20, 0),
            location_name="Test Venue",
            location_normalized="test venue",
            description="x",
            event_url="https://example.com/e",
            tags=tags,
            status="live",
            source=_SRC,
            verified=True,
            is_recurring=recurring,
        )
    )
    db.commit()


def _calendar_titles(groups: list[dict]) -> dict[str, list[str]]:
    """{group_key: [row titles]} for a Calendar (events_only) day."""
    return {g["key"]: [r["title"] for r in g["rows"]] for g in groups}


# --- Calendar surface: only dated happenings render --------------------------


def test_golf_course_hours_absent_from_calendar(db: Session) -> None:
    _add(db, title="Lake Havasu Golf Club", tags=["activity:golf", "facet:hours"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    all_titles = [t for titles in _calendar_titles(groups).values() for t in titles]
    assert not any("Golf Club" in t for t in all_titles), all_titles


def test_recurring_class_absent_from_calendar(db: Session) -> None:
    _add(db, title="Vinyasa Flow Yoga", tags=["activity:yoga"], recurring=True)
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    all_titles = [t for titles in _calendar_titles(groups).values() for t in titles]
    assert not any("Yoga" in t for t in all_titles), all_titles


def test_cosmic_bowling_special_lands_in_special_sessions(db: Session) -> None:
    _add(db, title="Rock & Bowl Black-Light Night", tags=["activity:bowling", "facet:special"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    by_key = _calendar_titles(groups)
    assert "specials" in by_key, list(by_key)
    assert any("Rock & Bowl" in t for t in by_key["specials"])
    # ...and it is NOT left in the leisure Things-to-Do (events) group.
    assert not any("Rock & Bowl" in t for t in by_key.get("events", []))


def test_oneoff_market_lands_in_events(db: Session) -> None:
    _add(db, title="Lake Havasu Farmers Market", tags=["events"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    by_key = _calendar_titles(groups)
    assert any("Farmers Market" in t for t in by_key.get("events", [])), by_key


def test_civic_meeting_lands_in_local_government(db: Session) -> None:
    _add(db, title="City Council Meeting", tags=["civic", "government", "meeting"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    by_key = _calendar_titles(groups)
    assert any("Council" in t for t in by_key.get("civic", [])), by_key


def test_senior_special_stays_gated_under_seniors(db: Session) -> None:
    _add(db, title="Senior Center Holiday Luncheon", tags=["senior", "facet:special"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    by_key = _calendar_titles(groups)
    assert any("Luncheon" in t for t in by_key.get("seniors", [])), by_key
    # Gated: never cross-listed into Special sessions (spec §5.2).
    assert not any("Luncheon" in t for t in by_key.get("specials", []))


# --- Places & Ongoing surface ------------------------------------------------


def test_places_rows_are_all_non_events(db: Session) -> None:
    groups = ev.places_groups(db, today=date.today())
    for g in groups:
        assert all(not ev._row_is_event(r) for r in g["rows"]), g["key"]


def test_places_top_level_keys_and_order(db: Session) -> None:
    groups = ev.places_groups(db, today=date.today())
    keys = [g["key"] for g in groups]
    # Subset of the three Places top-levels, in spec §3 order; empties hidden.
    order = ["things-to-do", "sports-fitness", "seniors"]
    assert keys == [k for k in order if k in keys]


def test_places_dedupes_recurring_venue_to_one_row(db: Session) -> None:
    # Havasu Lanes posts curated hours every day in the window; Places shows it
    # once, not once per day.
    groups = {g["key"]: g for g in ev.places_groups(db, today=date.today())}
    ttd = groups.get("things-to-do")
    assert ttd is not None
    lanes = [r for r in ttd["rows"] if "Havasu Lanes" in (r["title"] or "")]
    assert len(lanes) == 1, [r["title"] for r in ttd["rows"]]


def test_places_top_key_mapping() -> None:
    assert ev._places_top_key("classes") == "sports-fitness"
    assert ev._places_top_key("seniors") == "seniors"
    for k in ("events", "water", "learn"):
        assert ev._places_top_key(k) == "things-to-do"


# --- Route smoke: the surface toggle + Places tab render ----------------------


def test_route_renders_surface_toggle_and_places_tab() -> None:
    with TestClient(app) as client:
        cal = client.get("/events-ui")
        places = client.get("/events-ui?view=places")
    assert cal.status_code == 200
    assert 'class="ev-surf"' in cal.text  # Calendar ⇄ Places toggle present
    assert places.status_code == 200
    assert "Places &amp; Ongoing" in places.text
    assert 'data-group="things-to-do"' in places.text or "No places listed" in places.text
