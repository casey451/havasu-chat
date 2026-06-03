"""Read-only prod probe to scope the remaining audit work. NO writes.

Answers four questions that need real prod data to size:
  1. C-2 cuisine drill-down — do restaurant providers carry Google types we can
     derive a cuisine from? (If null, the feature isn't buildable yet.)
  2. C-4 duplicates — which providers share a normalized name (dup clusters)?
  3. C-1 label mismatch — how many providers' legacy category and derived
     subcategory disagree on bucket (the "Specialty on Services" class)?
  4. ED-1 / ED-3 events — how many events still look scrambled, and how many
     already carry an image_url.

Usage (with prod env):  railway run python scripts/audit_data_probe.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

# Provider/event names can contain emoji; the default Windows console is cp1252
# and would crash on print(). Force UTF-8 with replacement so the probe never dies
# on a stray character.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import subcategory_by_slug  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event, Provider  # noqa: E402
from app.v1.categories import bucket_for_legacy_category  # noqa: E402

_RESTAURANT_CATS = ("restaurant", "food_drink", "food")
_CUISINE_TOKENS = (
    "italian", "mexican", "chinese", "japanese", "thai", "indian", "american",
    "pizza", "sushi", "bbq", "barbecue", "steak", "seafood", "greek", "mediterranean",
    "vietnamese", "korean", "french", "burger", "sandwich", "breakfast", "diner",
)
_norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def run() -> None:
    db = SessionLocal()
    try:
        # --- 1. Cuisine coverage -------------------------------------------------
        rests = db.query(Provider).filter(
            Provider.category.in_(_RESTAURANT_CATS),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        ).all()
        with_primary = sum(1 for p in rests if (p.google_primary_category or "").strip())
        with_cats = sum(1 for p in rests if p.google_categories)
        cuisine_hits: Counter = Counter()
        for p in rests:
            blob = f"{p.google_primary_category or ''} {p.google_categories or ''}".lower()
            for tok in _CUISINE_TOKENS:
                if tok in blob:
                    cuisine_hits[tok] += 1
        print("\n=== 1. CUISINE (C-2) ===")
        print(f"  restaurant providers:                 {len(rests)}")
        print(f"  with google_primary_category:         {with_primary}")
        print(f"  with google_categories:               {with_cats}")
        print(f"  cuisine tokens detected:              {dict(cuisine_hits.most_common(12)) or 'NONE'}")
        print("  -> buildable" if cuisine_hits else "  -> NOT buildable from Google types (would need name heuristics)")

        # --- 2. Duplicate clusters ----------------------------------------------
        all_active = db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        ).all()
        by_name: dict[str, list[Provider]] = {}
        for p in all_active:
            by_name.setdefault(_norm(p.provider_name), []).append(p)
        dup_clusters = {k: v for k, v in by_name.items() if k and len(v) > 1}
        print("\n=== 2. DUPLICATE NAME CLUSTERS (C-4) ===")
        print(f"  providers (active):                   {len(all_active)}")
        print(f"  name clusters with >1 provider:       {len(dup_clusters)}")
        for k, v in sorted(dup_clusters.items(), key=lambda kv: -len(kv[1]))[:12]:
            print(f"    {len(v)}x  {v[0].provider_name!r}  (place_ids: {[bool(x.google_place_id) for x in v]})")

        # --- 3. Category/subcategory bucket mismatch (C-1) ----------------------
        mismatch = 0
        examples: list[str] = []
        for p in all_active:
            sub = subcategory_by_slug(getattr(p, "subcategory", None))
            if sub is None:
                continue
            cat_bucket = bucket_for_legacy_category(p.category)
            if sub.bucket_id != cat_bucket:
                mismatch += 1
                if len(examples) < 10:
                    examples.append(f"{p.provider_name!r}: cat={p.category}({cat_bucket}) sub={sub.slug}({sub.bucket_id})")
        print("\n=== 3. CATEGORY/SUBCATEGORY MISMATCH (C-1 data) ===")
        print(f"  providers whose category & subcategory buckets disagree: {mismatch}")
        for e in examples:
            print(f"    {e}")

        # --- 4. Event scramble / image scope (ED-1 / ED-3) ----------------------
        events = db.query(Event).all()
        scrambled = 0
        has_image = 0
        for ev in events:
            desc = ev.description or ""
            if re.search(r"^\s*(LOCATION|VENUE|Image|Date|Time):", desc, re.MULTILINE | re.IGNORECASE):
                scrambled += 1
            if getattr(ev, "image_url", None):
                has_image += 1
        print("\n=== 4. EVENTS (ED-1 / ED-3) ===")
        print(f"  total events:                         {len(events)}")
        print(f"  events with scramble markers in desc: {scrambled}")
        print(f"  events already carrying image_url:    {has_image}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
