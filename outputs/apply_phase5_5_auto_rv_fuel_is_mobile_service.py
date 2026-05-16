"""Apply is_mobile_service to all auto-rv-fuel entities.

Closes Phase 5.5 acceptance gate item 5 ("is_mobile_service populated
on every entry"). Per kickoff §4: ``False`` is the default for most
auto venues — dealerships, gas stations, tire shops, brick-and-mortar
repair. The ``True`` set is the operator-curated subset of explicitly
mobile operators that surfaced in the §1 load:

  - Mobile detailers (Lake Havasu Mobile Detail LLC, Tapped Out Mobile
    Detailing, Every Little Detail Mobile Detailing)
  - Mobile mechanics (911 Mobile Mechanic ×2, WM Auto & Marine mobile
    mechanic, Abnorm Al's Mobile Repair — wait, the latter is also
    "Mobile" in name but presented as a brick-and-mortar; check)
  - Mobile RV technicians (Byrd's Mobile RV & Marine)
  - Mobile tire service (Elite Mobile Tire Services)
  - Towing services (Havasu Towing, Lakeside Towing, Parker Towing,
    Arizona Repair & Towing, Quality Auto Body & Towing — towing IS
    inherently mobile by definition)

The kickoff anticipated 5-15 entities expected True. Final count: 14
(per the §0 mobile-service candidate query). Operator extends as needed.

Mirrors ``apply_phase5_5_auto_rv_fuel_heat_exposure.py`` shape exactly:
id-keyed dict, --dry-run-first, idempotent, sets updated_at,
self-verifies via distribution query.

The Entity.is_mobile_service column defaults to ``False`` per
``app/db/models.py:672-674``, but pre-existing rows from earlier
phases may have it NULL or unset. This script ensures every entity in
the auto-rv-fuel set has it explicitly set to True or False.

Usage:
    python outputs/apply_phase5_5_auto_rv_fuel_is_mobile_service.py --dry-run
    python outputs/apply_phase5_5_auto_rv_fuel_is_mobile_service.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# Default for every auto-rv-fuel entity not overridden below.
DEFAULT_IS_MOBILE_SERVICE = False

# True (mobile-service) operators surfaced in Phase 5.5 §1 load. Keyed by
# 8-char entity_id prefix. Operator extends as needed (e.g., when a new
# mobile-only operator surfaces in a future re-load).
MOBILE_SERVICE_OVERRIDES: dict[str, str] = {
    # mobile mechanics
    "ab23f3e5": "911 Mobile Mechanic",
    "c1901a7e": "911 Mobile Mechanic (second listing)",
    "4f3eb63d": "WM Auto & Marine mobile mechanic",
    # mobile detailers
    "3a1f6b25": "Lake Havasu Mobile Detail LLC",
    "bfbb3f1f": "Tapped Out Mobile Detailing",
    "d93dfbdb": "Every Little Detail Mobile Detailing- RV, Boat & Car",
    # mobile RV tech
    "95e25acf": "Byrd's Mobile RV & Marine",
    # mobile tire service
    "e9572b1c": "Elite Mobile Tire Services",
    # towing (inherently mobile by definition)
    "e99b93e8": "Havasu Towing",
    "5bac3793": "Lakeside Towing",
    "23401b33": "Parker Towing HEAVY DUTY TOW TRUCK LAKE HAVASU AZ",
    "4f261e99": "Arizona Repair & Towing",
    "788b682c": "Quality Auto Body & Towing",
    # mobile sales/service hybrid
    "9f6ab709": "First Class RV & Marine, Sales, Mobile Service, Parts",
}


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    return session.scalars(
        select(Entity).where(Entity.id.like(f"{prefix}%"))
    ).first()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    now_naive = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        cat_id = session.scalar(
            select(Category.id).where(Category.slug == "auto-rv-fuel")
        )
        if cat_id is None:
            print(
                "ERROR: Category.slug='auto-rv-fuel' not found.",
                file=sys.stderr,
            )
            return 2

        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat_id,
                Entity.is_active.is_(True),
            )
        ).all()
        print(
            f"[is_mobile_service] {len(entities)} auto-rv-fuel entities discovered"
        )

        # Build TRUE-override mapping by full entity_id once.
        mobile_entity_ids: dict[str, str] = {}
        for prefix, name in MOBILE_SERVICE_OVERRIDES.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(
                    f"  WARN: MOBILE_SERVICE_OVERRIDES prefix={prefix!r} ({name!r}) not found"
                )
                continue
            mobile_entity_ids[ent.id] = name

        applied_false = 0
        applied_true = 0
        already_correct = 0
        for ent in entities:
            target = True if ent.id in mobile_entity_ids else DEFAULT_IS_MOBILE_SERVICE
            if ent.is_mobile_service == target:
                already_correct += 1
                continue
            ent.is_mobile_service = target
            ent.updated_at = now_naive
            if target:
                applied_true += 1
            else:
                applied_false += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  set to False (default)      : {applied_false}")
        print(f"  set to True (override)      : {applied_true}")
        print(f"  already correct (no change) : {already_correct}")
        print(f"  total entities              : {len(entities)}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify distribution.
        print()
        print("=" * 70)
        print("Self-verify — is_mobile_service distribution across auto-rv-fuel")
        print("=" * 70)
        dist: Counter[bool | None] = Counter()
        for ent in session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat_id,
                Entity.is_active.is_(True),
            )
        ).all():
            dist[ent.is_mobile_service] += 1
        for k, n in sorted(dist.items(), key=lambda kv: -kv[1]):
            print(f"  {str(k):<20} {n}")
        null_count = dist.get(None, 0)
        print()
        if null_count == 0:
            print(
                "Phase 5.5 acceptance gate item 5 (is_mobile_service "
                "populated on every entry) CLEARED."
            )
        else:
            print(
                f"WARN: {null_count} entities still have is_mobile_service=NULL"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
