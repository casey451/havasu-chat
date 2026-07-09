"""Regression guard for the google-type → A.3 leaf resolver and its wiring into
``scripts/places_load._resolve_category_id`` (2026-06-11 category-misfile fix).

Locks three properties:

1. **The reported bug stays fixed.** ``event_venue`` (Buses by the Bridge,
   Desert Storm) is non-directory — it never resolves to a directory leaf, and
   the places_load resolver returns ``None`` for it.
2. **Casey's venue decision.** bowling / arcades / trampoline / indoor play are
   directory venues under ``family-fun-and-arcades``.
3. **No dangling slugs.** every leaf slug the mapper can emit exists in the live
   taxonomy seed, so a typo or renamed leaf fails CI instead of routing nowhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contrib.leaf_type_mapping import (
    _TYPE_TO_LEAF,
    NON_DIRECTORY_TYPES,
    map_google_types_to_leaf_slug,
)

_ROOT = Path(__file__).resolve().parents[1]
_SEED = _ROOT / "docs" / "proposals" / "taxonomy-seed.json"


def _seed_leaf_slugs() -> set[str]:
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for dept in seed.values():
        slugs.update((dept.get("leaves") or {}).keys())
    return slugs


# --- 1. the reported event→arcade bug -------------------------------------

@pytest.mark.parametrize("event_type", sorted(NON_DIRECTORY_TYPES))
def test_calendar_event_venue_types_are_non_directory(event_type: str) -> None:
    """A pure event-venue row resolves to no directory leaf (guardrail)."""
    slug, non_directory = map_google_types_to_leaf_slug([event_type])
    assert slug is None
    assert non_directory is True


def test_event_venue_never_maps_to_family_fun_and_arcades() -> None:
    """The exact 2026-06-11 misfile: event_venue must not land in arcades."""
    slug, _ = map_google_types_to_leaf_slug(["event_venue"])
    assert slug != "family-fun-and-arcades"
    assert slug is None


def test_primary_restaurant_with_event_venue_secondary_is_restaurant() -> None:
    """A restaurant (primary) that also lists event_venue still files as
    restaurants — the primary type decides."""
    slug, non_directory = map_google_types_to_leaf_slug(
        ["restaurant", "event_venue"]
    )
    assert slug == "restaurants"
    assert non_directory is False


def test_secondary_types_are_ignored() -> None:
    """PRIMARY-ONLY: noisy secondary tokens must not pick a leaf. Regression for
    the 2026-06-12 backfill incident (Dillard's department_store + a shoe_store
    secondary was reassigned to `shoes`; a book exchange to `jewelry`)."""
    assert map_google_types_to_leaf_slug(
        ["department_store", "shoe_store", "jewelry_store", "clothing_store"]
    ) == (None, False)
    assert map_google_types_to_leaf_slug(
        ["book_store", "jewelry_store"]
    ) == (None, False)
    assert map_google_types_to_leaf_slug(
        ["body_art_service", "jewelry_store"]
    ) == (None, False)


def test_specific_restaurant_suffix_maps_to_restaurants() -> None:
    """A specific '<style>_restaurant' primary is a restaurant."""
    assert map_google_types_to_leaf_slug(["taco_restaurant"]) == ("restaurants", False)
    assert map_google_types_to_leaf_slug(["hamburger_restaurant"]) == (
        "restaurants",
        False,
    )
    # dict entry still wins over the suffix rule
    assert map_google_types_to_leaf_slug(["fast_food_restaurant"]) == (
        "quick-bites-and-takeout",
        False,
    )


# --- 2. Casey's venue decision (directory family-fun venues) ---------------

@pytest.mark.parametrize(
    "gtype",
    [
        "bowling_alley",
        "amusement_arcade",
        "video_arcade",
        "amusement_park",
        "amusement_center",
        "indoor_playground",
        "trampoline_park",
    ],
)
def test_family_fun_venue_types_map_to_arcades_leaf(gtype: str) -> None:
    slug, non_directory = map_google_types_to_leaf_slug([gtype])
    assert slug == "family-fun-and-arcades"
    assert non_directory is False


# --- spot checks across departments ----------------------------------------

@pytest.mark.parametrize(
    "gtype,expected",
    [
        ("pizza_restaurant", "restaurants"),
        ("coffee_shop", "cafes-and-coffee"),
        ("gas_station", "gas-stations"),
        ("car_dealer", "car-dealerships"),
        ("veterinary_care", "veterinarians"),
        ("museum", "museums-and-galleries"),
        ("movie_theater", "theaters-and-cinema"),
        ("casino", "casinos-and-gaming"),
        ("plumber", "plumbing"),
        ("library", "libraries"),
        ("hotel", "hotels-and-motels"),
        ("rv_park", "rv-parks-and-campgrounds"),
        ("preschool", "preschools-and-childcare"),
        ("gym", "gyms-and-fitness-centers"),
    ],
)
def test_representative_types_resolve_to_expected_leaf(
    gtype: str, expected: str
) -> None:
    slug, non_directory = map_google_types_to_leaf_slug([gtype])
    assert slug == expected
    assert non_directory is False


def test_primary_first_order() -> None:
    """First matching type (primary first) wins."""
    slug, _ = map_google_types_to_leaf_slug(["dentist", "doctor"])
    assert slug == "dentists-and-orthodontists"


def test_unmapped_type_falls_through() -> None:
    """An unmapped, non-event type returns (None, False) → legacy fallback."""
    slug, non_directory = map_google_types_to_leaf_slug(["some_unknown_type"])
    assert slug is None
    assert non_directory is False


def test_empty_types() -> None:
    assert map_google_types_to_leaf_slug([]) == (None, False)
    assert map_google_types_to_leaf_slug(None) == (None, False)


# --- 3. no dangling slugs --------------------------------------------------

def test_every_emitted_leaf_exists_in_taxonomy_seed() -> None:
    """Every slug the mapper can emit must be a real seeded leaf."""
    seed_slugs = _seed_leaf_slugs()
    bad = {s for s in _TYPE_TO_LEAF.values() if s not in seed_slugs}
    assert not bad, f"leaf slugs not in taxonomy seed: {sorted(bad)}"


def test_non_directory_and_leaf_tables_disjoint() -> None:
    """A type is either a directory leaf or non-directory, never both."""
    assert not (set(_TYPE_TO_LEAF) & NON_DIRECTORY_TYPES)


# --- places_load wiring ----------------------------------------------------

def test_places_load_resolver_uses_leaf_then_guardrail() -> None:
    from scripts.places_load import _resolve_category_id

    cat_by_slug = {
        "family-fun-and-arcades": 4242,
        "restaurants": 11,
        "events": 99,  # legacy 13-category; must NOT be used for event_venue
    }
    # bowling alley → leaf id
    assert (
        _resolve_category_id({"primary_type": "bowling_alley"}, cat_by_slug)
        == 4242
    )
    # event_venue → guardrail returns None (not the legacy events bucket)
    assert (
        _resolve_category_id({"primary_type": "event_venue"}, cat_by_slug)
        is None
    )
