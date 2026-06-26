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
from app.events import activity_taxonomy as at
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


# --- Phase 3: subcategory tree + collapse + empty-hiding ----------------------


def test_places_subcategories_collapsed_by_default(db: Session) -> None:
    groups = ev.places_groups(db, today=date.today())
    for g in groups:
        assert g.get("subgroups"), f"{g['key']} should have a subcategory split"
        for sub in g["subgroups"]:
            assert sub["open"] is False, (g["key"], sub["label"])
            assert sub["count"] > 0  # empty subsections are hidden (§5.3)


def _nested_labels(nodes: list[dict]) -> list[str]:
    """All labels in a subgroup/children tree, recursing the youth/discipline
    third level (Phase 1, 2026-06-26)."""
    out: list[str] = []
    for n in nodes:
        out.append(n["label"])
        out += _nested_labels(n.get("children", []) or [])
    return out


def test_places_sports_fitness_splits_by_activity(db: Session) -> None:
    groups = {g["key"]: g for g in ev.places_groups(db, today=date.today())}
    sf = groups.get("sports-fitness")
    assert sf is not None
    labels = _nested_labels(sf["subgroups"])
    # The curated youth studios (Universal Sonics gymnastics, Black Belt taekwondo)
    # recur into every 7-day window, so these activity subsections are always
    # present. Youth nests as a child now (Phase 1): Youth Gymnastics under
    # Gymnastics, Youth Taekwondo under Martial arts → Taekwondo.
    assert "Youth Gymnastics" in labels
    assert "Youth Taekwondo" in labels


def test_calendar_subcategories_collapsed_by_default(db: Session) -> None:
    # Two games happenings on one day make the events group split into the
    # "Games & Social" venue-type subsection; it must render collapsed (§5.3).
    for i in range(2):
        _add(db, title=f"Community Bingo Night {i} {_DAY.isoformat()}", tags=["events", "activity:games"])
    groups = ev.day_groups(db, day=_DAY, events_only=True)
    for g in groups:
        for sub in g.get("subgroups", []):
            assert sub["open"] is False, (g["key"], sub["label"])


def test_places_top_key_mapping() -> None:
    assert ev._places_top_key("classes") == "sports-fitness"
    assert ev._places_top_key("seniors") == "seniors"
    for k in ("events", "water", "learn"):
        assert ev._places_top_key(k) == "things-to-do"


# --- Phase 4: "For kids" filter on both surfaces ------------------------------


def test_for_kids_chip_present_and_toggles_on_unified_calendar() -> None:
    # UNIFY (Rule 0b 2026-06-26): one calendar, so the "For kids" chip is a single
    # cross-cutting narrow on it (no second Places surface to mirror).
    with TestClient(app) as client:
        cal = client.get("/events-ui").text
        cal_on = client.get("/events-ui?family=1").text
    assert 'class="ev-kids ' in cal and 'aria-pressed="false"' in cal
    assert 'class="ev-kids on"' in cal_on and 'aria-pressed="true"' in cal_on


def test_places_family_narrow_keeps_only_kid_rows(db: Session) -> None:
    groups = ev.places_groups(db, today=date.today(), family=True)
    from app.events.family_filter import is_family_event
    for g in groups:
        for r in g["rows"]:
            assert is_family_event(r.get("title"), r.get("tags"), r.get("venue")), r.get("title")


# --- Phase 5: martial arts discipline + youth split (§4.1) --------------------


def test_martial_discipline_is_data_driven_not_title() -> None:
    assert at.classify_martial_discipline({"discipline": "taekwondo"}) == "Taekwondo"
    assert at.classify_martial_discipline({"tags": ["discipline:bjj"]}) == "BJJ"
    # No discipline signal → undetermined (never guessed from the title).
    assert at.classify_martial_discipline({"title": "Kids Karate", "tags": []}) is None
    assert at.classify_martial_discipline({"tags": ["activity:martial-arts"]}) is None


def test_martial_arts_splits_by_discipline_with_youth() -> None:
    adult = [
        {"title": "Open Mat", "tags": ["discipline:bjj"]},
        {"title": "Adult Forms", "discipline": "taekwondo"},
        {"title": "Generic Self-Defense", "tags": []},  # undetermined → flat base
    ]
    youth = [
        {"title": "Kids BJJ", "tags": ["discipline:bjj"]},
        {"title": "Tiny Tigers", "discipline": "taekwondo"},
    ]
    # Phase 1: youth nests as a child of its discipline (not a flat sibling).
    facets = at.split_martial_arts_facets(adult, youth)
    assert [f["label"] for f in facets] == ["BJJ", "Taekwondo", "Martial Arts"]
    bjj, tkd, base = facets
    assert [c["label"] for c in bjj["children"]] == ["Youth BJJ"]
    assert [c["label"] for c in tkd["children"]] == ["Youth Taekwondo"]
    assert "children" not in base  # undetermined base has no youth here
    # Parent count = total descendants (adult + nested youth).
    assert bjj["count"] == 2 and tkd["count"] == 2 and base["count"] == 1


def test_untagged_martial_arts_stays_in_flat_base() -> None:
    subs = at.split_martial_arts_facets([{"title": "Martial Arts", "tags": []}], [])
    assert [s["label"] for s in subs] == ["Martial Arts"]


def test_curated_black_belt_academy_renders_youth_taekwondo(db: Session) -> None:
    groups = {g["key"]: g for g in ev.places_groups(db, today=date.today())}
    labels = _nested_labels(groups["sports-fitness"]["subgroups"])
    # The curated taekwondo dojo's youth classes nest under Martial arts →
    # Taekwondo → Youth Taekwondo (Phase 1).
    assert "Youth Taekwondo" in labels
    assert "Martial arts" in labels and "Taekwondo" in labels


# --- Phase 6: horseback removal (§6) ------------------------------------------


def test_horseback_removed_from_pageless_venue_map() -> None:
    from app.events.class_occurrences import _PAGELESS_VENUE_WEBSITES

    assert "havasu-horseback-rides" not in _PAGELESS_VENUE_WEBSITES


def test_deactivating_venue_stops_its_occurrences(db: Session) -> None:
    # The spec §6 data-layer op: deactivating the Entity (publish flag) stops its
    # Schedule occurrences from expanding onto either surface — without deleting.
    import uuid
    from datetime import UTC, datetime, time, timedelta

    from app.db.models import Entity, Schedule
    from app.events.class_occurrences import class_occurrences_in_window

    suf = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).replace(tzinfo=None)
    ent = Entity(
        entity_type="venue", slug=f"horseback-{suf}",
        name=f"Havasu Horseback Rides {suf}", source="test-two-surface", is_active=True,
    )
    db.add(ent)
    db.commit()
    db.add(
        Schedule(
            entity_id=ent.id, schedule_type="recurring", days_of_week=["wednesday"],
            start_time=time(10, 0), end_time=time(11, 0), notes=f"Pony Rides {suf}",
            created_at=now, updated_at=now,
        )
    )
    db.commit()
    win_start = date.today()
    win_end = win_start + timedelta(days=13)
    try:
        before = [
            o for o in class_occurrences_in_window(db, window_start=win_start, window_end=win_end)
            if suf in o.title
        ]
        assert before, "an active venue's recurring schedule should expand"
        ent.is_active = False
        db.commit()
        after = [
            o for o in class_occurrences_in_window(db, window_start=win_start, window_end=win_end)
            if suf in o.title
        ]
        assert after == [], "deactivated venue must produce no occurrences"
    finally:
        db.query(Schedule).filter(Schedule.entity_id == ent.id).delete()
        db.query(Entity).filter(Entity.id == ent.id).delete()
        db.commit()


# --- Route smoke: the surface toggle + Places tab render ----------------------


def test_places_toggle_retired_and_route_falls_through() -> None:
    # UNIFY (Rule 0b 2026-06-26): the Calendar⇄Places toggle and the ?view=places
    # surface are retired. The toggle is gone, and a legacy ?view=places link falls
    # through to the unified calendar (Today) rather than 404-ing.
    with TestClient(app) as client:
        cal = client.get("/events-ui")
        legacy = client.get("/events-ui?view=places")
    assert cal.status_code == 200
    assert 'class="ev-surf"' not in cal.text  # toggle removed
    assert "Places &amp; Ongoing" not in cal.text
    assert legacy.status_code == 200
    # Fell through to a normal calendar view (the Today/Week/Month tabs are shown).
    assert 'class="ev-seg"' in legacy.text
