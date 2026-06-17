"""Deactivate a place-only DUPLICATE entity (gated, reference-guarded).

A leaf page renders a "place card" for any active ``Entity`` whose PRIMARY
``EntityCategory`` is the leaf — even with no ``Provider`` (see
``app/categories/leaf_pages.leaf_listing`` / ``_place_card``). So a stray
provider-less entity shows as a bare, link-less duplicate card next to the real
provider-backed one. ``provider_merge.merge_providers`` can't touch it (it needs
two Providers), so this script retires the duplicate Entity directly.

Surfaced 2026-06-17: TWO "Next Generation Mixed Martial Arts" cards on the
martial-arts leaf — the real provider (slug ``next-generation-mixed-martial-arts-2``)
and a bare place card. The bike/Next-Gen dedupe (``scripts/dedupe_providers.py``)
found only ONE active Provider by that name, confirming the bare one is
Entity-only.

  python scripts/dedupe_place_entity.py            # preview / diagnostic (default)
  python scripts/dedupe_place_entity.py --apply    # deactivate dup(s) + undo snapshot

Per spec (``name_contains`` + ``leaf``): gather active entities whose primary link
is that leaf and whose name matches. The KEEPER is the one with an active,
non-draft Provider; the DUPLICATE(s) are the provider-less place entities. The dry
run reports the keeper, each duplicate, AND each duplicate's inbound references
(events / programs / photos / peer-recs / favorites / claims).

No-guess safety:
  * require exactly ONE keeper (a provider-backed entity) and >= 1 place-only dup,
    else report and SKIP;
  * REFUSE to deactivate a duplicate that has ANY inbound references — those must
    be repointed to the keeper first (manual / future extension), never silently
    orphaned.

``--apply`` sets ``Entity.is_active = False`` on each clean duplicate (which drops
it from both the provider and place leaf queries) and writes an undo snapshot
(entity id + prior ``is_active``) to ``relay/`` before the commit. Dry-run asserts
zero writes.
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

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    Claim,
    Entity,
    EntityCategory,
    Event,
    PeerRecommendation,
    Photo,
    Program,
    Provider,
    UserFavorite,
)

# Entity-level inbound FKs we check before retiring a duplicate entity.
_ENTITY_REFS: tuple[tuple[Any, str], ...] = (
    (Event, "entity_id"),
    (Program, "entity_id"),
    (Photo, "entity_id"),
    (PeerRecommendation, "entity_id"),
    (UserFavorite, "entity_id"),
    (Claim, "entity_id"),
)


@dataclass(frozen=True)
class DedupeSpec:
    name_contains: str
    leaf: str
    reason: str


SPECS: list[DedupeSpec] = [
    DedupeSpec(
        "next generation mixed martial",
        "martial-arts",
        "bare place-only entity duplicates the real Next Generation MMA provider",
    ),
]


def _leaf_id(db: Session, slug: str) -> int | None:
    cat = db.scalars(select(Category).where(Category.slug == slug).limit(1)).first()
    return cat.id if cat else None


def _entities_on_leaf_by_name(db: Session, term: str, leaf_id: int) -> list[Entity]:
    like = f"%{term.lower()}%"
    return list(
        db.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(EntityCategory.category_id == leaf_id)
            .where(EntityCategory.is_primary.is_(True))
            .where(Entity.is_active.is_(True))
            .where(Entity.name.ilike(like))
        ).all()
    )


def _active_provider(db: Session, entity_id: str) -> Provider | None:
    return db.scalars(
        select(Provider)
        .where(Provider.entity_id == entity_id)
        .where(Provider.is_active.is_(True))
        .where(Provider.draft.is_(False))
        .limit(1)
    ).first()


def _ref_counts(db: Session, entity_id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for model, attr in _ENTITY_REFS:
        n = int(
            db.scalar(
                select(func.count()).select_from(model).where(getattr(model, attr) == entity_id)
            )
            or 0
        )
        if n:
            out[model.__tablename__] = n
    return out


def dedupe(db: Session, *, apply: bool, undo: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()

    for spec in SPECS:
        c["total"] += 1
        print(f"\n=== {spec.name_contains!r} on {spec.leaf!r} — {spec.reason} ===")
        leaf_id = _leaf_id(db, spec.leaf)
        if leaf_id is None:
            c["leaf_missing"] += 1
            print(f"--- LEAF MISSING: {spec.leaf!r}")
            continue

        ents = _entities_on_leaf_by_name(db, spec.name_contains, leaf_id)
        keepers = [e for e in ents if _active_provider(db, e.id) is not None]
        dups = [e for e in ents if _active_provider(db, e.id) is None]

        for e in ents:
            prov = _active_provider(db, e.id)
            tag = "KEEPER (provider-backed)" if prov else "place-only"
            print(f"--- {tag}: entity id={e.id} name={e.name!r} slug={e.slug!r} "
                  f"type={getattr(e, 'entity_type', None)!r}")

        if len(keepers) != 1:
            c["skipped"] += 1
            print(f"--- SKIP: need exactly 1 provider-backed keeper, found {len(keepers)}")
            continue
        if not dups:
            c["skipped"] += 1
            print("--- SKIP: no place-only duplicate to retire")
            continue

        for dup in dups:
            refs = _ref_counts(db, dup.id)
            if refs:
                c["has_references"] += 1
                print(f"--- REFUSE (has references, handle manually): {dup.id} refs={refs}")
                continue
            c["would_deactivate"] += 1
            print(f"--- DEACTIVATE: place-only dup entity {dup.id} ({dup.name!r}) — 0 references")
            if not apply:
                continue
            undo.append(
                {
                    "op": "deactivate_entity",
                    "entity_id": dup.id,
                    "name": dup.name,
                    "prior_is_active": dup.is_active,
                }
            )
            dup.is_active = False
            db.flush()
            c["deactivated"] += 1

    return c


def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_dedupe_place_entity_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def run(db: Session, *, apply: bool, snapshot_dir: Path | None = None) -> Counter[str]:
    undo: list[dict[str, Any]] = []
    c = dedupe(db, apply=apply, undo=undo)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: deactivated {len(undo)} entity(ies); undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply.")

    print("\n--- summary ---")
    for k in ("total", "leaf_missing", "skipped", "has_references", "would_deactivate",
              "deactivated"):
        print(f"  {k:16} {c[k]}")

    if not apply:
        assert c["deactivated"] == 0, "dry-run must not persist"
    return c


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview/diagnose without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Deactivate dup(s) + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
