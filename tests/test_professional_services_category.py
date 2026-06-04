"""WP-9 step 2 — the 13th canonical Category ``professional-services``.

Covers the seed/repoint plan (mirrors test_category_id_backfill.py) and the
route pivot: ``/categories/professional-services`` renders, the legacy
``/categories/professional`` 301s to it.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.categories.backfill_plan import (
    PROFESSIONAL_SERVICES_SLUG,
    reverse_professional_services,
    seed_professional_services,
)
from app.categories.queries import CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.db.models import Category, Provider
from app.main import app


def test_professional_services_is_a_real_route() -> None:
    assert PROFESSIONAL_SERVICES_SLUG in CATEGORY_FILTERS
    assert "professional" not in CATEGORY_FILTERS  # pivoted, not duplicated


def test_seed_repoints_null_and_legacy_rows_only_and_is_reversible() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        conn = db.connection()
        counts = seed_professional_services(conn)
        db.commit()

        cat = db.scalars(
            select(Category).where(Category.slug == PROFESSIONAL_SERVICES_SLUG)
        ).first()
        assert cat is not None
        assert cat.name == "Professional Services"

        # NULL category_id row with the canonical primary -> repointed.
        p_null = Provider(
            provider_name=f"Pro Null {suf}",
            slug=f"pro-null-{suf}",
            category="professional_services",
            primary_category=PROFESSIONAL_SERVICES_SLUG,
            category_id=None,
            source="test-ps",
            draft=False,
            is_active=True,
        )
        # Deliberate different assignment -> never clobbered.
        other = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
        p_other = Provider(
            provider_name=f"Pro Other {suf}",
            slug=f"pro-other-{suf}",
            category="professional_services",
            primary_category=PROFESSIONAL_SERVICES_SLUG,
            category_id=other.id if other else None,
            source="test-ps",
            draft=False,
            is_active=True,
        )
        db.add_all([p_null, p_other])
        db.commit()

        try:
            counts = seed_professional_services(db.connection())
            db.commit()
            assert counts["repointed"] >= 1

            db.refresh(p_null)
            db.refresh(p_other)
            assert p_null.category_id == cat.id
            if other is not None:
                assert p_other.category_id == other.id  # untouched

            # Idempotent: second run changes nothing.
            counts2 = seed_professional_services(db.connection())
            db.commit()
            assert counts2 == {"seeded": 0, "repointed": 0}

            # Reversible.
            reverse_professional_services(db.connection())
            db.commit()
            assert (
                db.scalars(
                    select(Category).where(Category.slug == PROFESSIONAL_SERVICES_SLUG)
                ).first()
                is None
            )
            # Restore for other tests (migration state expects the row).
            seed_professional_services(db.connection())
            db.commit()
        finally:
            # tearDown mirrors test_tier2_business_shortcut: leftover providers
            # (and their dual-written entities) pollute later catalog-driven tests.
            for p in (p_null, p_other):
                row = db.get(Provider, p.id)
                if row is not None:
                    db.delete(row)
            db.commit()


def test_route_renders_and_legacy_slug_redirects() -> None:
    client = TestClient(app)
    r = client.get("/categories/professional-services", follow_redirects=False)
    assert r.status_code == 200
    r = client.get("/categories/professional", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/professional-services"
