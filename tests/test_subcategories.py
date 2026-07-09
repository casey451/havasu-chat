"""P0 Task 2 — subcategory taxonomy, derivation, facets, and SEO landing."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.categories import subcategories as subcats
from app.categories.queries import CategoryFacets, category_listing
from app.categories.subcategories import derive_subcategory
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# --- taxonomy ---------------------------------------------------------------


def test_storage_lives_under_services_not_recreation() -> None:
    storage = subcats.subcategory_by_slug("storage")
    assert storage is not None
    assert storage.bucket_id == "services"
    rec_slugs = {s.slug for s in subcats.subcategories_for_bucket("recreation-outdoors")}
    assert "storage" not in rec_slugs
    svc_slugs = {s.slug for s in subcats.subcategories_for_bucket("services")}
    assert "storage" in svc_slugs


def test_marine_trade_subcategories_resolve_to_on_the_water() -> None:
    # 2026-06-13 audit: boat dealers / repair / supply split out of the generic
    # "on-the-water" recreation bucket into their own pages, all folding back to
    # the on-the-water primary.
    from app.categories.subcategories import primary_for_subcategory

    rec_slugs = {s.slug for s in subcats.subcategories_for_bucket("recreation-outdoors")}
    for slug, label in (
        ("marine-dealers", "Boat Dealers"),
        ("marine-repair", "Boat Repair & Mechanics"),
        ("marine-supply", "Marine Supply & Stores"),
    ):
        sub = subcats.subcategory_by_slug(slug)
        assert sub is not None and sub.label == label
        assert slug in rec_slugs
        assert primary_for_subcategory(slug) == "on-the-water"


@pytest.mark.parametrize(
    "name,expected",
    [
        # marine trade routed from the NAME (generic Google types would miss it)
        ("West Marine", "marine-supply"),
        ("Nordic Boats", "marine-dealers"),
        ("Alco Marine Sales & Services", "marine-dealers"),
        ("Shimmer Boat Service", "marine-repair"),
        ("Xtreme Speed And Marine", "marine-repair"),
        ("Prestige Marine", None),  # anchor only, no qualifier -> fall through
        ("Germaine Marine", None),  # anchor only, no qualifier -> fall through
        # NOT marine trade: watersports rentals stay out of the marine split
        ("Lake Havasu Jet Ski Rentals", None),
        ("Wacko kayak & paddleboard rentals", None),
        # no marine anchor at all
        ("Whiz Kid Computer Services / Ink & Toner", None),
    ],
)
def test_derive_subcategory_marine_name_routing(name: str, expected: str | None) -> None:
    from app.categories.subcategories import derive_subcategory

    got = derive_subcategory(category="retail", name=name, google_primary_category="service")
    if expected is None:
        assert got != "marine-dealers" and got != "marine-repair" and got != "marine-supply"
    else:
        assert got == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        # Dojos carry a generic "gym" Google type; the NAME router must override
        # it so the martial-arts subcategory stops rendering empty.
        ("The Tap Room Jiu Jitsu", "martial-arts"),
        ("Lake Havasu Black Belt Academy", "martial-arts"),
        ("Arizona Krav Maga", "martial-arts"),
        ("Havasu Shao-Lin Kempo", "martial-arts"),
        ("Next Generation Mixed Martial Arts", "martial-arts"),
        ("Seibukan Karate-Do", "martial-arts"),
        # NOT martial arts: generic fitness / dance names must not be swept in.
        ("Anytime Fitness", None),
        ("Footlite School of Dance", None),
    ],
)
def test_derive_subcategory_martial_arts_name_routing(name: str, expected: str | None) -> None:
    from app.categories.subcategories import derive_subcategory

    got = derive_subcategory(category="fitness_sports", name=name, google_primary_category="gym")
    if expected is None:
        assert got != "martial-arts"
    else:
        assert got == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        # Property managers carry a generic "lodging" Google type; the NAME
        # router must override it so vacation-rentals stops rendering empty.
        ("Empty Spaces Vacation Rental Management", "vacation-rentals"),
        ("First Choice Property Vacation Rentals", "vacation-rentals"),
        ("Integrity Arizona Vacation Rentals", "vacation-rentals"),
        # NOT a vacation rental: a plain hotel/motel must stay under hotels.
        ("Windsor Inn Lake Havasu City", None),
        # Bare "property management" is intentionally ambiguous -> not routed.
        ("Lake Havasu Property Management", None),
    ],
)
def test_derive_subcategory_vacation_rental_name_routing(name: str, expected: str | None) -> None:
    from app.categories.subcategories import derive_subcategory

    got = derive_subcategory(category="lodging", name=name, google_primary_category="lodging")
    if expected is None:
        assert got != "vacation-rentals"
    else:
        assert got == expected


def test_derive_subcategory_without_name_unchanged() -> None:
    # Backward compatibility: omitting name must not change existing behaviour.
    from app.categories.subcategories import derive_subcategory

    assert derive_subcategory(category="x", google_primary_category="dentist") == "health-medical"
    assert derive_subcategory(category="x", google_primary_category="plumber") == "home-services"


# --- derivation -------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"category": "x", "google_primary_category": "plumber"}, "home-services"),
        ({"category": "x", "google_primary_category": "self_storage"}, "storage"),
        ({"category": "x", "google_primary_category": "dentist"}, "health-medical"),
        ({"category": "x", "google_categories": ["bar", "establishment"]}, "bars-breweries"),
        ({"category": "lodging"}, "hotels"),  # legacy fallback
        ({"category": "professional_services"}, "professional"),
        ({"category": "religion_community"}, "civic-community"),
        ({"category": "totally-unknown-bucket"}, None),  # no guess
    ],
)
def test_derive_subcategory(kwargs: dict, expected: str | None) -> None:
    assert derive_subcategory(**kwargs) == expected


def test_specific_google_type_beats_legacy_bucket() -> None:
    # legacy "services" is vague; the Google type pins it to auto.
    assert (
        derive_subcategory(category="services", google_primary_category="car_repair") == "auto"
    )


# --- facets + SEO landing (integration) ------------------------------------


def _seed(db, *, name: str, category: str, subcategory: str | None, rating: float | None = None) -> str:
    suf = uuid.uuid4().hex[:8]
    p = Provider(
        provider_name=f"{name} {suf}",
        category=category,
        subcategory=subcategory,
        google_rating=rating,
        google_review_count=50 if rating else None,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-subcat",
        slug=f"{name.lower().replace(' ', '-')}-{suf}",
    )
    db.add(p)
    db.commit()
    return p.entity_id


def test_subcategory_seo_landing_renders_and_filters(client: TestClient) -> None:
    ids: list[str] = []
    with SessionLocal() as db:
        ids.append(_seed(db, name="Ace Plumbing", category="home_services", subcategory="home-services", rating=4.8))
        ids.append(_seed(db, name="Bob Electric", category="home_services", subcategory="home-services", rating=3.2))
        ids.append(_seed(db, name="Zed Storage", category="services", subcategory="storage"))
    try:
        r = client.get("/lake-havasu/home-services")
        assert r.status_code == 200
        body = r.text
        # Own headline + active chip + does not leak the storage row.
        assert "Home Services in Lake Havasu City" in body
        assert "Ace Plumbing" in body
        assert "Zed Storage" not in body
        # Top-rated facet drops the 3.2 provider.
        r2 = client.get("/lake-havasu/home-services?rating=4")
        assert "Ace Plumbing" in r2.text
        assert "Bob Electric" not in r2.text
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()


def test_unknown_subcategory_token_is_not_a_landing(client: TestClient) -> None:
    # A token that is neither a subcategory nor a provider slug → 404 (falls
    # through to the provider alias).
    r = client.get("/lake-havasu/definitely-not-a-subcategory-or-business", follow_redirects=False)
    assert r.status_code == 404


def test_category_listing_facets_combine() -> None:
    ids: list[str] = []
    with SessionLocal() as db:
        ids.append(_seed(db, name="Pro One", category="professional_services", subcategory="professional", rating=4.9))
        ids.append(_seed(db, name="Pro Two", category="professional_services", subcategory="professional", rating=2.0))
    try:
        now = now_lake_havasu()
        _, total_all = category_listing(
            SessionLocal(), "services", now=now, facets=CategoryFacets(subcategory="professional")
        )
        _, total_top = category_listing(
            SessionLocal(),
            "services",
            now=now,
            facets=CategoryFacets(subcategory="professional", top_rated=True),
        )
        assert total_all >= 2
        assert total_top < total_all  # the 2.0-rated row is filtered out
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()


def test_plural_page_shows_subcategory_chips(client: TestClient) -> None:
    # WP-5 (C8/N-16): chips are now generated from subtypes ACTUALLY present, so
    # seed one Storage provider under Services for the chip to render.
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Test Self Storage {suf}",
            category="services",
            subcategory="storage",
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-subcats",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
    try:
        r = client.get("/lake-havasu/storage")
        assert r.status_code == 200
        body = r.text
        # Lake Ink & Brass: subcategory chips render in the Subcategory toolbar,
        # each a ``chip`` anchor; the filter/sort toolbar renders below.
        assert 'aria-label="Subcategory"' in body
        assert 'class="chip' in body
        assert "?sub=storage" in body  # Storage subcategory chip present under Services
        assert 'aria-label="Filter and sort"' in body
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


# --- type-token precedence (2026-06-04 category patrol fixes) -----------------
#
# The patrol's first real prod sweep flagged 365 rows, most caused by two bugs
# in _subcat_from_types: (1) rule order was the outer loop, so a generic early
# rule matching a noisy google_categories token outvoted a specific later rule
# matching the primary type; (2) the bare "store" needle substring-matched every
# "*_store" type. Tokens are now decisive in signal order (primary, sub_trades,
# categories array) and "store" matches exactly.


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        # primary type outranks generic array tokens (was: specialty)
        (
            {
                "category": "auto",
                "google_primary_category": "car_dealer",
                "google_categories": ["car_dealer", "store", "point_of_interest"],
            },
            "auto",
        ),
        # "store" no longer substring-swallows specific *_store types
        ({"category": "x", "google_primary_category": "auto_parts_store"}, "auto"),
        ({"category": "x", "google_primary_category": "pet_store"}, "pets"),
        # explicit *_store rules still win
        ({"category": "x", "google_primary_category": "book_store"}, "specialty"),
        # unmatched *_store primaries stay shops instead of falling through to
        # incidental array tokens (atm/finance -> professional was the bug)
        (
            {
                "category": "shopping",
                "google_primary_category": "convenience_store",
                "google_categories": ["convenience_store", "atm", "finance"],
            },
            "specialty",
        ),
        ({"category": "x", "google_primary_category": "jewelry_store"}, "specialty"),
        # bare "store" still matches exactly
        ({"category": "x", "google_primary_category": "store"}, "specialty"),
        # curated sub_trades outrank the categories array
        (
            {
                "category": "x",
                "google_categories": ["store"],
                "attributes": {"sub_trades": ["plumber"]},
            },
            "home-services",
        ),
        # patrol regression guards
        ({"category": "x", "google_primary_category": "gift_shop"}, "specialty"),
        ({"category": "x", "google_primary_category": "juice_shop"}, "quick-bites"),
        # gas stations: primary gas_station beats the convenience-store/food array
        # noise that had been filing them as shopping-essentials (2026-06-05 patrol).
        (
            {
                "category": "x",
                "google_primary_category": "gas_station",
                "google_categories": ["gas_station", "convenience_store", "store", "food"],
            },
            "auto",
        ),
        # needle is "gas_station", not bare "gas" — must NOT swallow gastropub
        # (which correctly stays bars-breweries via the "pub" needle).
        ({"category": "x", "google_primary_category": "gastropub"}, "bars-breweries"),
    ],
)
def test_type_token_precedence(kwargs: dict, expected: str | None) -> None:
    assert derive_subcategory(**kwargs) == expected


def test_primary_category_follows_fixed_subcategory() -> None:
    from app.categories.subcategories import derive_primary_category

    assert (
        derive_primary_category(
            category="auto",
            subcategory=None,
            google_primary_category="car_dealer",
            google_categories=["car_dealer", "store", "point_of_interest"],
        )
        == "auto-rv-fuel"
    )


# --- "A Toe Truck" regression (2026-06-05 prod bug) -------------------------
#
# A towing company swept up by the food_drink discovery sweep's "food trucks"
# keyword landed with legacy category="food_drink". With no type-tier rule for
# tow/roadside trades, derivation fell through to the legacy tier and filed it
# as restaurants -> eat-drink, where its 999 reviews ranked it the #1
# "restaurant". The provider's primary trade (towing_service) must beat the
# coarse discovery-domain label, and "food truck" only counts as the full
# bigram — never bare "truck".


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        # tow company mis-swept into the food_drink domain: type tier wins
        (
            {
                "category": "food_drink",
                "google_primary_category": "towing_service",
                "google_categories": ["towing_service", "service", "establishment"],
            },
            "auto",
        ),
        ({"category": "food", "google_primary_category": "tow_truck_service"}, "auto"),
        ({"category": "food_drink", "google_primary_category": "roadside_assistance"}, "auto"),
        # curated tow sub_trades pin it too (no Google type needed)
        (
            {"category": "food_drink", "attributes": {"sub_trades": ["towing", "wrecker"]}},
            "auto",
        ),
        # genuine food truck stays food: full bigram, both separators
        ({"category": "food_drink", "google_primary_category": "food_truck"}, "quick-bites"),
        (
            {"category": "x", "attributes": {"sub_trades": ["food truck"]}},
            "quick-bites",
        ),
        # bare "truck" never implies food — unmatched type falls to legacy
        ({"category": "auto", "google_primary_category": "truck_repair"}, "auto"),
    ],
)
def test_tow_truck_is_not_a_food_truck(kwargs: dict, expected: str | None) -> None:
    assert derive_subcategory(**kwargs) == expected


def test_tow_company_excluded_from_eat_drink_membership() -> None:
    """End-to-end: a tow company whose NAME contains "truck" and whose legacy
    category is the food_drink discovery label must not satisfy the eat-drink
    route filter once classified, while a genuine food truck must."""
    from app.categories.queries import route_provider_filter
    from app.categories.subcategories import derive_primary_category

    ids: list[str] = []
    with SessionLocal() as db:
        try:
            for name, gpc in (
                ("A Toe Truck", "towing_service"),
                ("Lobster 3 Ways Food Truck", "food_truck"),
            ):
                sub = derive_subcategory(category="food_drink", google_primary_category=gpc)
                primary = derive_primary_category(
                    category="food_drink", subcategory=sub, google_primary_category=gpc
                )
                suf = uuid.uuid4().hex[:8]
                p = Provider(
                    provider_name=f"{name} {suf}",
                    category="food_drink",
                    subcategory=sub,
                    primary_category=primary,
                    google_primary_category=gpc,
                    draft=False,
                    is_active=True,
                    pending_review=False,
                    source="test-toe-truck",
                    slug=f"{name.lower().replace(' ', '-')}-{suf}",
                )
                db.add(p)
                db.commit()
                ids.append(p.entity_id)
            eat_rows = (
                db.query(Provider)
                .filter(Provider.entity_id.in_(ids), route_provider_filter("eat-drink"))
                .all()
            )
            eat_names = {r.provider_name for r in eat_rows}
            assert not any("A Toe Truck" in n for n in eat_names)
            assert any("Food Truck" in n for n in eat_names)
            auto_rows = (
                db.query(Provider)
                .filter(Provider.entity_id.in_(ids), route_provider_filter("auto-rv-fuel"))
                .all()
            )
            assert any("A Toe Truck" in r.provider_name for r in auto_rows)
        finally:
            if ids:
                db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
                db.commit()
