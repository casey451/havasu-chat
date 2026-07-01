"""Backfill the web-verified missing tourist-activity businesses (2026-06-30).

Inserts the high-value businesses the search audit found absent, each LIVE on its
target leaf. Setting ``Provider.category_id`` makes the catalog dual-write hook
(app.db.entity_dual_write) create the entity graph + the PRIMARY entity_categories
link to that leaf + a Location from the address + phone/website contacts — so the
row renders on the leaf immediately (LEAF_PAGE_MIN_PROVIDERS == 1).

Every business here was confirmed currently-operating via live web search
(Yelp/Tripadvisor/first-party site, 2025-2026) before inclusion — per the
"only add verified-current data" rule.

Idempotent on the name slug (skips an existing one). Reversible: every row
carries ``source = BACKFILL_SOURCE``, so undo is a single
``UPDATE providers SET is_active=false WHERE source=...``.

Usage:
    .venv\\Scripts\\python.exe scripts/backfill_search_missing_businesses_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/backfill_search_missing_businesses_2026_06_30.py --apply --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402
from app.utils.slug import slugify  # noqa: E402

BACKFILL_SOURCE = "search_audit_backfill_2026_06_30"

# (name, leaf_slug, legacy_category, subcategory, address, phone, website)
_BUSINESSES: tuple[tuple[str, str, str, str, str | None, str | None, str | None], ...] = (
    ("Havasu Parasail", "jet-ski-and-watersports", "lake_recreation", "watersports",
     "1477 Queens Bay, Lake Havasu City, AZ 86403", "(928) 723-0944",
     "https://parasailhavasu.com/"),
    ("VR Escape Reality", "family-fun-and-arcades", "entertainment_attractions", "attractions",
     "231 Swanson Ave Ste 208, Lake Havasu City, AZ 86403", "(928) 733-5049",
     "https://www.golakehavasu.com/directory/vr-escape-reality/"),
    ("Lake Havasu Wakesurf Co.", "jet-ski-and-watersports", "lake_recreation", "watersports",
     "Lake Havasu City, AZ 86403", "(928) 208-8857",
     "https://lake-havasu-wakesurf-co.square.site/"),
    ("Wakesurf Havasu", "jet-ski-and-watersports", "lake_recreation", "watersports",
     "Lake Havasu City, AZ 86403", "(928) 706-2504", "http://wakesurfhavasu.com/"),
    ("Optic Helicopters", "tours-and-sightseeing", "entertainment_attractions", "tours",
     "Lake Havasu City, AZ 86403", None, "https://www.optichelicopters.com/havasu"),
    ("Havasu Helicopters", "tours-and-sightseeing", "entertainment_attractions", "tours",
     "Lake Havasu City Airport (KHII), Lake Havasu City, AZ 86404", None, None),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill verified missing businesses (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"SEARCH BACKFILL — {'APPLY (writing, LIVE rows)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    inserted = 0
    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        with db.no_autoflush:
            for name, leaf_slug, legacy, subcat, address, phone, website in _BUSINESSES:
                slug = slugify(name)
                leaf = leaf_by_slug.get(leaf_slug)
                if leaf is None:
                    print(f"  SKIP  {name}: leaf {leaf_slug!r} not found")
                    continue
                if db.scalar(select(Provider).where(Provider.slug == slug)) is not None:
                    print(f"  SKIP  {name}: already exists (slug {slug})")
                    continue
                print(f"  INSERT  {name[:34]:34s} -> {leaf_slug:26s} | {phone or '(no phone)'}")
                if writing:
                    db.add(Provider(
                        provider_name=name,
                        category=legacy,
                        subcategory=subcat,
                        category_id=leaf.id,  # hook -> PRIMARY entity_categories link
                        address=address,
                        phone=phone,
                        website=website,
                        slug=slug,
                        source=BACKFILL_SOURCE,
                        draft=False,
                        is_active=True,
                    ))
                inserted += 1
        if writing:
            db.commit()

    print(f"\n{'INSERTED' if writing else 'would insert'}: {inserted} live businesses.")
    if not writing:
        print("DRY RUN — nothing written. Re-run with --apply --confirm after approval.")
    else:
        print(f"Undo: UPDATE providers SET is_active=false WHERE source='{BACKFILL_SOURCE}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
