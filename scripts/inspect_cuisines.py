"""Read-only (Phase D §6.2): infer a cuisine for every eat-drink provider from
Google category signals + name tokens, and tally them — the evidence base for a
proposed cuisine-landing taxonomy. No writes."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# Ordered: first match wins (more specific cuisines before generic "american").
CUISINES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Mexican", ("mexican", "taco", "taqueria", "burrito", "michoacana")),
    ("Pizza", ("pizza",)),
    ("Italian", ("italian", "pasta", "trattoria")),
    ("Chinese", ("chinese", "dim sum", "wok")),
    ("Japanese / Sushi", ("japanese", "sushi", "ramen", "hibachi", "teriyaki")),
    ("Thai", ("thai",)),
    ("Indian", ("indian", "curry")),
    ("Vietnamese", ("vietnamese", "pho")),
    ("Korean", ("korean",)),
    ("Mediterranean / Greek", ("mediterranean", "greek", "gyro", "falafel")),
    ("BBQ", ("barbecue", "bbq", "smokehouse")),
    ("Seafood", ("seafood", "fish ", "oyster", "crab")),
    ("Steakhouse", ("steak", "steakhouse", "chophouse")),
    ("Burgers / Fast food", ("burger", "fast food", "hamburger", "hot dog", "wienerschnitzel")),
    ("Sandwiches / Deli", ("sandwich", "deli", "sub ", "subs", "jersey mike", "jimmy john")),
    ("Breakfast / Brunch", ("breakfast", "brunch", "pancake", "diner")),
    ("Cafe / Coffee", ("coffee", "cafe", "café", "espresso")),
    ("Bakery", ("bakery", "donut", "doughnut", "bagel")),
    ("Dessert / Ice cream", ("ice cream", "creamery", "frozen yogurt", "gelato", "dessert", "candy")),
    ("Juice / Smoothie", ("juice", "smoothie", "nutrition", "acai")),
    ("Bar / Pub / Brewery", ("bar ", "pub", "brewery", "brewpub", "tavern", "saloon", "cocktail")),
    ("Wings / Chicken", ("wings", "chicken", "fried chicken")),
    ("American", ("american", "grill", "kitchen", "eatery")),
)


def cuisine_for(p: Provider) -> str:
    hay = " ".join(filter(None, [
        (p.google_primary_category or ""),
        " ".join(p.google_categories or []),
        (p.provider_name or ""),
    ])).lower()
    for label, toks in CUISINES:
        if any(t in hay for t in toks):
            return label
    return "(uncategorized)"


def main() -> int:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Provider).where(
            Provider.primary_category == "eat-drink", Provider.is_active.is_(True))))
        # also catch eat-drink subcats whose primary may still be NULL
        extra = list(db.scalars(select(Provider).where(
            Provider.subcategory.in_(("restaurants", "quick-bites", "cafes-coffee", "bars-breweries")),
            Provider.is_active.is_(True))))
        seen = {p.id for p in rows}
        for p in extra:
            if p.id not in seen:
                rows.append(p); seen.add(p.id)

        tally = Counter(cuisine_for(p) for p in rows)
        print(f"{len(rows)} active eat-drink rows\n")
        for label, n in tally.most_common():
            print(f"  {label:24} {n}")

        print("\nSample (uncategorized):")
        unc = [p.provider_name for p in rows if cuisine_for(p) == "(uncategorized)"]
        for name in sorted(unc)[:40]:
            print(f"  {name}")
        print("DONE_MARKER")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
