"""Singular ``/category/{slug}`` route — P1.1 collapse to plural (D1).

The singular Tier-1 SEO landing surface was retired in favour of the plural
``/categories/{slug}`` Sandstone pages. These tests pin the 301 mapping, the
query-string passthrough, and the helpers that remain live (sort defaults via
``themed_groups``; provider-profile district chips render on their own page).
The old Lake Light rendering tests were removed with the surface.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.routes.category_pages import SINGULAR_TO_PLURAL_REDIRECTS
from app.db.database import SessionLocal
from app.db.models import Category, District, Entity, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _eat_category_id(db) -> int:
    row = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
    assert row is not None
    return row.id


def test_unknown_category_slug_returns_404(client: TestClient) -> None:
    r = client.get("/category/not-a-real-tier1-slug")
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("slug", "dest"),
    [
        ("eat-drink", "/categories/eat-drink"),
        ("on-the-water", "/categories/on-the-water"),
        ("home-property-services", "/categories/home-property-services"),
        ("health-wellness-care", "/categories/health-wellness-care"),
        ("auto-rv-fuel", "/categories/auto-rv-fuel"),
        ("shopping-essentials", "/categories/shopping-essentials"),
        ("classes-sports-recreation", "/categories/classes-sports-recreation"),
        ("lodging-vacation-rentals", "/categories/lodging-vacation-rentals"),
        ("pets", "/categories/pets"),
        ("public-civic-resources", "/categories/public-civic-resources"),
        ("professional-services", "/categories/professional-services"),
        # No plural twin -- follow the BUCKET_SLUG_REDIRECTS precedent.
        ("events", "/categories/things-to-do"),
        ("outdoors-parks-trails", "/categories/on-the-water"),
    ],
)
def test_singular_tier1_slug_301s_to_plural(
    client: TestClient, slug: str, dest: str
) -> None:
    r = client.get(f"/category/{slug}", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == dest


def test_redirect_map_covers_every_tier1_slug() -> None:
    from app.api.routes.category_pages import TIER_1_CATEGORY_SLUGS

    assert set(SINGULAR_TO_PLURAL_REDIRECTS) == set(TIER_1_CATEGORY_SLUGS)


def test_redirect_preserves_query_string(client: TestClient) -> None:
    r = client.get("/category/eat-drink?cuisine=mexican&open=1", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/eat-drink?cuisine=mexican&open=1"


def test_redirect_lands_on_canonical_plural_page(client: TestClient) -> None:
    r = client.get("/category/eat-drink")  # TestClient follows the 301
    assert r.status_code == 200
    assert 'rel="canonical"' in r.text
    assert "/categories/eat-drink" in r.text


@pytest.mark.parametrize(
    ("slug", "expected_sort"),
    [
        ("on-the-water", "closest_now"),
        ("home-property-services", "editorial_pick"),
        ("health-wellness-care", "closest_now"),
        ("auto-rv-fuel", "closest_now"),
        ("shopping-essentials", "closest_now"),
        ("events", "chronological"),
        ("outdoors-parks-trails", "closest_now"),
        ("classes-sports-recreation", "closest_now"),
        ("lodging-vacation-rentals", "closest_now"),
        ("pets", "closest_now"),
        ("public-civic-resources", "closest_now"),
    ],
)
def test_category_sort_default_matches_brief(slug: str, expected_sort: str) -> None:
    from app.api.routes import category_pages

    cfg = category_pages.category_page_config(slug)
    assert cfg.sort_default == expected_sort


def test_provider_profile_district_chip_renders(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        dist = db.scalars(select(District).where(District.slug == "english-village")).first()
        assert dist is not None
        p = Provider(
            provider_name=f"District Profile {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase63",
            slug=f"district-profile-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.district_id = dist.id
        db.commit()
        slug = f"district-profile-{suf}"

    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert f"District Profile {suf}" in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_provider_profile_omits_district_chip_without_district(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        p = Provider(
            provider_name=f"No District {suf}",
            category="restaurant",
            category_id=eat_id,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase63",
            slug=f"no-district-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        slug = f"no-district-{suf}"

    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert 'class="chip district-chip"' not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


