"""Calendar taxonomy rebuild — Phase 5 (2026-06-25): pickleball court-hours
restructure + the Bowling/Billiards/Family-Fun cluster under Things to Do.

Pickleball court hours move to Fitness & Sports → Pickleball and split into Court
Hours (Indoor/Outdoor) + Leagues & Competitions, tag-driven. The funzone venues'
hours surface as a Things-to-Do section, with Cosmic Bowling / Glow in the Park
as distinct ``facet:special`` destination events apart from the hours.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.contrib.lakehavasu_pickleball import pickleball_event_tags
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.activity_taxonomy import (
    EVENTS_SUBGROUP_ORDER,
    PB_COMPETITION_LABEL,
    PB_INDOOR_LABEL,
    PB_OUTDOOR_LABEL,
    classify_events_subgroup,
    classify_pickleball_facet,
    split_class_subgroups,
    split_events_subgroups,
)
from app.home import events_views

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


# ── pickleball loader tag helper ──────────────────────────────────────────────
def test_pickleball_event_tags() -> None:
    op = pickleball_event_tags("Pickleball Open Play – Ark Center", indoor=True)
    assert "activity:pickleball" in op and "facet:open-play" in op and "indoor:true" in op
    out = pickleball_event_tags("Pickleball Open Play – Dick Samp Park", indoor=False)
    assert "facet:open-play" in out and "indoor:false" in out
    rr = pickleball_event_tags("Pickleball Round Robin - Aquatic Center", indoor=True)
    assert "facet:competition" in rr and "facet:open-play" not in rr
    glow = pickleball_event_tags("GLOW Pickleball - Aquatic Center", indoor=True)
    assert "facet:special" in glow and "facet:open-play" not in glow
    fest = pickleball_event_tags("PickleFest 2027", indoor=False)
    assert "facet:competition" in fest


# ── pickleball facet split (pure) ─────────────────────────────────────────────
def test_classify_pickleball_facet() -> None:
    assert classify_pickleball_facet(["facet:open-play", "indoor:true"]) == PB_INDOOR_LABEL
    assert classify_pickleball_facet(["facet:open-play", "indoor:false"]) == PB_OUTDOOR_LABEL
    assert classify_pickleball_facet(["facet:open-play"]) == PB_OUTDOOR_LABEL  # default outdoor
    assert classify_pickleball_facet(["facet:competition"]) == PB_COMPETITION_LABEL
    assert classify_pickleball_facet(["activity:pickleball"]) == "Pickleball & Racquet"


def test_split_class_subgroups_expands_pickleball() -> None:
    rows = [
        {"title": "Pickleball Open Play – Ark Center",
         "tags": ["activity:pickleball", "facet:open-play", "indoor:true"]},
        {"title": "Pickleball Open Play – Dick Samp Park",
         "tags": ["activity:pickleball", "facet:open-play", "indoor:false"]},
        {"title": "PickleFest 2027",
         "tags": ["activity:pickleball", "facet:competition"]},
        {"title": "Pickleball Lessons", "tags": ["activity:pickleball"]},
    ]
    subs = split_class_subgroups(rows)
    labels = [s["label"] for s in subs]
    # The flat "Pickleball" subgroup is replaced by its facet subgroups, in order.
    assert PB_OUTDOOR_LABEL in labels
    assert PB_INDOOR_LABEL in labels
    assert PB_COMPETITION_LABEL in labels
    assert "Pickleball & Racquet" in labels
    assert "Pickleball" not in labels  # the bare label no longer renders
    assert labels.index(PB_OUTDOOR_LABEL) < labels.index(PB_INDOOR_LABEL)
    assert all(s["count"] == len(s["rows"]) for s in subs)


# ── Things-to-Do split (pure) ─────────────────────────────────────────────────
def test_classify_events_subgroup() -> None:
    assert classify_events_subgroup("Cosmic Bowling", ["activity:bowling", "facet:special"]) \
        == "Special Sessions"
    assert classify_events_subgroup("Bowling — Havasu Lanes", ["activity:bowling", "facet:hours"]) \
        == "Bowling, Billiards & Family Fun"
    assert classify_events_subgroup("Billiards — Mr. Lucky's", ["activity:billiards", "facet:hours"]) \
        == "Bowling, Billiards & Family Fun"
    assert classify_events_subgroup("Rowdy Bingo", ["activity:games"]) == "Games & Social"
    assert classify_events_subgroup("Farmers Market", None) == "Around Town"


def test_split_events_subgroups_orders_and_omits_empty() -> None:
    rows = [
        {"title": "Farmers Market", "tags": None},
        {"title": "Cosmic Bowling", "tags": ["activity:bowling", "facet:special"]},
        {"title": "Rowdy Bingo", "tags": ["activity:games"]},
        {"title": "Bowling — Havasu Lanes", "tags": ["activity:bowling", "facet:hours"]},
    ]
    subs = split_events_subgroups(rows)
    labels = [s["label"] for s in subs]
    assert labels == list(EVENTS_SUBGROUP_ORDER)  # all four present, in canonical order


# ── integration: pickleball indoor court hours land under Fitness → facet ──────
def _add(db, *, title, tags, start=time(0, 0), recurring=False) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name="Venue",
        location_normalized="venue", description="x",
        event_url="https://example.com/e", tags=tags, status="live",
        source="test-taxo-p5", verified=True, is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def _by_key(groups) -> dict[str, set[str]]:
    return {g["key"]: {r["title"] for r in g["rows"]} for g in groups}


def test_pickleball_court_hours_render_under_fitness_indoor_facet() -> None:
    s = uuid.uuid4().hex[:6]
    title = f"Pickleball Open Play – Ark Center {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=title,
                         tags=["activity:pickleball", "facet:open-play", "indoor:true"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = _by_key(groups)
        assert any(title in t for t in by_key.get("classes", set()))
        assert not any(title in t for t in by_key.get("events", set()))
        classes = next(g for g in groups if g["key"] == "classes")
        assert any(sub["label"] == PB_INDOOR_LABEL for sub in classes.get("subgroups", []))
    finally:
        _cleanup(eids)


def test_cosmic_bowling_is_special_not_folded_into_hours() -> None:
    s = uuid.uuid4().hex[:6]
    cosmic = f"Cosmic Bowling {s}"
    hours = f"Bowling — Havasu Lanes {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=cosmic, start=time(21, 0),
                         tags=["activity:bowling", "facet:special", "family"]))
        eids.append(_add(db, title=hours,
                         tags=["activity:bowling", "facet:hours", "family"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        events = next(g for g in groups if g["key"] == "events")
        subs = {sub["label"]: {r["title"] for r in sub["rows"]} for sub in events.get("subgroups", [])}
        # The cosmic night is a Special Session; the regular hours are the funzone
        # cluster — the two are distinct subsections, never merged.
        assert any(cosmic in t for t in subs.get("Special Sessions", set()))
        assert any(hours in t for t in subs.get("Bowling, Billiards & Family Fun", set()))
        assert not any(cosmic in t for t in subs.get("Bowling, Billiards & Family Fun", set()))
    finally:
        _cleanup(eids)


def test_plain_things_to_do_day_stays_flat() -> None:
    # A market-only day has no themed subsection, so Things to Do renders flat
    # (no subgroups) — the split is applied only when specialised content exists.
    s = uuid.uuid4().hex[:6]
    market = f"ZZ Farmers Market {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=market, start=time(9, 0), tags=["community"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        events = next(g for g in groups if g["key"] == "events")
        assert any(market in r["title"] for r in events["rows"])
        assert "subgroups" not in events
    finally:
        _cleanup(eids)
