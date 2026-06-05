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


def looks_non_food(*labels: str | None) -> bool:
    blob = " ".join(x for x in labels if x)
    if not blob.strip():
        return False
    if FOOD_OK_RE.search(blob):
        return False
    return bool(NON_FOOD_RE.search(blob))


def main() -> None:
    db = SessionLocal()
    try:
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
