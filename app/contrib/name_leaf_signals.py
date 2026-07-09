"""Name-signal → leaf rules for on-the-water + land-rental operators.

This is step 2 of the categorization precedence adopted in
``docs/audits/2026-07/PARITY_AND_COMPLETENESS_PLAN_2026-07-03.md``:

    1. explicit high-trust source category (crosswalk)
    2. name signal (this module)
    3. Google Places types
    4. legacy category

It mirrors the existing ``_marine_subcat_from_name`` pattern in
``app/categories/subcategories.py`` (anchor + qualifier regexes, order matters)
and ``app/contrib/name_leaf_rules.py`` (martial-arts / dance name→leaf). It
targets two families of leaf that a coarse source tag or a Google type would
otherwise mis-shelve:

  * the *lake-recreation* leaves, where golakehavasu's charters, tours and
    fishing guides get trapped in the generic ``boat-and-watercraft-rentals``
    leaf; and
  * the *land-rental* leaves (Session 6b, 2026-07-05), where a UTV/off-road
    **rental** tagged "off road"/"ohv" lands on the ``off-road-and-ohv``
    *trails* leaf (or, via Google's ``motorcycle_dealer`` type, on the
    ``powersports-and-atv`` *dealer* leaf), and golf-cart / bike / e-bike
    rentals have no name path at all.

Every rule is deliberately conservative: it fires only on strong tokens so a
"Charter School" or a landlocked "Sunset Salon" never gets pulled into a boat
leaf, and a powersports *dealer* (no rental language) stays a dealer. When no
rule matches it returns ``None`` and the caller falls through to the next
precedence layer.
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

# --- land rentals (Session 6b — stop the next scrape re-misfiling these) -----
# Off-road / UTV: an off-road *vehicle* token PAIRED with a rental token (so a
# powersports *dealer* with no rental language stays a dealer), or an
# unambiguous recreational-rental term (rzr / side-by-side) on its own.
_OFFROAD_VEHICLE = re.compile(
    r"\b(utvs?|atvs?|sxs|off[\s-]?road|offroad|ohv|dune\s+buggy|dune\s+buggies"
    r"|dirt\s?bikes?|powersports?)\b",
    re.I,
)
_OFFROAD_STRONG = re.compile(r"\b(rzrs?|side[\s-]?by[\s-]?sides?)\b", re.I)
_RENTAL_TOKEN = re.compile(r"\b(rental|rentals|rent)\b", re.I)

# Golf carts: the ``golf-carts`` leaf is a sales/service/rental hub, so any
# golf-cart operator belongs (no rental token required). "golf course" never
# matches — "course" is not "car"/"cart".
_GOLF_CART = re.compile(r"\bgolf\s+cart?s?\b", re.I)

# Bikes / e-bikes: an e-bike token is a strong standalone signal; a plain
# bike/bicycle needs a rental-or-shop context. Motorbikes / dirt-bikes (off-road)
# and bike-week/night events are excluded.
_EBIKE = re.compile(r"\b(e[\s-]?bikes?|electric\s+bikes?)\b", re.I)
_BIKE = re.compile(r"\b(bikes?|bicycles?|cyclery)\b", re.I)
_BIKE_CONTEXT = re.compile(r"\b(rental|rentals|rent|shop|shops|store)\b", re.I)
_BIKE_NEGATIVE = re.compile(
    r"\b(motor\s?bikes?|motorcycles?|dirt\s?bikes?|mini\s?bikes?"
    r"|bike\s?week|bike\s?night)\b",
    re.I,
)


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

    # Land rentals (order: off-road motor vehicle → golf cart → pedal/e-bike).
    if _OFFROAD_STRONG.search(n) or (_OFFROAD_VEHICLE.search(n) and _RENTAL_TOKEN.search(n)):
        return "utv-and-offroad-rentals"
    if _GOLF_CART.search(n):
        return "golf-carts"
    if _EBIKE.search(n) and not _BIKE_NEGATIVE.search(n):
        return "bikes-and-e-bikes"
    if _BIKE.search(n) and _BIKE_CONTEXT.search(n) and not _BIKE_NEGATIVE.search(n):
        return "bikes-and-e-bikes"

    return None
