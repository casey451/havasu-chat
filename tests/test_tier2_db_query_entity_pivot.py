"""Phase 1C regression — ENTITY-aware Tier 2 catalog reads stay shape-stable."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_db_query
from app.chat.tier2_schema import Tier2Filters
from app.contrib.hours_helper import LAKE_HAVASU_TZ
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import Entity, Event, Hours, Location, Program, Provider


def _mk_entity(*, etype: str, name: str) -> Entity:
    slug = f"pivot-{uuid4().hex[:12]}"
    return Entity(
        id=str(uuid4()),
        entity_type=etype,
        slug=slug,
        name=name,
        source="test-tier2-pivot",
    )


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_pivot_entity_name_query_returns_stable_provider_payload(
    db: Session,
) -> None:
    """ENTITY-linked commercial provider appears under entity-name filter."""
    suf = uuid4().hex[:8]
    name = f"Pivot Name Cafe {suf}"
    ent = _mk_entity(etype=ENTITY_TYPE_COMMERCIAL, name=name)
    db.add(ent)
    p = Provider(
        provider_name=name,
        category="food_drink",
        source="test-tier2-pivot",
        google_place_id=f"gpid_{suf}",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add(p)
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False),
    )
    hit = next((r for r in rows if r.get("type") == "provider" and name in r.get("name", "")), None)
    assert hit is not None
    assert set(hit.keys()) >= {
        "type",
        "name",
        "category",
        "address",
        "phone",
        "hours",
        "description",
    }

    db.delete(p)
    db.delete(ent)
    db.commit()


def test_pivot_time_window_event_payload_stable(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 7, 10))
    title = f"Pivot Concert {uuid4().hex[:6]}"
    ent = _mk_entity(etype=ENTITY_TYPE_EVENT, name=title)
    db.add(ent)
    db.flush()
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=date(2026, 7, 11),
        start_time=time(18, 0),
        end_time=time(21, 0),
        location_name="Rotary Park",
        location_normalized="rotary park",
        description="music",
        status="live",
        entity_id=ent.id,
    )
    db.add(ev)
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, time_window="tomorrow", fallback_to_tier3=False),
    )
    hit = next((r for r in rows if r.get("type") == "event" and title in r.get("name", "")), None)
    assert hit is not None
    assert hit["date"] == "2026-07-11"

    db.delete(ev)
    db.delete(ent)
    db.commit()


def test_pivot_location_filter_uses_entity_location_address(db: Session) -> None:
    suf = uuid4().hex[:8]
    needle = "Entity Dock Row"
    ent = _mk_entity(etype=ENTITY_TYPE_COMMERCIAL, name=f"Marina Pivot {suf}")
    db.add(ent)
    db.flush()
    db.add(
        Location(
            entity_id=ent.id,
            address=f"100 {needle}, Lake Havasu City, AZ",
            city="Lake Havasu City",
            state="AZ",
        )
    )
    p = Provider(
        provider_name=f"Marina Pivot {suf}",
        category="lake_recreation",
        address="1 Legacy Wrong St",
        source="test-tier2-pivot",
        google_place_id=f"gpid_{suf}",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add(p)
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, location="dock row", fallback_to_tier3=False),
    )
    assert any(
        r.get("type") == "provider" and needle.lower() in (r.get("address") or "").lower()
        for r in rows
    )

    db.delete(p)
    db.delete(db.query(Location).filter_by(entity_id=ent.id).one())
    db.delete(ent)
    db.commit()


def test_pivot_open_now_reads_hours_extension_when_legacy_json_absent(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open_now uses :func:`effective_hours_structured` (ENTITY hours rows)."""
    monkeypatch.setattr(
        tier2_db_query,
        "_now_lake_havasu",
        lambda: datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ),
    )
    suf = uuid4().hex[:8]
    name = f"Hours Ext Diner {suf}"
    ent = _mk_entity(etype=ENTITY_TYPE_COMMERCIAL, name=name)
    db.add(ent)
    db.flush()
    # Monday = 0 per backfill convention
    db.add(
        Hours(
            entity_id=ent.id,
            day_of_week=0,
            opens_at=time(9, 0),
            closes_at=time(23, 0),
        )
    )
    p = Provider(
        provider_name=name,
        category="restaurant",
        source="test-tier2-pivot",
        draft=False,
        is_active=True,
        description="food",
        hours_structured=None,
        entity_id=ent.id,
    )
    db.add(p)
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, entity_name=name, open_now=True, fallback_to_tier3=False),
    )
    assert any(r.get("type") == "provider" and name in r.get("name", "") for r in rows)

    db.delete(p)
    db.delete(db.query(Hours).filter_by(entity_id=ent.id).one())
    db.delete(ent)
    db.commit()


def test_pivot_program_outerjoin_does_not_drop_orphan_program(db: Session) -> None:
    """Programs without ``entity_id`` remain visible (transition orphan path)."""
    suf = uuid4().hex[:8]
    title = f"Orphan Swim {suf}"
    prog = Program(
        title=title,
        description="lessons",
        activity_category="aquatics",
        schedule_days=["monday"],
        schedule_start_time=time(9, 0),
        schedule_end_time=time(10, 0),
        location_name="Pool",
        location_address=None,
        provider_name="City",
        source="test-tier2-pivot",
        draft=False,
        is_active=True,
        entity_id=None,
    )
    db.add(prog)
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(Tier2Filters(parser_confidence=0.9, entity_name=title, fallback_to_tier3=False))
    assert any(r.get("type") == "program" and title in r.get("name", "") for r in rows)

    db.delete(prog)
    db.commit()
