"""Re-home audit-confirmed miscategorized listings (dry-run default; --apply gated).

Directory-audit follow-up (§"Re-home the clear miscategorizations"). The leaf
pages read the PRIMARY entity_categories link, so a listing whose primary leaf is
wrong (auto-classifier word-trap: "Charles-Italy" → Colleges, "Vet Center" → ...,
"Bluewater" → Boat Tours) both shows in the wrong place AND inflates that leaf's
"N Best X" count. This repoints the primary entity_categories row to the correct
leaf for a HAND-CURATED, web-verified set with an UNAMBIGUOUS target leaf.

Conservative by construction:
  * only entities whose lowered name CONTAINS the curated key are touched;
  * a key that matches 0 or >1 active entities is reported and SKIPPED (never a
    guess);
  * the target leaf must exist (level-1 Category by slug) or the row is skipped;
  * a row already on the target leaf is a no-op.

Writes only ``entity_categories.category_id`` of the existing PRIMARY row (no new
rows, no deletes); a before/after snapshot is printed for rollback. Reversible.

Usage:
    .venv\\Scripts\\python.exe scripts/rehome_directory_miscategorized_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_directory_miscategorized_2026_06_27.py --apply
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

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# Curated, web-verified moves: lowercased name substring -> target LEAF slug.
# Only unambiguous targets included; ambiguous-target cases (VA Vet Center,
# Western States Restaurant Consulting, Project 72 Custom Baits, Nature's
# Integrative Medicine) are intentionally LEFT OUT for manual handling.
_MOVES: tuple[tuple[str, str, str], ...] = (
    # (name substring, target leaf slug, human note)
    ("charles-italy", "day-spas-and-massage", "massage school, not a college"),
    ("bluewater accounting", "accountants-and-tax", "CPA firm, not a boat tour"),
    ("lake havasu cigars", "smoke-vape-and-cannabis", "cigar retailer, not a bar"),
    ("a toe truck", "towing-and-roadside", "towing co, not a mover"),
    ("303tattoo", "tattoo-and-piercing", "tattoo studio, not a museum"),
    ("universal sonics", "kids-classes-and-camps", "kids gymnastics/cheer, not a gym"),
    ("lake havasu golf club east", "golf-courses", "golf course, mis-tagged disc golf"),
    # --- batch 2 (audit §4 category-by-category; clear targets) ---
    # NB: "Lions Dog Park" and "Nautical Watersports" are duplicate PAIRS — they
    # need a dedup+rehome, deferred to manual, not auto-moved here.
    ("campbell cove complex", "self-storage", "boat/RV self-storage, not a beach"),
    ("wolf watersports", "boat-sales", "boat dealership, not jet-ski rentals"),
    ("kaizen golf", "golf-courses", "golf academy, not a gym"),
    ("relax mobile massage", "day-spas-and-massage", "massage, not a chiropractor"),
    ("loaded gun coffee", "cafes-and-coffee", "coffee shop, not specialty food"),
    ("islander rv resort", "rv-parks-and-campgrounds", "RV resort (lodging), not RV service"),
    # --- batch 3 (audit §4: non-parks dumped in Parks/Beaches; misc) ---
    ("havasu pools & repairs", "pools-and-spas", "pool service, not a park"),
    ("blue persuasion", "pools-and-spas", "pool service, not a park"),
    # "Toy Brokers Havasu" is the golf-cart dealer (vs unrelated "AZ Toy Brokers").
    ("toy brokers havasu", "golf-carts", "golf-cart dealer, not a park"),
    ("grill max", "restaurants", "restaurant, not a park"),
    # "Bogeys & Stogies" and "Rentals on the Beach" are duplicate PAIRS (renamed
    # + old) — deferred to manual dedup, not auto-moved here.
    ("htm performance", "boat-sales", "boat dealer/manufacturer, not a park"),
    ("farm fresh", "smoke-vape-and-cannabis", "cannabis dispensary, not a doctor"),
    ("simply savage", "print-signs-and-marketing", "print/design shop, not a museum"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-home miscategorized listings (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: repoint the primary entity_categories row (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"RE-HOME MISCATEGORIZED LISTINGS — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {
            c.slug: c
            for c in db.query(Category).filter(Category.level == 1).all()
        }

        planned: list[tuple[Entity, EntityCategory, Category, Category, str]] = []
        for key, target_slug, note in _MOVES:
            cands = [
                e for e in db.query(Entity).filter(
                    Entity.is_active.is_(True),
                    Entity.entity_type.in_(("commercial", "place")),
                ).all()
                if key in (e.name or "").lower()
            ]
            target = leaf_by_slug.get(target_slug)
            if target is None:
                print(f"  SKIP  '{key}': target leaf '{target_slug}' not found")
                continue
            if not cands:
                print(f"  SKIP  '{key}': no active entity matches")
                continue
            if len(cands) > 1:
                names = ", ".join(e.name for e in cands[:5])
                print(f"  SKIP  '{key}': {len(cands)} matches (ambiguous) — {names}")
                continue
            ent = cands[0]
            prim = (
                db.query(EntityCategory)
                .filter(EntityCategory.entity_id == ent.id, EntityCategory.is_primary.is_(True))
                .one_or_none()
            )
            if prim is None:
                print(f"  SKIP  '{ent.name}': no primary entity_categories row")
                continue
            cur = db.get(Category, prim.category_id)
            if cur is not None and cur.id == target.id:
                print(f"  OK    '{ent.name}': already on {target.slug}")
                continue
            # The entity may ALREADY carry the target leaf as a SECONDARY link
            # (uq on (entity_id, category_id) — repointing would collide). In that
            # case we swap the primary flag instead of rewriting category_id.
            existing = (
                db.query(EntityCategory)
                .filter(
                    EntityCategory.entity_id == ent.id,
                    EntityCategory.category_id == target.id,
                )
                .one_or_none()
            )
            planned.append((ent, prim, cur, target, note, existing))

        print(f"\nmoves planned: {len(planned)}\n")
        print("--- primary entity_categories moves ---")
        for ent, _prim, cur, target, note, existing in planned:
            cur_slug = cur.slug if cur is not None else "(none)"
            mode = "swap-flag" if existing is not None else "repoint"
            print(f"  MOVE  {ent.name[:32]:32s} | {cur_slug:24s} -> {target.slug:22s} "
                  f"| {mode:9s} | {note}")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot (entity_id, old_primary_ec_id, from_cat -> to_cat, mode) ---")
        for ent, prim, _cur, target, _note, existing in planned:
            mode = "swap-flag" if existing is not None else "repoint"
            print(f"  {ent.id} ec={prim.id} {prim.category_id} -> {target.id} ({mode})")
            if existing is not None:
                # Demote the old primary, promote the existing target link.
                prim.is_primary = False
                existing.is_primary = True
            else:
                prim.category_id = target.id
        db.commit()
        print(f"\nAPPLIED: moved {len(planned)} primary entity_categories links. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
