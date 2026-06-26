"""Golf routes by venue type (Phase 2, 2026-06-26).

The golf-hours scraper publishes all-day rows tagged ``activity:golf`` +
``facet:hours`` + ``venue-kind:<course|range|simulator>``. The COURSES are
structured play → Sports & Fitness → "Golf — courses"; the indoor simulators and
the Top Tracer driving range are drop-in entertainment → Things to Do → "Golf —
simulators & Top Tracer" (Indoor simulators / Top Tracer driving range facets).
An explicit ingest/loader-stamped activity tag remains authoritative for the
non-golf fitness rows (drop-in rec excepted).
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import events_views
from app.home.events_views import _explicit_activity_bucket, _occurrence_group_keys

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


def test_explicit_activity_bucket_helper() -> None:
    assert _explicit_activity_bucket(["activity:golf", "facet:hours"]) == "classes"
    assert _explicit_activity_bucket(["activity:arts"]) == "learn"
    # No explicit tag → None (classifier-only rows are untouched by this path).
    assert _explicit_activity_bucket(["sports"]) is None
    assert _explicit_activity_bucket(None) is None


def test_golf_course_hours_route_to_fitness() -> None:
    # venue-kind:course → Sports & Fitness (structured play).
    assert _occurrence_group_keys(
        "events", title="Golf Course — Lake Havasu Golf Club", venue="Lake Havasu Golf Club",
        activity=None, tags=["activity:golf", "facet:hours", "venue-kind:course"],
        is_senior=False,
    ) == ["classes"]


def test_golf_sim_and_range_hours_route_to_things_to_do() -> None:
    # Phase 2: venue-kind:simulator / range → Things to Do (drop-in entertainment).
    assert _occurrence_group_keys(
        "events", title="Indoor Golf Simulators — Back Nine", venue="Back Nine Golf",
        activity=None, tags=["activity:golf", "facet:hours", "venue-kind:simulator", "indoor:true"],
        is_senior=False,
    ) == ["events"]
    assert _occurrence_group_keys(
        "events", title="Driving Range — Toptracer — Iron Wolf", venue="Iron Wolf Top Tracer Range",
        activity=None, tags=["activity:golf", "facet:hours", "venue-kind:range"],
        is_senior=False,
    ) == ["events"]


def test_pickleball_court_hours_move_to_fitness() -> None:
    # Phase 5 (Casey 2026-06-25): pickleball COURT HOURS carry a drop-in-rec title
    # ("…Open Play") but a venue-hours facet (facet:open-play) now overrides the
    # drop-in-rec exception → they move to Fitness & Sports → Pickleball.
    assert _occurrence_group_keys(
        "events", title="Pickleball Open Play – Ark Center", venue="The Ark Center",
        activity=None, tags=["activity:pickleball", "facet:open-play", "indoor:true"],
        is_senior=False,
    ) == ["classes"]


def test_bare_dropin_without_hours_facet_stays_things_to_do() -> None:
    # A bare drop-in (Open Gym) with a non-pickleball fitness tag but NO court/
    # venue-hours facet stays in Things to Do — only the venue-hours facets
    # override the drop-in-rec rule, so generic open gym/swim is unaffected.
    # (Pickleball is the one exception → Sports & Fitness; see the pickleball test.)
    assert _occurrence_group_keys(
        "events", title="Open Gym – Ark Center", venue="The Ark Center",
        activity=None, tags=["activity:strength-cardio"],
        is_senior=False,
    ) == ["events"]


def test_pickleball_open_play_stays_in_fitness() -> None:
    # Phase 4 exception (Casey 2026-06-26): "Open Play" is pickleball's normal
    # format, so a bare pickleball drop-in (no hours facet) still routes to Sports
    # & Fitness → Pickleball, NOT Things to Do.
    assert _occurrence_group_keys(
        "events", title="Pickleball Open Play – Ark Center", venue="The Ark Center",
        activity=None, tags=["sports", "activity:pickleball"],
        is_senior=False,
    ) == ["classes"]


def test_untagged_fitness_oneoff_unchanged() -> None:
    # A legacy row with NO explicit activity tag is not pulled into Fitness by
    # this path (classifier-only inference is unchanged).
    assert _occurrence_group_keys(
        "events", title="Yoga in the Park", venue=None, activity=None,
        tags=["community"], is_senior=False,
    ) == ["events"]


def _add(db, *, title, tags) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=time(0, 0), end_time=None, location_name="Iron Wolf",
        location_normalized="iron wolf", description="x",
        event_url="https://example.com/g", tags=tags, status="live",
        source="test-golf-route", verified=True, is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def test_golf_range_hours_render_under_things_to_do_golf_subgroup() -> None:
    # Phase 2: a Top Tracer range row renders in Things to Do → "Golf — simulators
    # & Top Tracer" → "Top Tracer driving range" (NOT Fitness).
    s = uuid.uuid4().hex[:6]
    title = f"Driving Range — Toptracer — Iron Wolf {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=title, tags=["activity:golf", "facet:hours", "venue-kind:range"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = {g["key"]: {r["title"] for r in g["rows"]} for g in groups}
        assert any(title in t for t in by_key.get("events", set()))
        assert not any(title in t for t in by_key.get("classes", set()))
        events = next(g for g in groups if g["key"] == "events")
        golf = next(sub for sub in events["subgroups"]
                    if sub["label"] == "Golf — simulators & Top Tracer")
        rng = next(c for c in golf["children"] if c["label"] == "Top Tracer driving range")
        assert any(title in r["title"] for r in rng["rows"])
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()
