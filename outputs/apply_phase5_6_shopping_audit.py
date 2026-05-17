"""Apply the Phase 5.6 shopping-essentials data-quality audit decisions.

Mirrors outputs/apply_phase5_3_home_property_audit.py: id-prefix-keyed
dicts, --dry-run first, idempotent, sets updated_at, self-verifies via
/category/<slug> rendering count for the affected slugs.

Source of truth for the decisions:
``outputs/phase5_6_ambig_audit_data.json`` + the §2 edge-case review
section of outputs/phase5_6_ambig_audit_dump.py stdout.

Usage:
    python outputs/apply_phase5_6_shopping_audit.py --dry-run
    python outputs/apply_phase5_6_shopping_audit.py

Net effect:
    /category/shopping-essentials    : 94 -> 83 (11 flips out)
        - render-count drops further to ~76 (excluding the 7 draft providers)
    /category/health-wellness-care   : +5 (Hospice + 2 eye-exam docs + 2 medical_clinic
                                          eye-care centers added in §4 top-10 sweep)
    /category/auto-rv-fuel           : +4 (2 Anderson Powersports + Just 4 Fun + Lead Dog)
    /category/home-property-services : +2 (AQUACLEAN + Apple Valley Alarms)
    drafts in shopping-essentials    : +7 (5 B2B wholesale + community garden + Anderson AZ West)

Re-run safety: the apply-script is idempotent. The first run flipped 9 + drafted 7;
the §4 top-10 sweep surfaced 2 additional medical_clinic eye-care misroutes and
extended FLIPS_OUT_OF_SHOPPING from 9 to 11. Re-running re-applies the 9 original
flips as no-ops (DELETE + re-INSERT same row, new created_at) and applies the 2
new flips. Drafts are no-op'd (already draft=True).

NOTE: 13 borderline edge-case routings are intentionally KEPT in shopping-
essentials per operator review:
    - Havasu Computers (electronics retail)
    - Clothes Closet Lake Havasu (thrift)
    - Hospice of Havasu Resale Store (thrift — distinct from the main hospice)
    - Dillard's (department store)
    - Serrano's Nursery (retail nursery)
    - Phil's Band Instrument Repair (retail-adjacent)
    - Havasu Technologies / QED / Vertical IT / ReConnected Phone / Whiz Kid
      (IT/electronics service hybrids — borderline; default KEEP)
    - Epic_lifestyles (assumed retail brand)
    - JCPenney Optical (retail framing wins over health)

DB-write — stop FastAPI dev server first to avoid events.db lock per the
5.4 / 5.5 close-out gotcha.
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

# Slice A — 11 FLIPs out of /category/shopping-essentials into other Tier-1.
# Keyed by entity_id prefix (first 8 chars of UUID, looked up by name in the
# audit dump §2 edge-case review section). Single-cat flip per V1 policy +
# operator approval — removes shopping-essentials EntityCategory link and
# replaces with the target slug's link, also resets Provider.category_id.
# Idempotent: re-running on an already-flipped entity DELETEs + re-INSERTs
# the same row (net no-op except updated_at).
FLIPS_OUT_OF_SHOPPING: dict[str, str] = {
    # 5 -> health-wellness-care (cat-5) — google_primary_category in {health,
    # medical_clinic} — eye-care and hospice that the (None, "retail")
    # catch-all routed via the discovery domain
    "ef1c1270": "health-wellness-care",  # Christina Martinez, OD - Eye Exam (health)
    "2f53214c": "health-wellness-care",  # Dr. Sylvia Rimbergas - Pediatric Eye Exam (health)
    "2853055b": "health-wellness-care",  # Hospice of Havasu (health — the actual
                                          # hospice, NOT the resale store at
                                          # bfacd472 which stays in shopping-essentials)
    "7993f2b5": "health-wellness-care",  # Lake Havasu Family Eyecare (medical_clinic,
                                          # 1787 reviews — surfaced in §4 top-10 sweep,
                                          # added after the initial audit because
                                          # 'medical_clinic' wasn't in the edge_types
                                          # filter of phase5_6_ambig_audit_dump.py)
    "7329dd44": "health-wellness-care",  # Barnet Dulaney Perkins Eye Center
                                          # (medical_clinic, 519 reviews — same
                                          # rationale as above)

    # 4 -> auto-rv-fuel (cat-9) — powersports/motorsports dealers Google tagged
    # as supplier/adventure_sports_center
    "64b1eb3d": "auto-rv-fuel",  # Anderson Powersports Lake Havasu (supplier)
    "da327e86": "auto-rv-fuel",  # Anderson PowerSports (supplier — distinct
                                  # location; camelCase in DB)
    "c3958b0f": "auto-rv-fuel",  # Just 4 Fun Powersports (supplier)
    "f227c238": "auto-rv-fuel",  # Lead Dog Motorsports (adventure_sports_center)

    # 2 -> home-property-services (cat-4) — service businesses Google tagged
    # as service primary_type that are clearly home-services not retail
    "6364a641": "home-property-services",  # AQUACLEAN HAVASU LLC (water/pool)
    "3a21a8fb": "home-property-services",  # Apple Valley Communications Alarms
}

# Slice B — 7 DRAFT marks. Provider.draft=True hides the entity from
# /category/ rendering but preserves the EntityCategory link so the
# operator can re-evaluate / un-draft later without re-creating the row.
# These are B2B-only or non-retail-civic that shouldn't show in a consumer
# retail directory but don't have a more appropriate Tier-1 home either.
DRAFTS_IN_SHOPPING: list[str] = [
    "9d3b86aa",  # A & A Electronics Assembly (manufacturer — B2B)
    "f791b8b5",  # Geary Pacific Supply (manufacturer — HVAC wholesale B2B)
    "dd2e31c7",  # Keenan Supply (manufacturer — plumbing wholesale B2B)
    "1fa2736b",  # Romer Beverage Co (corporate_office — wholesale distributor)
    "3667c4b2",  # Essco Wholesale Electric (service — wholesale electric B2B)
    "b103ea17",  # Lake Havasu Community Garden (garden — civic non-profit)
    "c5a5868b",  # Anderson AZ West (supplier — appears wholesale; if operator
                 # later confirms consumer-retail, just flip draft back to False)
]


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    return session.scalars(
        select(Entity).where(Entity.id.like(f"{prefix}%"))
    ).first()


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
            "shopping-essentials",
            "health-wellness-care",
            "auto-rv-fuel",
            "home-property-services",
        )
        for needed in needed_slugs:
            if needed not in slug_to_id:
                print(
                    f"ERROR: Category.slug={needed!r} not found.",
                    file=sys.stderr,
                )
                return 2

        print("=" * 70)
        print("Slice A — FLIPs OUT of /category/shopping-essentials")
        print("=" * 70)
        flips_done = 0
        flips_missing = 0
        for prefix, target_slug in FLIPS_OUT_OF_SHOPPING.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(
                    f"  MISSING entity_id prefix={prefix!r} "
                    f"(target={target_slug})"
                )
                flips_missing += 1
                continue
            _flip_entity_to_slug(session, ent.id, target_slug, slug_to_id)
            print(f"  {ent.name!r:55s}  ->  {target_slug}")
            flips_done += 1
        print(f"  total: {flips_done} flipped, {flips_missing} missing")
        print()

        print("=" * 70)
        print("Slice B — DRAFTs (Provider.draft=True; EntityCategory preserved)")
        print("=" * 70)
        drafts_done = 0
        drafts_missing = 0
        for prefix in DRAFTS_IN_SHOPPING:
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
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
            print(f"  {ent.name!r:55s}  ->  draft=True")
            drafts_done += 1
        print(f"  total: {drafts_done} drafted, {drafts_missing} missing")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify
        print()
        print("=" * 70)
        print("Self-verify — /category/<slug> rendering counts (post-apply)")
        print("=" * 70)
        for slug in (
            "shopping-essentials",
            "health-wellness-care",
            "auto-rv-fuel",
            "home-property-services",
            "eat-drink",
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
