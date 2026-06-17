"""Phase 4b — Targeted recat of 4 misfiled martial-arts / dance rows.

Source of truth: ``relay/ASK_HAVA_TARGETED_RECAT_SCOPE_2026-06-17.md``. Surfaced by
the PR #372 name-rule backfill dry-run: four businesses already in the DB are
misfiled and — because they carry a stale ``Provider.category_id`` — will NOT
self-heal when the scraper re-pulls them. They need a deliberate, gated re-file,
the same shape as Phase 4 (``scripts/phase4_fitness_load.py``).

  python scripts/phase4b_misfile_recat.py            # preview (default)
  python scripts/phase4b_misfile_recat.py --dry-run  # explicit preview
  python scripts/phase4b_misfile_recat.py --apply    # persist + undo snapshot

Why a TARGETED script and not the broad backfill: ``scripts/backfill_leaf_categories.py
--apply`` would fix these four BUT also revert the Phase 4 pilates studios + studio
2959 back to gyms (filed against Google's ``gym`` type, no curation guard yet). So we
touch ONLY these four rows.

How a move works: the leaf page lists an entity by its PRIMARY ``EntityCategory``
link, so a move repoints that link from the source leaf to the target leaf
(promoting an existing target link if one is already present, else repointing the
source primary). ``Provider.category_id`` is also set to the target leaf so the
Google Places re-scrape's preserve-and-ensure logic keeps the move sticky across
future pulls (without it the next re-pull would re-insert the OLD leaf link from
the stale ``Provider.category_id``).

Safety check (stronger than Phase 4's source-leaf assertion, and needs no prior
knowledge of where each row currently sits): for each target row, assert
``name_leaf_rules.leaf_for_name(provider.provider_name) == target_leaf``. The name
rule is the authority for this slice (it's how the backfill dry-run found these),
so if it does not agree the row is reported ``unexpected`` and SKIPPED — no
guessing (repo rule). A row already sitting on the target leaf is reported
``already_correct`` and left untouched.

On ``--apply`` an undo snapshot (prior EntityCategory state + prior
``Provider.category_id``) is written to ``relay/`` before the commit. Dry-run
asserts zero writes.
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

from app.contrib.name_leaf_rules import leaf_for_name  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# Leaf Category slugs (level=1) under the Fitness & Classes department.
LEAF_MARTIAL = "martial-arts"
LEAF_DANCE = "dance-studios"


# --------------------------------------------------------------------------- #
# Spec
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecatSpec:
    """Move one existing entity's primary EntityCategory onto ``target_leaf``.

    ``name_contains`` matches against ``Entity.name`` (case-insensitive); exactly
    one active provider must match. ``target_leaf`` is validated against the name
    rule (``leaf_for_name``), which is this slice's authority.
    """

    name_contains: str  # case-insensitive substring match against Entity.name
    target_leaf: str  # leaf the primary link must end on
    reason: str


# The 4 misfiled rows the #372 name-rule backfill dry-run found. Each carries a
# stale category_id, so a re-scrape will not self-heal it — hence this targeted
# re-file. Search terms picked to match exactly one live provider (see scope doc):
# "women kravmaga" — NOT bare "kravmaga", which the 2026-06-17 dry-run showed also
# matches a second business, "Arizona Kravmaga" (out of scope for this slice);
# "next generation mixed martial" because the row is the long-form name.
RECAT_SPECS: list[RecatSpec] = [
    RecatSpec("seibukan", LEAF_MARTIAL, "Seibukan Karate-Do (karate)"),
    RecatSpec("next generation mixed martial", LEAF_MARTIAL, "Next Generation MMA"),
    RecatSpec("women kravmaga", LEAF_MARTIAL, "Women KravMaga Self Defense"),
    RecatSpec("the dance center", LEAF_DANCE, "The Dance Center (sports_school type)"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _category_id_by_slug(db: Session) -> dict[str, int]:
    return {c.slug: c.id for c in db.scalars(select(Category)).all()}


def _find_provider_by_name(db: Session, term: str) -> list[Provider]:
    """Active providers whose entity name contains ``term`` (case-insensitive)."""
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


def _primary_entity_category(db: Session, entity_id: str) -> EntityCategory | None:
    return db.scalars(
        select(EntityCategory)
        .where(EntityCategory.entity_id == entity_id)
        .where(EntityCategory.is_primary.is_(True))
        .limit(1)
    ).first()


def _slug_for_cat(cat_by_slug: dict[str, int], cid: int | None) -> str:
    if cid is None:
        return "none"
    return next((s for s, c in cat_by_slug.items() if c == cid), str(cid))


# --------------------------------------------------------------------------- #
# RECAT
# --------------------------------------------------------------------------- #
def recat_listings(
    db: Session,
    *,
    apply: bool,
    cat_by_slug: dict[str, int],
    undo: list[dict[str, Any]],
) -> Counter[str]:
    c: Counter[str] = Counter()

    for spec in RECAT_SPECS:
        c["total"] += 1
        tgt_id = cat_by_slug.get(spec.target_leaf)
        if tgt_id is None:
            c["leaf_missing"] += 1
            print(f"--- LEAF MISSING: {spec.target_leaf!r} for {spec.name_contains!r}")
            continue

        matches = _find_provider_by_name(db, spec.name_contains)
        if not matches:
            c["no_match"] += 1
            print(f"--- no_match: {spec.name_contains!r}")
            continue
        if len(matches) > 1:
            c["ambiguous"] += 1
            names = ", ".join(sorted(p.provider_name for p in matches))
            print(f"--- ambiguous ({len(matches)} matches, skip): {spec.name_contains!r} -> {names}")
            continue

        provider = matches[0]

        # Safety check: the name rule is the authority for this slice. If it does
        # not independently agree the row belongs on the target leaf, skip it.
        ruled = leaf_for_name(provider.provider_name)
        if ruled != spec.target_leaf:
            c["unexpected"] += 1
            print(
                f"--- unexpected (skip): {provider.provider_name!r} — name rule says "
                f"{ruled!r}, spec target is {spec.target_leaf!r}"
            )
            continue

        primary = _primary_entity_category(db, provider.entity_id)
        if primary is not None and primary.category_id == tgt_id:
            c["already_correct"] += 1
            print(f"--- already_correct (skip): {provider.provider_name} on {spec.target_leaf}")
            continue

        cur = _slug_for_cat(cat_by_slug, primary.category_id if primary else None)
        c["would_move"] += 1
        print(
            f"--- MOVE: {provider.provider_name}  {cur} -> {spec.target_leaf}  ({spec.reason})"
        )
        if not apply:
            continue

        all_ecs = list(
            db.scalars(
                select(EntityCategory).where(EntityCategory.entity_id == provider.entity_id)
            ).all()
        )
        undo.append(
            {
                "op": "recat",
                "entity_id": provider.entity_id,
                "provider_id": provider.id,
                "name": provider.provider_name,
                "provider_category_id": provider.category_id,
                "entity_categories": [
                    {"id": ec.id, "category_id": ec.category_id, "is_primary": ec.is_primary}
                    for ec in all_ecs
                ],
            }
        )

        existing_tgt = next((ec for ec in all_ecs if ec.category_id == tgt_id), None)
        if existing_tgt is not None:
            # Target link already present: promote it, demote the source link.
            existing_tgt.is_primary = True
            if primary is not None and primary.id != existing_tgt.id:
                primary.is_primary = False
        elif primary is not None:
            # Repoint the source primary link onto the target leaf.
            primary.category_id = tgt_id
        else:
            # No primary link at all: create one on the target leaf.
            db.add(EntityCategory(entity_id=provider.entity_id, category_id=tgt_id, is_primary=True))
        # Sustainability: the Google Places re-scrape (places_load.py) PRESERVES an
        # operator-set Provider.category_id and re-ensures the matching primary
        # EntityCategory from it. Setting it to the target leaf here is what keeps
        # the move sticky across future scrapes.
        provider.category_id = tgt_id
        db.flush()
        c["moved"] += 1

    return c


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_phase4b_misfile_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def run(
    db: Session,
    *,
    apply: bool,
    snapshot_dir: Path | None = None,
) -> Counter[str]:
    cat_by_slug = _category_id_by_slug(db)
    undo: list[dict[str, Any]] = []

    print("\n=== RECAT (targeted re-file of 4 misfiled rows) ===")
    recat = recat_listings(db, apply=apply, cat_by_slug=cat_by_slug, undo=undo)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: applied {len(undo)} ops; undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply (no eligible rows).")

    print("\n--- RECAT summary ---")
    for k in ("total", "no_match", "ambiguous", "unexpected", "already_correct",
              "leaf_missing", "would_move", "moved"):
        print(f"  {k:18} {recat[k]}")

    if not apply:
        assert recat["moved"] == 0, "dry-run must not persist"
    return recat


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Persist updates + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
