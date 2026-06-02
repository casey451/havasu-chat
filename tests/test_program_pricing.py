"""Program price display (Step 3): pure helper + the offering-join wiring.

The price *facet* is deferred (Offering.price_min_cents is unpopulated, so there
is nothing structured to range-filter); this covers the display path, which is
offering-first with a Program.cost fallback.
"""

from __future__ import annotations

import uuid
from datetime import time

import pytest
from sqlalchemy import delete

from app.chat.intents.queries import _query_programs
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Entity, EntityCategory, Location, Offering, Program, Provider
from app.db.seed_helpers import derive_provider_slug
from app.programs.pricing import format_offering_price, format_program_price


class _Off:
    def __init__(self, price_text=None, price_min_cents=None, price_max_cents=None):
        self.price_text = price_text
        self.price_min_cents = price_min_cents
        self.price_max_cents = price_max_cents


# --- pure helper --------------------------------------------------------------


def test_program_cost_used_when_no_offering():
    assert format_program_price("$15/class") == "$15/class"
    assert format_program_price("  Free  ") == "Free"


def test_empty_when_nothing_present():
    assert format_program_price(None) == ""
    assert format_program_price("") == ""
    assert format_program_price("   ") == ""
    assert format_program_price(None, None) == ""


def test_offering_price_text_wins_over_cost():
    assert format_program_price("$15/class", _Off(price_text="$20 drop-in")) == "$20 drop-in"


def test_offering_falls_back_to_cost_when_offering_has_no_price():
    assert format_program_price("$15/class", _Off()) == "$15/class"


@pytest.mark.parametrize(
    "off, expected",
    [
        (_Off(price_text="$22 drop-in"), "$22 drop-in"),
        (_Off(price_min_cents=1500, price_max_cents=3000), "$15-$30"),
        (_Off(price_min_cents=1599), "$15.99"),
        (_Off(price_min_cents=2000), "$20"),
        (_Off(price_min_cents=2500, price_max_cents=2500), "$25"),
        (_Off(price_max_cents=4000), "$40"),
        (_Off(), ""),
        (None, ""),
    ],
)
def test_format_offering_price(off, expected):
    assert format_offering_price(off) == expected


# --- DB-backed wiring (Program -> Provider.entity -> Offering) -----------------


def _seed_program_with_offering(db, *, offering_price_text, program_cost):
    suf = uuid.uuid4().hex[:8]
    prov = Provider(
        provider_name=f"Havasu Swim School {suf}",
        category="fitness_sports",
        subcategory="gyms",
        slug=derive_provider_slug(db, f"Havasu Swim School {suf}"),
        source="test",
        draft=False,
        is_active=True,
    )
    db.add(prov)
    create_provider_and_entity(db, prov)
    db.flush()
    if offering_price_text is not None:
        db.add(
            Offering(
                entity_id=prov.entity_id,
                name="Drop-in",
                price_text=offering_price_text,
                display_order=0,
            )
        )
    prog = Program(
        title=f"Kids Swim {suf}",
        description="Learn to swim, ages 4-12.",
        activity_category="swim",
        age_min=4,
        age_max=12,
        schedule_days=["monday"],
        schedule_start_time=time(9, 0),
        schedule_end_time=time(10, 0),
        location_name="City Pool",
        cost=program_cost,
        provider_name=prov.provider_name,
        provider_id=prov.id,
        source="admin",
        verified=True,
        is_active=True,
        tags=[],
    )
    db.add(prog)
    db.commit()
    return prov, prog, suf


def _cleanup(db, prov, prog):
    db.execute(delete(Program).where(Program.id == prog.id))
    eid = prov.entity_id
    db.execute(delete(Provider).where(Provider.id == prov.id))
    if eid:
        db.execute(delete(Offering).where(Offering.entity_id == eid))
        db.execute(delete(Location).where(Location.entity_id == eid))
        db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
    db.commit()


def test_query_programs_prefers_offering_price():
    with SessionLocal() as db:
        prov, prog, suf = _seed_program_with_offering(
            db, offering_price_text="$22 drop-in", program_cost="$15/class"
        )
        try:
            rows = _query_programs(db, age_band="kids")
            row = next((r for r in rows if r["name"] == f"Kids Swim {suf}"), None)
            assert row is not None
            assert row["detail"] == "$22 drop-in"  # offering wins over Program.cost
        finally:
            _cleanup(db, prov, prog)


def test_query_programs_falls_back_to_program_cost():
    with SessionLocal() as db:
        prov, prog, suf = _seed_program_with_offering(
            db, offering_price_text=None, program_cost="$15/class"
        )
        try:
            rows = _query_programs(db, age_band="kids")
            row = next((r for r in rows if r["name"] == f"Kids Swim {suf}"), None)
            assert row is not None
            assert row["detail"] == "$15/class"
        finally:
            _cleanup(db, prov, prog)
