"""Phase 6.2 — Tier 1 category landing template + Eat & Drink proof."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.timezone import LAKE_HAVASU_TZ
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


def test_all_tier1_category_slugs_return_200(client: TestClient) -> None:
    slugs = (
        "eat-drink",
        "on-the-water",
        "home-property-services",
        "health-wellness-care",
        "auto-rv-fuel",
        "shopping-essentials",
        "events",
        "outdoors-parks-trails",
        "classes-sports-recreation",
        "lodging-vacation-rentals",
        "pets",
        "public-civic-resources",
    )
    for slug in slugs:
        r = client.get(f"/category/{slug}")
        assert r.status_code == 200, slug


@pytest.mark.parametrize(
    ("slug", "chip_label"),
    [
        ("on-the-water", "Marinas"),
        ("home-property-services", "Plumber"),
        ("health-wellness-care", "Doctor"),
        ("auto-rv-fuel", "Auto repair"),
        ("shopping-essentials", "Grocery"),
        ("events", "Event venues"),
        ("outdoors-parks-trails", "Parks"),
        ("classes-sports-recreation", "Daycare"),
        ("lodging-vacation-rentals", "Hotels"),
        ("pets", "Pet stores"),
        ("public-civic-resources", "Library"),
    ],
)
def test_category_chip_dispatcher_renders_sub_trade(
    client: TestClient, slug: str, chip_label: str
) -> None:
    r = client.get(f"/category/{slug}")
    assert r.status_code == 200
    assert chip_label in r.text


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
def test_category_sort_default_matches_brief(
    client: TestClient, slug: str, expected_sort: str
) -> None:
    from app.api.routes import category_pages

    cfg = category_pages.category_page_config(slug)
    assert cfg.sort_default == expected_sort
    r = client.get(f"/category/{slug}")
    assert r.status_code == 200
    assert f'sort={expected_sort}' in r.text or expected_sort in r.text


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
    assert "/district/english-village" in r.text
    assert "English Village" in r.text or "english-village" in r.text.lower()

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


def test_eat_drink_renders_shell_and_footer(client: TestClient) -> None:
    r = client.get("/category/eat-drink")
    assert r.status_code == 200
    body = r.text
    assert "Eat &amp; Drink" in body
    assert "category-sponsor-slot" in body
    assert "Dock-and-dine" in body


def test_sparse_banner_when_stream_short(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from app.api.routes import category_pages

    monkeypatch.setattr(
        category_pages.provider_queries,
        "build_card_view_model",
        lambda *_args, **_kw: None,
    )
    r = client.get("/category/eat-drink")
    assert r.status_code == 200
    assert "still building this section" in r.text.lower()


def test_cuisine_filter_mexican(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        mx = Provider(
            provider_name=f"Taqueria Phase62 {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="mexican_restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
            hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
        )
        it = Provider(
            provider_name=f"Trattoria Phase62 {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="italian_restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
            hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
        )
        db.add(mx)
        db.add(it)
        db.commit()
        mx_eid = mx.entity_id
        it_eid = it.entity_id

    r = client.get("/category/eat-drink?cuisine=mexican")
    assert r.status_code == 200
    assert f"Taqueria Phase62 {suf}" in r.text
    assert f"Trattoria Phase62 {suf}" not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_([mx_eid, it_eid])))
        db.execute(delete(Entity).where(Entity.id.in_([mx_eid, it_eid])))
        db.commit()


def test_sort_alphabetical(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        a = Provider(
            provider_name=f"AAA Eatery {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        z = Provider(
            provider_name=f"ZZZ Eatery {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        db.add(a)
        db.add(z)
        db.commit()
        ae = a.entity_id
        ze = z.entity_id

    r = client.get("/category/eat-drink?sort=alphabetical")
    assert r.status_code == 200
    ia = r.text.index(f"AAA Eatery {suf}")
    iz = r.text.index(f"ZZZ Eatery {suf}")
    assert ia < iz

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_([ae, ze])))
        db.execute(delete(Entity).where(Entity.id.in_([ae, ze])))
        db.commit()


def test_district_filter_matches_slug(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        dist = db.scalars(select(District).where(District.slug == "english-village")).first()
        assert dist is not None
        inner = Provider(
            provider_name=f"Village Cafe {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="cafe",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        outer = Provider(
            provider_name=f"North Grill {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        db.add(inner)
        db.add(outer)
        db.commit()
        ie = inner.entity_id
        oe = outer.entity_id
        ent_inner = db.get(Entity, ie)
        ent_outer = db.get(Entity, oe)
        assert ent_inner is not None and ent_outer is not None
        ent_inner.district_id = dist.id
        ent_outer.district_id = None
        db.commit()

    r = client.get("/category/eat-drink?district=english-village")
    assert r.status_code == 200
    assert f"Village Cafe {suf}" in r.text
    assert f"North Grill {suf}" not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_([ie, oe])))
        db.execute(delete(Entity).where(Entity.id.in_([ie, oe])))
        db.commit()


def test_open_now_filter(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from app.api.routes import category_pages

    fixed = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    monkeypatch.setattr(category_pages, "now_lake_havasu", lambda: fixed)

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        open_p = Provider(
            provider_name=f"Open Now Diner {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
            hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
        )
        closed_p = Provider(
            provider_name=f"Closed Cafe {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="cafe",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
            hours_structured={"monday": [{"open": "17:00", "close": "20:00"}]},
        )
        db.add(open_p)
        db.add(closed_p)
        db.commit()
        oe = open_p.entity_id
        ce = closed_p.entity_id

    r = client.get("/category/eat-drink?open=now")
    assert r.status_code == 200
    assert f"Open Now Diner {suf}" in r.text
    assert f"Closed Cafe {suf}" not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_([oe, ce])))
        db.execute(delete(Entity).where(Entity.id.in_([oe, ce])))
        db.commit()


def test_inactive_entity_hidden(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        p = Provider(
            provider_name=f"Inactive Listing {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.is_active = False
        db.commit()

    r = client.get("/category/eat-drink")
    assert r.status_code == 200
    assert f"Inactive Listing {suf}" not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_combined_filters(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import category_pages

    fixed = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    monkeypatch.setattr(category_pages, "now_lake_havasu", lambda: fixed)

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        dist = db.scalars(select(District).where(District.slug == "english-village")).first()
        assert dist is not None
        match = Provider(
            provider_name=f"Dock MX Combo {suf}",
            category="restaurant",
            category_id=eat_id,
            google_primary_category="mexican_restaurant",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
            hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
        )
        db.add(match)
        db.commit()
        eid = match.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.district_id = dist.id
        ent.boat_access = {"dock": True}
        db.commit()

    url = "/category/eat-drink?cuisine=mexican&district=english-village&open=now&dock=1"
    r = client.get(url)
    assert r.status_code == 200
    assert f"Dock MX Combo {suf}" in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_category_css_mobile_then_desktop_rules() -> None:
    css = (Path(__file__).resolve().parents[1] / "app/static/styles/category_landing.css").read_text(
        encoding="utf-8"
    )
    assert "overflow-x: auto" in css
    assert "@media (min-width: 768px)" in css
    assert "flex-wrap: wrap" in css


def test_cat_href_toggle_removes_duplicate_query_keys(client: TestClient) -> None:
    r = client.get("/category/eat-drink?cuisine=mexican&sort=alphabetical")
    assert r.status_code == 200
    assert "cuisine=mexican" in r.text


def test_entity_without_eat_drink_category_not_force_linked(client: TestClient) -> None:
    """Regression: listing queries join entity_categories — orphans stay excluded."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        home_id = db.scalars(select(Category).where(Category.slug == "home-property-services")).first()
        assert home_id is not None
        p = Provider(
            provider_name=f"Plumber Not Food {suf}",
            category="plumbing",
            category_id=home_id.id,
            google_primary_category="plumber",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase62",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

    r = client.get("/category/eat-drink")
    assert r.status_code == 200
    assert f"Plumber Not Food {suf}" not in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()
