"""Chat catalog rows must carry the entity's class schedule (Offerings+Schedules).

The schedule-hunt pipeline attaches Offering + recurring Schedule rows to
existing venues; without serializing them into the tier-2 entity rows the chat
can never answer "what classes / when" questions (it told users it had no
classes "in the provided rows" while 40+ were live in the DB).
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

from app.chat.entity_catalog_query import _entity_row_dict, _program_lines
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Offering, Schedule


def _seed_entity(db, name="Catalog Programs Gym", *, categorize=False) -> Entity:
    ent = Entity(
        id=str(uuid4()),
        entity_type="commercial",
        slug=f"cpq-{uuid4().hex[:8]}",
        name=name,
        source="test-catalog-programs",
        is_active=True,
    )
    db.add(ent)
    if categorize:
        # the schedule-hunt import assigns one primary category per venue
        cat = db.query(Category).order_by(Category.id).first()
        assert cat is not None, "seeded Category required"
        db.add(EntityCategory(entity_id=ent.id, category_id=cat.id, is_primary=True))
    db.commit()
    return ent


def _add_pair(db, eid, title, days, start, end, price=None, notes=None):
    db.add(
        Offering(
            entity_id=eid,
            name=title,
            description=f"{title} class.",
            price_text=price,
            display_order=0,
        )
    )
    db.add(
        Schedule(
            entity_id=eid,
            schedule_type="recurring",
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
            days_of_week=days,
            notes=notes,
        )
    )
    db.commit()


def _cleanup(db, eid):
    db.query(EntityCategory).filter(EntityCategory.entity_id == eid).delete()
    db.query(Schedule).filter(Schedule.entity_id == eid).delete()
    db.query(Offering).filter(Offering.entity_id == eid).delete()
    db.query(Entity).filter(Entity.id == eid).delete()
    db.commit()


def test_program_lines_pair_by_schedule_notes() -> None:
    db = SessionLocal()
    ent = _seed_entity(db)
    try:
        _add_pair(db, ent.id, "Aqua Aerobics", ["monday", "wednesday", "friday"],
                  "09:30", "10:30", price="$5/class", notes="Aqua Aerobics")
        _add_pair(db, ent.id, "Warm Water Yoga", ["tuesday", "thursday"],
                  "10:15", "11:15", notes="Warm Water Yoga")
        db.refresh(ent)
        lines = _program_lines(ent)
        assert "Aqua Aerobics | Mon/Wed/Fri 09:30-10:30 | $5/class" in lines
        assert "Warm Water Yoga | Tue/Thu 10:15-11:15" in lines
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_program_lines_zip_fallback_without_notes() -> None:
    """Rows published before Schedule.notes carried the title (notes=None)
    pair positionally when offering/schedule counts match."""
    db = SessionLocal()
    ent = _seed_entity(db, name="Zip Fallback Studio")
    try:
        _add_pair(db, ent.id, "Ballet 1 & 2", ["monday"], "15:30", "16:30")
        _add_pair(db, ent.id, "Pointe", ["tuesday"], "20:30", "21:30")
        db.refresh(ent)
        lines = _program_lines(ent)
        assert "Ballet 1 & 2 | Mon 15:30-16:30" in lines
        assert "Pointe | Tue 20:30-21:30" in lines
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_program_lines_unpaired_offering_still_renders() -> None:
    """Offering without any schedule (count mismatch, no notes): name+price only."""
    db = SessionLocal()
    ent = _seed_entity(db, name="Unpaired Offerings Bar")
    try:
        db.add(Offering(entity_id=ent.id, name="Taco Tuesday Special",
                        price_text="$2 tacos", display_order=0))
        db.commit()
        db.refresh(ent)
        lines = _program_lines(ent)
        assert lines == ["Taco Tuesday Special | $2 tacos"]
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_program_lines_capped() -> None:
    db = SessionLocal()
    ent = _seed_entity(db, name="Many Classes Dance Hall")
    try:
        for i in range(15):
            _add_pair(db, ent.id, f"Class {i:02d}", ["monday"], "10:00", "11:00",
                      notes=f"Class {i:02d}")
        db.refresh(ent)
        lines = _program_lines(ent)
        assert len(lines) == 13  # 12 + "(+3 more)"
        assert lines[-1] == "(+3 more)"
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_entity_row_dict_includes_programs() -> None:
    db = SessionLocal()
    ent = _seed_entity(db, name="Row Dict Wellness")
    try:
        _add_pair(db, ent.id, "Tai Chi", ["monday", "wednesday"], "08:00", "09:00",
                  price="$5/class", notes="Tai Chi")
        db.refresh(ent)
        row = _entity_row_dict(ent, provider=None, event=None, rank_score=1.0)
        assert row["programs"] == ["Tai Chi | Mon/Wed 08:00-09:00 | $5/class"]
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_entity_row_dict_programs_empty_for_plain_business() -> None:
    db = SessionLocal()
    ent = _seed_entity(db, name="Plain Plumber LLC")
    try:
        row = _entity_row_dict(ent, provider=None, event=None, rank_score=1.0)
        assert row["programs"] == []
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_commercial_entity_with_offerings_visible_without_provider() -> None:
    """Schedule-hunt venues are commercial Entities with no Provider row; the
    provider gate must not hide them once they carry published offerings."""
    from app.chat.chat_request_context import ChatRequestContext
    from app.chat.entity_catalog_query import query_entities
    from app.chat.tier2_schema import Tier2Filters

    db = SessionLocal()
    ent = _seed_entity(db, name="Gateless Quilt Guild Annex", categorize=True)
    try:
        _add_pair(db, ent.id, "Open Sew", ["wednesday"], "10:00", "14:00",
                  notes="Open Sew")
        db.refresh(ent)
        rows = query_entities(
            db, Tier2Filters(entity_name="Gateless Quilt Guild", parser_confidence=1.0), ChatRequestContext()
        )
        names = [r["name"] for r in rows]
        assert "Gateless Quilt Guild Annex" in names
        row = next(r for r in rows if r["name"] == "Gateless Quilt Guild Annex")
        assert row["programs"] == ["Open Sew | Wed 10:00-14:00"]
    finally:
        _cleanup(db, ent.id)
        db.close()


def test_commercial_entity_without_offerings_stays_gated() -> None:
    """No provider AND no published content -> still hidden (quality gate)."""
    from app.chat.chat_request_context import ChatRequestContext
    from app.chat.entity_catalog_query import query_entities
    from app.chat.tier2_schema import Tier2Filters

    db = SessionLocal()
    ent = _seed_entity(db, name="Bare Gateless Entity", categorize=True)
    try:
        rows = query_entities(
            db, Tier2Filters(entity_name="Bare Gateless Entity", parser_confidence=1.0), ChatRequestContext()
        )
        assert all(r["name"] != "Bare Gateless Entity" for r in rows)
    finally:
        _cleanup(db, ent.id)
        db.close()
