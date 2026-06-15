"""Detect non-food providers polluting the Eat & Drink bucket (B6).

Promotes the proven heuristic from ``scripts/archive/audit_eat_bucket_pollution.py``
(prod 2026-06-04: a wedding planner/florist surfaced under "good restaurants")
into an importable, testable module so the recat ops script and its tests share
one implementation.

A row is flagged when a conservative non-food deny-list matches any of its
labels AND a food allow-list does NOT match its PRIMARY label (Google primary
first, else the catalog ``category``). Pure — no DB.
"""

from __future__ import annotations

import re

# Labels that are clearly NOT a place to eat/drink. Conservative: only terms that
# cannot plausibly be a food venue.
NON_FOOD_RE = re.compile(
    r"event\s*planner|wedding|florist|photograph|videograph|"
    r"\bsalon\b|barber|nail|spa\b|tattoo|"
    r"plumb|electric|hvac|roof|contractor|landscap|handyman|"
    r"real\s*estate|insurance|attorney|lawyer|account|"
    r"auto\s*repair|car\s*dealer|boat\s*(repair|dealer)|storage|"
    r"^service s?$|^services?$",
    re.IGNORECASE,
)

# Food-adjacent labels that legitimately live in the eat bucket even when the
# deny-list would otherwise graze them.
FOOD_OK_RE = re.compile(
    r"restaurant|cafe|coffee|bakery|brewery|brewpub|bar\b|pub\b|grill|pizza|taco|"
    r"deli|diner|food|caterer|catering|ice\s*cream|juice|smoothie|donut|bbq|barbecue|"
    r"steak|sushi|winery|distillery|snack|sandwich|burger",
    re.IGNORECASE,
)


def flatten_label(label: object) -> str:
    """Coerce a label to text. ``Provider.google_categories`` is a JSON list on
    Postgres (string/None on the SQLite fixtures) — handle both."""
    if label is None:
        return ""
    if isinstance(label, (list, tuple)):
        return " ".join(flatten_label(x) for x in label)
    return str(label)


def looks_non_food(
    category: object, google_primary: object, google_categories: object
) -> bool:
    """Whether an eat-bucket row is actually a non-food business.

    The food allow-list only counts on PRIMARY labels (Google primary, else the
    catalog ``category``): prod had an event planner with a secondary Google
    "Caterer" tag from dessert carts that wrongly rescued it. The deny-list is
    checked per-label so anchored patterns (``^services?$``) can match a bare
    ``category="Service"``.
    """
    cat = flatten_label(category).strip()
    gp = flatten_label(google_primary).strip()
    gcs = flatten_label(google_categories).strip()
    if gp:
        if FOOD_OK_RE.search(gp):
            return False
    elif cat and FOOD_OK_RE.search(cat):
        return False
    return any(NON_FOOD_RE.search(lb) for lb in (cat, gp, gcs) if lb)
