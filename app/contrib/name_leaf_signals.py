"""Name-signal → leaf rules for on-the-water / tour operators.

This is step 2 of the categorization precedence adopted in
``docs/audits/2026-07/PARITY_AND_COMPLETENESS_PLAN_2026-07-03.md``:

    1. explicit high-trust source category (crosswalk)
    2. name signal (this module)
    3. Google Places types
    4. legacy category

It mirrors the existing ``_marine_subcat_from_name`` pattern in
``app/categories/subcategories.py`` (anchor + qualifier regexes, order matters)
and ``app/contrib/name_leaf_rules.py`` (martial-arts / dance name→leaf), but
targets the *lake-recreation* leaves where golakehavasu's charters, tours and
fishing guides otherwise get trapped in the generic
``boat-and-watercraft-rentals`` leaf.

Every rule is deliberately conservative: it fires only on strong, water-context
tokens so a "Charter School" or a landlocked "Sunset Salon" never gets pulled
into a boat leaf. When no rule matches it returns ``None`` and the caller falls
through to the next precedence layer.
"""

from __future__ import annotations

import re

# --- negative guards: tokens that look watery but aren't -------------------
# "Charter School", "Charter Academy" are education, never a boat charter.
_NEGATIVE = re.compile(r"\bcharter\s+(school|academy|academies|high)\b", re.I)

# --- fishing (most specific first) -----------------------------------------
_FISHING = re.compile(
    r"\b(fishing\s+(guide|charter|charters|guides)|guided\s+fishing"
    r"|net\s?'?\s?em|fishing\s+guide\s+service)\b",
    re.I,
)

# --- captained tours / charters --------------------------------------------
# Standalone strong tokens (captain, cruise, excursion) OR "charter"/"tour"
# paired with a water/boat anchor.
_CHARTER_STRONG = re.compile(
    r"\b(captain|captained|sunset\s+cruise|dinner\s+cruise|cruises?"
    r"|excursions?|jet\s?boat\s+tours?|boat\s+tours?|water\s+tours?|tiki\s+tours?"
    r"|duck\s+safari|amphibious)\b",
    re.I,
)
_CHARTER_WEAK = re.compile(r"\b(charter|charters|guided\s+tour)\b", re.I)
_WATER_ANCHOR = re.compile(
    r"\b(boat|boats|lake|river|water|marine|nautical|yacht|pontoon|tiki|jet\s?boat)\b",
    re.I,
)

# --- kayak / paddle ---------------------------------------------------------
_KAYAK = re.compile(r"\b(kayak|kayaks|paddle|paddleboard|canoe|canoes|s\.?u\.?p\.?|stand[\s-]?up\s+paddle)\b", re.I)

# --- jet ski / motorised watersports ---------------------------------------
_JETSKI = re.compile(
    r"\b(jet\s?ski|jetski|jet\s?skis|wave\s?runner|waverunner|parasail"
    r"|parasailing|flyboard|fly\s?board|watersports?|water\s+sports)\b",
    re.I,
)

# --- marinas / launch ramps -------------------------------------------------
_MARINA = re.compile(r"\b(marina|marinas|launch\s+ramp|boat\s+launch)\b", re.I)


def leaf_from_name(name: str | None) -> str | None:
    """Return an on-the-water leaf slug from a strong business-name signal.

    Ordered most-specific → least-specific. Returns ``None`` when no rule fires
    (the caller then falls through to Google types / legacy).
    """
    if not name:
        return None
    n = name.lower()

    if _NEGATIVE.search(n):
        return None

    # Fishing guides beat generic charters ("fishing charter" is a fishing guide).
    if _FISHING.search(n):
        return "fishing-charters-and-guides"

    # Captained tours / charters.
    if _CHARTER_STRONG.search(n):
        return "boat-tours-and-charters"
    if _CHARTER_WEAK.search(n) and _WATER_ANCHOR.search(n):
        return "boat-tours-and-charters"

    # Human-powered vs motorised watersports.
    if _KAYAK.search(n):
        return "kayak-and-paddle"
    if _JETSKI.search(n):
        return "jet-ski-and-watersports"

    # Marinas / launch ramps.
    if _MARINA.search(n):
        return "marinas-and-launch-ramps"

    return None
