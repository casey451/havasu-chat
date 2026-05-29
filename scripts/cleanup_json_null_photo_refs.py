"""Cosmetic: convert JSON-null google_photo_refs to SQL NULL so future
backfill runs don't report them as misleading leftovers.

Run via:
    railway run python -m scripts.cleanup_json_null_photo_refs --dry-run
    railway run python -m scripts.cleanup_json_null_photo_refs --apply

No behavior change on the site either way.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        # Count rows that match (JSON null, not SQL null)
        count_stmt = text(
            "SELECT COUNT(*) FROM providers "
            "WHERE google_photo_refs IS NOT NULL "
            "AND google_photo_refs::jsonb = 'null'::jsonb"
        )
        n = db.execute(count_stmt).scalar_one()
        print(f"Found {n} rows with JSON-null google_photo_refs")

        if args.apply and n > 0:
            update_stmt = text(
                "UPDATE providers SET google_photo_refs = NULL "
                "WHERE google_photo_refs IS NOT NULL "
                "AND google_photo_refs::jsonb = 'null'::jsonb"
            )
            result = db.execute(update_stmt)
            db.commit()
            print(f"Updated {result.rowcount} rows to SQL NULL")
        elif args.dry_run:
            print("Dry-run: no changes written")


if __name__ == "__main__":
    main()
