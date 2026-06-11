"""Pins for the health/beauty leaf classifier (categorization workstream,
2026-06-11). Cases are taken from the real audit CSV
(subcategory_audit_20260611T201931Z) so the rule is tested against the exact
rows Casey flagged, plus the must-NOT-touch rows that guard blast radius.

Casey's routing decisions:
  * dermatologists / pure medical skin -> dermatology-and-skin (Health)
  * medical med-spas (Botox/laser/IV/medspa) -> med-spas-and-aesthetics (Beauty)
  * cosmetic esthetics / day spa / massage -> day-spas-and-massage (Beauty)
  * hair, nail, GPs, and non-beauty rows -> untouched (None)
"""

from __future__ import annotations

import pytest

from app.categories.health_beauty_leaf_rules import (
    DAY_SPAS,
    DERMATOLOGY,
    MED_SPAS,
    classify_skin_spa_leaf,
)

# (name, google_primary_category, google_categories, expected)
CASES = [
    # --- Dermatology (medical skin) ---------------------------------------
    (
        "Arizona Desert Dermatology",
        "skin_care_clinic",
        ["skin_care_clinic", "hair_care", "beauty_salon", "spa", "medical_clinic", "health"],
        DERMATOLOGY,
    ),  # name 'dermatology' beats the cosmetic markers in its types[]
    (
        "Thomas Dermatology",
        "skin_care_clinic",
        ["skin_care_clinic", "doctor", "medical_clinic"],
        DERMATOLOGY,
    ),
    (
        "California Dermatology Institute",
        "doctor",
        ["doctor", "point_of_interest", "health"],
        DERMATOLOGY,
    ),  # currently mis-shelved on Primary Care
    (
        "928 SKIN",
        "skin_care_clinic",
        ["skin_care_clinic", "medical_clinic", "health"],
        DERMATOLOGY,
    ),  # pure medical skin clinic, no cosmetic markers

    # --- Medical med-spas -------------------------------------------------
    ("Desert Oasis Wellness and Medspa", "spa", ["spa", "health"], MED_SPAS),
    ("Restoration MedSpa", "spa", ["spa", "health"], MED_SPAS),
    ("Peak Rejuvenation Med Spa & Surgery", "spa", ["spa", "health"], MED_SPAS),
    (
        "Botox Synergy Skin and Laser Center",
        "spa",
        ["spa", "point_of_interest", "health"],
        MED_SPAS,
    ),
    (
        "Acacia Medical Spa of Lake Havasu City",
        "spa",
        ["spa", "medical_clinic", "health"],
        MED_SPAS,
    ),
    (
        "HYDR8AZ IVs & Medspa | Mobile IV Therapy Lake Havasu",
        "spa",
        ["spa", "health"],
        MED_SPAS,
    ),
    (
        "Define Medical Esthetics",
        "spa",
        ["skin_care_clinic", "beauty_salon", "massage_spa", "spa", "medical_clinic"],
        MED_SPAS,
    ),  # 'medical esthetic' beats the cosmetic-marker fallback
    ("HavaSpa IV & Boutique, LLC", "spa", ["spa", "health"], MED_SPAS),

    # --- Cosmetic esthetics / day spa / massage ---------------------------
    (
        "Complexions, Clinical Skin Care and Waxing Studio",
        "skin_care_clinic",
        ["skin_care_clinic", "massage_spa", "makeup_artist", "spa", "hair_care",
         "medical_clinic", "beauty_salon"],
        DAY_SPAS,
    ),
    (
        "Skin Deep Esthetics",
        "skin_care_clinic",
        ["skin_care_clinic", "beauty_salon", "medical_clinic", "hair_care"],
        DAY_SPAS,
    ),
    (
        "Luxe Esthetics & Beauty Bar",
        "spa",
        ["spa", "skin_care_clinic", "massage_spa", "tanning_studio", "hair_care",
         "beauty_salon"],
        DAY_SPAS,
    ),
    ("Evie Aesthetics", "spa", ["spa", "health"], DAY_SPAS),
    ("Luna's Massage", "massage", ["massage", "point_of_interest"], DAY_SPAS),
    ("Chasing Rays Body Spa", "spa", ["spa", "point_of_interest"], DAY_SPAS),

    # --- Must NOT be touched (None) — guards blast radius ------------------
    ("Salon 928", "beauty_salon", ["beauty_salon", "nail_salon", "service"], None),
    ("Nails By Jen", "nail_salon", ["nail_salon", "beauty_salon"], None),
    ("Havasu Family Practice", "doctor", ["doctor", "health"], None),
    ("In-N-Out Burger", "hamburger_restaurant", ["hamburger_restaurant", "restaurant"], None),
    ("Beautinails Skincare & More", "beauty_salon", ["beauty_salon", "nail_salon"], None),

    # Regressions caught by the 2026-06-11 dry-run: rows whose types[] array
    # carries stray spa/massage tokens, or whose name has a cosmetic word, must
    # NOT be pulled into Day Spas. The branch keys on PRIMARY type only.
    (
        "Hair Productions Inc",
        "hair_salon",
        ["hair_salon", "nail_salon", "beauty_salon", "massage_spa", "spa", "massage",
         "hair_care"],
        None,
    ),
    ("Beacon Of Health Family Chiropractic", "chiropractor", ["chiropractor", "massage", "health"], None),
    ("Aesthetic Dental Care-Arizona", "dentist", ["dentist", "doctor", "health"], None),
    ("Ocean Nail & Waxing Salon", "nail_salon", ["nail_salon", "beauty_salon"], None),
    ("Eight Lotus Wellness and Yoga", "yoga_studio", ["yoga_studio", "spa", "massage"], None),
    ("Brittany Brown", "physiotherapist", ["physiotherapist", "massage"], None),
]


@pytest.mark.parametrize("name,gpc,cats,expected", CASES)
def test_classify_skin_spa_leaf(name, gpc, cats, expected):
    assert classify_skin_spa_leaf(name, gpc, cats) == expected


def test_none_inputs_are_safe():
    assert classify_skin_spa_leaf(None, None, None) is None
    assert classify_skin_spa_leaf("", "", []) is None


def test_dermatology_beats_cosmetic_markers():
    # A derm whose types[] are loaded with cosmetic tokens still reads medical.
    assert (
        classify_skin_spa_leaf(
            "Lakeside Dermatology",
            "skin_care_clinic",
            ["beauty_salon", "hair_care", "spa", "makeup_artist"],
        )
        == DERMATOLOGY
    )


def test_iv_word_boundary_not_substring():
    # '\biv\b' must not fire inside 'River' / 'Riviera'.
    assert classify_skin_spa_leaf("Riviera Nails", "nail_salon", ["nail_salon"]) is None
