"""C-2 — cuisine derived deterministically from Google restaurant types."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories.queries import (
    CategoryFacets,
    available_cuisines_for_route,
    category_listing,
)
from app.categories.subcategories import (
    cuisine_label,
    cuisine_slugs_in_order,
    derive_cuisine,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider


def test_primary_type_maps_to_cuisine() -> None:
    assert derive_cuisine("mexican_restaurant", None) == "mexican"
    assert derive_cuisine("italian_restaurant", None) == "italian"
    assert derive_cuisine("japanese_restaurant", None) == "japanese"
    assert derive_cuisine("hamburger_restaurant", None) == "burgers"


def test_pizza_beats_italian() -> None:
    # A pizzeria tagged both should read as Pizza, not Italian.
    assert derive_cuisine("pizza_restaurant", ["italian_restaurant"]) == "pizza"


def test_sushi_is_japanese() -> None:
    assert derive_cuisine("sushi_restaurant", None) == "japanese"


def test_secondary_types_are_considered() -> None:
    assert derive_cuisine("restaurant", ["mexican_restaurant", "bar"]) == "mexican"


def test_json_string_categories_are_parsed() -> None:
    assert derive_cuisine("restaurant", '["seafood_restaurant"]') == "seafood"


def test_american_is_a_fallback_not_a_winner_over_specific() -> None:
    # american token present alongside mexican -> mexican wins (listed first).
    assert derive_cuisine("mexican_restaurant", ["american_restaurant"]) == "mexican"
    # american alone still resolves.
    assert derive_cuisine("american_restaurant", None) == "american"


def test_no_cuisine_when_no_match() -> None:
    assert derive_cuisine("restaurant", None) is None
    assert derive_cuisine(None, None) is None
    assert derive_cuisine("plumber", ["hardware_store"]) is None


def test_labels_and_order() -> None:
    assert cuisine_label("mexican") == "Mexican"
    assert cuisine_label("bbq") == "BBQ"
    assert cuisine_label(None) is None
    order = cuisine_slugs_in_order()
    # Pizza precedes Italian; american/diner are last-ish fallbacks.
    assert order.index("pizza") < order.index("italian")
    assert order.index("mexican") < order.index("american")


# --- Integration: cuisine chips + facet filtering on the eat-drink page --------

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


def _make_restaurant(name: str, primary: str) -> Provider:
    return Provider(
        provider_name=name,
        category="restaurant",  # in CATEGORY_FILTERS["eat-drink"]
        google_primary_category=primary,
        verified=False,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-cuisine",
    )


def test_cuisine_chips_and_facet_filter() -> None:
    # Two providers per cuisine: chips gate on the cuisine RENDER gate
    # (CUISINE_PAGE_MIN_PROVIDERS = 2, 2026-07-01 audit A4), not bare presence.
    suf = uuid.uuid4().hex[:8]
    mx = f"Los Test Tacos {suf}"
    it = f"Test Trattoria {suf}"
    with SessionLocal() as db:
        a = _make_restaurant(mx, "mexican_restaurant")
        b = _make_restaurant(it, "italian_restaurant")
        a2 = _make_restaurant(f"Dos Test Tacos {suf}", "mexican_restaurant")
        b2 = _make_restaurant(f"Test Osteria {suf}", "italian_restaurant")
        for p in (a, b, a2, b2):
            db.add(p)
        db.commit()
        eids = [a.entity_id, b.entity_id, a2.entity_id, b2.entity_id]

    try:
        with SessionLocal() as db:
            chips = available_cuisines_for_route(db, "eat-drink")
            chip_slugs = {c["slug"] for c in chips}
            assert {"mexican", "italian"} <= chip_slugs

            cards, _total = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(cuisine="mexican")
            )
            names = {c["name"] for c in cards}
            assert mx in names
            assert it not in names
            # The card carries its cuisine token.
            mx_card = next(c for c in cards if c["name"] == mx)
            assert mx_card["cuisine"] == "mexican"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()
