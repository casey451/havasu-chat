"""Phase 4d — Cosmetic: realign re-filed providers' card subtype chip.

The leaf placement of the Phase 4 / 4b re-files is correct (driven by the PRIMARY
``EntityCategory`` link), but the small chip tag on each card reads
``Provider.subcategory`` — a slug from the COARSER chip taxonomy
(``app/categories/subcategories.py``) that the re-file scripts intentionally left
untouched. So a re-filed dojo can still carry a ``kids-lessons`` chip, a re-filed
yoga studio a ``gyms`` chip, etc. This one-off sets ``Provider.subcategory`` to the
right chip for each re-filed row. It is scrape-safe: ``places_load`` does not write
``Provider.subcategory``, so the value sticks.

  python scripts/phase4d_card_tag_realign.py            # preview (default)
  python scripts/phase4d_card_tag_realign.py --apply    # persist + undo snapshot

The chip taxonomy is coarser than the leaf taxonomy, so the leaf -> chip map is a
deliberate, best-fit choice (Casey-approved 2026-06-17):

  martial-arts          -> ``martial-arts``   ("Martial Arts")
  dance-studios         -> ``studios``        ("Studios")
  yoga-and-pilates      -> ``studios``        ("Studios")
  personal-training     -> ``gyms``           ("Gyms"; gym-adjacent, the nearest chip)
  sporting-goods        -> ``biking``         ("Biking"; the bike shop's true descriptor)
  nutrition-and-wellness-> None               (blank; no honest chip beats a wrong one)

``None`` clears the chip (card shows no subtype tag). ``Provider.primary_category``
is a separate canonical field and is deliberately NOT touched here.

Per-row safety (no guessing): each row must resolve to exactly one active provider
whose PRIMARY ``EntityCategory`` is actually on the expected leaf — otherwise it is
reported (``no_match`` / ``ambiguous`` / ``not_on_leaf``) and SKIPPED. A row already
carrying the target chip is ``already_correct`` and skipped. ``--apply`` writes an
undo snapshot (prior ``subcategory`` per row) to ``relay/`` before the commit;
dry-run asserts zero writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.categories.subcategories import subcategory_by_slug  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# Leaf slug -> chip subcategory slug (None => blank the chip). See module docstring.
LEAF_TO_CHIP: dict[str, str | None] = {
    "martial-arts": "martial-arts",
    "dance-studios": "studios",
    "yoga-and-pilates": "studios",
    "personal-training": "gyms",
    "sporting-goods": "biking",
    "nutrition-and-wellness": None,
}


@dataclass(frozen=True)
class RealignSpec:
    """One re-filed provider: match by name, expected to sit on ``leaf`` now."""

    name_contains: str
    leaf: str


# Mirrors the Phase 4 (``phase4_fitness_load``) + Phase 4b (``phase4b_misfile_recat``)
# recat targets — the rows whose leaf moved but whose chip tag did not.
REALIGN_SPECS: list[RealignSpec] = [
    # Phase 4 martial-arts re-files.
    RealignSpec("arevalo", "martial-arts"),
    RealignSpec("shao-lin", "martial-arts"),
    RealignSpec("elite martial", "martial-arts"),
    RealignSpec("black belt", "martial-arts"),
    RealignSpec("tap room", "martial-arts"),
    # Phase 4 dance re-files.
    RealignSpec("arizona coast", "dance-studios"),
    RealignSpec("foot lite", "dance-studios"),
    # Phase 4 yoga/pilates re-files.
    RealignSpec("align and define", "yoga-and-pilates"),
    RealignSpec("pilates of lake havasu", "yoga-and-pilates"),
    RealignSpec("crazy ed", "yoga-and-pilates"),
    # Phase 4 personal-training re-files.
    RealignSpec("heart and sole", "personal-training"),
    RealignSpec("studio 2959", "personal-training"),
    # Phase 4 nutrition + sporting-goods re-files.
    RealignSpec("nutrition one", "nutrition-and-wellness"),
    RealignSpec("havasu bike and fitness", "sporting-goods"),
    # Phase 4b re-files.
    RealignSpec("seibukan", "martial-arts"),
    RealignSpec("next generation mixed martial", "martial-arts"),
    RealignSpec("women kravmaga", "martial-arts"),
    RealignSpec("the dance center", "dance-studios"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _category_id_by_slug(db: Session) -> dict[str, int]:
    return {c.slug: c.id for c in db.scalars(select(Category)).all()}


def _find_provider_by_name(db: Session, term: str) -> list[Provider]:
    like = f"%{term.lower()}%"
    return list(
        db.scalars(
            select(Provider)
            .join(Entity, Provider.entity_id == Entity.id)
            .where(Provider.is_active.is_(True))
            .where(Entity.is_active.is_(True))
            .where(Entity.name.ilike(like))
        ).all()
    )


def _primary_category_id(db: Session, entity_id: str) -> int | None:
    ec = db.scalars(
        select(EntityCategory)
        .where(EntityCategory.entity_id == entity_id)
        .where(EntityCategory.is_primary.is_(True))
        .limit(1)
    ).first()
    return ec.category_id if ec else None


# --------------------------------------------------------------------------- #
# Realign
# --------------------------------------------------------------------------- #
def realign(
    db: Session,
    *,
    apply: bool,
    cat_by_slug: dict[str, int],
    undo: list[dict[str, Any]],
) -> Counter[str]:
    c: Counter[str] = Counter()

    for spec in REALIGN_SPECS:
        c["total"] += 1
        if spec.leaf not in LEAF_TO_CHIP:
            c["bad_spec"] += 1
            print(f"--- bad_spec (no chip mapping): {spec.leaf!r}")
            continue
        target_chip = LEAF_TO_CHIP[spec.leaf]

        leaf_id = cat_by_slug.get(spec.leaf)
        if leaf_id is None:
            c["leaf_missing"] += 1
            print(f"--- LEAF MISSING: {spec.leaf!r} for {spec.name_contains!r}")
            continue

        matches = _find_provider_by_name(db, spec.name_contains)
        if not matches:
            c["no_match"] += 1
            print(f"--- no_match: {spec.name_contains!r}")
            continue
        if len(matches) > 1:
            c["ambiguous"] += 1
            names = ", ".join(sorted(p.provider_name for p in matches))
            print(f"--- ambiguous ({len(matches)}, skip): {spec.name_contains!r} -> {names}")
            continue

        provider = matches[0]
        # Only realign a row that actually sits on the expected leaf now.
        if _primary_category_id(db, provider.entity_id) != leaf_id:
            c["not_on_leaf"] += 1
            print(
                f"--- not_on_leaf (skip): {provider.provider_name} is not primary on "
                f"{spec.leaf!r}"
            )
            continue

        current = provider.subcategory
        if current == target_chip:
            c["already_correct"] += 1
            print(f"--- already_correct (skip): {provider.provider_name} chip={current!r}")
            continue

        c["would_set"] += 1
        print(
            f"--- SET: {provider.provider_name}  subcategory {current!r} -> {target_chip!r}  "
            f"(leaf {spec.leaf})"
        )
        if not apply:
            continue

        undo.append(
            {
                "op": "subcategory",
                "provider_id": provider.id,
                "name": provider.provider_name,
                "prior_subcategory": current,
                "new_subcategory": target_chip,
            }
        )
        provider.subcategory = target_chip
        db.flush()
        c["set"] += 1

    return c


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_phase4d_card_tag_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def run(db: Session, *, apply: bool, snapshot_dir: Path | None = None) -> Counter[str]:
    cat_by_slug = _category_id_by_slug(db)
    undo: list[dict[str, Any]] = []

    print("\n=== REALIGN (card subtype chip on re-filed rows) ===")
    c = realign(db, apply=apply, cat_by_slug=cat_by_slug, undo=undo)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: applied {len(undo)} ops; undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply (no eligible rows).")

    print("\n--- REALIGN summary ---")
    for k in ("total", "no_match", "ambiguous", "not_on_leaf", "already_correct",
              "leaf_missing", "bad_spec", "would_set", "set"):
        print(f"  {k:16} {c[k]}")

    if not apply:
        assert c["set"] == 0, "dry-run must not persist"
    return c


def _validate_chip_map() -> None:
    """Every non-None chip in the map must be a real subcategory slug."""
    for leaf, chip in LEAF_TO_CHIP.items():
        if chip is not None and subcategory_by_slug(chip) is None:
            raise SystemExit(f"chip {chip!r} for leaf {leaf!r} is not a known subcategory slug")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Persist updates + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    _validate_chip_map()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
