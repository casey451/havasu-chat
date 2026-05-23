"""Layer 5 seed script for cat-13 public-civic-resources starter entities.

USAGE
-----
    python -m scripts.seed_cat13_civic              # dry-run (default)
    python -m scripts.seed_cat13_civic --commit     # persist batch

Idempotent upserts on (name, address) via scripts.ingest.lhc_civic_scrape.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from scripts.ingest.lhc_civic_scrape import (  # noqa: E402
    CivicEntityRecord,
    _cat13_id,
    upsert_civic_entity,
)

logger = logging.getLogger(__name__)

SEED_SOURCE = "seed_cat13_civic"

# High-trust starter entities for the 8 master-plan sub-categories.
SEED_ENTITIES: tuple[CivicEntityRecord, ...] = (
    CivicEntityRecord(
        name="Lake Havasu Area Chamber of Commerce",
        address="422 N Lake Havasu Ave, Lake Havasu City, AZ 86403",
        website="https://www.havasuchamber.com",
        phone="(928) 855-4115",
        hours_text="Mon–Fri 9am–4pm",
        description="Regional chamber supporting local businesses and civic events.",
        sub_category="civic_org",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Lake Havasu City Visitor Center",
        address="422 English Village, Lake Havasu City, AZ 86403",
        website="https://www.golakehavasu.com",
        phone="(928) 453-3444",
        hours_text="Daily 9am–5pm",
        description="Official visitor bureau and tourism information for Lake Havasu City.",
        sub_category="visitor_info",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Lake Havasu City Senior Center",
        address="8680 S Mohave Dr, Lake Havasu City, AZ 86406",
        website="https://www.lhcaz.gov/parks-recreation/senior-center",
        phone="(928) 453-4148",
        description="City senior center programs, activities, and resources.",
        sub_category="senior_resource",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Meals on Wheels - Lake Havasu City",
        address="8680 S Mohave Dr, Lake Havasu City, AZ 86406",
        website="https://www.wacog.com",
        phone="(928) 453-4148",
        description="Home-delivered meals program for homebound seniors (Western Arizona Council of Governments).",
        sub_category="senior_resource",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Republic Services - Lake Havasu City",
        address="3750 Industrial Blvd, Lake Havasu City, AZ 86404",
        website="https://www.republicservices.com",
        phone="(928) 855-5508",
        description="Residential and commercial trash and recycling service provider.",
        sub_category="utility",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="UniSource Energy Services",
        address="1801 Industrial Blvd, Lake Havasu City, AZ 86403",
        website="https://www.unisourceenergy.com",
        phone="(928) 855-2233",
        description="Natural gas and electric utility serving Lake Havasu City.",
        sub_category="utility",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Mohave Electric Cooperative",
        address="928 Hancock Rd, Bullhead City, AZ 86442",
        website="https://www.mohaveelectric.com",
        phone="(928) 763-4111",
        description="Member-owned electric cooperative serving parts of Mohave County including LHC area.",
        sub_category="utility",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="City of Lake Havasu Water & Sewer Department",
        address="2240 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        website="https://www.lhcaz.gov/government/utilities",
        phone="(928) 453-4141",
        description="Municipal water and sewer utility services for Lake Havasu City.",
        sub_category="utility",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="Mohave County Superior Court - Records Portal",
        address="401 E Spring St, Kingman, AZ 86401",
        website="https://www.mohavecounty.us/departments/superior-court/",
        description="Mohave County court records and case search portal.",
        sub_category="payment_licensing",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="City of Lake Havasu - Business License Portal",
        address="2240 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        website="https://www.lhcaz.gov/government/finance/business-license",
        description="Online business license application and renewal for Lake Havasu City.",
        sub_category="payment_licensing",
        source=SEED_SOURCE,
    ),
    CivicEntityRecord(
        name="City of Lake Havasu - Utility Bill Payment Portal",
        address="2240 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        website="https://www.lhcaz.gov/government/finance/utility-billing",
        description="Pay water, sewer, and other city utility bills online.",
        sub_category="payment_licensing",
        source=SEED_SOURCE,
    ),
)


def run_seed(*, dry_run: bool = True) -> dict[str, int]:
    stats = {"insert": 0, "update": 0, "noop": 0}
    with SessionLocal() as db:
        cat_id = _cat13_id(db)
        for rec in SEED_ENTITIES:
            action = upsert_civic_entity(db, rec, cat_id=cat_id)
            stats[action] += 1
            logger.info("%s %s", action.upper(), rec.name)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed cat-13 civic starter entities")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print planned upserts without committing (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist the seed batch",
    )
    args = parser.parse_args(argv)
    dry_run = not args.commit
    stats = run_seed(dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "COMMITTED"
    print(
        f"[{mode}] seed entities={len(SEED_ENTITIES)} "
        f"insert={stats['insert']} update={stats['update']} noop={stats['noop']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
