"""Integration coverage for Provider.slug (migration + ORM behavior)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine
from app.db.models import Provider
from app.utils.slug import slugify


def test_provider_slug_column_exists_after_migration() -> None:
    insp = inspect(engine)
    names = {c["name"] for c in insp.get_columns("providers")}
    assert "slug" in names


def test_provider_slug_column_not_null_sqlite() -> None:
    if not str(engine.url).startswith("sqlite"):
        pytest.skip("PRAGMA table_info is SQLite-specific")
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(providers)")).fetchall()
    slug_row = next(r for r in rows if r[1] == "slug")
    assert slug_row[3] == 1  # NOT NULL flag


def test_no_providers_with_null_slug_after_migration() -> None:
    with SessionLocal() as db:
        n_null = db.scalar(
            select(func.count()).select_from(Provider).where(Provider.slug.is_(None))
        )
    assert n_null == 0


def test_provider_slug_assigned_on_insert_when_omitted() -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"Slug Insert Test {suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="other",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-slug-migration",
        )
        db.add(p)
        db.commit()
        pid = p.id

    with SessionLocal() as db:
        loaded = db.get(Provider, pid)
        assert loaded is not None
        assert loaded.slug == slugify(name)


def test_provider_slug_collision_suffixed() -> None:
    base = f"Duplicate Plumbing Co {uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        p1 = Provider(
            provider_name=base,
            category="other",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-slug-migration",
        )
        p2 = Provider(
            provider_name=base,
            category="other",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-slug-migration",
        )
        db.add(p1)
        db.add(p2)
        db.commit()
        s1, s2 = p1.slug, p2.slug

    slugs = sorted({s1, s2})
    assert slugs[0] == base.lower().replace(" ", "-")
    assert slugs[1] == f"{slugs[0]}-2"


def test_provider_slug_unique_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    shared = f"manual-slug-{suf}"
    with SessionLocal() as db:
        a = Provider(
            provider_name=f"A {suf}",
            category="other",
            slug=shared,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-slug-migration",
        )
        b = Provider(
            provider_name=f"B {suf}",
            category="other",
            slug=shared,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-slug-migration",
        )
        db.add(a)
        db.flush()
        db.add(b)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
