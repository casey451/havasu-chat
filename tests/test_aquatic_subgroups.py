"""Aquatic Center subcategorization — Phase E §3.2, behind TAXONOMY_REORG_ENABLED.

The audit reframed the "fitness wall" as the ~101 Aquatic Center programs, so the
only place subcategories pay off is inside that one accordion group. With the flag
OFF the Aquatic Center group renders flat exactly as before (regression guard);
with the flag ON its rows split into the five §3.2 subsections, in canonical
order, with empty subsections omitted (honest-omission contract).

Two layers are tested: the pure ``_aquatic_subgroup`` classifier (cheap, exact),
and ``day_groups`` end-to-end with a monkeypatched flag (proves the wiring and
the flag gate). Patterns mirror tests/test_events_ui_views.py: far-future 2099
dates, uuid suffixes, targeted cleanup.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import events_views
from app.home.events_views import _aquatic_subgroup, day_groups

# --- (a) the pure classifier ------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Lap Swim", "Lap Swim"),
        ("Adult Lane Swim", "Lap Swim"),
        ("Free Swim Day", "Open & Family Swim"),
        ("Open Swim", "Open & Family Swim"),
        ("Splash Bash", "Open & Family Swim"),
        ("Aqua Aerobics", "Aqua Fitness"),
        ("Deep Water Fit", "Aqua Fitness"),
        ("Aqua Challenge", "Aqua Fitness"),
        ("Warm Water Yoga", "Warm-Water Yoga & Mind-Body"),
        ("Tai Chi", "Warm-Water Yoga & Mind-Body"),
        ("Water Wellness", "Warm-Water Yoga & Mind-Body"),
        ("Arthritis Class", "Gentle / Therapeutic"),
        ("Motion & Mobility", "Gentle / Therapeutic"),
        ("Fit & Flex", "Gentle / Therapeutic"),
        ("Pool Party", "More pool sessions"),  # no specific signal -> catch-all
    ],
)
def test_aquatic_subgroup_classifier(title: str, expected: str) -> None:
    assert _aquatic_subgroup(title) == expected


def test_specific_beats_broad_lap_before_aqua_fitness() -> None:
    # "Lap Swim" must win over the broad Aqua Fitness net even though both could
    # plausibly read as fitness; specificity order is load-bearing.
    assert _aquatic_subgroup("Morning Lap Swim") == "Lap Swim"
    # Word boundaries: "fit" inside "outfit" must NOT pull a row into a bucket.
    assert _aquatic_subgroup("Swimsuit Outfit Swap") != "Gentle / Therapeutic"


# --- (b) end-to-end through day_groups, gated on the flag --------------------


def _add(db, *, title: str, on: date, start: time, recurring: bool = True) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name="Aquatic Center",
        location_normalized="aquatic center",
        description="x",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test-aquatic-subgroups",
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def _aquatic_group(groups: list[dict]) -> dict | None:
    return next((g for g in groups if g["key"] == "aquatic"), None)


def test_flag_off_aquatic_group_is_flat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events_views, "taxonomy_reorg_enabled", lambda: False)
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 8, 4)
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=f"ZZ Adult Lap Swim {suffix}", on=day, start=time(5, 0)))
        eids.append(_add(db, title=f"ZZ Aqua Aerobics {suffix}", on=day, start=time(8, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            grp = _aquatic_group(day_groups(db, day=day))
        assert grp is not None
        assert "subgroups" not in grp  # flat, unchanged behaviour
        assert grp["count"] == 2
    finally:
        _cleanup(eids)


def test_flag_on_aquatic_group_splits_in_canonical_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(events_views, "taxonomy_reorg_enabled", lambda: True)
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 8, 5)
    # Each row carries an explicit pool word so it reaches the aquatic GROUP via
    # _event_tier's pool hints (group membership is title-keyword based, not
    # venue based — see the module's membership caveat), then distributes across
    # all five subsections. "Adult" vetoes the Kids & Family collector so the
    # swim rows stay in Aquatic Center.
    eids: list[str] = []
    with SessionLocal() as db:
        # Open & Family Swim
        eids.append(_add(db, title=f"ZZ Free Swim Day {suffix}", on=day, start=time(12, 0)))
        # Lap Swim
        eids.append(_add(db, title=f"ZZ Adult Lap Swim {suffix}", on=day, start=time(5, 0)))
        # Aqua Fitness (x2)
        eids.append(_add(db, title=f"ZZ Aqua Aerobics {suffix}", on=day, start=time(8, 0)))
        eids.append(_add(db, title=f"ZZ Aqua Challenge {suffix}", on=day, start=time(9, 0)))
        # Warm-Water Yoga & Mind-Body (pool word "Aqua" carries it into the group)
        eids.append(_add(db, title=f"ZZ Aqua Yoga {suffix}", on=day, start=time(10, 0)))
        # Gentle / Therapeutic ("Aquatics" carries it into the group)
        eids.append(_add(db, title=f"ZZ Arthritis Aquatics {suffix}", on=day, start=time(11, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            grp = _aquatic_group(day_groups(db, day=day))
        assert grp is not None
        subs = grp.get("subgroups")
        assert subs, "flag on must attach subgroups"
        labels = [s["label"] for s in subs]
        # Canonical order, empty subsections omitted (no "More pool sessions").
        assert labels == [
            "Open & Family Swim",
            "Lap Swim",
            "Aqua Fitness",
            "Warm-Water Yoga & Mind-Body",
            "Gentle / Therapeutic",
        ]
        by_label = {s["label"]: s for s in subs}
        assert by_label["Aqua Fitness"]["count"] == 2  # aerobics + deep water fit
        # Every row in the flat group is preserved across the split (no drops).
        assert sum(s["count"] for s in subs) == grp["count"]
    finally:
        _cleanup(eids)
