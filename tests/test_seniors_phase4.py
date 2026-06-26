"""Phase 4 — Seniors parity: filter, /events-ui toggle, and chat senior intent.

Mirrors tests/test_events_ui_views.py seeding (far-future 2099 Monday, uuid
suffixes, ``app.home.router.now_lake_havasu`` monkeypatch, targeted cleanup).
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.senior_filter import is_senior_event
from app.home import calendar_view, events_views
from app.main import app

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


def _add_event(db, *, title, start, loc, tags=None) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url="https://example.com/e", tags=tags or [],
        status="live", source="test-seniors-p4", verified=True, is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


# --- senior_filter -----------------------------------------------------------


def test_is_senior_event_tag_and_venue_only() -> None:
    # Phase 4 / Q5 (Casey 2026-06-26): senior membership is by TAG or VENUE only —
    # NEVER a title keyword. The Seniors group is the gated Senior-Center surface.
    assert is_senior_event("Exercise Class", ["senior"]) is True
    assert is_senior_event("Generic Class", None, "Lake Havasu Senior Center") is True
    # Title keywords no longer gate: a public Aquatic-Center class whose title
    # merely contains arthritis / tai chi / water wellness stays OUT of Seniors.
    assert is_senior_event("Tai Chi for Balance") is False
    assert is_senior_event("Low-Impact Aerobics") is False
    assert is_senior_event("Water Wellness") is False
    assert is_senior_event("Arthritis Water Class", None, "Lake Havasu City Aquatic Center") is False
    # Ambiguous terms still don't imply seniors.
    assert is_senior_event("London Bridge Days") is False
    assert is_senior_event("Live Music at the Brewery") is False
    assert is_senior_event("Bunco Night") is False


def test_is_senior_event_decided_by_venue() -> None:
    # Provider/venue-aware (brief: "decide by provider + tags, not just the
    # literal word in the title"): a generically-named program at the Senior
    # Center is senior; the same generic title elsewhere is not.
    assert is_senior_event("Exercise Class", None, "Lake Havasu Senior Center") is True
    assert is_senior_event("Bunco", None, "Lake Havasu Senior Center") is True
    assert is_senior_event("Exercise Class", None, "Gold's Gym") is False


# --- day_groups seniors narrow ----------------------------------------------


def test_day_groups_seniors_narrows() -> None:
    s = uuid.uuid4().hex[:6]
    senior = f"ZZ Senior Stretch {s}"
    music = f"ZZ Live Band Night {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=senior, start=time(20, 0), loc="Senior Center",
                               tags=["senior"]))
        eids.append(_add_event(db, title=music, start=time(20, 30), loc="Bar", tags=["music"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), seniors=True, now=_MONDAY)
        titles = {r["title"] for g in groups for r in g["rows"]}
        assert any(senior in t for t in titles)
        assert not any(music in t for t in titles)
        # The narrowed view does not also build the cross-cutting overlays.
        assert not any(g["key"] in ("family", "seniors") for g in groups)
    finally:
        _cleanup(eids)


def _add_recurring(db, *, title, start, loc, tags) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url="https://example.com/e", tags=tags,
        status="live", source="test-seniors-p4", verified=True, is_recurring=True,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def test_senior_items_route_to_seniors_only_never_dual() -> None:
    # 2026-06-23 brief: EVERY senior item — social game AND senior fitness —
    # renders under Seniors and ONLY there. No dual-listing into Fitness &
    # classes (the live "Water Wellness" bug showed under both). This supersedes
    # the earlier "senior fitness stays dual" rule.
    s = uuid.uuid4().hex[:6]
    billiards = f"ZZ Open Billiards {s}"   # senior social game
    taichi = f"ZZ Tai Chi {s}"             # senior fitness (a real activity type)
    water = f"ZZ Water Wellness {s}"       # senior aquatic fitness
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_recurring(db, title=billiards, start=time(10, 0),
                                   loc="Senior Center", tags=["senior"]))
        eids.append(_add_recurring(db, title=taichi, start=time(9, 0),
                                   loc="Senior Center", tags=["senior"]))
        eids.append(_add_recurring(db, title=water, start=time(8, 0),
                                   loc="Lake Havasu City Aquatic Center", tags=["senior"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = {g["key"]: {r["title"] for r in g["rows"]} for g in groups}
        seniors = by_key.get("seniors", set())
        classes = by_key.get("classes", set())
        # All three appear under Seniors...
        for t in (billiards, taichi, water):
            assert any(t in s2 for s2 in seniors), t
        # ...and NONE of them is dual-listed in the adult Fitness & classes list.
        for t in (billiards, taichi, water):
            assert not any(t in s2 for s2 in classes), t
    finally:
        _cleanup(eids)


def test_nonfitness_class_routes_to_happening_today() -> None:
    # 2026-06-23: a recurring non-fitness "class" (dog obedience) has no fitness
    # activity type, so it files under Happening today — NOT a Fitness & classes
    # "Other classes" residue (which no longer exists).
    s = uuid.uuid4().hex[:6]
    dog = f"ZZ Dog Obedience {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_recurring(db, title=dog, start=time(10, 0),
                                   loc="Jack Hardie Park", tags=["adult"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = {g["key"]: {r["title"] for r in g["rows"]} for g in groups}
        assert any(dog in t for t in by_key.get("events", set()))
        assert not any(dog in t for t in by_key.get("classes", set()))
    finally:
        _cleanup(eids)


def test_kids_venue_class_lands_in_youth_sub() -> None:
    # A generically-named class at a kids-only venue is youth-flagged. With no
    # Kids & Family group (Casey 2026-06-26) it lands ONCE in its primary group
    # and peels into that group's Youth sub. An untyped "class" residue routes to
    # Things to Do, so it surfaces under Things to Do → Youth & Family.
    s = uuid.uuid4().hex[:6]
    enr = f"ZZ Enrichment Lab {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_recurring(db, title=enr, start=time(13, 0),
                                   loc="Desert Bloom Learning Center", tags=["adult"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = {g["key"]: {r["title"] for r in g["rows"]} for g in groups}
        # No "family" group exists any more.
        assert not by_key.get("family")
        assert any(enr in t for t in by_key.get("events", set()))
        assert not any(enr in t for t in by_key.get("classes", set()))
        events = next(g for g in groups if g["key"] == "events")

        def _walk(nodes: list[dict]) -> list[dict]:
            out: list[dict] = []
            for n in nodes:
                out.append(n)
                out += _walk(n.get("children", []) or [])
            return out

        # Phase 1: the youth residue nests as a "Youth & Family" CHILD under its
        # activity (Around Town), not a flat top-level sibling.
        youth = [n for n in _walk(events.get("subgroups", [])) if n["label"] == "Youth & Family"]
        assert youth and any(enr in r["title"] for r in youth[0]["rows"])
    finally:
        _cleanup(eids)


# --- /events-ui audience tabs removed (Item 4) ------------------------------


def test_events_ui_has_no_audience_tabs() -> None:
    """Item 4: the Kids & family / Seniors filter tabs are gone from /events-ui
    (the calendar already makes everything browsable). Chat senior intent is a
    separate behavior covered below."""
    with TestClient(app) as client:
        body = client.get("/events-ui?theme=lake").text
    assert 'class="ev-fam' not in body
    assert "ev-sen" not in body
    assert "Kids &amp; family" not in body


# --- chat senior intent (calendar_view) -------------------------------------


def test_calendar_parses_senior_intent() -> None:
    assert calendar_view.parse_calendar_query("what is there for seniors this week")["aud"] == "seniors"
    assert calendar_view.parse_calendar_query("older adults activities")["aud"] == "seniors"
    # A senior ask is a discovery query (routes to /calendar, not a directory leaf).
    assert calendar_view.is_discovery_query("things for seniors tonight") is True
    # Kids intent still resolves to kids (not regressed).
    assert calendar_view.parse_calendar_query("toddler story time")["aud"] == "kids"


def test_calendar_senior_query_narrows_and_shows_understood_chip() -> None:
    """Item 4: the manual audience toggle (seg_aud) is gone, but a senior ask
    typed in plain words still narrows the calendar and surfaces a removable
    "Seniors" understood-chip — chat senior intent is preserved."""
    s = uuid.uuid4().hex[:6]
    senior = f"ZZ Senior Bingo {s}"
    music = f"ZZ DJ Night {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=senior, start=time(20, 0), loc="Senior Center",
                               tags=["senior"]))
        eids.append(_add_event(db, title=music, start=time(20, 30), loc="Bar", tags=["music"]))
        db.commit()
    try:
        with SessionLocal() as db:
            vm = calendar_view.build_calendar(
                db, q="for seniors", today=_MONDAY.date(), now=_MONDAY
            )
        # No manual audience toggle in the view model anymore …
        assert "seg_aud" not in vm
        # … but the parsed senior intent narrows and shows a removable chip.
        assert any(c["label"] == "Seniors" for c in vm["chips"])
        all_titles = {it["title"] for col in vm["columns"] for it in col["entries"]}
        assert any(senior in t for t in all_titles)
        assert not any(music in t for t in all_titles)
    finally:
        _cleanup(eids)
