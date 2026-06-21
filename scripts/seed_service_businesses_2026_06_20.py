"""Seed the 2026-06-20 search-coverage service businesses as draft listings.

Reads ``data/service_coverage_candidates_2026-06-20.csv`` (verified Lake Havasu
businesses for junk removal, property management, laundry/dry cleaning, auto
glass, painting, locksmiths) and inserts each as a Provider row with
``draft=True, pending_review=True`` — so they land in the /admin approval queue
rather than going straight live, exactly like ``scripts/seed_family_venues.py``.

Approving a row in /admin is what publishes it AND assigns its primary category
(dual-writing the entity graph). To make a leaf page render, assign the matching
leaf from the CSV ``leaf_slug`` column at approval; create the leaf first with
``scripts/create_missing_service_leaves_2026_06_20.py`` if it doesn't exist yet.

Idempotent: upsert keyed on the name slug (skips a row that already exists).
DEFAULT IS DRY-RUN.

    .venv\\Scripts\\python.exe scripts\\seed_service_businesses_2026_06_20.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\seed_service_businesses_2026_06_20.py --commit   # stage drafts

PROD GATE (CLAUDE.md): run the dry-run, show Casey the plan, get approval, THEN a
human runs --commit. The agent never runs --commit against prod.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.utils.slug import slugify  # noqa: E402

logger = logging.getLogger(__name__)

SEED_SOURCE = "seed_service_coverage_2026_06_20"
CSV_PATH = _ROOT / "data" / "service_coverage_candidates_2026-06-20.csv"


def _clean(val: str | None) -> str | None:
    val = (val or "").strip()
    return val or None


def load_rows(csv_path: Path = CSV_PATH) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def upsert(db: Session, rec: dict, *, commit: bool, counts: Counter) -> str:
    name = (rec.get("provider_name") or "").strip()
    if not name:
        counts["skipped_blank"] += 1
        return "skip (blank name)"
    slug = slugify(name)
    existing = db.scalar(select(Provider).where(Provider.slug == slug))
    if existing is not None:
        counts["skip_exists"] += 1
        return f"skip (exists): {name} -> /provider/{slug}"
    row = Provider(
        provider_name=name,
        category=_clean(rec.get("legacy_category")) or "home_services",
        address=_clean(rec.get("address")),
        phone=_clean(rec.get("phone")),
        website=_clean(rec.get("website")),
        slug=slug,
        source=SEED_SOURCE,
        draft=True,
        pending_review=True,
        is_active=True,
    )
    if commit:
        db.add(row)
    counts["insert"] += 1
    return f"insert (draft, pending review): {name} [{rec.get('leaf_slug')}] -> slug {slug}"


def run(*, commit: bool = False, csv_path: Path = CSV_PATH) -> Counter:
    counts: Counter = Counter()
    rows = load_rows(csv_path)
    with SessionLocal() as db:
        with db.no_autoflush:
            for rec in rows:
                logger.info("%s", upsert(db, rec, commit=commit, counts=counts))
        if commit:
            db.commit()
        else:
            db.rollback()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Stage drafts (default: dry-run).")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    counts = run(commit=args.commit)
    mode = "COMMITTED" if args.commit else "DRY-RUN"
    logger.info("[%s] %s", mode, ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if not args.commit:
        logger.info("Nothing written. Re-run with --commit to stage drafts for /admin approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
