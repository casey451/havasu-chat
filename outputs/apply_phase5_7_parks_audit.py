"""Apply the Phase 5.7 outdoors-parks-trails data-quality audit decisions.

Mirrors outputs/apply_phase5_6_shopping_audit.py: --dry-run first,
idempotent, sets updated_at, self-verifies via /category/<slug>
rendering count for the affected slugs.

Source of truth for the decisions:
``outputs/phase5_7_parks_audit.md`` §4 Slice A (FLIPs) + Slice B (DRAFTs).
Cross-referenced against the §1-inserted-entries edge-case rubric in
``outputs/phase5_7_ambig_audit_stdout.txt`` (the §9 "edge-case review"
table from the dump script).

Differs from 5.6's apply-script in two ways:
1. Lookup is name-based (the 4 affected entries have unique names in the
   30-entry cat-7 pool; no need for entity_id-prefix indirection). Single
   `_resolve_entity_by_name` helper with a safety assert that exactly one
   row matches.
2. Much smaller scope (3 FLIPs + 1 DRAFT vs 5.6's 11 FLIPs + 7 DRAFTs)
   reflecting Narrow scope + cleaner sustainability layer landed at
   `1dfd28e` pre-§1.

Usage:
    python outputs/apply_phase5_7_parks_audit.py --dry-run
    python outputs/apply_phase5_7_parks_audit.py

Net effect:
    /category/outdoors-parks-trails  : 30 -> 27 (3 flips out)
        - render-count drops to 26 (excluding the 1 draft provider:
          Altitude Trampoline Park)
    /category/events                 : +2 (Buses By The Bridge,
                                            Desert Storm Headquarters)
    /category/public-civic-resources : +1 (Parks & Recreation Department)
    drafts in outdoors-parks-trails  : +1 (Altitude Trampoline Park)

Re-run safety: the apply-script is idempotent. The FLIPs DELETE all
existing EntityCategory rows for the entity + INSERT a single target
row; re-running on an already-flipped entity DELETEs + re-INSERTs the
same row (net no-op except updated_at). Drafts are no-op'd if already
draft=True.

NOTE: 5 §1-inserted entries flagged as V1.5 dual-cat soft-edges (per
§9 of the audit doc) are intentionally KEPT in cat-7 with no script
action:
    - SARA Park Disc Golf Course (V1.5 dual-cat with cat-12)
    - Lake Havasu Motocross Park (V1.5 dual-cat with cat-12)
    - Ofd Racing (V1.5 dual-cat with cat-12 + venue-shape investigation)
    - Thompson Bay Beach (V1.5 dual-cat with cat-6)
    - Lake Havasu City Sportsman's Club (V1.5 dual-cat with cat-12)
Plus Butterfly Garden (KEEP per operator decision; V1.5 community-vs-
public-garden investigation).

DB-write — stop FastAPI dev server first to avoid events.db lock per
the 5.4 / 5.5 / 5.6 close-out gotcha.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# Slice A — 3 FLIPs out of /category/outdoors-parks-trails into other
# Tier-1 slugs. Keyed by Provider.provider_name / Entity.name (the 4
# affected entries have unique names in the 30-entry cat-7 pool;
# `_resolve_entity_by_name` asserts exactly one match). Single-cat flip
# per V1 policy + operator approval — removes outdoors-parks-trails
# EntityCategory link and replaces with the target slug's link, also
# resets Provider.category_id.
FLIPS_OUT_OF_PARKS: dict[str, str] = {
    # 2 -> events (cat-2) — event_venue primary_type; annual seasonal
    # activations rather than place-based recreation surfaces.
    "Buses By The Bridge": "events",                  # event_venue —
                                                       # annual bus-and-cars festival
    "Desert Storm Headquarters": "events",            # event_venue —
                                                       # annual boat poker run venue

    # 1 -> public-civic-resources (cat-13) — municipal department, not
    # a place-based recreation surface. Consumer discovery utility lives
    # in cat-13 ("how do I rent a pavilion / register for a program"),
    # not cat-7 ("where do I go play"). Operator-confirmed at session 2
    # decision-matrix review.
    "Parks & Recreation Department": "public-civic-resources",
                                                       # sports_activity_location —
                                                       # municipal dept
}

# Slice B — 1 DRAFT mark. Provider.draft=True hides the entity from
# /category/outdoors-parks-trails rendering but preserves the
# EntityCategory link so it can be re-evaluated / un-drafted later
# without re-creating the row. Per kickoff §1 indoor-entertainment-defer
# policy — Altitude Trampoline Park is the only obvious indoor candidate
# in the 30-entry cat-7 pool today.
DRAFTS_IN_PARKS: list[str] = [
    "Altitude Trampoline Park",  # amusement_park — indoor trampoline
                                  # facility; defer to V1.5 indoor-
                                  # entertainment phase
]


def _resolve_entity_by_name(session, name: str) -> Entity | None:
    """Resolve Entity.name exact-match. Asserts at most one active row;
    returns None if zero rows. Raises RuntimeError if multiple rows
    match (defensive against future name collisions)."""
    rows = session.scalars(
        select(Entity).where(Entity.name == name, Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"name-resolution collision: {len(rows)} active entities "
            f"match Entity.name={name!r}; expected exactly 1. Update "
            f"this apply-script to disambiguate before re-running."
        )
    return rows[0]


def _flip_entity_to_slug(
    session, entity_id: str, target_slug: str, slug_to_id: dict[str, int]
) -> None:
    """Replace all EntityCategory rows with a single (entity_id, target_id,
    is_primary=True) row, and update Provider.category_id to match."""
    target_id = slug_to_id[target_slug]
    session.execute(
        delete(EntityCategory).where(EntityCategory.entity_id == entity_id)
    )
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=target_id,
            is_primary=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is not None:
        prov.category_id = target_id
        prov.updated_at = datetime.now(UTC).replace(tzinfo=None)


def _mark_provider_draft(session, entity_id: str) -> bool:
    """Set Provider.draft=True for the entity. Returns True on success."""
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is None:
        return False
    prov.draft = True
    prov.updated_at = datetime.now(UTC).replace(tzinfo=None)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        slug_to_id: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }
        needed_slugs = (
            "outdoors-parks-trails",
            "events",
            "public-civic-resources",
        )
        for needed in needed_slugs:
            if needed not in slug_to_id:
                print(
                    f"ERROR: Category.slug={needed!r} not found.",
                    file=sys.stderr,
                )
                return 2

        print("=" * 70)
        print("Slice A — FLIPs OUT of /category/outdoors-parks-trails")
        print("=" * 70)
        flips_done = 0
        flips_missing = 0
        for name, target_slug in FLIPS_OUT_OF_PARKS.items():
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(
                    f"  MISSING entity name={name!r} "
                    f"(target={target_slug})"
                )
                flips_missing += 1
                continue
            _flip_entity_to_slug(session, ent.id, target_slug, slug_to_id)
            print(f"  {ent.name!r:42s}  ->  {target_slug}")
            flips_done += 1
        print(f"  total: {flips_done} flipped, {flips_missing} missing")
        print()

        print("=" * 70)
        print("Slice B — DRAFTs (Provider.draft=True; EntityCategory preserved)")
        print("=" * 70)
        drafts_done = 0
        drafts_missing = 0
        for name in DRAFTS_IN_PARKS:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  MISSING entity name={name!r}")
                drafts_missing += 1
                continue
            ok = _mark_provider_draft(session, ent.id)
            if not ok:
                print(
                    f"  MISSING provider for entity_id={ent.id} "
                    f"(name={ent.name!r})"
                )
                drafts_missing += 1
                continue
            print(f"  {ent.name!r:42s}  ->  draft=True")
            drafts_done += 1
        print(f"  total: {drafts_done} drafted, {drafts_missing} missing")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify — /category/<slug> rendering counts for the
        # affected slugs (post-apply).
        print()
        print("=" * 70)
        print("Self-verify — /category/<slug> rendering counts (post-apply)")
        print("=" * 70)
        for slug in (
            "outdoors-parks-trails",
            "events",
            "public-civic-resources",
        ):
            # Total EntityCategory linkage (ignores draft)
            total = session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM entities e
                    JOIN entity_categories ec ON ec.entity_id = e.id
                    JOIN categories c ON c.id = ec.category_id
                    WHERE c.slug = :slug AND e.is_active = 1
                    """
                ),
                {"slug": slug},
            ).scalar()
            # Draft-aware count (excludes draft providers)
            render = session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM entities e
                    JOIN entity_categories ec ON ec.entity_id = e.id
                    JOIN categories c ON c.id = ec.category_id
                    LEFT JOIN providers p ON p.entity_id = e.id
                    WHERE c.slug = :slug AND e.is_active = 1
                      AND (p.draft IS NULL OR p.draft = 0)
                    """
                ),
                {"slug": slug},
            ).scalar()
            print(f"  /category/{slug:30s} : total={total}  render={render}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
