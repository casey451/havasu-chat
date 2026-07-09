"""Tests for name-based leaf routing (``app/contrib/name_leaf_rules.py``) and its
wire-in to the Places resolver (``scripts/places_load._resolve_category_id``).

The durable fix for the 2026-06-17 Phase 4 misfile class: Google gives dojos and
dance studios generic primary types (gym/school/point_of_interest), so a confident
NAME signal must route them onto martial-arts / dance-studios and BEAT the generic
type map. These tests pin both the matcher and the resolver precedence.
"""

from __future__ import annotations

import pytest

from app.contrib.name_leaf_rules import DANCE_LEAF, MARTIAL_ARTS_LEAF, leaf_for_name
from scripts.places_load import _resolve_category_id

# --------------------------- matcher behavior --------------------------- #
_MARTIAL_NAMES = [
    "Four Dragons Martial Arts",
    "Havasu Shao-Lin Kempo",
    "THE TAP ROOM JIU JITSU",
    "Lake Havasu Black Belt Academy LLC",
    "Elite Martial Arts, Inc.",
    "Desert Karate Dojo",
]
_DANCE_NAMES = [
    "Foot Lite School of Dance",
    "Ballet Havasu",
    "Marsh Dance Studios",
    "Havasu Dance Academy",
]
# Names that must NOT match — conservative guard against false positives.
_NO_MATCH = [
    "Joe's Gym",
    "Havasu Dance Club",        # nightlife — bare "dance" is intentionally ignored
    "Riverside Dance Hall",     # nightlife
    "Arizona Coast Performing Arts",  # "performing arts" excluded (theatre-ambiguous)
    "Anytime Fitness",
    "Nutrition One",
    "",
]


@pytest.mark.parametrize("name", _MARTIAL_NAMES)
def test_martial_arts_names_route_to_martial_arts(name: str) -> None:
    assert leaf_for_name(name) == MARTIAL_ARTS_LEAF == "martial-arts"


@pytest.mark.parametrize("name", _DANCE_NAMES)
def test_dance_names_route_to_dance_studios(name: str) -> None:
    assert leaf_for_name(name) == DANCE_LEAF == "dance-studios"


@pytest.mark.parametrize("name", _NO_MATCH)
def test_non_signal_names_return_none(name: str) -> None:
    assert leaf_for_name(name) is None


def test_none_name_returns_none() -> None:
    assert leaf_for_name(None) is None


def test_martial_arts_wins_over_dance_in_hybrid() -> None:
    # A "Martial Arts & Dance" hybrid is overwhelmingly a dojo.
    assert leaf_for_name("Havasu Martial Arts & Dance Studio") == MARTIAL_ARTS_LEAF


# --------------------- resolver precedence (the fix) -------------------- #
def test_resolver_name_beats_generic_gym_type_for_dojo() -> None:
    # CRITICAL: a dojo Google typed as ``gym`` must file on martial-arts, not the
    # gym leaf the type map would otherwise pick.
    cat_by_slug = {"martial-arts": 30, "gyms-and-fitness-centers": 10}
    row = {
        "display_name": "Four Dragons Martial Arts",
        "primary_type": "gym",
        "types": ["gym"],
        "_first_seen_domain": "fitness_sports",
    }
    assert _resolve_category_id(row, cat_by_slug) == 30


def test_resolver_name_beats_school_type_for_dance_studio() -> None:
    cat_by_slug = {"dance-studios": 31, "k-12-schools": 12}
    row = {
        "display_name": "Foot Lite School of Dance",
        "primary_type": "school",
        "types": ["school"],
        "_first_seen_domain": "childcare_education",
    }
    assert _resolve_category_id(row, cat_by_slug) == 31


def test_resolver_falls_through_for_a_real_gym() -> None:
    # No name signal -> the gym type map still wins (no regression).
    cat_by_slug = {"martial-arts": 30, "gyms-and-fitness-centers": 10}
    row = {
        "display_name": "Anytime Fitness",
        "primary_type": "gym",
        "types": ["gym"],
        "_first_seen_domain": "fitness_sports",
    }
    assert _resolve_category_id(row, cat_by_slug) == 10


def test_resolver_name_override_noop_when_leaf_absent() -> None:
    # If the martial-arts leaf isn't in the slug map, the override can't fire and
    # the resolver falls back to the type map (gym -> gyms).
    cat_by_slug = {"gyms-and-fitness-centers": 10}
    row = {
        "display_name": "Four Dragons Martial Arts",
        "primary_type": "gym",
        "types": ["gym"],
        "_first_seen_domain": "fitness_sports",
    }
    assert _resolve_category_id(row, cat_by_slug) == 10
