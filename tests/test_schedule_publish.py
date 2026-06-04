"""Tests for the schedule-hunt auto-publish engine (app/contrib/schedule_publish.py).

Against the isolated session SQLite DB from conftest.py. Each test seeds its own
Entity + Contribution and cleans up.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func

from app.contrib.schedule_publish import publish_contribution, resolve_target_entity
from app.db.database import SessionLocal
from app.db.models import Contribution, Entity, Offering, Schedule

_VALID_RECORD = {
    "title": "Vinyasa Flow",
    "description": "All-levels vinyasa flow class, bring your own mat.",
    "schedule_days": ["monday", "wednesday"],
    "schedule_start_time": "09:00",
    "schedule_end_time": "10:00",
    "location_name": "Amalaya Yoga",
    "provider_name": "Amalaya Yoga",
    "cost": "$15/class",
}


def _seed_entity(db, name="Amalaya Yoga") -> str:
    eid = str(uuid4())
    db.add(
        Entity(
            id=eid,
            entity_type="commercial",
            slug=f"sp-{eid[:8]}",
            name=name,
            source="test-schedpub",
            is_active=True,
        )
    )
    db.commit()
    return eid


def _seed_contribution(db, **over) -> int:
    row = Contribution(
        entity_type="program",
        submission_name=over.get("submission_name", "Amalaya Yoga"),
        source="facebook_scrape",
        status="pending",
        confidence=over.get("confidence", 0.95),
        target_entity_id=over.get("target_entity_id"),
        proposed_record=over.get("proposed_record", dict(_VALID_RECORD)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def _cleanup(eid: str, cid: int) -> None:
    with SessionLocal() as db:
        for tbl in (Offering, Schedule):
            for r in db.query(tbl).filter(tbl.entity_id == eid):
                db.delete(r)
        from app.db.models import ContactPoint, SourceEvidence

        for tbl in (ContactPoint, SourceEvidence):
            for r in db.query(tbl).filter(tbl.entity_id == eid):
                db.delete(r)
        c = db.get(Contribution, cid)
        if c:
            db.delete(c)
        e = db.get(Entity, eid)
        if e:
            db.delete(e)
        db.commit()


def test_publish_attaches_to_existing_entity_no_dup() -> None:
    with SessionLocal() as db:
        eid = _seed_entity(db)
        cid = _seed_contribution(db, target_entity_id=eid)
        before = db.query(func.count(Entity.id)).scalar()
    try:
        with SessionLocal() as db:
            c = db.get(Contribution, cid)
            res = publish_contribution(db, c)
            assert res["status"] == "published"
            assert res["entity_id"] == eid
        with SessionLocal() as db:
            # No new Entity minted.
            assert db.query(func.count(Entity.id)).scalar() == before
            # Schedule + Offering attached to the existing entity.
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 1
            off = db.query(Offering).filter(Offering.entity_id == eid).one()
            assert off.name == "Vinyasa Flow"
            sch = db.query(Schedule).filter(Schedule.entity_id == eid).one()
            assert sch.days_of_week == ["monday", "wednesday"]
            assert sch.start_time.hour == 9
            # notes carries the class title so readers can pair the Schedule
            # with its Offering (no FK between the tables).
            assert sch.notes == "Vinyasa Flow"
            c = db.get(Contribution, cid)
            assert c.status == "approved"
            assert c.created_entity_id == eid
    finally:
        _cleanup(eid, cid)


def test_publish_is_idempotent() -> None:
    with SessionLocal() as db:
        eid = _seed_entity(db)
        cid = _seed_contribution(db, target_entity_id=eid)
    try:
        with SessionLocal() as db:
            assert publish_contribution(db, db.get(Contribution, cid))["status"] == "published"
        with SessionLocal() as db:
            res = publish_contribution(db, db.get(Contribution, cid))
            assert res["status"] == "skipped"
            # Re-publish is refused (already approved + has created_entity_id).
            assert res["reason"] in ("not_pending", "already_published")
            # Still exactly one schedule (no duplicate attach).
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 1
    finally:
        _cleanup(eid, cid)


def test_publish_skips_when_no_entity_match() -> None:
    with SessionLocal() as db:
        # No seeded entity; bogus target + name that won't reconcile.
        cid = _seed_contribution(
            db, submission_name="Nonexistent Phantom Studio XYZ", target_entity_id="does-not-exist"
        )
    try:
        with SessionLocal() as db:
            res = publish_contribution(db, db.get(Contribution, cid))
            assert res["status"] == "skipped"
            assert res["reason"] == "no_entity_match"
            assert db.get(Contribution, cid).status == "pending"
    finally:
        with SessionLocal() as db:
            c = db.get(Contribution, cid)
            if c:
                db.delete(c)
                db.commit()


def test_publish_skips_invalid_proposed_record() -> None:
    with SessionLocal() as db:
        eid = _seed_entity(db, name="Iron Age Gym")
        cid = _seed_contribution(
            db, target_entity_id=eid, proposed_record={"title": "x"}  # too short / missing fields
        )
    try:
        with SessionLocal() as db:
            res = publish_contribution(db, db.get(Contribution, cid))
            assert res["status"] == "skipped"
            assert res["reason"] == "invalid_proposed_record"
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 0
    finally:
        _cleanup(eid, cid)


def test_resolve_prefers_explicit_target() -> None:
    with SessionLocal() as db:
        eid = _seed_entity(db, name="Resolve Probe Gym")
        cid = _seed_contribution(db, target_entity_id=eid)
        try:
            assert resolve_target_entity(db, db.get(Contribution, cid)) == eid
        finally:
            pass
    _cleanup(eid, cid)


def test_attach_program_to_existing_entity_uses_edited_fields() -> None:
    """Manual-approve attach path lands the operator-edited fields on the venue."""
    from app.contrib.schedule_publish import attach_program_to_existing_entity
    from app.schemas.contribution import ProgramApprovalFields

    with SessionLocal() as db:
        eid = _seed_entity(db, name="Attach Probe Studio")
        cid = _seed_contribution(db, target_entity_id=eid)
    try:
        edited = ProgramApprovalFields(
            title="Edited Class Name",
            description="Operator-edited description, at least twenty chars.",
            schedule_days=["friday"],
            schedule_start_time="17:30",
            schedule_end_time="18:30",
            location_name="Attach Probe Studio",
            provider_name="Attach Probe Studio",
        )
        with SessionLocal() as db:
            c = db.get(Contribution, cid)
            before = db.query(func.count(Entity.id)).scalar()
            rid = attach_program_to_existing_entity(db, c, edited, eid)
            assert rid == eid
        with SessionLocal() as db:
            assert db.query(func.count(Entity.id)).scalar() == before  # no new venue
            off = db.query(Offering).filter(Offering.entity_id == eid).one()
            assert off.name == "Edited Class Name"
            assert db.get(Contribution, cid).status == "approved"
            assert db.get(Contribution, cid).created_entity_id == eid
    finally:
        _cleanup(eid, cid)
