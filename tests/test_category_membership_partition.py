"""S2/C-1 — top-level category membership is de-overlapped; off-bucket labels suppressed."""

from __future__ import annotations

from types import SimpleNamespace

from app.categories.queries import (
    CATEGORY_FILTERS,
    _allowed_subcategory_slugs,
    _card_subcategory_token,
    _route_bucket_id,
)


def test_things_to_do_no_longer_cross_lists_civic_or_fitness() -> None:
    # The audit's core S2 bug: churches/gyms appeared under BOTH Things-to-Do and
    # Community/Sports. Things-to-Do is now attractions/tourism only.
    ttd = CATEGORY_FILTERS["things-to-do"]
    assert "religion_community" not in ttd
    assert "fitness_sports" not in ttd
    assert "childcare_education" not in ttd
    assert set(ttd) == {"entertainment_attractions", "tourism"}


def test_religion_community_single_top_level_home() -> None:
    # A church's legacy category now resolves to exactly one top-level route.
    homes = [route for route, slugs in CATEGORY_FILTERS.items() if "religion_community" in slugs]
    assert homes == ["public-civic-resources"]


def test_services_page_excludes_shopping_specialty_label() -> None:
    # "Specialty" is a Shopping subtype; it must not be an allowed label on Services.
    allowed = _allowed_subcategory_slugs("services")
    assert allowed is not None
    assert "specialty" not in allowed
    assert "health-medical" in allowed  # a real Services subtype stays allowed


def test_off_bucket_subcategory_token_is_blanked() -> None:
    # A retail/"specialty" row that leaked onto Services shows no foreign label (C-1).
    provider = SimpleNamespace(subcategory="specialty")
    allowed = _allowed_subcategory_slugs("services")
    assert _card_subcategory_token(provider, allowed) == ""


def test_on_bucket_subcategory_token_is_kept() -> None:
    provider = SimpleNamespace(subcategory="health-medical")
    allowed = _allowed_subcategory_slugs("services")
    assert _card_subcategory_token(provider, allowed) == "health-medical"


def test_route_bucket_resolves_for_mega_and_tile_routes() -> None:
    assert _route_bucket_id("services") == "services"
    assert _route_bucket_id("things-to-do") == "events"
    # Tile route with no chip bucket falls back to its representative legacy bucket.
    assert _route_bucket_id("beauty-care") == "services"
    assert _route_bucket_id("shopping-essentials") == "shopping"
