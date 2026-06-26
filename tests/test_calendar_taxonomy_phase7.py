"""Calendar taxonomy — Phase 7 (2026-06-26): no Kids & Family overlay; youth as
an activity-specific sub-category; funzone venue-type cluster with real hours;
event-only auto-expand.

Casey 2026-06-26: remove the additive Kids & Family group. Every occurrence
appears once in its primary group; a kid-specific item peels into a "Youth
<activity>" sub-section there (youth BJJ → Fitness → Youth Martial Arts). All-ages
venues (bowling/arcade) stay in their venue-type sub, never youth. Sections open
by default only when they hold a real event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.activity_taxonomy import (
    split_class_subgroups,
    youth_subgroup_label,
)
from app.home import events_views
from app.home.events_views import _row_is_event

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


# ── youth label + paired split (pure) ─────────────────────────────────────────
def test_youth_subgroup_label() -> None:
    assert youth_subgroup_label("Martial Arts") == "Youth Martial Arts"
    assert youth_subgroup_label("Dance") == "Youth Dance"
    assert youth_subgroup_label("Arts & Crafts") == "Youth Arts & Crafts"
    # Residual / awkward bases collapse to a generic youth label.
    assert youth_subgroup_label("Around Town") == "Youth & Family"
    assert youth_subgroup_label("Other classes") == "Youth Classes"
    assert youth_subgroup_label("Comedy & Theater") == "Youth Theater"


def test_split_class_subgroups_pairs_adult_and_youth() -> None:
    rows = [
        {"title": "Adult BJJ", "venue": "Dojo", "youth": False},
        {"title": "Kids BJJ", "venue": "Dojo", "youth": True},
        {"title": "Ballet Beginnings", "activity": "Dance", "youth": True},
    ]
    subs = split_class_subgroups(rows)
    # Phase 1: youth NESTS as a child of its activity/discipline (no flat sibling).
    # Martial arts → (base) Martial Arts → Youth Martial Arts.
    ma = next(s for s in subs if s["label"] == "Martial arts")
    base = next(c for c in ma["children"] if c["label"] == "Martial Arts")
    assert {r["title"] for r in base["rows"]} == {"Adult BJJ"}
    assert [c["label"] for c in base["children"]] == ["Youth Martial Arts"]
    assert {r["title"] for r in base["children"][0]["rows"]} == {"Kids BJJ"}
    # A youth-only activity yields the activity parent (empty adult rows) with its
    # nested Youth child — e.g. Dance → Youth Dance.
    dance = next(s for s in subs if s["label"] == "Dance")
    assert dance["rows"] == []
    assert [c["label"] for c in dance["children"]] == ["Youth Dance"]


# ── auto-expand predicate ─────────────────────────────────────────────────────
def test_row_is_event_predicate() -> None:
    # Real events: a one-off happening, a themed special, a competition.
    assert _row_is_event({"title": "Classic Car Show", "tags": []})
    assert _row_is_event({"title": "Cosmic Bowling", "tags": ["activity:bowling", "facet:special"]})
    assert _row_is_event({"title": "Pool League", "tags": ["facet:competition"]})
    # Listings (never force-open): a class, venue hours, drop-in rec.
    assert not _row_is_event({"title": "Vinyasa Yoga", "tags": ["activity:yoga"]})
    assert not _row_is_event({"title": "Bowling — Lanes", "tags": ["activity:bowling", "facet:hours"]})
    assert not _row_is_event({"title": "Havasu Lanes", "ongoing": True, "tags": []})
    assert not _row_is_event({"title": "Open Swim", "tags": []})


# ── integration ───────────────────────────────────────────────────────────────
def _add(db, *, title, tags, loc="Venue", start=time(16, 0), recurring=True) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url=f"https://example.com/{uuid.uuid4().hex[:8]}",
        tags=tags, status="live", source="test-taxo-p7", verified=True, is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_no_family_group_and_youth_bjj_under_fitness_youth_sub() -> None:
    s = uuid.uuid4().hex[:6]
    kid_bjj = f"ZZ Kids Jiu Jitsu {s}"
    adult_bjj = f"ZZ Adult Jiu Jitsu {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=kid_bjj, tags=["youth"], loc="Bridge City BJJ"))
        eids.append(_add(db, title=adult_bjj, tags=[], loc="Bridge City BJJ"))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = {g["key"] for g in groups}
        assert "family" not in by_key  # no Kids & Family group exists
        classes = next(g for g in groups if g["key"] == "classes")

        def _collect(node: dict, acc: dict) -> None:
            acc.setdefault(node["label"], set()).update(
                r["title"] for r in node.get("rows", []) or []
            )
            for c in node.get("children", []) or []:
                _collect(c, acc)

        subs: dict = {}
        for sub in classes["subgroups"]:
            _collect(sub, subs)
        # Both appear once, in Fitness — the kid one NESTED into Youth Martial Arts
        # (Phase 1), the adult in the Martial Arts base; never duplicated.
        assert any(adult_bjj in t for t in subs.get("Martial Arts", set()))
        assert any(kid_bjj in t for t in subs.get("Youth Martial Arts", set()))
        assert not any(kid_bjj in t for t in subs.get("Martial Arts", set()))
    finally:
        _cleanup(eids)


def test_funzone_hours_show_real_times_and_collapse_when_no_event() -> None:
    # A day with only funzone venue hours (no real event): Things to Do shows the
    # venue-type subs with REAL hours (no "Time TBD"), and stays collapsed (hours
    # are listings, not events).
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
    events = next((g for g in groups if g["key"] == "events"), None)
    assert events is not None and events.get("subgroups")
    billiards = next((s for s in events["subgroups"] if s["label"] == "Billiards"), None)
    assert billiards is not None  # Mr. Lucky's is open daily
    assert all(r["time_label"] != "Time TBD" for r in billiards["rows"])
    # Mr. Lucky's daily 11 AM–11 PM shows a real range; In the Pocket → "Hours vary".
    labels = {r["time_label"] for r in billiards["rows"]}
    assert "Hours vary" in labels or any("11" in lbl for lbl in labels)
    # No real event on this synthetic day → the group is not auto-expanded.
    assert events["open"] is False


def test_golf_hours_read_hours_vary_not_time_tbd() -> None:
    s = uuid.uuid4().hex[:6]
    title = f"Golf Course — ZZ Links {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=title, tags=["activity:golf", "facet:hours", "venue-kind:course"],
                         start=time(0, 0), recurring=False))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        classes = next(g for g in groups if g["key"] == "classes")
        golf_rows = [r for sub in classes.get("subgroups", []) if sub["label"] == "Golf"
                     for r in sub["rows"]]
        row = next(r for r in golf_rows if title in r["title"])
        assert row["time_label"] == "Hours vary"  # never "Time TBD"
    finally:
        _cleanup(eids)
