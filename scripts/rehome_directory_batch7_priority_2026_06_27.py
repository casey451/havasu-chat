"""Batch-7 re-home: priority-cluster (boats/pools/HVAC) misfiles (dry-run default; --apply gated).

Directory-audit follow-up. The 6 moves below were surfaced by
``audit_directory_batch7_priority_2026_06_27.py`` and operator-approved
(2026-06-27): each is a single, unambiguous, web-verified ``google_places``
listing whose PRIMARY leaf is wrong (mis-filed by the auto-classifier), so it
both shows in the wrong place AND inflates that leaf's "N Best X" count.

These are the priority-cluster misfiles the earlier ``rehome_directory_
miscategorized_2026_06_27.py`` left out (they were uncurated, not that they were
ambiguous). Same conservative mechanism as that tool:
  * only entities whose lowered name CONTAINS the curated key are touched;
  * a key matching 0 or >1 active entities is reported and SKIPPED (never a guess);
  * the target leaf must exist (level-1 Category by slug) or the row is skipped;
  * a row already on the target leaf is a no-op.

Writes only ``entity_categories.category_id`` of the existing PRIMARY row (or
swaps the is_primary flag when the target leaf is already a secondary link). No
new rows, no deletes. A before/after snapshot is printed for rollback. Reversible.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/rehome_directory_batch7_priority_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_directory_batch7_priority_2026_06_27.py --apply
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

# (name substring, target LEAF slug, human note) — operator-approved 2026-06-27.
_MOVES: tuple[tuple[str, str, str], ...] = (
    ("sandbar powersports", "boat-sales", "powersports/boat dealer, mis-filed Self-Storage"),
    ("horizon motorsports", "boat-sales", "DCB/Playcraft boat dealer, mis-filed Self-Storage"),
    ("amici pools", "pools-and-spas", "pool retail+service, mis-filed Sporting Goods"),
    ("mohave mist", "pools-and-spas", "hot-tub/spa dealer, mis-filed Sporting Goods"),
    ("all american air", "hvac", "HVAC co stranded under General Contractors"),
    ("air control", "hvac", "HVAC co stranded under General Contractors"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-7 priority-cluster re-home (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: repoint the primary entity_categories row (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"BATCH-7 PRIORITY-CLUSTER RE-HOME — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {
            c.slug: c for c in db.query(Category).filter(Category.level == 1).all()
        }

        planned: list[tuple[Entity, EntityCategory, Category | None, Category, str, EntityCategory | None]] = []
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
            m = "swap-flag" if existing is not None else "repoint"
            print(f"  MOVE  {ent.name[:32]:32s} | {cur_slug:24s} -> {target.slug:22s} "
                  f"| {m:9s} | {note}")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot (entity_id, old_primary_ec_id, from_cat -> to_cat, mode) ---")
        for ent, prim, _cur, target, _note, existing in planned:
            m = "swap-flag" if existing is not None else "repoint"
            print(f"  {ent.id} ec={prim.id} {prim.category_id} -> {target.id} ({m})")
            if existing is not None:
                prim.is_primary = False
                existing.is_primary = True
            else:
                prim.category_id = target.id
        db.commit()
        print(f"\nAPPLIED: moved {len(planned)} primary entity_categories links. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
