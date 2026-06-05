"""Audit: non-food providers polluting the Eat & Drink bucket (READ-ONLY).

Production 2026-06-04: "what are some good restaurants in town" surfaced
"Lovedwell Creative" (a wedding planner/florist, Provider.category="Service")
in the business_list. Rows land in the eat bucket via subcategory in
EAT_SUBCATS or category in EAT_LEGACY_CATEGORIES; a mis-derived subcategory
poisons every eat listing (intent layer + category pages).

This script lists eat-bucket members whose category / google_primary_category
matches a conservative non-food deny-list, with an allow-list override for
food-adjacent labels (caterer, bakery, ...). Read-only; prints counts + rows.

Usage:
    .venv\\Scripts\\python.exe scripts\\audit_eat_bucket_pollution.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import or_  # noqa: E402

from app.chat.intents.dicts import EAT_LEGACY_CATEGORIES, EAT_SUBCATS  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# Labels that are clearly NOT a place to eat/drink. Conservative: only terms
# that cannot plausibly be a food venue.
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


def _flatten(label: object) -> str:
    """Coerce a label to text. ``Provider.google_categories`` is a JSON list on
    Postgres (string/None on the SQLite fixtures) -- handle both."""
    if label is None:
        return ""
    if isinstance(label, (list, tuple)):
        return " ".join(_flatten(x) for x in label)
    return str(label)


def looks_non_food(category: object, google_primary: object, google_categories: object) -> bool:
    """Pollution test with tiered signals (2026-06-05 prod fix).

    The food allow-list only counts on PRIMARY labels (category +
    google_primary_category). Prod showed why: Lovedwell Creative (an event
    planner) carries a secondary Google "Caterer" tag from their dessert carts,
    which rescued them from the deny-list. A real caterer has it as the primary
    label and is still protected. The deny-list is checked per-label so anchored
    patterns like ^services?$ can match category="Service" on its own.
    """
    cat = _flatten(category).strip()
    gp = _flatten(google_primary).strip()
    gcs = _flatten(google_categories).strip()
    # Allow-list precedence (2026-06-05 prod fix #2): trust GOOGLE's primary
    # label first. The catalog's own ``category`` is the field under audit --
    # prod had Lovedwell Creative (florist/event planner, google_primary
    # ='service') with category='food_drink', and the "food" inside that bad
    # value rescued the row from the deny-list. Only fall back to ``category``
    # for the allow-list when Google gives us nothing.
    if gp:
        if FOOD_OK_RE.search(gp):
            return False
    elif cat and FOOD_OK_RE.search(cat):
        return False
    return any(NON_FOOD_RE.search(lb) for lb in (cat, gp, gcs) if lb)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show",
        metavar="NAME",
        help="print the raw row (category/subcategory/google fields) for one provider "
        "name (exact or substring match) and exit -- read-only diagnostics",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.show:
            needle = args.show.lower()
            matches = [
                p
                for p in db.query(Provider).filter(Provider.is_active.is_(True)).all()
                if needle in (p.provider_name or "").lower()
            ]
            for p in matches[:10]:
                print(
                    f"name={p.provider_name!r}\n  category={p.category!r}"
                    f"\n  subcategory={p.subcategory!r}"
                    f"\n  google_primary_category={p.google_primary_category!r}"
                    f"\n  google_categories={p.google_categories!r}"
                    f"\n  flagged={looks_non_food(p.category, p.google_primary_category, p.google_categories)}"
                )
            if not matches:
                print(f"no active provider matching {args.show!r}")
            return
        rows = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                or_(
                    Provider.subcategory.in_(EAT_SUBCATS),
                    Provider.category.in_(EAT_LEGACY_CATEGORIES),
                ),
            )
            .all()
        )
        flagged = [
            p
            for p in rows
            if looks_non_food(p.category, p.google_primary_category, p.google_categories)
        ]
        print(f"eat-bucket members: {len(rows)}; flagged non-food: {len(flagged)}\n")
        for p in flagged:
            print(
                f"  {p.provider_name!r:<45} category={p.category!r} "
                f"subcategory={p.subcategory!r} google={p.google_primary_category!r}"
            )
        if not flagged:
            print("  (none -- bucket is clean by this heuristic)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
