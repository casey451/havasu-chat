"""Search-audit round-2 recategorization — N3a/N4 clear-cut rows (2026-07-01).

Repoints each listed entity's PRIMARY ``EntityCategory`` link off a wrong leaf
onto the correct one, and drops one stray secondary link (VA Clinic ↔ Urgent
Care). Every row was confirmed read-only by
``investigate_search_round2_2026_07_01.py``. Idempotent + reversible: each move
prints its old→new category_id so it can be hand-reverted.

Scope: the clear-cut rows + the destinations Casey chose (2026-07-01) — Phil's
Band → Hobby & Craft, the two real-estate industry orgs → Nonprofits &
Charities. Deliberately NOT here: the 4 dental labs (left in Dentists, no good
home), retail optical, and the practitioner/practice de-dup (its own reviewed
dry-run — a judgment call).

Dry-run default; --apply --confirm gated.

Usage:
    .venv\\Scripts\\python.exe scripts/recat_search_round2_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/recat_search_round2_2026_07_01.py --apply --confirm
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

from sqlalchemy import func  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# (entity_id, name-guard, from-leaf-slug, to-leaf-slug)
_MOVES: tuple[tuple[str, str, str, str], ...] = (
    ("79eccf7f-bfea-47b3-aee7-1fea501b2406", "sears appliance",
     "auto-repair", "appliance-repair"),
    ("f48bc634-9139-459f-92bb-d6c5f0a63ef5", "serrano's nursery",
     "preschools-and-childcare", "nurseries-and-garden-centers"),
    ("e5496161-db64-4677-ae66-cdb289d5fd51", "caley nursery",
     "preschools-and-childcare", "nurseries-and-garden-centers"),
    ("0efb027b-68ac-4a61-af32-366d34c03e5f", "pixeopro",
     "real-estate", "photographers"),
    ("47841fd6-42d0-4450-afbc-12903bd556e2", "watercraft rental",
     "real-estate", "boat-and-watercraft-rentals"),
    # Round-2 decisions (Casey approved): orphan + RE-org homes.
    ("0e2938ab-7bb5-4a2b-aaf9-57a63213f303", "band instrument",
     "auto-repair", "hobby-and-craft"),
    ("d4165a8b-c650-4257-aa69-5f5f3bb7486b", "board of realtors",
     "real-estate", "nonprofits-and-charities"),
    ("fc094453-95cb-4e63-bc88-dbbebcbda190", "realtor convention",
     "real-estate", "nonprofits-and-charities"),
)

# (entity_id, name-guard, secondary-leaf-slug-to-drop) — primary is left as-is.
_DROP_SECONDARY: tuple[tuple[str, str, str], ...] = (
    ("3899931b-4046-46f7-a8da-d1897457f73a", "va clinic", "urgent-care-and-er"),
)


def _leaf_count(db, slug: str) -> int:
    c = db.query(Category).filter_by(slug=slug).first()
    if c is None:
        return -1
    return (
        db.query(func.count(EntityCategory.id))
        .filter(EntityCategory.category_id == c.id, EntityCategory.is_primary.is_(True))
        .scalar()
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Round-2 recat, tier 1 (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 72)
    print(f"ROUND-2 RECAT (TIER 1) — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 72)
    print(f"DB target: …@{redacted}\n")

    touched_slugs: set[str] = set()
    with SessionLocal() as db:
        # Resolve target leaves up front.
        for _eid, _g, _from, to in _MOVES:
            if db.query(Category).filter_by(slug=to).first() is None:
                print(f"ABORT: target leaf {to!r} not found")
                return 1

        print("PRIMARY re-homes:")
        planned_primary = []
        for eid, guard, from_slug, to_slug in _MOVES:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP {eid}: missing / name mismatch (guard={guard!r})")
                continue
            prim = (
                db.query(EntityCategory)
                .filter_by(entity_id=eid, is_primary=True)
                .one_or_none()
            )
            cur = db.get(Category, prim.category_id) if prim else None
            to_cat = db.query(Category).filter_by(slug=to_slug).first()
            cur_slug = cur.slug if cur else "(none)"
            state = "OK" if cur_slug == from_slug else f"NOTE cur={cur_slug}"
            print(f"  {ent.name[:38]:38s} | {cur_slug} -> {to_slug}  [{state}]")
            touched_slugs.update({from_slug, to_slug})
            if prim is not None and to_cat is not None and prim.category_id != to_cat.id:
                planned_primary.append((prim, cur.id if cur else None, to_cat.id))

        print("\nSECONDARY link drops (primary unchanged):")
        planned_drop = []
        for eid, guard, sec_slug in _DROP_SECONDARY:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP {eid}: missing / name mismatch (guard={guard!r})")
                continue
            sec_cat = db.query(Category).filter_by(slug=sec_slug).first()
            link = (
                db.query(EntityCategory)
                .filter_by(entity_id=eid, category_id=sec_cat.id, is_primary=False)
                .one_or_none()
                if sec_cat
                else None
            )
            if link is None:
                print(f"  {ent.name[:38]:38s} | no secondary {sec_slug} link (already clean)")
                continue
            print(f"  {ent.name[:38]:38s} | DROP secondary link -> {sec_slug} (ec={link.id})")
            touched_slugs.add(sec_slug)
            planned_drop.append(link)

        print("\nLeaf primary-counts (before):")
        before = {s: _leaf_count(db, s) for s in sorted(touched_slugs)}
        for s, n in before.items():
            print(f"  {s:34s} {n}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        for prim, old_id, new_id in planned_primary:
            print(f"  snapshot: ec={prim.id} category_id {old_id} -> {new_id}")
            prim.category_id = new_id
        for link in planned_drop:
            print(f"  snapshot: delete ec={link.id} (entity={link.entity_id})")
            db.delete(link)
        db.commit()

        print("\nLeaf primary-counts (after):")
        for s in sorted(touched_slugs):
            print(f"  {s:34s} {before[s]} -> {_leaf_count(db, s)}")
        print(f"\nAPPLIED: {len(planned_primary)} primary re-homes, "
              f"{len(planned_drop)} secondary drops.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
