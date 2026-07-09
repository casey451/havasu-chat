"""Seed the canary listings (A4) into the database. GATED prod write.

Defaults to a DRY RUN: it reports exactly what it would create and rolls back,
writing nothing. Pass ``--apply`` to commit.

    python scripts/seed_canaries.py            # dry run — show counts, write nothing
    python scripts/seed_canaries.py --apply    # actually create the canary rows

Per the repo rules, a production write follows dry-run → show counts → Casey
approves → apply. This script never auto-applies. Canaries are stamped
``source = CANARY_SOURCE`` so they are excluded from every "N listed" count and
from the sitemap (see app/monitoring/canaries.py); they are created
``is_active=True, draft=False`` so the /provider/<slug> page renders for a
site-cloning scraper to pick up. They are intentionally NOT linked from any
listing — surfacing them more prominently is a follow-up product decision.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.monitoring.canaries import CANARIES, CANARY_SOURCE

# A required legacy ``Provider.category``; the canary is excluded from listings by
# its source regardless, so this only needs to be a valid non-empty string.
_CANARY_CATEGORY = "services"


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed canary listings (A4).")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    args = ap.parse_args()

    created = 0
    skipped = 0
    with SessionLocal() as db:
        for c in CANARIES:
            exists = db.query(Provider).filter(Provider.slug == c.slug).one_or_none()
            if exists is not None:
                skipped += 1
                print(f"  skip (already present): {c.slug}")
                continue
            provider = Provider(
                provider_name=c.name,
                category=_CANARY_CATEGORY,
                slug=c.slug,
                address=c.address,
                phone=c.phone,
                website=c.website,
                description=c.description,
                source=CANARY_SOURCE,
                is_active=True,
                draft=False,
            )
            db.add(provider)
            db.flush()
            create_provider_and_entity(db, provider)
            created += 1
            print(f"  would create: {c.slug} ({c.name})")

        print(f"\ncanaries: {created} to create, {skipped} already present.")
        if args.apply:
            db.commit()
            print("APPLIED — canary rows committed.")
        else:
            db.rollback()
            print("DRY RUN — nothing written. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
