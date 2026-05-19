"""Phase 6.3 — seasonal hours resolution + profile VM wiring."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Category, District, Entity, Provider
from app.providers import queries, view_models


def _winter_hours() -> dict:
    return {
        "monday": [{"open": "09:00", "close": "17:00"}],
        "tuesday": [{"open": "09:00", "close": "17:00"}],
    }


def _summer_hours() -> dict:
    return {
        "monday": [{"open": "08:00", "close": "20:00"}],
    }


def _seasonal_json() -> dict:
    return {
        "summer": {"hours": _summer_hours()},
        "fall": {"hours": {"monday": [{"open": "10:00", "close": "16:00"}]}},
        "winter": {"hours": _winter_hours(), "status_copy": "Winter hours (Nov 1 - Apr 30)"},
        "spring": {"hours": {"monday": [{"open": "09:00", "close": "18:00"}]}},
    }


def test_effective_seasonal_hours_null_json() -> None:
    ent = Entity(name="X", entity_type="place", slug="x", source="test")
    ent.seasonal_hours = None
    assert queries.effective_seasonal_hours(ent) == (None, None, None)


def test_effective_seasonal_hours_non_dict() -> None:
    ent = Entity(name="X", entity_type="place", slug="x2", source="test")
    ent.seasonal_hours = ["not", "a", "dict"]
    assert queries.effective_seasonal_hours(ent) == (None, None, None)


def test_winter_active_mid_january() -> None:
    ent = Entity(name="Park", entity_type="place", slug="park-w", source="test")
    ent.seasonal_hours = _seasonal_json()
    now = datetime(2026, 1, 15, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    season, rows, copy = queries.effective_seasonal_hours(ent, now=now)
    assert season == "winter"
    assert rows == _winter_hours()
    assert copy is not None and "Winter" in copy


def test_summer_active_mid_july() -> None:
    ent = Entity(name="Park", entity_type="place", slug="park-s", source="test")
    ent.seasonal_hours = _seasonal_json()
    now = datetime(2026, 7, 15, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    season, rows, copy = queries.effective_seasonal_hours(ent, now=now)
    assert season == "summer"
    assert rows == _summer_hours()
    assert copy is not None and "Summer" in copy


def test_fall_active_october() -> None:
    ent = Entity(name="Park", entity_type="place", slug="park-f", source="test")
    ent.seasonal_hours = _seasonal_json()
    now = datetime(2026, 10, 15, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    season, rows, _copy = queries.effective_seasonal_hours(ent, now=now)
    assert season == "fall"
    assert rows is not None


def test_spring_active_may_edge() -> None:
    ent = Entity(name="Park", entity_type="place", slug="park-sp", source="test")
    ent.seasonal_hours = _seasonal_json()
    now = datetime(2026, 5, 15, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    season, rows, copy = queries.effective_seasonal_hours(ent, now=now)
    assert season == "spring"
    assert rows is not None
    assert copy is not None and "Spring" in copy


def test_profile_vm_uses_seasonal_hours_when_present() -> None:
    suf = uuid.uuid4().hex[:8]
    fixed = datetime(2026, 1, 15, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        cat = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
        assert cat is not None
        p = Provider(
            provider_name=f"Seasonal Cafe {suf}",
            category="restaurant",
            category_id=cat.id,
            hours="Call for hours",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase63",
            slug=f"seasonal-cafe-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.seasonal_hours = _seasonal_json()
        db.commit()

    with SessionLocal() as db:
        prov = queries.get_provider_by_slug(db, f"seasonal-cafe-{suf}")
        assert prov is not None
        vm = view_models.build(prov, db=db, now=fixed)
        assert vm.seasonal_hours_active_season == "winter"
        assert vm.seasonal_hours_active_rows == _winter_hours()
        assert vm.season_status_copy is not None
        assert vm.hours_structured == _winter_hours()

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.slug == f"seasonal-cafe-{suf}"))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_profile_vm_falls_back_without_seasonal_hours() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
        assert cat is not None
        p = Provider(
            provider_name=f"Plain Cafe {suf}",
            category="restaurant",
            category_id=cat.id,
            hours="Mon-Fri 9-5",
            hours_structured={"monday": [{"open": "09:00", "close": "17:00"}]},
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase63",
            slug=f"plain-cafe-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

    with SessionLocal() as db:
        prov = queries.get_provider_by_slug(db, f"plain-cafe-{suf}")
        assert prov is not None
        vm = view_models.build(prov, db=db)
        assert vm.seasonal_hours_active_season is None
        assert vm.seasonal_hours_active_rows is None
        assert vm.hours_freetext == "Mon-Fri 9-5"

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_district_chip_url_on_profile() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
        dist = db.scalars(select(District).where(District.slug == "english-village")).first()
        assert cat is not None and dist is not None
        p = Provider(
            provider_name=f"District Cafe {suf}",
            category="restaurant",
            category_id=cat.id,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase63",
            slug=f"district-cafe-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.district_id = dist.id
        db.commit()

    with SessionLocal() as db:
        prov = queries.get_provider_by_slug(db, f"district-cafe-{suf}")
        assert prov is not None
        vm = view_models.build(prov, db=db)
        assert vm.district_chip_url == "/district/english-village"
        assert vm.district_chip_name is not None

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()
