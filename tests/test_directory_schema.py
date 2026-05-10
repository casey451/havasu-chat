"""Tests for directory pivot V1 schema (Category + FKs + Provider attributes/district)."""

from __future__ import annotations

import uuid
from datetime import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.models import Category, Program, Provider

_EXPECTED_CATEGORY_SLUGS = [
    "eat-and-drink",
    "events",
    "family",
    "home-services",
    "health",
    "on-the-water",
    "outdoors-and-parks",
    "shopping",
    "auto-and-gas",
    "lodging",
    "pets",
    "community",
]


def test_twelve_seeded_categories_exist_and_ordered() -> None:
    """Migration seeds 12 rows; slug set and sort_order ordering match pivot §8.1."""
    with SessionLocal() as db:
        rows = db.query(Category).order_by(Category.sort_order).all()
        assert len(rows) == 12
        assert [c.slug for c in rows] == _EXPECTED_CATEGORY_SLUGS
        orders = [c.sort_order for c in rows]
        assert orders == sorted(orders)


def test_provider_round_trips_category_id_attributes_district_with_legacy_string() -> None:
    suf = uuid.uuid4().hex[:8]
    attrs = {"service_area": "86403", "emergency": True}
    with SessionLocal() as db:
        home = db.query(Category).filter_by(slug="home-services").one()
        home_id = home.id
        p = Provider(
            provider_name=f"RoundTrip Plumbing {suf}",
            category="plumbing",
            category_id=home_id,
            attributes=attrs,
            district="English Village",
            verified=True,
            draft=False,
            is_active=True,
            source="test-directory-schema",
        )
        db.add(p)
        db.commit()
        pid = p.id

    with SessionLocal() as db:
        loaded = db.get(Provider, pid)
        assert loaded is not None
        assert loaded.category == "plumbing"
        assert loaded.category_id == home_id
        assert loaded.attributes == attrs
        assert loaded.district == "English Village"


def test_provider_category_ref_relationship() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="pets").one()
        p = Provider(
            provider_name=f"Vet {suf}",
            category="veterinary",
            category_id=cat.id,
            verified=True,
            draft=False,
            is_active=True,
            source="test-directory-schema",
        )
        db.add(p)
        db.commit()
        pid = p.id

    with SessionLocal() as db:
        loaded = db.get(Provider, pid)
        assert loaded is not None
        db.refresh(loaded, ["category_ref"])
        assert loaded.category_ref is not None
        assert loaded.category_ref.slug == "pets"


def test_program_round_trips_category_id_with_legacy_activity_category() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="family").one()
        family_id = cat.id
        prog = Program(
            title=f"Kids craft {suf}",
            description="Weekly crafts session.",
            activity_category="arts",
            category_id=family_id,
            schedule_days=["saturday"],
            schedule_start_time=time(10, 0),
            schedule_end_time=time(11, 30),
            location_name="Community Center",
            provider_name="City Parks",
            source="test-directory-schema",
        )
        db.add(prog)
        db.commit()
        mid = prog.id

    with SessionLocal() as db:
        loaded = db.get(Program, mid)
        assert loaded is not None
        assert loaded.activity_category == "arts"
        assert loaded.category_id == family_id


def test_program_category_ref_relationship() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="events").one()
        prog = Program(
            title=f"Sunset concert {suf}",
            description="Live music by the lake.",
            activity_category="music",
            category_id=cat.id,
            schedule_days=["friday"],
            schedule_start_time=time(18, 0),
            schedule_end_time=time(21, 0),
            location_name="Rotary Park",
            provider_name="City Events",
            source="test-directory-schema",
        )
        db.add(prog)
        db.commit()
        mid = prog.id

    with SessionLocal() as db:
        loaded = db.get(Program, mid)
        assert loaded is not None
        db.refresh(loaded, ["category_ref"])
        assert loaded.category_ref is not None
        assert loaded.category_ref.slug == "events"


def test_category_slug_uniqueness_enforced() -> None:
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.add(
                Category(
                    slug="eat-and-drink",
                    name="Duplicate",
                    sort_order=999,
                )
            )
            db.commit()
        db.rollback()


def test_provider_legacy_category_string_independent_of_category_id() -> None:
    """Additive schema: free-text `category` remains authoritative until backfill."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        lodging = db.query(Category).filter_by(slug="lodging").one()
        lodging_id = lodging.id
        p = Provider(
            provider_name=f"Motel {suf}",
            category="hotel-motel-free-text",
            category_id=lodging_id,
            verified=True,
            draft=False,
            is_active=True,
            source="test-directory-schema",
        )
        db.add(p)
        db.commit()
        pid = p.id

    with SessionLocal() as db:
        loaded = db.get(Provider, pid)
        assert loaded is not None
        assert loaded.category == "hotel-motel-free-text"
        assert loaded.category_id == lodging_id
