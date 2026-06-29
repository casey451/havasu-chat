"""Calendar taxonomy rebuild — Phase 2 (2026-06-25): surfaces read the activity
tag, not the title.

The day view now routes the non-fitness activities to their real bucket from the
canonical ``activity:<slug>`` signal (tag-first, classifier fallback):
arts/cooking/maker/learning → **learn** (Classes & Workshops), theater →
**music**, games → **events** (Things to Do). Seniors stays a GATED, EXCLUSIVE
group — a senior-tagged item appears under Seniors ONLY — and sub-splits
internally so it stays browsable. Fitness and non-activity rows are unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.activity_taxonomy import (
    LEARN_SUBGROUP_ORDER,
    SENIOR_SUBGROUP_ORDER,
    classify_senior_subgroup,
    split_learn_subgroups,
)
from app.home import events_views
from app.home.events_views import _occurrence_group_keys

_LHC = ZoneInfo("America/Phoenix")
_MONDAY = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)


def _add_recurring(db, *, title, start, loc, tags=None) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=_MONDAY.date(),
        start_time=start, end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url="https://example.com/e", tags=tags or [],
        status="live", source="test-taxo-p2", verified=True, is_recurring=True,
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


# ── routing (pure function) ───────────────────────────────────────────────────
def test_occurrence_group_keys_reroutes_nonfitness() -> None:
    # Casey 2026-06-29: a craft "class" leaves Fitness for its OWN top-level
    # Classes & Workshops group (learn bucket → "learn" primary), NOT Things to Do.
    assert _occurrence_group_keys(
        "classes", title="Stained Glass Painting", venue=None, activity=None,
        tags=["activity:arts"], is_senior=False,
    ) == ["learn"]
    # Cooking too.
    assert _occurrence_group_keys(
        "classes", title="Taco Cooking Class", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["learn"]
    # Theater → Music & Nightlife.
    assert _occurrence_group_keys(
        "events", title="SpongeBob Musical", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["music"]
    # All-ages games stay in Things to Do.
    assert _occurrence_group_keys(
        "events", title="Rowdy Bingo", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["events"]
    # Senior gate wins over everything (exclusive).
    assert _occurrence_group_keys(
        "classes", title="Laughing Yoga", venue="Senior Center", activity=None,
        tags=["senior"], is_senior=True,
    ) == ["seniors"]


def test_fitness_and_nonactivity_rows_unchanged() -> None:
    # Line Dancing is fitness dance, NOT the learn craft bucket.
    assert _occurrence_group_keys(
        "classes", title="Line Dancing", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["classes"]
    # A plain market is untouched.
    assert _occurrence_group_keys(
        "events", title="Farmers Market", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["events"]
    # A kids' craft lands once in the top-level Classes & Workshops group (learn)
    # and peels into its Youth child there.
    assert _occurrence_group_keys(
        "classes", title="Kids Cake Pop Maker", venue=None, activity=None,
        tags=None, is_senior=False,
    ) == ["learn"]


# ── learn sub-split ───────────────────────────────────────────────────────────
def test_split_learn_subgroups_orders_and_types() -> None:
    rows = [
        {"title": "Stained Glass", "tags": ["activity:arts"]},
        {"title": "Paint & Sip", "tags": ["activity:arts"]},
        {"title": "Taco Cooking Class", "tags": ["activity:cooking"]},
        {"title": "Cake Pop Maker", "tags": ["activity:maker"]},
        {"title": "Genealogy Seminar", "tags": ["activity:learning"]},
    ]
    subs = split_learn_subgroups(rows)
    assert [s["label"] for s in subs] == list(LEARN_SUBGROUP_ORDER)
    assert all(s["count"] == len(s["rows"]) for s in subs)


# ── seniors internal sub-split ────────────────────────────────────────────────
def test_classify_senior_subgroup() -> None:
    assert classify_senior_subgroup("Party Bridge") == "Games & Social"
    assert classify_senior_subgroup("Open Billiards") == "Games & Social"
    assert classify_senior_subgroup("Laughing Yoga") == "Fitness & Movement"
    assert classify_senior_subgroup("Open Arts & Crafts") == "Arts & Crafts"
    assert classify_senior_subgroup("Thursday Music Jam") == "Social, Music & Meals"
    assert classify_senior_subgroup("Community Lunch") == "Social, Music & Meals"
    assert classify_senior_subgroup("Christmas in July Luncheon") == "Special"
    assert classify_senior_subgroup(
        "Glow Bowl", tags=["facet:special"]
    ) == "Special"


# ── integration: senior items appear ONLY under Seniors ───────────────────────
def test_senior_items_are_exclusive_to_seniors() -> None:
    s = uuid.uuid4().hex[:6]
    pinochle = f"ZZ Pinochle {s}"
    yoga = f"ZZ Laughing Yoga {s}"
    billiards = f"ZZ Open Billiards {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_recurring(db, title=pinochle, start=time(10, 0),
                                   loc="Lake Havasu Senior Center", tags=["senior"]))
        eids.append(_add_recurring(db, title=yoga, start=time(9, 0),
                                   loc="Lake Havasu Senior Center", tags=["senior"]))
        eids.append(_add_recurring(db, title=billiards, start=time(11, 0),
                                   loc="Lake Havasu Senior Center", tags=["senior"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = _by_key(groups)
        seniors = by_key.get("seniors", set())
        for t in (pinochle, yoga, billiards):
            # present under Seniors...
            assert any(t in s2 for s2 in seniors), t
            # ...and NOWHERE in the public buckets (Games/Fitness/Funzone/Learn).
            for pub in ("events", "classes", "learn", "music", "family"):
                assert not any(t in s2 for s2 in by_key.get(pub, set())), (t, pub)
        # The Seniors group is sub-split internally and stays browsable.
        sgroup = next(g for g in groups if g["key"] == "seniors")
        assert sgroup.get("subgroups")
        labels = {s["label"] for s in sgroup["subgroups"]}
        assert labels <= set(SENIOR_SUBGROUP_ORDER)
        assert "Games & Social" in labels and "Fitness & Movement" in labels
    finally:
        _cleanup(eids)


# ── integration: a craft class lands in the top-level Classes & Workshops group ─
def test_craft_class_routes_to_classes_and_workshops() -> None:
    s = uuid.uuid4().hex[:6]
    glass = f"ZZ Stained Glass {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_recurring(db, title=glass, start=time(13, 0),
                                   loc="Havasu Art Guild", tags=["arts"]))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=_MONDAY.date(), now=_MONDAY)
        by_key = _by_key(groups)
        # Casey 2026-06-29: its OWN top-level "learn" group (Classes & Workshops),
        # NOT Fitness, NOT Things to Do.
        assert any(glass in t for t in by_key.get("learn", set()))
        assert not any(glass in t for t in by_key.get("events", set()))
        assert not any(glass in t for t in by_key.get("classes", set()))
        # And it renders as a real top-level group with that label.
        learn_group = next((g for g in groups if g["key"] == "learn"), None)
        assert learn_group is not None
        assert learn_group["label"] == "Classes & Workshops"
        # The craft splits into a typed subsection (Arts & Crafts) of the group.
        assert any(
            sub["label"] == "Arts & Crafts" for sub in learn_group.get("subgroups", [])
        )
    finally:
        _cleanup(eids)
