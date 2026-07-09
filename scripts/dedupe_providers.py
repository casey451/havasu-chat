"""Dedupe known duplicate providers via ``provider_merge.merge_providers``.

Source of truth: ``relay/ASK_HAVA_NEXT_SESSION_2026-06-17.md`` §2 (+ the 2026-07-08
re-audit). Known duplicates, all gated like every prod data op (``--dry-run``
default / ``--apply``, per-pair diff, undo snapshot to ``relay/``, dry-run asserts
zero merges):

  python scripts/dedupe_providers.py            # preview (default)
  python scripts/dedupe_providers.py --dry-run  # explicit preview
  python scripts/dedupe_providers.py --apply    # persist + undo snapshot

Pairs:
  1. "Lake Havasu Bike & Fitness" (the ``&`` variant, suspected duplicate) folded
     into "Havasu Bike and Fitness" (the real bike shop, the ``and`` variant moved
     to sporting-goods in Phase 4). Distinct names -> resolve keep/dup by name.
  2. "Next Generation Mixed Martial Arts" appears twice on the martial-arts leaf:
     one real provider (has a ``google_place_id``) and a bare/thin duplicate
     (no place id). Same name -> keeper is the one WITH a ``google_place_id``.
  3. "911 Mobile Mechanic" appears twice (2026-07-08 re-audit). Same name ->
     keeper is the one WITH a ``google_place_id``; ambiguous pairs skip safely.

``merge_providers`` soft-retires the loser (``is_active=False``, ``draft=True``)
and stamps a ``merged_into_slug`` redirect, gap-fills the keeper's empty scalars,
repoints FKs (events/programs/favorites/claims), and refuses to retire an
operator-sourced row. It is reversible-ish (the loser is tombstoned, not
hard-deleted), but gap-filled keeper fields are NOT auto-restorable — so we
snapshot the plan + the loser's prior active flags before each merge.

No-guess rule: each pair must resolve to exactly one keeper and at least one
distinct duplicate. Anything ambiguous (or a "duplicate" that isn't a Provider
row at all — e.g. an Entity-only place card) is reported and SKIPPED for manual
handling, never merged blindly. The script also prints Cycle Therapy's current
leaf as a read-only sanity check (the other real cycling shop).
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

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402


# --------------------------------------------------------------------------- #
# Spec
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MergeSpec:
    """One dedupe. ``gather`` collects active candidates by name (ilike).

    ``strategy``:
      * ``"names"`` — keeper is the lone candidate matching ``keep_contains``,
        the duplicate(s) match ``dup_contains`` (substring). Use when names differ.
      * ``"place_id"`` — names collide, so the keeper is the lone candidate WITH a
        ``google_place_id`` and the duplicate(s) are those without one.
      * ``"slugs"`` — names AND place-ids collide (two Google records for one
        business), so pick keeper/dup by EXACT slug: ``keep_contains`` is the
        survivor slug, ``dup_contains`` the loser slug. Use when a human has
        already chosen which of two equally-real listings to keep.
    """

    label: str
    gather: str
    strategy: str
    reason: str
    keep_contains: str | None = None
    dup_contains: str | None = None


MERGE_SPECS: list[MergeSpec] = [
    MergeSpec(
        label="Bike shop dup",
        gather="bike",  # broad on purpose: "&" vs "and" differ, so match the common token
        strategy="names",
        keep_contains="havasu bike and fitness",
        dup_contains="lake havasu bike",
        reason="'Lake Havasu Bike & Fitness' duplicates the real 'Havasu Bike and Fitness'",
    ),
    MergeSpec(
        label="Next Generation MMA dup",
        gather="next generation mixed martial",
        strategy="place_id",
        reason="bare Next Gen MMA entry duplicates the real provider (the one with a place id)",
    ),
    # 2026-07-08 re-audit (item 6): two "911 Mobile Mechanic" rows — the SAME
    # business (identical website 911mobilemechanic.com), but Google has two place
    # records at different addresses, so BOTH carry a (distinct) google_place_id.
    # The place_id strategy therefore skipped it (dry-run 2026-07-09); Casey chose
    # to keep the 620 Lake Havasu Ave listing (`911-mobile-mechanic`) and retire
    # the 2660 Sweetwater one (a gas-station geocode). Resolve by exact slug.
    MergeSpec(
        label="911 Mobile Mechanic dup",
        gather="911 mobile mechanic",
        strategy="slugs",
        keep_contains="911-mobile-mechanic",
        dup_contains="911-mobile-mechanic-2",
        reason="same business (same website), two Google records — keep 620 Lake Havasu Ave",
    ),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _candidates(db: Session, term: str) -> list[Provider]:
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


def _primary_leaf_slug(db: Session, entity_id: str) -> str | None:
    ec = db.scalars(
        select(EntityCategory)
        .where(EntityCategory.entity_id == entity_id)
        .where(EntityCategory.is_primary.is_(True))
        .limit(1)
    ).first()
    if ec is None:
        return None
    cat = db.get(Category, ec.category_id)
    return cat.slug if cat else str(ec.category_id)


def _describe(db: Session, p: Provider) -> str:
    return (
        f"id={p.id} name={p.provider_name!r} slug={p.slug!r} "
        f"place_id={p.google_place_id!r} leaf={_primary_leaf_slug(db, p.entity_id)!r} "
        f"source={p.source!r}"
    )


def _resolve(db: Session, spec: MergeSpec) -> tuple[Provider | None, list[Provider], str]:
    """Return (keeper, duplicates, note). keeper None => skip (note says why)."""
    cands = _candidates(db, spec.gather)
    if not cands:
        return None, [], "no_match (nothing found)"

    if spec.strategy == "names":
        keeps = [p for p in cands if spec.keep_contains and spec.keep_contains in p.provider_name.lower()]
        dups = [p for p in cands if spec.dup_contains and spec.dup_contains in p.provider_name.lower()]
        # A row matching both filters (e.g. "lake havasu bike and fitness") is
        # ambiguous — bail rather than guess.
        overlap = {p.id for p in keeps} & {p.id for p in dups}
        if overlap:
            return None, [], f"ambiguous (a row matched both keep+dup filters: {overlap})"
        if len(keeps) != 1:
            return None, [], f"keeper not unique ({len(keeps)} matched {spec.keep_contains!r})"
        dups = [p for p in dups if p.id != keeps[0].id]
        if not dups:
            return None, [], "no distinct duplicate to merge"
        return keeps[0], dups, "ok"

    if spec.strategy == "slugs":
        keeps = [p for p in cands if p.slug == spec.keep_contains]
        dups = [p for p in cands if p.slug == spec.dup_contains]
        if len(keeps) != 1:
            return None, [], f"keeper slug not unique ({len(keeps)} matched {spec.keep_contains!r})"
        if not dups:
            return None, [], f"no duplicate matched slug {spec.dup_contains!r}"
        return keeps[0], dups, "ok"

    if spec.strategy == "place_id":
        with_pid = [p for p in cands if (p.google_place_id or "").strip()]
        without_pid = [p for p in cands if not (p.google_place_id or "").strip()]
        if len(with_pid) != 1:
            return None, [], (
                f"keeper not unique ({len(with_pid)} candidates have a place_id; "
                f"need exactly 1)"
            )
        if not without_pid:
            return None, [], (
                "no place-id-less duplicate among Provider rows (the bare entry may "
                "be an Entity-only place card — handle manually)"
            )
        return with_pid[0], without_pid, "ok"

    return None, [], f"unknown strategy {spec.strategy!r}"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_dedupe_providers_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def dedupe(
    db: Session,
    *,
    apply: bool,
    undo: list[dict[str, Any]],
) -> Counter[str]:
    c: Counter[str] = Counter()

    for spec in MERGE_SPECS:
        c["total"] += 1
        print(f"\n=== {spec.label} — {spec.reason} ===")
        keeper, dups, note = _resolve(db, spec)
        if keeper is None:
            c["skipped"] += 1
            print(f"--- SKIP: {note}")
            for p in _candidates(db, spec.gather):
                print(f"      candidate: {_describe(db, p)}")
            continue

        print(f"--- KEEP: {_describe(db, keeper)}")
        for dup in dups:
            print(f"--- DUP : {_describe(db, dup)}")
            # Always compute the plan (no mutations) for the diff / blast radius.
            plan = merge_providers(db, keep_id=keeper.id, dup_id=dup.id, dry_run=True)
            print(
                f"      plan: gap_fill={plan.gap_filled}  repoint={dict(plan.repointed)}  "
                f"combined_source={plan.combined_source!r}"
            )
            c["would_merge"] += 1
            if not apply:
                continue

            keep_prior = {f: getattr(keeper, f, None) for f in plan.gap_filled}
            undo.append(
                {
                    "op": "merge",
                    "keep_id": keeper.id,
                    "keep_name": keeper.provider_name,
                    "dup_id": dup.id,
                    "dup_name": dup.provider_name,
                    "plan_gap_filled": list(plan.gap_filled),
                    "plan_repointed": dict(plan.repointed),
                    "keep_prior_gapfill": keep_prior,
                    "dup_prior": {
                        "is_active": dup.is_active,
                        "draft": dup.draft,
                        "pending_review": dup.pending_review,
                        "attributes": dict(dup.attributes or {}),
                        "google_place_id": dup.google_place_id,
                    },
                }
            )
            merge_providers(db, keep_id=keeper.id, dup_id=dup.id, dry_run=False)
            db.flush()
            c["merged"] += 1

    return c


def sanity_check_cycle_therapy(db: Session) -> None:
    print("\n=== Sanity check: Cycle Therapy (read-only) ===")
    rows = _candidates(db, "cycle therapy")
    if not rows:
        print("--- Cycle Therapy not found among active providers.")
        return
    for p in rows:
        print(f"--- {_describe(db, p)}")


def run(db: Session, *, apply: bool, snapshot_dir: Path | None = None) -> Counter[str]:
    undo: list[dict[str, Any]] = []
    c = dedupe(db, apply=apply, undo=undo)
    sanity_check_cycle_therapy(db)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: applied {len(undo)} merge(s); undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply (no eligible duplicates).")

    print("\n--- DEDUPE summary ---")
    for k in ("total", "skipped", "would_merge", "merged"):
        print(f"  {k:14} {c[k]}")

    if not apply:
        assert c["merged"] == 0, "dry-run must not merge"
    return c


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Persist merges + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
