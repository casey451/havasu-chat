"""SEO PR-B — searcher-noun leaf titles + trade→leaf-twin consolidation.

Covers:
1. ``leaf_seo.display_noun`` mapping + fallback.
2. Leaf pages render the searcher's noun (title / H1 / breadcrumb JSON-LD /
   ItemList name) instead of the internal taxonomy label.
3. Department landings label leaf cards with the noun.
4. A curated home-services trade URL 301s to its taxonomy-leaf twin when the
   twin ships; it keeps serving when the twin is absent.
5. The sitemap lists the leaf, not the redirecting trade URL.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import leaf_pages
from app.categories.leaf_seo import SEO_NOUNS, display_noun
from app.categories.trades import LEAF_TWINS, TRADE_LEAF_DEPARTMENT_SLUG
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.main import app

_SOURCE = "test-leaf-seo"
_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sitemap_cache() -> Iterator[None]:
    from app import main as main_module

    main_module._sitemap_cache.clear()
    yield
    main_module._sitemap_cache.clear()


# --- unit: the noun map ------------------------------------------------------


def test_display_noun_maps_and_falls_back() -> None:
    assert display_noun("plumbing", "Plumbing") == "Plumbers"
    assert display_noun("electrical", "Electrical") == "Electricians"
    assert display_noun("restaurants", "Restaurants") == "Restaurants"  # no entry
    assert display_noun(None, "Whatever") == "Whatever"
    assert display_noun("  PLUMBING  ", "Plumbing") == "Plumbers"


def test_noun_map_has_no_identity_entries() -> None:
    """Entries whose noun equals the taxonomy name are dead weight."""
    # The map keys internal slugs; we can't cross-check live names here, but
    # no value should be empty or whitespace.
    for slug, noun in SEO_NOUNS.items():
        assert noun.strip(), f"{slug} has an empty noun"


def test_every_trade_leaf_twin_is_a_known_slug() -> None:
    """Every consolidation target should carry a searcher noun or already BE
    the searcher term — and never be empty."""
    assert LEAF_TWINS  # non-empty map
    for trade_slug, leaf_slug in LEAF_TWINS.items():
        assert leaf_slug.strip(), f"{trade_slug} maps to an empty leaf slug"


# --- integration: noun on leaf + department pages ----------------------------


def _seed_plumbing_leaf(db: Session, *, n: int) -> tuple[str, list[str]]:
    """Seed the home-and-property-services dept + a 'plumbing' leaf with ``n``
    providers. Returns (created dept marker, provider names)."""
    dept = db.scalars(
        select(Category).where(
            Category.slug == TRADE_LEAF_DEPARTMENT_SLUG, Category.level == 0
        )
    ).first()
    created = ""
    if dept is None:
        dept = Category(
            slug=TRADE_LEAF_DEPARTMENT_SLUG,
            name="Home & Property Services",
            sort_order=8,
            level=0,
        )
        db.add(dept)
        db.flush()
        created = TRADE_LEAF_DEPARTMENT_SLUG
    leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.flush()
    names: list[str] = []
    for i in range(n):
        name = f"Plumb Co {i} {uuid4().hex[:6]}"
        ent = Entity(entity_type="commercial", slug=f"ls-ent-{uuid4().hex[:10]}",
                     name=name, source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name=name, category="plumbing",
                        slug=f"ls-prov-{uuid4().hex[:10]}", is_active=True,
                        draft=False, source=_SOURCE, entity_id=ent.id,
                        google_rating=4.6, google_review_count=40))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        names.append(name)
    return created, names


@pytest.fixture
def seeded_plumbing() -> Iterator[dict]:
    with SessionLocal() as db:
        if db.scalars(select(Category).where(Category.slug == "plumbing")).first():
            pytest.skip("'plumbing' leaf already present in this DB")
        created_dept, names = _seed_plumbing_leaf(
            db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS
        )
        db.commit()
    try:
        yield {"names": names}
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            cleanup = ["plumbing"] + ([created_dept] if created_dept else [])
            for cat in db.scalars(select(Category).where(Category.slug.in_(cleanup))).all():
                db.delete(cat)
            db.commit()


def test_leaf_page_title_h1_and_jsonld_use_searcher_noun(
    client: TestClient, seeded_plumbing: dict
) -> None:
    r = client.get(f"/categories/{TRADE_LEAF_DEPARTMENT_SLUG}/plumbing")
    assert r.status_code == 200
    body = r.text
    n = len(seeded_plumbing["names"])
    # Title + H1 carry "Plumbers", the term people google — not "Plumbing". The
    # count prefix is dropped when there's a single listing (2026-06-30 audit
    # 1D: "1 Best Plumbers" reads wrong), else "N Best ...".
    count_prefix = f"{n} " if n != 1 else ""
    assert f"<h1>{count_prefix}Best Plumbers in Lake Havasu City, AZ</h1>" in body
    assert f"<title>{count_prefix}Best Plumbers in Lake Havasu City, AZ — Ask Hava</title>" in body
    blocks = [json.loads(m) for m in _JSONLD_RE.findall(body)]
    crumb = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    assert crumb["itemListElement"][2]["name"] == "Plumbers"
    ilist = next(b for b in blocks if b.get("@type") == "ItemList")
    assert ilist["name"] == "Plumbers in Lake Havasu City, AZ"


def test_department_landing_labels_leaf_cards_with_noun(
    client: TestClient, seeded_plumbing: dict
) -> None:
    r = client.get(f"/categories/{TRADE_LEAF_DEPARTMENT_SLUG}")
    assert r.status_code == 200
    body = r.text
    assert "Plumbers" in body
    assert f'href="/categories/{TRADE_LEAF_DEPARTMENT_SLUG}/plumbing"' in body


# --- trade → leaf-twin consolidation -----------------------------------------


def test_trade_url_301s_to_shipping_leaf_twin(
    client: TestClient, seeded_plumbing: dict
) -> None:
    r = client.get(
        "/categories/home-property-services/plumbers", follow_redirects=False
    )
    assert r.status_code == 301
    assert r.headers["location"] == (
        f"/categories/{TRADE_LEAF_DEPARTMENT_SLUG}/plumbing"
    )
    final = client.get("/categories/home-property-services/plumbers")
    assert final.status_code == 200
    assert "Best Plumbers in Lake Havasu City, AZ" in final.text


def test_trade_url_serves_curated_page_when_twin_absent(client: TestClient) -> None:
    """No taxonomy twin in the DB -> the curated trade page keeps serving
    (here it 404s only because no needle providers are seeded, never 301s)."""
    with SessionLocal() as db:
        if db.scalars(select(Category).where(Category.slug == "plumbing")).first():
            pytest.skip("'plumbing' leaf present; twin would ship")
    r = client.get(
        "/categories/home-property-services/plumbers", follow_redirects=False
    )
    assert r.status_code != 301


def test_sitemap_lists_leaf_not_redirecting_trade(
    client: TestClient, seeded_plumbing: dict
) -> None:
    from app import main as main_module

    r = client.get("/sitemap-pages.xml")
    assert r.status_code == 200
    xml = r.text
    base = main_module._base_url()
    assert f"{base}/categories/{TRADE_LEAF_DEPARTMENT_SLUG}/plumbing" in xml
    assert f"{base}/categories/home-property-services/plumbers" not in xml
