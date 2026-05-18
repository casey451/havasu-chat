"""Phase 5.11 -- regression guard for the _PRIMARY_TYPE_MAP + _DISCOVERY_
DOMAIN_FALLBACK extensions shipped this session (4 direct mappings for
pets (cat-11) primary_types + 1 new pets domain catch-all -- per Phase
5.11 1 sustainability commit Option A).

5.11 ships under the clean single-domain scope (no Narrow scope
decision needed): all 4 labels in the ``pets`` domain are in scope (pet
stores / dog groomers / dog boarding / dog trainers). Vet clinics are
NOT in 5.11 scope by design -- 5.4 HWC absorbed them via the
``medical_clinic`` direct mapping in google_types_mapping.py (per the
5.7 1dfd28e widening). Vets with primary=``veterinary_care`` continue
to route to cat-11 via the pre-Phase-5 direct mapping (5 baseline
entries pre-load: Animal Hospital of Havasu, Buckman Cary DVM, Exotic
Pet Kingdom, Paws and Claws Animal Care, PetVet Vaccination Clinic).

The 4 new direct ``_PRIMARY_TYPE_MAP`` entries beat the new ``(None,
"pets")`` catch-all per the resolver order in
``scripts/places_load._resolve_category_id`` (direct ``_PRIMARY_TYPE_MAP``
lookup at Layer 2 runs before the ``_DISCOVERY_DOMAIN_FALLBACK`` lookup
at Layer 3). The 5.11 1 load empirically observed:

  * ``pet_care`` x4 inserts at category_id=None pre-sustainability
    (Google consolidated dog grooming + pet boarding + dog training
    under a single ``pet_care`` primary type; this direct mapping
    catches them on the post-sustainability re-run).
  * ``service`` x3 inserts at category_id=None pre-sustainability
    (Google's generic catch-all primary -- same shape as 5.10's
    Vanderpump villa case; the new ``(None, "pets")`` catch-all
    catches these on the post-sustainability re-run).

The 3 defensive direct mappings (``dog_groomer`` / ``pet_boarding`` /
``dog_trainer``) document intent + provide future-proofing in case
Google ever un-consolidates ``pet_care`` back into the label-specific
primary types. All 4 entries land in cat-11 either way (same
destination), so the direct mappings document intent + provide the
explicit ``commercial`` entity_type that the catch-all alone can't
supply (catch-all returns slug only; entity_type defaults to None).

Mirrors the shape of tests/test_phase5_10_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP
from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, (expected_slug, expected_entity_type)) tuples for the
# 4 direct mappings shipped this session. All 4 start as ``commercial``
# per the 5.11 kickoff 1 Option A starting point (fee-based, staffed
# pet-service businesses). The 2 audit may flip individual entries to
# ``place`` for public-good edge cases (rare for cat-11 -- pet services
# are venue-based commercial offerings).
_CAT11_PRIMARY_TYPES: list[tuple[str, tuple[str, str]]] = [
    ("pet_care", ("pets", "commercial")),
    ("dog_groomer", ("pets", "commercial")),
    ("pet_boarding", ("pets", "commercial")),
    ("dog_trainer", ("pets", "commercial")),
]


@pytest.mark.parametrize("primary_type,expected", _CAT11_PRIMARY_TYPES)
def test_cat11_primary_type_maps_to_pets(
    primary_type: str, expected: tuple[str, str]
) -> None:
    """Each cat-11 primary_type direct mapping shipped this session must
    persist. Removing any direct mapping would cause the type to fall
    through to the new ``(None, "pets")`` catch-all (still cat-11 --
    visible behavior preserved). But the direct mapping documents
    intent + provides the explicit ``commercial`` entity_type that the
    catch-all alone can't supply, AND is defensive against Google's
    types[] array changes (e.g., if Google ever un-consolidates
    ``pet_care`` back into ``dog_groomer`` / ``pet_boarding`` /
    ``dog_trainer`` per the original kickoff forecast)."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"Missing _PRIMARY_TYPE_MAP entry for {primary_type!r}. "
        "Regression of the Phase 5.11 1 sustainability extension."
    )
    assert _PRIMARY_TYPE_MAP[primary_type] == expected, (
        f"_PRIMARY_TYPE_MAP[{primary_type!r}] = "
        f"{_PRIMARY_TYPE_MAP[primary_type]!r}, expected {expected!r}."
    )


def test_phase5_11_pets_catch_all_present() -> None:
    """The NEW ``(None, "pets") -> "pets"`` catch-all shipped this
    session covers any unmapped pets primary_types Google emits for
    the 4 in-scope labels (pet stores / dog groomers / dog boarding /
    dog trainers). No prior phase populated the pets domain in the
    fallback. The 5.11 1 load surfaced 3 such cases -- 3 entities
    with primary=``service`` discovered under the pets domain
    (Google's generic catch-all type; same shape as 5.10's Vanderpump
    villa case). This catch-all routes those edge cases + any future
    similar cases to cat-11 instead of operator queue."""
    assert (None, "pets") in _DISCOVERY_DOMAIN_FALLBACK, (
        "Missing pets catch-all in _DISCOVERY_DOMAIN_FALLBACK. "
        "Regression of the Phase 5.11 1 sustainability extension."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "pets")] == "pets"


def test_phase5_11_pre_existing_pet_store_and_veterinary_care_mappings_preserved() -> None:
    """Defensive: the pre-Phase-5 ``veterinary_care`` + ``pet_store``
    direct mappings to cat-11 must persist after the 5.11 extension.
    The 5.11 0 DB spot-check found 5 pre-existing cat-11 entries that
    depend on these mappings (4 vet clinics via ``veterinary_care``:
    Animal Hospital of Havasu, Buckman Cary DVM, Paws and Claws Animal
    Care, PetVet Vaccination Clinic; 1 pet store via ``pet_store``:
    Exotic Pet Kingdom). If either mapping breaks, those 5 entries
    would drift to operator-queue on next re-pull."""
    assert "veterinary_care" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["veterinary_care"] == ("pets", "commercial")
    assert "pet_store" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["pet_store"] == ("pets", "commercial")


def test_phase5_11_cat11_entries_are_all_commercial() -> None:
    """Defensive: all 4 cat-11 primary types shipped this session are
    intentionally ``commercial``-typed at the 5.11 1 starting point
    (fee-based, staffed pet-service businesses). The 2 audit may flip
    individual entries to ``place`` for public-good edge cases (rare
    for cat-11 -- pet services are venue-based commercial offerings),
    but this test guards against accidental flips of the type-map
    default itself."""
    for pt, (_, entity_type) in _CAT11_PRIMARY_TYPES:
        assert _PRIMARY_TYPE_MAP[pt][1] == "commercial", (
            f"_PRIMARY_TYPE_MAP[{pt!r}] entity_type = "
            f"{_PRIMARY_TYPE_MAP[pt][1]!r}, expected 'commercial'. "
            "If the operator wants ``place`` for a specific entry, "
            "flip via the 2 audit apply-script -- not the type-map "
            "default."
        )


def test_phase5_10_cat10_primary_type_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.11 entries didn't disturb the
    Phase 5.10 cat-10 primary_type direct mappings (``bf24e16``)."""
    required_cat10 = {
        "hotel": ("lodging-vacation-rentals", "commercial"),
        "motel": ("lodging-vacation-rentals", "commercial"),
        "resort_hotel": ("lodging-vacation-rentals", "commercial"),
        "extended_stay_hotel": ("lodging-vacation-rentals", "commercial"),
        "bed_and_breakfast": ("lodging-vacation-rentals", "commercial"),
    }
    for primary_type, expected in required_cat10.items():
        assert primary_type in _PRIMARY_TYPE_MAP, (
            f"Phase 5.10 cat-10 direct mapping {primary_type!r} is missing. "
            "Regression of bf24e16."
        )
        assert _PRIMARY_TYPE_MAP[primary_type] == expected


def test_phase5_10_lodging_catch_all_preserved() -> None:
    """Defensive: ensure adding Phase 5.11 entries didn't disturb the
    Phase 5.10 ``(None, "lodging")`` catch-all (``bf24e16``)."""
    assert (None, "lodging") in _DISCOVERY_DOMAIN_FALLBACK, (
        "Phase 5.10 lodging catch-all is missing. Regression of bf24e16."
    )
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "lodging")]
        == "lodging-vacation-rentals"
    )


def test_phase5_9_cat12_primary_type_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.11 entries didn't disturb the
    Phase 5.9 cat-12 primary_type direct mappings (``0af5f73``)."""
    required_cat12 = {
        "child_care_agency": ("classes-sports-recreation", "commercial"),
        "preschool": ("classes-sports-recreation", "commercial"),
        "music_school": ("classes-sports-recreation", "commercial"),
        "driving_school": ("classes-sports-recreation", "commercial"),
        "tutor": ("classes-sports-recreation", "commercial"),
        "personal_trainer": ("classes-sports-recreation", "commercial"),
        "swimming_pool": ("classes-sports-recreation", "place"),
        "tennis_court": ("classes-sports-recreation", "place"),
        "pickleball_court": ("classes-sports-recreation", "place"),
    }
    for primary_type, expected in required_cat12.items():
        assert primary_type in _PRIMARY_TYPE_MAP, (
            f"Phase 5.9 cat-12 direct mapping {primary_type!r} is missing. "
            "Regression of 0af5f73."
        )
        assert _PRIMARY_TYPE_MAP[primary_type] == expected


def test_phase5_9_childcare_education_catch_all_preserved() -> None:
    """Defensive: ensure adding Phase 5.11 entries didn't disturb the
    Phase 5.9 childcare_education catch-all (``0af5f73``)."""
    assert (None, "childcare_education") in _DISCOVERY_DOMAIN_FALLBACK
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "childcare_education")]
        == "classes-sports-recreation"
    )


def test_phase5_x_other_domain_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.11 entries didn't disturb the
    Phase 5.2 / 5.3 / 5.4 / 5.5 / 5.6 / 5.8 domain fallback entries."""
    # 5.2 lake_recreation
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "lake_recreation")]
        == "on-the-water"
    )
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[("tour_agency", "lake_recreation")]
        == "on-the-water"
    )
    # 5.3 home_services
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "home_services")]
        == "home-property-services"
    )
    # 5.4 health_medical
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "health_medical")]
        == "health-wellness-care"
    )
    # 5.4 fitness_sports
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "fitness_sports")]
        == "health-wellness-care"
    )
    # 5.5 auto
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "auto")] == "auto-rv-fuel"
    # 5.6 retail
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "retail")] == "shopping-essentials"
    )


def test_park_and_dog_park_primary_types_preserved() -> None:
    """Defensive: ensure adding the 4 cat-11 primary_type entries near
    the existing pet_store / veterinary_care entries in _PRIMARY_TYPE_MAP
    didn't accidentally perturb the cat-7 outdoors-parks-trails
    direct mappings. ``dog_park`` specifically is the cross-cat axis
    that the 5.11 2 audit's secondary axis depends on (5.11 labels
    don't map to dog_park primary so cross-cat hits forecast 0)."""
    assert _PRIMARY_TYPE_MAP["park"] == ("outdoors-parks-trails", "place")
    assert _PRIMARY_TYPE_MAP["dog_park"] == ("outdoors-parks-trails", "place")


def test_phase5_4_medical_clinic_mapping_preserved() -> None:
    """Defensive: 5.4 HWC absorption of vet clinics depends on
    ``medical_clinic`` direct mapping in google_types_mapping.py
    (added at 5.7 1dfd28e). The 5.11 kickoff §2 cross-cat audit
    treats vet clinics with primary=``medical_clinic`` as cat-5 HWC
    (out of 5.11 scope by design); breaking this mapping would mis-
    route those vets to operator queue."""
    assert "medical_clinic" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["medical_clinic"] == (
        "health-wellness-care",
        "commercial",
    )
