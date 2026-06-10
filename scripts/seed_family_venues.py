"""Seed: missing family-fun venues — Desert Hawks RC Club + the roller rink.

USAGE
-----
    python -m scripts.seed_family_venues              # dry-run (default)
    python -m scripts.seed_family_venues --commit     # persist batch

Closes the 2026-06-10 coverage gap: neither the Desert Hawks RC track nor the
Havasu roller skating rink exists anywhere in the catalog (no Provider row, no
entity, no scrape hit — verified against live-site search and the repo's
enrichment output). Both are real, active Lake Havasu venues and both belong
in the chat's family-fun answer set (app/chat/family_fun.py matches them by
name keyword once live).

Rows are created as ``draft=True, pending_review=True`` so they land in the
admin approval queue (/admin → provider approval) rather than going straight
to the public surfaces; approving flips ``draft`` and dual-writes the entity
graph (app/admin/provider_approval.py). Idempotent: upsert keyed on slug.

Facts sourced 2026-06-10 from deserthawksrc.club, modelaircraft.org (AMA club
#1545), rctracks.io, havasuskates.com, and Yelp. Anything not confirmed by an
operator source is omitted rather than guessed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.utils.slug import slugify  # noqa: E402

logger = logging.getLogger(__name__)

SEED_SOURCE = "seed_family_venues"

SEED_PROVIDERS: tuple[dict, ...] = (
    {
        "provider_name": "Desert Hawks RC Club",
        "category": "entertainment_attractions",
        "address": (
            "Jim Sterling Memorial R/C Complex, 7200 Dub Campbell Pkwy, "
            "Lake Havasu City, AZ"
        ),
        "phone": "(951) 970-7829",
        "email": "info@deserthawksrc.club",
        "website": "https://deserthawksrc.club",
        "hours": "Daily 6am–10pm (field hours)",
        "description": (
            "AMA-chartered radio-control club (charter #1545) at the Jim "
            "Sterling Memorial R/C Complex in SARA Park, run with Lake Havasu "
            "City Parks & Recreation. The complex has a 750-foot paved "
            "runway, a dirt oval track, a short-course dirt track, and a "
            "helicopter/drone field. Visitors welcome; AMA membership "
            "required to fly."
        ),
    },
    {
        "provider_name": "Havasu Skates (SARA Park Roller Rink)",
        "category": "entertainment_attractions",
        "address": "7260 Sara Pkwy, Lake Havasu City, AZ 86406",
        "website": "https://www.havasuskates.com",
        "hours": None,  # schedule varies — themed skate nights, typically Fri/Sat
        "description": (
            "Volunteer-run nonprofit roller skating at the SARA Park rink — "
            "free themed skate nights and family skate sessions, typically "
            "Friday and Saturday evenings. Check the website or Facebook for "
            "the current schedule."
        ),
    },
)


def upsert(db: Session, rec: dict, *, commit: bool) -> str:
    slug = slugify(rec["provider_name"])
    existing = db.scalar(select(Provider).where(Provider.slug == slug))
    if existing is not None:
        return f"skip (exists): {rec['provider_name']} → /provider/{slug}"
    row = Provider(
        provider_name=rec["provider_name"],
        category=rec["category"],
        address=rec.get("address"),
        phone=rec.get("phone"),
        email=rec.get("email"),
        website=rec.get("website"),
        hours=rec.get("hours"),
        description=rec.get("description"),
        slug=slug,
        source=SEED_SOURCE,
        draft=True,
        pending_review=True,
        is_active=True,
    )
    if commit:
        db.add(row)
    return f"insert (draft, pending review): {rec['provider_name']} → slug {slug}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist the batch (default is dry-run).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with SessionLocal() as db:
        actions = [upsert(db, rec, commit=args.commit) for rec in SEED_PROVIDERS]
        for line in actions:
            logger.info("%s", line)
        if args.commit:
            db.commit()
            logger.info("Committed %d row(s).", sum("insert" in a for a in actions))
        else:
            db.rollback()
            logger.info("Dry-run — nothing written. Re-run with --commit to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
