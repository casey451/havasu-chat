"""Canonical-domain consolidation (askhava.com, 2026-06).

Covers:
1. ``base_url()`` defaults to https://askhava.com (env ``BASE_URL`` still wins).
2. ``CanonicalHostRedirectMiddleware`` — legacy Railway-host traffic 301s to
   the same path + query on askhava.com; POST gets a method-preserving 308;
   ``/health`` is exempt (Railway liveness probe); non-alias hosts (the
   TestClient's ``testserver``, localhost) pass through; loop guard when a
   stale ``BASE_URL`` still points at the legacy host.
3. Leaf-page surface check: canonical + og:url emit the askhava.com origin.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seo.urls import base_url

_LEGACY = "havasu-chat-production.up.railway.app"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _default_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the shipped default unless a test sets BASE_URL itself."""
    monkeypatch.delenv("BASE_URL", raising=False)


# --- base_url default --------------------------------------------------------


def test_base_url_defaults_to_askhava() -> None:
    assert base_url() == "https://askhava.com"


def test_base_url_env_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "https://staging.example.test/")
    assert base_url() == "https://staging.example.test"


# --- legacy-host redirect -----------------------------------------------------


def test_legacy_host_get_301s_to_askhava_same_path(client: TestClient) -> None:
    r = client.get(
        "/categories", headers={"host": _LEGACY}, follow_redirects=False
    )
    assert r.status_code == 301
    assert r.headers["location"] == "https://askhava.com/categories"


def test_legacy_host_redirect_preserves_query(client: TestClient) -> None:
    r = client.get(
        "/chat?q=plumbers", headers={"host": _LEGACY}, follow_redirects=False
    )
    assert r.status_code == 301
    assert r.headers["location"] == "https://askhava.com/chat?q=plumbers"


def test_legacy_host_post_gets_method_preserving_308(client: TestClient) -> None:
    r = client.post(
        "/api/chat", headers={"host": _LEGACY}, follow_redirects=False, json={}
    )
    assert r.status_code == 308
    assert r.headers["location"] == "https://askhava.com/api/chat"


def test_legacy_host_health_is_exempt(client: TestClient) -> None:
    """Railway's liveness probe hits the service domain — must stay 200."""
    r = client.get("/health", headers={"host": _LEGACY}, follow_redirects=False)
    assert r.status_code == 200


def test_normal_host_passes_through(client: TestClient) -> None:
    """testserver (and any non-alias host) is never redirected."""
    r = client.get("/robots.txt", follow_redirects=False)
    assert r.status_code == 200


def test_loop_guard_when_base_url_is_still_legacy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale BASE_URL pointing at the legacy host must not redirect-loop."""
    monkeypatch.setenv("BASE_URL", f"https://{_LEGACY}")
    r = client.get("/robots.txt", headers={"host": _LEGACY}, follow_redirects=False)
    assert r.status_code == 200


# --- surface check: canonical / og:url / robots on the new origin -------------


def test_robots_and_canonical_emit_askhava(client: TestClient) -> None:
    r = client.get("/robots.txt")
    assert "Sitemap: https://askhava.com/sitemap.xml" in r.text

    r = client.get("/home")
    assert '<link rel="canonical" href="https://askhava.com/home">' in r.text
    assert 'property="og:url" content="https://askhava.com/home"' in r.text


def test_leaf_page_canonical_and_og_use_askhava(client: TestClient) -> None:
    """The user-facing acceptance check: a taxonomy leaf page emits the
    askhava.com origin in canonical + og:url. Seeds a minimal dept/leaf."""
    from uuid import uuid4

    from sqlalchemy import select

    from app.categories import leaf_pages
    from app.db.database import SessionLocal
    from app.db.models import Category, Entity, EntityCategory, Provider

    source = "test-canonical-host"
    suf = uuid4().hex[:6]
    dept_slug = f"canon-dept-{suf}"
    leaf_slug = f"canon-leaf-{suf}"
    with SessionLocal() as db:
        dept = Category(slug=dept_slug, name="Canon Dept", sort_order=0, level=0)
        db.add(dept)
        db.flush()
        leaf = Category(
            slug=leaf_slug, name="Canon Leaf", sort_order=0, level=1, parent_id=dept.id
        )
        db.add(leaf)
        db.flush()
        for i in range(leaf_pages.LEAF_PAGE_MIN_PROVIDERS):
            ent = Entity(
                entity_type="commercial",
                slug=f"ch-ent-{uuid4().hex[:10]}",
                name=f"Canon Biz {i}",
                source=source,
            )
            db.add(ent)
            db.flush()
            db.add(
                Provider(
                    provider_name=f"Canon Biz {i}",
                    category="x",
                    slug=f"ch-prov-{uuid4().hex[:10]}",
                    is_active=True,
                    draft=False,
                    source=source,
                    entity_id=ent.id,
                )
            )
            db.add(
                EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True)
            )
        db.commit()
    try:
        r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
        assert r.status_code == 200
        page = f"https://askhava.com/categories/{dept_slug}/{leaf_slug}"
        assert f'<link rel="canonical" href="{page}">' in r.text
        assert f'property="og:url" content="{page}"' in r.text
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(
                select(Provider).where(Provider.source == source)
            ).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == source)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            for cat in db.scalars(
                select(Category).where(Category.slug.in_([dept_slug, leaf_slug]))
            ).all():
                db.delete(cat)
            db.commit()
