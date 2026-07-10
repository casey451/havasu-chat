"""Add the Split Finger Athletics directory listing (WS12 credential-checklist §2).

Split Finger Athletics is a youth baseball/softball + athletic-training facility
(batting/HitTrax cages, camps, clinics, strength & agility) that is **absent
from the directory entirely**, so ``/search?q=batting cages`` returns nothing —
a named coverage gap (WS9 synonym: batting cages → Split Finger). This adds the
single Provider row that closes it.

Scope: the directory *identity* row only. The facility's dated camps/clinics and
recurring classes live on RunSwift (a JS SPA) and are a separate, larger scraper
effort (see docs/prompts/PROMPT_CC_SPLIT_FINGER_SCRAPER_2026-06-24.md). This
script does NOT touch those.

Gated data-op discipline (CLAUDE.md): **dry-run by default**; ``--apply`` writes.
Idempotent — if a Split Finger provider already exists (by name / phone /
website) it reports and makes no change, so a re-run is a no-op. On ``--apply``
it prints the created provider id + slug for reversibility (undo = deactivate or
delete that one row).

Verified 2026-07-09: splitfingerathletics.com resolves (200). Address/phone from
the WS12 credential checklist §2 — confirm current before the real apply.

Usage:
    python scripts/add_split_finger_athletics.py            # dry-run (default)
    python scripts/add_split_finger_athletics.py --apply    # writes to the DB
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import create_provider_and_entity  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

# --- Verified facility identity (WS12 credential checklist §2) ---------------
NAME = "Split Finger Athletics"
ADDRESS = "5601 Hwy 95, Bldg F, Ste 600, Lake Havasu City, AZ 86404"
PHONE = "(928) 223-1504"
WEBSITE = "https://splitfingerathletics.com"
# Category: a youth-sports + fitness training facility. Primary department is
# Fitness & Classes; the "batting cages" head term lives in the description/tags
# so search (name/description FTS) resolves it — the acceptance criterion.
PRIMARY_CATEGORY_SLUG = "fitness-and-wellness"
SUBCATEGORY_SLUG = "gyms-and-fitness-centers"
LEGACY_CATEGORY = "fitness"
DESCRIPTION = (
    "Youth baseball & softball training facility with indoor batting cages "
    "(HitTrax), private hitting and pitching lessons, seasonal camps and "
    "clinics, strength & agility classes, and open gym. Lake Havasu City's home "
    "for batting cages and youth-sports coaching."
)
SOURCE = "operator_backfill"


def find_existing(db: Session) -> list[Provider]:
    """Any provider that already looks like Split Finger (idempotency guard)."""
    name_like = func.lower(Provider.provider_name).like("%split finger%")
    digits = "9282231504"
    phone_like = func.replace(
        func.replace(
            func.replace(func.replace(Provider.phone, "(", ""), ")", ""), " ", ""
        ),
        "-",
        "",
    ).like(f"%{digits}%")
    web_like = func.lower(func.coalesce(Provider.website, "")).like("%splitfingerathletics%")
    stmt = select(Provider).where(or_(name_like, phone_like, web_like))
    return list(db.scalars(stmt))


def resolve_category_id(db: Session, slug: str) -> int | None:
    """Look up the categories-table id for a slug (robust across DBs)."""
    try:
        return db.scalar(select(Category.id).where(Category.slug == slug))
    except Exception:
        return None


def build_provider(category_id: int | None) -> Provider:
    return Provider(
        provider_name=NAME,
        category=LEGACY_CATEGORY,
        primary_category=PRIMARY_CATEGORY_SLUG,
        subcategory=SUBCATEGORY_SLUG,
        category_id=category_id,
        address=ADDRESS,
        phone=PHONE,
        website=WEBSITE,
        description=DESCRIPTION,
        draft=False,
        is_active=True,
        verified=True,
        pending_review=False,
        source=SOURCE,
    )


def run(db: Session, *, apply: bool) -> int:
    existing = find_existing(db)
    if existing:
        print(f"IDEMPOTENT NO-OP: {len(existing)} existing Split Finger row(s) found:")
        for p in existing:
            print(
                f"  - id={p.id} slug={p.slug!r} active={p.is_active} "
                f"cat={p.category!r} primary={p.primary_category!r} phone={p.phone!r}"
            )
        print("  -> not creating a duplicate. Review/activate the existing row instead.")
        return 0

    category_id = resolve_category_id(db, PRIMARY_CATEGORY_SLUG)
    print("PLAN: INSERT 1 provider")
    print(f"  name:        {NAME}")
    print(f"  address:     {ADDRESS}")
    print(f"  phone:       {PHONE}")
    print(f"  website:     {WEBSITE}")
    print(f"  category:    {LEGACY_CATEGORY} / primary={PRIMARY_CATEGORY_SLUG} "
          f"/ sub={SUBCATEGORY_SLUG} / category_id={category_id}")
    print(f"  description: {DESCRIPTION[:80]}...")

    if not apply:
        print("\nDRY-RUN: would_create=1 (re-run with --apply to write).")
        return 0

    prov = build_provider(category_id)
    try:
        db.add(prov)
        create_provider_and_entity(db, prov)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(prov)
    print(f"\nAPPLIED: created provider id={prov.id} slug={prov.slug!r} "
          f"entity_id={prov.entity_id!r}")
    print(f"UNDO: deactivate or delete provider id={prov.id} (slug {prov.slug!r}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add Split Finger Athletics directory row")
    ap.add_argument("--apply", action="store_true", help="Write to the DB (default: dry-run)")
    args = ap.parse_args(argv)
    with SessionLocal() as db:
        return run(db, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
