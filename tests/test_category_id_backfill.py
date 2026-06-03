"""Tests for the Provider.category_id backfill plan + migration logic."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from app.categories.backfill_plan import (
    LEGACY_TO_BUCKET,
    NEW_BUCKETS,
    reverse_backfill,
    seed_and_backfill,
)
from app.categories.queries import CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.db.models import Category, Provider


def test_plan_targets_are_real_routes() -> None:
    routes = set(CATEGORY_FILTERS.keys())
    for _slug, _name, _order in NEW_BUCKETS:
        assert _slug in routes, f"seeded bucket {_slug} is not a real tier-1 route"
    for legacy, bucket in LEGACY_TO_BUCKET.items():
        assert bucket in routes, f"{legacy} -> {bucket} is not a real route"


def test_seeded_buckets_present_after_migration() -> None:
    """The migration ran at test-DB setup, so the new buckets exist."""
    with SessionLocal() as db:
        slugs = {c.slug for c in db.query(Category).all()}
    for slug, _name, _order in NEW_BUCKETS:
        assert slug in slugs


def test_seed_and_backfill_assigns_null_rows_and_is_reversible() -> None:
    suf = uuid.uuid4().hex[:8]
    slug = f"ttd-{suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Things Provider {suf}",
            slug=slug,
            category="things-to-do",  # legacy value mapped by the plan
            category_id=None,
            source="test-backfill",
            draft=False,
            is_active=True,
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

        # Apply the plan, then confirm this NULL row now points at things-to-do.
        seed_and_backfill(db.connection())
        db.commit()
        ttd = db.scalars(select(Category).where(Category.slug == "things-to-do")).first()
        refreshed = db.scalars(select(Provider).where(Provider.slug == slug)).first()
        assert ttd is not None
        assert refreshed.category_id == ttd.id

        # Reverse: the row goes back to NULL.
        reverse_backfill(db.connection())
        db.commit()
        refreshed2 = db.scalars(select(Provider).where(Provider.slug == slug)).first()
        assert refreshed2.category_id is None

        # cleanup
        db.execute(delete(Provider).where(Provider.slug == slug))
        if eid:
            from app.db.models import Entity

            db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_existing_category_id_is_never_overwritten() -> None:
    suf = uuid.uuid4().hex[:8]
    slug = f"keep-{suf}"
    with SessionLocal() as db:
        eat = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
        p = Provider(
            provider_name=f"Keep {suf}",
            slug=slug,
            category="things-to-do",
            category_id=eat.id,  # already assigned — must be preserved
            source="test-backfill",
            draft=False,
            is_active=True,
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

        seed_and_backfill(db.connection())
        db.commit()
        refreshed = db.scalars(select(Provider).where(Provider.slug == slug)).first()
        assert refreshed.category_id == eat.id  # untouched

        db.execute(delete(Provider).where(Provider.slug == slug))
        if eid:
            from app.db.models import Entity

            db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()
