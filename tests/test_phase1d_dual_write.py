"""Phase 1D — dual-write helpers + sponsor resolution pins."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.entity_dual_write import (
    create_event_and_entity,
    create_program_and_entity,
    create_provider_and_entity,
)
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import (
    ContactPoint,
    Entity,
    Event,
    Location,
    Program,
    Provider,
    Schedule,
    SourceEvidence,
    Sponsor,
)
from app.db.sponsor_resolve import resolve_sponsor_linked_provider


def test_create_provider_and_entity_writes_entity_and_extensions() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="p1d-prov-1",
            provider_name="Phase1D Test Provider",
            category="retail",
            address="1 Main St",
            phone="555-0100",
            source="test",
            slug="phase1d-test-provider-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        p2 = db.get(Provider, "p1d-prov-1")
        assert p2 is not None and p2.entity_id is not None
        ent = db.get(Entity, p2.entity_id)
        assert ent is not None and ent.entity_type == "commercial"
        assert (
            db.scalars(select(Location).where(Location.entity_id == ent.id)).first() is not None
        )
        assert (
            db.scalars(select(ContactPoint).where(ContactPoint.entity_id == ent.id)).first()
            is not None
        )
        assert (
            db.scalars(select(SourceEvidence).where(SourceEvidence.entity_id == ent.id)).first()
            is not None
        )


def test_create_event_and_entity_writes_schedule_and_evidence() -> None:
    with SessionLocal() as db:
        ev = Event(
            title="Phase1D Test Event",
            normalized_title="phase1d test event",
            date=date(2026, 6, 1),
            start_time=time(10, 0),
            end_time=None,
            location_name="Rotary Park",
            location_normalized="rotary park",
            description="Fun run.",
            event_url="https://example.com/e",
            status="live",
            source="admin",
        )
        db.add(ev)
        create_event_and_entity(db, ev)
        db.commit()
        eid = ev.id

    with SessionLocal() as db:
        ev2 = db.get(Event, eid)
        assert ev2 is not None and ev2.entity_id is not None
        assert (
            db.scalars(select(Schedule).where(Schedule.entity_id == ev2.entity_id)).first()
            is not None
        )
        assert (
            db.scalars(select(SourceEvidence).where(SourceEvidence.entity_id == ev2.entity_id)).first()
            is not None
        )


def test_create_program_and_entity_writes_schedule_offering_evidence() -> None:
    with SessionLocal() as db:
        prog = Program(
            title="Phase1D Swim Class",
            description="Learn to swim",
            activity_category="aquatics",
            schedule_days=["Monday"],
            schedule_start_time=time(9, 0),
            schedule_end_time=time(10, 0),
            location_name="Aquatic Center",
            provider_name="P&R",
            source="admin",
        )
        db.add(prog)
        create_program_and_entity(db, prog)
        db.commit()
        pid = prog.id

    with SessionLocal() as db:
        pr = db.get(Program, pid)
        assert pr is not None and pr.entity_id is not None
        eid = pr.entity_id
        assert db.scalars(select(Schedule).where(Schedule.entity_id == eid)).first() is not None


def test_resolve_sponsor_linked_provider_commercial() -> None:
    with SessionLocal() as db:
        pid = "900042"
        prov = Provider(
            id=pid,
            provider_name="Sponsor Target Biz",
            category="retail",
            source="test",
            slug="sponsor-target-biz-900042",
        )
        db.add(prov)
        create_provider_and_entity(db, prov)
        sp = Sponsor(
            name="Test Sponsor",
            cta_url="https://example.com",
            business_id=900042,
            entity_type=ENTITY_TYPE_COMMERCIAL,
        )
        db.add(sp)
        db.commit()

    with SessionLocal() as db:
        s = db.scalars(select(Sponsor).where(Sponsor.name == "Test Sponsor")).first()
        assert s is not None
        p = resolve_sponsor_linked_provider(db, s)
        assert p is not None and p.id == "900042" and p.provider_name == "Sponsor Target Biz"


def test_resolve_sponsor_linked_provider_place_is_no_row() -> None:
    with SessionLocal() as db:
        sp = Sponsor(
            name="Place Sponsor",
            cta_url="https://example.com",
            business_id=1,
            entity_type="place",
        )
        db.add(sp)
        db.commit()
        sid = sp.id
    with SessionLocal() as db:
        s = db.get(Sponsor, sid)
        assert s is not None
        assert resolve_sponsor_linked_provider(db, s) is None


def test_explicit_dual_write_idempotent_with_prefilled_entity_id() -> None:
    """Second call is a no-op when ``entity_id`` is already populated."""
    with SessionLocal() as db:
        p = Provider(
            id="p1d-prov-idem",
            provider_name="Idem Test",
            category="services",
            source="test",
            slug="phase1d-idem-test",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        eid = p.entity_id
        create_provider_and_entity(db, p)
        assert p.entity_id == eid
        db.commit()


def test_scraper_entry_point_import_chain_does_not_cycle() -> None:
    """Phase 1D regression — Session-22 (2026-05-13).

    Reproduces the parks-rec-scrapes CI failure where ``scripts/parks_rec_load.py``
    transitively reached ``app.db.contribution_store -> app.db.models ->
    app.db.database`` before ``app.db.models`` finished initializing. The old
    ``_register_orm_listeners()`` hook at ``database.py`` module-top would then
    try to import ``ContactPoint`` from a partially-initialized ``app.db.models``
    and raise ``ImportError``.

    The fix moved hook registration to the bottom of ``app/db/models.py`` (after
    all ORM classes are defined). This test runs the failing import chain in a
    fresh subprocess so it isn't masked by sys.modules caching from earlier
    tests, and asserts both: the import succeeds, and ``register_catalog_dual_write_hooks``
    actually fired (idempotency-flag check).
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "from app.contrib.parks_rec_loader import load_latest_snapshots  # noqa: F401\n"
        "import app.db.entity_dual_write as edw\n"
        "from app.db.models import ContactPoint\n"
        "print(json.dumps({\n"
        '   "loaded": True,\n'
        '   "hooks_registered": bool(edw._CATALOG_DUAL_WRITE_HOOKS_REGISTERED),\n'
        '   "contact_point_class": ContactPoint.__name__,\n'
        "}))\n"
    ) % str(repo_root)

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"scraper import chain raised in subprocess:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )

    import json

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["loaded"] is True
    assert payload["hooks_registered"] is True, (
        "register_catalog_dual_write_hooks() did not fire on parks-rec import path"
    )
    assert payload["contact_point_class"] == "ContactPoint"
