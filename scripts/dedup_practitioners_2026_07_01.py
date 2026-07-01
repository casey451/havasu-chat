"""Search round-2 N3b — deactivate duplicate practitioner rows (GATED).

The "N Best" counts for eye care, dentists, and real estate are inflated by
individual practitioners listed separately from — and at the same address as —
their practice/brokerage (a Google-Places artifact: each doctor/agent gets its
own place row). This deactivates the redundant INDIVIDUAL rows (``Entity
.is_active = False``) while KEEPING the co-located distinctly-named practice as
the canonical listing.

Conservative scope (Casey, 2026-07-01): clear solo individuals only — teams,
groups, and ambiguous rows are left alone. Every row is anchored to a specific
kept practice; the script refuses to deactivate an individual unless its anchor
practice is present + active at run time. Reversible (flip is_active back).

Dry-run default; --apply --confirm gated.

Usage:
    .venv\\Scripts\\python.exe scripts/dedup_practitioners_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/dedup_practitioners_2026_07_01.py --apply --confirm
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

# (individual_id, ind_guard, anchor_id, anchor_guard, leaf_slug)
# Each individual is a solo practitioner co-located with the named anchor
# practice/brokerage, which is KEPT. Guards = lowercased name substrings.
_DEACTIVATE: tuple[tuple[str, str, str, str, str], ...] = (
    # --- Eye Care: solo ODs under Lake Havasu Family Eyecare ---
    ("ad5e5bbc-00ae-472d-be8f-299db9553544", "brooke vetter",
     "3aeb40d6-4961-41d7-a95c-f8357a07bef4", "family eyecare", "eye-care"),
    ("6e08e0e2-3c66-4335-9d38-2762a782d1de", "tania sobchuk",
     "3aeb40d6-4961-41d7-a95c-f8357a07bef4", "family eyecare", "eye-care"),
    ("81482d34-f88f-4d27-b352-5add7b9073de", "crystal eppling",
     "3aeb40d6-4961-41d7-a95c-f8357a07bef4", "family eyecare", "eye-care"),
    ("4da6b7a5-bff9-4dc3-85f3-9f89844edd23", "christina martinez",
     "3aeb40d6-4961-41d7-a95c-f8357a07bef4", "family eyecare", "eye-care"),
    ("77f76e41-e4d5-4d6d-bf05-573c1ea05b8e", "jack buckman",
     "99f0992f-f647-438d-ae44-3e4163e88f96", "family eyecare", "eye-care"),
    # --- Dentists: solo DDS/DMD under a named clinic ---
    ("bcd0bcba-9779-4e9b-9bd9-98dd67d49231", "thang ngo",
     "75dda913-0662-480c-a812-1783cc6ec0e9", "aspen dental", "dentists-and-orthodontists"),
    ("47adaf51-bad6-41f3-8122-3654515894d3", "eugenia osbon",
     "46dd88ca-c693-4c66-8de4-d6f5202f2785", "lakeview family dental", "dentists-and-orthodontists"),
    ("8c4037bf-292b-4314-bf59-4023174751f0", "kelsey m. little",
     "46dd88ca-c693-4c66-8de4-d6f5202f2785", "lakeview family dental", "dentists-and-orthodontists"),
    ("c7f1ae73-0cc1-45bd-afe9-ac24d78acc9f", "sheena l lyn",
     "46dd88ca-c693-4c66-8de4-d6f5202f2785", "lakeview family dental", "dentists-and-orthodontists"),
    ("0ea15802-6282-4a5c-a2fd-3b05ba0089ad", "kinzer deborah",
     "914d22ed-d8e2-4986-bd0d-f8720950b538", "pleasant valley dental", "dentists-and-orthodontists"),
    ("0dd53bd3-e9b5-4f5d-bb23-2bbdb322daaa", "jason yole",
     "914d22ed-d8e2-4986-bd0d-f8720950b538", "pleasant valley dental", "dentists-and-orthodontists"),
    ("e9ae3197-8cbc-4a15-975a-f1561b6b82ce", "lavene",
     "755d9a0c-9972-4a3c-9623-cb30f9a8eddd", "dental specialists", "dentists-and-orthodontists"),
    ("98a26522-f106-46a5-9a7f-61dbfd0859fa", "ryan bullen",
     "3586abbf-6ea2-457e-a48a-9a6e73ea8167", "bullen and beckstrand", "dentists-and-orthodontists"),
    ("acc89a0c-aaff-41cb-b7b7-7341b22e8ed1", "ryan kurtz",
     "31c155c2-7264-419c-b791-aa873b503d2a", "havasu dentistry", "dentists-and-orthodontists"),
    ("822a6ea6-513b-4e63-8f01-c57d60d180fc", "michael e. thomas",
     "cc845bbe-17f3-4720-b612-f2b68dcc3e91", "riviera family dental", "dentists-and-orthodontists"),
    ("c81f54ae-5096-464d-a07a-c60c36c4a992", "sorkin edward",
     "cfd5a665-cef6-42ac-97f2-9bbb0489bb73", "havasu valley dental", "dentists-and-orthodontists"),
    # --- Real Estate: solo agents under a named brokerage ---
    ("75646e42-80a8-4fa9-8319-3087d2af4db7", "brenda fischer",
     "3be61f8c-6388-4098-b3f7-08117fad79bd", "keller williams", "real-estate"),
    ("056d0540-4fc5-41a2-9411-bf978ed64e0d", "michelle pepper",
     "3be61f8c-6388-4098-b3f7-08117fad79bd", "keller williams", "real-estate"),
    ("3a73987d-b54d-4fce-8b52-3ebb521aee93", "paige mueller",
     "3be61f8c-6388-4098-b3f7-08117fad79bd", "keller williams", "real-estate"),
    ("0ecab925-3a24-47d6-9811-8d0fd767bebe", "lisa irwin",
     "dc7fb51f-6446-49ab-a52a-bce80986eb61", "realty one group mountain", "real-estate"),
    ("75789482-e5f9-4c0f-8338-020e73658161", "niky goudreau",
     "dc7fb51f-6446-49ab-a52a-bce80986eb61", "realty one group mountain", "real-estate"),
    ("6f28c785-77fa-4a47-b2f8-3b4f83a19f36", "rey de leon",
     "9e5ff591-4142-4d10-ab69-11ba5faa927f", "coldwell banker realty lake havasu", "real-estate"),
    ("ed687fa8-af69-4036-9d68-d8a558569b03", "travis redman",
     "e8f64d9f-0c57-4595-ac7d-9eb131d24aea", "sunstone real estate", "real-estate"),
    ("564ec3c1-2f99-4825-af25-4d6de30f440d", "travis mancuso",
     "3a8fd5d2-8672-4dd4-8581-ebee75a3ebe3", "havasu realty", "real-estate"),
    # NOTE: Jenna Quiggle (@2036 McCulloch) is eXp Realty, NOT the co-located APX
    # Real Estate Group — they only share a building. Excluded to avoid a
    # false collapse; her listing stays.
)


def _leaf_count(db, slug: str) -> int:
    c = db.query(Category).filter_by(slug=slug).first()
    if c is None:
        return -1
    return (
        db.query(func.count(EntityCategory.id))
        .join(Entity, Entity.id == EntityCategory.entity_id)
        .filter(
            EntityCategory.category_id == c.id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
        )
        .scalar()
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="N3b practitioner de-dup (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 74)
    print(f"N3b PRACTITIONER DE-DUP — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 74)
    print(f"DB target: …@{redacted}\n")

    slugs = sorted({row[4] for row in _DEACTIVATE})
    with SessionLocal() as db:
        before = {s: _leaf_count(db, s) for s in slugs}
        to_deactivate: list[Entity] = []
        skipped = 0
        print("Planned deactivations (individual → kept anchor practice):")
        for ind_id, ind_guard, anc_id, anc_guard, _slug in _DEACTIVATE:
            ind = db.get(Entity, ind_id)
            anc = db.get(Entity, anc_id)
            if ind is None or ind_guard not in (ind.name or "").lower():
                print(f"  SKIP {ind_id}: individual missing / name mismatch ({ind_guard!r})")
                skipped += 1
                continue
            if anc is None or anc_guard not in (anc.name or "").lower():
                print(f"  SKIP {ind.name[:34]!r}: anchor missing / mismatch ({anc_guard!r})")
                skipped += 1
                continue
            if not anc.is_active:
                print(f"  SKIP {ind.name[:34]!r}: anchor {anc.name[:30]!r} NOT active")
                skipped += 1
                continue
            if not ind.is_active:
                print(f"  noop {ind.name[:40]:40s} already inactive")
                continue
            print(f"  DEACTIVATE {ind.name[:40]:40s} | keep: {anc.name[:34]}")
            to_deactivate.append(ind)

        print(f"\nSummary: {len(to_deactivate)} to deactivate, {skipped} skipped.")
        print("\nLeaf counts (active primary rows) before:")
        for s in slugs:
            print(f"  {s:34s} {before[s]}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        for ind in to_deactivate:
            print(f"  snapshot: entity={ind.id} is_active True -> False")
            ind.is_active = False
        db.commit()

        print("\nLeaf counts (active primary rows) after:")
        for s in slugs:
            print(f"  {s:34s} {before[s]} -> {_leaf_count(db, s)}")
        print(f"\nAPPLIED: {len(to_deactivate)} practitioner rows deactivated (reversible).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
