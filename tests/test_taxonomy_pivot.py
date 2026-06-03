"""Taxonomy pivot — list providers by their (Google-derived) subcategory bucket,
not the often-wrong legacy category. Prod audit found 397 misfiled rows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories.queries import (
    CategoryFacets,
    _route_subcategory_slugs,
    category_listing,
)
from app.categories.subcategories import derive_subcategory
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


def _names(cards: list[dict]) -> set[str]:
    return {c["name"] for c in cards}


def test_provider_routes_by_subcategory_not_wrong_legacy_category() -> None:
    """A hospital filed as legacy `retail` but subcategorized `health-medical`
    appears on Health/Services — NOT on Shopping (the audit's core bug)."""
    suf = uuid.uuid4().hex[:8]
    name = f"Test Regional Medical Center {suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="retail",  # WRONG legacy category (shopping bucket)
            subcategory="health-medical",  # correct Google-derived (services bucket)
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-pivot",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with SessionLocal() as db:
            health, _ = category_listing(db, "health-wellness-care", now=_NOW, facets=CategoryFacets())
            services, _ = category_listing(db, "services", now=_NOW, facets=CategoryFacets())
            shopping, _ = category_listing(db, "shopping-essentials", now=_NOW, facets=CategoryFacets())
        assert name in _names(health), "hospital should show on Health"
        assert name in _names(services), "hospital should show on Services"
        assert name not in _names(shopping), "hospital must NOT show on Shopping"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_null_subcategory_falls_back_to_legacy_category() -> None:
    """An un-subcategorized provider still routes by its legacy category, so
    nothing drops off until it's been classified."""
    suf = uuid.uuid4().hex[:8]
    name = f"Unclassified Shop {suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="retail",
            subcategory=None,  # not yet classified -> legacy fallback
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-pivot",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with SessionLocal() as db:
            shopping, _ = category_listing(db, "shopping-essentials", now=_NOW, facets=CategoryFacets())
        assert name in _names(shopping)
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_route_subcategory_slugs_mapping() -> None:
    # Tile route owns a slice; mega route owns its whole bucket.
    assert _route_subcategory_slugs("health-wellness-care") == {"health-medical"}
    assert _route_subcategory_slugs("public-civic-resources") == {"civic-community"}
    assert "health-medical" in _route_subcategory_slugs("services")
    assert "beauty" in _route_subcategory_slugs("services")
    assert _route_subcategory_slugs("eat-drink") >= {"restaurants", "bars-breweries"}


def test_barber_matcher_no_longer_files_as_bar() -> None:
    """Matcher fix: 'barber_shop'/'barbecue' contain 'bar' but must not become
    bars-breweries (prod bug)."""
    assert derive_subcategory(category=None, google_primary_category="barber_shop") == "beauty"
    assert derive_subcategory(category=None, google_primary_category="barbecue_restaurant") == "restaurants"
    # A real bar still resolves correctly.
    assert derive_subcategory(category=None, google_primary_category="bar") == "bars-breweries"
    assert derive_subcategory(category=None, google_primary_category="wine_bar") == "bars-breweries"
