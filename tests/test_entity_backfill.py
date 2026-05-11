"""Phase 1B — ENTITY backfill from legacy Provider/Event/Program rows."""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import func, inspect, select, text

from app.db.database import SessionLocal, engine
from app.db.entity_backfill import run_entity_backfill
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT, ENTITY_TYPE_PROGRAM
from app.db.models import (
    Category,
    ContactPoint,
    Entity,
    EntityCategory,
    Event,
    Hours,
    Location,
    Offering,
    Program,
    Provider,
    Schedule,
    Sponsor,
)


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def test_provider_backfilled_to_entity() -> None:
    suf = _suffix()
    slug = f"bf-prov-{suf}"
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health").one()
        cat_id = cat.id
        p = Provider(
            provider_name=f"Backfill Plumbing {suf}",
            category="plumbing",
            slug=slug,
            category_id=cat_id,
            phone="555-0101",
            email="pipe@example.com",
            website="https://example.com/plumb",
            facebook="https://facebook.com/plumb",
            hours_structured=hs,
            description="We fix pipes.",
            verified=True,
            draft=False,
            is_active=True,
            source="entity-backfill-test",
            address="123 River Rd",
            zip="86403",
            lat=34.5,
            lng=-114.3,
            district="North End",
        )
        db.add(p)
        db.commit()
        pid = p.id

    with engine.connect() as conn:
        run_entity_backfill(conn)
        conn.commit()

    with SessionLocal() as db:
        p = db.get(Provider, pid)
        assert p is not None
        assert p.entity_id is not None
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        assert ent.entity_type == ENTITY_TYPE_COMMERCIAL
        assert ent.slug == slug
        loc = db.scalars(select(Location).where(Location.entity_id == ent.id)).first()
        assert loc is not None
        assert loc.address == "123 River Rd"
        assert db.scalar(select(func.count()).select_from(Hours).where(Hours.entity_id == ent.id)) >= 1
        assert (
            db.scalar(
                select(func.count()).select_from(ContactPoint).where(ContactPoint.entity_id == ent.id)
            )
            >= 3
        )
        ec = db.scalars(
            select(EntityCategory).where(
                EntityCategory.entity_id == ent.id, EntityCategory.category_id == cat_id
            )
        ).first()
        assert ec is not None
        assert ec.is_primary is True


def test_event_backfilled_to_entity() -> None:
    suf = _suffix()
    on = date(2030, 6, 15)
    loc = f"Lakeside Park {suf}"
    with SessionLocal() as db:
        e = Event(
            title=f"Concert Night {suf}",
            normalized_title=f"concert night {suf}".lower(),
            date=on,
            end_date=None,
            start_time=time(19, 30),
            end_time=time(21, 0),
            location_name=loc,
            location_normalized=loc.lower(),
            description="Live music outdoors.",
            event_url="https://example.com/concert",
            tags=["music"],
            status="live",
            source="entity-backfill-test",
            verified=True,
            contact_phone="555-0202",
            contact_name="Box Office",
        )
        db.add(e)
        db.commit()
        eid = e.id

    with engine.connect() as conn:
        run_entity_backfill(conn)
        conn.commit()

    with SessionLocal() as db:
        ev = db.get(Event, eid)
        assert ev is not None and ev.entity_id is not None
        ent = db.get(Entity, ev.entity_id)
        assert ent.entity_type == ENTITY_TYPE_EVENT
        loc_row = db.scalars(select(Location).where(Location.entity_id == ent.id)).first()
        assert loc_row is not None
        assert loc in (loc_row.address or "")
        sch = db.scalars(select(Schedule).where(Schedule.entity_id == ent.id)).first()
        assert sch is not None
        assert sch.schedule_type == "one_off"
        assert sch.start_date == on


def test_program_backfilled_to_entity() -> None:
    suf = _suffix()
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="family").one()
        pr = Program(
            title=f"Youth Swim {suf}",
            description="Lessons for kids.",
            activity_category="swim",
            category_id=cat.id,
            schedule_days=["saturday"],
            schedule_start_time=time(10, 0),
            schedule_end_time=time(11, 0),
            location_name="Aquatic Center",
            location_address="400 Pool Ln",
            cost="$10",
            provider_name="City Aquatics",
            contact_phone="555-0303",
            contact_email="swim@example.com",
            contact_url="https://example.com/swim",
            schedule_note="Bring goggles.",
            source="entity-backfill-test",
            verified=True,
            is_active=True,
            draft=False,
        )
        db.add(pr)
        db.commit()
        pid = pr.id

    with engine.connect() as conn:
        run_entity_backfill(conn)
        conn.commit()

    with SessionLocal() as db:
        prog = db.get(Program, pid)
        assert prog is not None and prog.entity_id is not None
        ent = db.get(Entity, prog.entity_id)
        assert ent.entity_type == ENTITY_TYPE_PROGRAM
        assert db.scalars(select(Location).where(Location.entity_id == ent.id)).first() is not None
        assert db.scalars(select(Schedule).where(Schedule.entity_id == ent.id)).first() is not None
        assert db.scalars(select(Offering).where(Offering.entity_id == ent.id)).first() is not None


def test_sponsor_entity_type_backfilled() -> None:
    suf = _suffix()
    with SessionLocal() as db:
        sp = Sponsor(
            name=f"Sponsor BF {suf}",
            cta_url="https://example.com/ad",
            entity_type=None,
        )
        db.add(sp)
        db.commit()
        sid = sp.id

    with engine.connect() as conn:
        run_entity_backfill(conn)
        conn.commit()

    with SessionLocal() as db:
        sp = db.get(Sponsor, sid)
        assert sp is not None
        assert sp.entity_type == ENTITY_TYPE_COMMERCIAL


def test_backfill_idempotent() -> None:
    with engine.connect() as conn:
        run_entity_backfill(conn)
        conn.commit()
    with engine.connect() as conn:
        n1 = conn.execute(text("SELECT COUNT(*) FROM entities")).scalar()
        run_entity_backfill(conn)
        conn.commit()
    with engine.connect() as conn:
        n2 = conn.execute(text("SELECT COUNT(*) FROM entities")).scalar()
    assert n1 == n2


def test_entity_id_fk_columns_are_not_null_after_phase_1d_closeout() -> None:
    """Phase 1D migration flips legacy ``entity_id`` FK columns to NOT NULL."""
    insp = inspect(engine)
    for tbl in ("providers", "events", "programs"):
        cols = {c["name"]: c for c in insp.get_columns(tbl)}
        assert cols["entity_id"]["nullable"] is False
