"""Regression guards for the 2026-06-27 Ask Hava data-quality fixes.

Covers the behavior-bearing pieces of docs/ASKHAVA_DATA_FIXES_2026-06-27.md:
  * Task 3 — scripts/dedup_glow_in_the_park_2026_06_27.py deletes the one-off
    "Glow in the Park" collision and keeps the recurring "- All Ages" series.
  * Task 4 — the gym rows added to docs/scraper/captured_class_schedules.json
    classify into the Fitness & Sports "Strength & Cardio" subgroup.
  * Task 2 — scripts/merge_havasu_lanes_2026_06_27.py folds the duplicate
    provider rows into the keeper and relabels the bowling events to one name.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, time
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Event, Provider
from app.db.seed_helpers import derive_provider_slug
from app.events.activity_taxonomy import classify_class_subgroup, provider_activity_label

_ROOT = Path(__file__).resolve().parents[1]
_DATASET = _ROOT / "docs" / "scraper" / "captured_class_schedules.json"
_GYMS = {"Havasu CrossFit", "Fit Lab 928", "Feelin' Good Fitness"}


# --------------------------------------------------------------------------- #
# Task 4 — dataset classification guard (pure)                                 #
# --------------------------------------------------------------------------- #
def test_gym_schedule_rows_classify_as_strength_and_cardio() -> None:
    data = json.loads(_DATASET.read_text(encoding="utf-8"))
    gyms = [v for v in data["venues"] if v["provider_name"] in _GYMS]
    assert {v["provider_name"] for v in gyms} == _GYMS, "all three gyms must be present"

    for venue in gyms:
        pa = provider_activity_label(venue["provider_name"])
        assert venue["classes"], f"{venue['provider_name']} has no classes"
        for cls in venue["classes"]:
            label = classify_class_subgroup(cls["title"], venue["location_name"], pa)
            assert label == "Strength & Cardio", (
                f"{venue['provider_name']} / {cls['title']!r} -> {label!r}"
            )


def test_gym_schedule_rows_pin_entity_ids() -> None:
    """Pinned entity_id avoids the fuzzy name match that has mis-homed classes."""
    data = json.loads(_DATASET.read_text(encoding="utf-8"))
    for venue in data["venues"]:
        if venue["provider_name"] in _GYMS:
            assert venue.get("entity_id"), f"{venue['provider_name']} must pin entity_id"
            # Full UUID, not the truncated 8-char form.
            assert len(venue["entity_id"]) == 36


# --------------------------------------------------------------------------- #
# Task 3 — glow-in-the-park dedup script                                       #
# --------------------------------------------------------------------------- #
def _seed_glow(db, *, title: str, day: date, start: time, source_url: str) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower().strip(),
        date=day,
        start_time=start,
        end_time=time(21, 0),
        location_name="Altitude Trampoline Park",
        location_normalized="altitude trampoline park",
        description="",
        event_url="https://example.com/e",
        source_url=source_url,
        tags=[],
        status="live",
        source="test_glow_dedup",
    )
    db.add(ev)
    db.flush()
    eid = ev.id
    db.commit()
    return eid


def test_glow_dedup_deletes_one_off_keeps_series() -> None:
    import scripts.dedup_glow_in_the_park_2026_06_27 as glow

    coll = date(2026, 6, 27)
    with SessionLocal() as db:
        one_off = _seed_glow(
            db, title="Glow in the Park", day=coll, start=time(18, 0),
            source_url="https://altitudetrampolinepark.com/location/lake-havasu-city/#funspecial|x",
        )
        series_same_day = _seed_glow(
            db, title="Glow in the Park - All Ages", day=coll, start=time(19, 0),
            source_url="https://www.altitudetrampolinepark.com/locations/arizona/x",
        )
        series_other = _seed_glow(
            db, title="Glow in the Park - All Ages", day=date(2026, 6, 20), start=time(19, 0),
            source_url="https://www.altitudetrampolinepark.com/locations/arizona/x",
        )

    # Dry run changes nothing.
    assert glow.main([]) == 0
    with SessionLocal() as db:
        assert db.get(Event, one_off) is not None

    # Apply deletes only the one-off; series untouched.
    assert glow.main(["--apply"]) == 0
    with SessionLocal() as db:
        assert db.get(Event, one_off) is None
        assert db.get(Event, series_same_day) is not None
        assert db.get(Event, series_other) is not None


def test_glow_dedup_aborts_without_series() -> None:
    """No '- All Ages' series present -> refuse to delete (return code 2)."""
    import scripts.dedup_glow_in_the_park_2026_06_27 as glow

    with SessionLocal() as db:
        one_off = _seed_glow(
            db, title="Glow in the Park", day=date(2026, 6, 27), start=time(18, 0),
            source_url="https://altitudetrampolinepark.com/x/#funspecial|x",
        )
    assert glow.main(["--apply"]) == 2
    with SessionLocal() as db:
        assert db.get(Event, one_off) is not None


# --------------------------------------------------------------------------- #
# Task 2 — Havasu Lanes merge + event relabel                                  #
# --------------------------------------------------------------------------- #
def _provider(db, name, **kw) -> Provider:
    prov = Provider(
        provider_name=name,
        category=kw.pop("category", "family-fun-and-arcades"),
        slug=derive_provider_slug(db, name),
        source=kw.pop("source", "go_lake_havasu"),
        draft=kw.pop("draft", False),
        is_active=kw.pop("is_active", True),
        **kw,
    )
    db.add(prov)
    create_provider_and_entity(db, prov)
    db.flush()
    return prov


def _seed_event(db, *, title: str, loc: str) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower().strip(),
        date=date(2026, 6, 27),
        start_time=time(18, 0),
        location_name=loc,
        location_normalized=loc.lower().strip(),
        description="",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test_lanes_merge",
    )
    db.add(ev)
    db.flush()
    eid = ev.id
    db.commit()
    return eid


def test_havasu_lanes_merge_folds_and_relabels() -> None:
    import scripts.merge_havasu_lanes_2026_06_27 as merge

    pid = f"testpid-{uuid.uuid4().hex}"
    with SessionLocal() as db:
        keep = _provider(db, "Havasu Lanes")
        loser = _provider(
            db, "Havasu Lanes & Keglers Pub",
            source="google_places", google_review_count=463, google_place_id=pid,
        )
        assert keep.slug == "havasu-lanes"
        assert loser.slug == "havasu-lanes-keglers-pub"
        keep_id, loser_id = keep.id, loser.id
        db.commit()
        ev_cosmic = _seed_event(db, title="Cosmic Bowling", loc="Havasu Lanes")
        ev_daily = _seed_event(db, title="Bowling - Havasu Lanes & Keglers Pub",
                               loc="Havasu Lanes & Keglers Pub")

    assert merge.main(["--keep-slug", "havasu-lanes", "--name", "Havasu Lanes", "--apply"]) == 0

    with SessionLocal() as db:
        keep = db.get(Provider, keep_id)
        loser = db.get(Provider, loser_id)
        # keeper gap-filled the Google data; loser soft-retired with a redirect.
        assert keep.google_review_count == 463
        assert keep.google_place_id == pid
        assert keep.provider_name == "Havasu Lanes"
        assert loser.is_active is False
        assert (loser.attributes or {}).get("merged_into_slug") == "havasu-lanes"
        # all bowling events now read one venue label.
        labels = set(db.scalars(
            select(Event.location_name).where(Event.id.in_([ev_cosmic, ev_daily]))
        ).all())
        assert labels == {"Havasu Lanes"}


def test_havasu_lanes_merge_dry_run_writes_nothing() -> None:
    import scripts.merge_havasu_lanes_2026_06_27 as merge

    with SessionLocal() as db:
        _provider(db, "Havasu Lanes")
        loser = _provider(db, "Havasu Lanes & Keglers Pub", source="google_places")
        loser_id = loser.id
        db.commit()
        ev = _seed_event(db, title="Bowling - Havasu Lanes & Keglers Pub",
                         loc="Havasu Lanes & Keglers Pub")

    assert merge.main(["--keep-slug", "havasu-lanes", "--name", "Havasu Lanes"]) == 0
    with SessionLocal() as db:
        assert db.get(Provider, loser_id).is_active is True
        assert db.get(Event, ev).location_name == "Havasu Lanes & Keglers Pub"


def test_merge_aborts_on_missing_keeper() -> None:
    import scripts.merge_havasu_lanes_2026_06_27 as merge

    assert merge.main(["--keep-slug", f"nonexistent-{uuid.uuid4().hex}"]) == 2


# --------------------------------------------------------------------------- #
# Publish captured gym schedules to the calendar (allowlist-scoped)            #
# --------------------------------------------------------------------------- #
def test_publish_gym_schedules_scopes_to_allowlist(monkeypatch) -> None:
    import scripts.import_captured_schedules as imp
    import scripts.publish_strength_gym_schedules_2026_06_27 as pub
    from app.db import contribution_store as cs
    from app.db.models import Contribution, Schedule
    from app.schemas.contribution import ContributionCreate

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        gym = _provider(db, f"Test Gym {suf}")
        other = _provider(db, f"Other Venue {suf}")
        gym_eid, other_eid = gym.entity_id, other.entity_id
        db.commit()

        def _pending(name: str, eid: str, title: str) -> str:
            fields = imp._to_program_fields(
                {"provider_name": name, "location_name": name, "tags": []},
                {"title": title, "days": ["monday"], "start": "05:00", "end": "06:00"},
            )
            row = cs.create_contribution(db, ContributionCreate(
                entity_type="program", submission_name=f"{name} — {title}",
                source="schedule_scrape", confidence=0.85, target_entity_id=eid,
                proposed_record=fields.model_dump(), unverified=True,
            ))
            db.commit()
            return row.id

        gym_cid = _pending(f"Test Gym {suf}", gym_eid, "CrossFit WOD")
        other_cid = _pending(f"Other Venue {suf}", other_eid, "Yoga Flow")

    # Only the allowlisted gym entity is published; the other stays pending.
    monkeypatch.setattr(pub, "GYM_ENTITY_IDS", {gym_eid: f"Test Gym {suf}"})
    assert pub.main(["--apply"]) == 0

    with SessionLocal() as db:
        assert db.get(Contribution, gym_cid).status == "approved"
        assert db.get(Contribution, other_cid).status == "pending"
        assert db.query(Schedule).filter(Schedule.entity_id == gym_eid).count() >= 1
        assert db.query(Schedule).filter(Schedule.entity_id == other_eid).count() == 0


def test_retract_stale_schedules_deletes_only_matching_titles(monkeypatch) -> None:
    import scripts.import_captured_schedules as imp
    import scripts.retract_stale_class_schedules_2026_06_27 as retract
    from app.db import contribution_store as cs
    from app.db.models import Contribution, Offering, Schedule
    from app.schemas.contribution import ContributionCreate

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        venue = _provider(db, f"Seasonal Studio {suf}")
        eid = venue.entity_id
        db.commit()
        # An approved schedule_scrape contribution + its rendered Schedule/Offering.
        fields = imp._to_program_fields(
            {"provider_name": f"Seasonal Studio {suf}", "location_name": f"Seasonal Studio {suf}", "tags": []},
            {"title": f"Ballet {suf}", "days": ["monday"], "start": "16:00", "end": "17:00"},
        )
        row = cs.create_contribution(db, ContributionCreate(
            entity_type="program", submission_name=f"Seasonal — Ballet {suf}",
            source="schedule_scrape", confidence=0.6, target_entity_id=eid,
            proposed_record=fields.model_dump(), unverified=True,
        ))
        row.status = "approved"
        row.created_entity_id = eid
        db.add(Schedule(entity_id=eid, schedule_type="recurring",
                        days_of_week=["monday"], notes=f"Ballet {suf}"))
        db.add(Offering(entity_id=eid, name=f"Ballet {suf}", display_order=0))
        # A non-schedule-hunt schedule (title-less) that must NOT be touched.
        db.add(Schedule(entity_id=eid, schedule_type="recurring",
                        days_of_week=["tuesday"], notes=None))
        db.commit()
        cid = row.id

    monkeypatch.setattr(retract, "STALE_VENUES", {eid: f"test {suf}"})
    assert retract.main(["--apply"]) == 0

    with SessionLocal() as db:
        assert db.query(Schedule).filter(Schedule.entity_id == eid, Schedule.notes == f"Ballet {suf}").count() == 0
        assert db.query(Offering).filter(Offering.entity_id == eid).count() == 0
        # title-less schedule survives
        assert db.query(Schedule).filter(Schedule.entity_id == eid, Schedule.notes.is_(None)).count() == 1
        # contribution reverted to pending (re-publishable), proposed_record intact
        c = db.get(Contribution, cid)
        assert c.status == "pending" and c.created_entity_id is None
        assert c.proposed_record["title"] == f"Ballet {suf}"


def test_publish_gym_schedules_dry_run_publishes_nothing(monkeypatch) -> None:
    import scripts.import_captured_schedules as imp
    import scripts.publish_strength_gym_schedules_2026_06_27 as pub
    from app.db import contribution_store as cs
    from app.db.models import Contribution
    from app.schemas.contribution import ContributionCreate

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        gym = _provider(db, f"Test Gym {suf}")
        gym_eid = gym.entity_id
        db.commit()
        fields = imp._to_program_fields(
            {"provider_name": f"Test Gym {suf}", "location_name": f"Test Gym {suf}", "tags": []},
            {"title": "WOD", "days": ["monday"], "start": "05:00", "end": "06:00"},
        )
        row = cs.create_contribution(db, ContributionCreate(
            entity_type="program", submission_name=f"Test Gym {suf} — WOD",
            source="schedule_scrape", confidence=0.85, target_entity_id=gym_eid,
            proposed_record=fields.model_dump(), unverified=True,
        ))
        db.commit()
        cid = row.id

    monkeypatch.setattr(pub, "GYM_ENTITY_IDS", {gym_eid: f"Test Gym {suf}"})
    assert pub.main([]) == 0
    with SessionLocal() as db:
        assert db.get(Contribution, cid).status == "pending"
