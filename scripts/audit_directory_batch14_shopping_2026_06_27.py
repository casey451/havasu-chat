"""Batch-14 read-only probe: Shopping & Retail cross-category misfiles + dupes.

READ-ONLY. SELECT-only, ZERO writes. All target leaves exist, so these are
re-homes. Scans each retail source leaf for off-category keywords and lists the
candidates with review count + source, plus a few dedup clusters.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch14_shopping_2026_06_27.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# (source slug, regex of off-category names, suggested target slug, label)
_SCANS: tuple[tuple[str, str, str, str], ...] = (
    ("gifts-and-boutiques", r"walmart", "grocery-and-markets", "big-box -> grocery"),
    ("gifts-and-boutiques", r"(smoke|vape|cigar|tobacco|hemp|cbd)", "smoke-vape-and-cannabis", "smoke shop"),
    ("hardware-and-home-improvement", r"(smoke|vape|slingers|cigar)", "smoke-vape-and-cannabis", "smoke shop"),
    ("hardware-and-home-improvement", r"(turf|landscap|lawn)", "landscaping-and-lawn", "landscaping"),
    ("furniture-and-mattress", r"(marine|boat|dek x|watercraft|nautical)", "boat-sales", "marine"),
    ("sporting-goods", r"(motorsport|powersport|watercraft|jet ?ski|marine|boat)", "boat-sales", "marine/powersports"),
    ("sporting-goods", r"(pool|spa)\b", "pools-and-spas", "pool/spa"),
    ("clothing-and-apparel", r"(nautical|watersport|marine|harley)", "boat-and-watercraft-rentals", "marine/watersport"),
    ("grocery-and-markets", r"(swap meet|flea)", "", "flea market — HOLD"),
)
_DUPE = (
    ("Goodwill", ("thrift-and-consignment",), "goodwill"),
    ("Lakeside Appliances", ("appliances-and-electronics", "furniture-and-mattress"), "lakeside appliance"),
    ("Randy's Hilltop", ("liquor-stores", "specialty-food"), "randy"),
    ("Star Nursery", ("nurseries-and-garden-centers",), "star nursery"),
)


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 84)
    print("BATCH-14 SHOPPING MISFILE PROBE  (READ-ONLY — no rows written)")
    print("=" * 84)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        cat_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        all_ents = db.query(Entity).filter(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(("commercial", "place"))).all()

        def members(slug: str) -> list[Entity]:
            cat = cat_by_slug.get(slug)
            if cat is None:
                return []
            ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
            return [e for e in all_ents if e.id in ids]

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        print("-" * 84)
        print("CROSS-CATEGORY MISFILES (source leaf -> suggested target)")
        for sslug, rx, tslug, label in _SCANS:
            hits = [e for e in members(sslug) if re.search(rx, (e.name or ""), re.I)]
            if not hits:
                continue
            print(f"\n  [{sslug}] {label} -> {tslug or '(hold)'}  ({len(hits)})")
            for e in sorted(hits, key=lambda e: -rev(e)):
                print(f"     rev={rev(e):>4d} {e.name[:50]}")

        print("\n" + "-" * 84)
        print("DUPE CLUSTERS")
        for label, slugs, key in _DUPE:
            seen = []
            for slug in slugs:
                for e in members(slug):
                    if key in (e.name or "").lower():
                        seen.append((slug, e))
            if not seen:
                continue
            print(f"\n  {label}  ({len(seen)})")
            for slug, e in sorted(seen, key=lambda t: -rev(t[1])):
                pr = sorted(provs_by_entity.get(e.id, []), key=lambda p: -(p.google_review_count or 0))
                addr = (pr[0].address[:24] if pr and pr[0].address else "")
                print(f"     rev={rev(e):>4d} [{slug[:16]:16s}] {e.name[:30]:30s} | {addr}")
        print("\n" + "=" * 84)
        print("READ-ONLY. Your eyeball before apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
