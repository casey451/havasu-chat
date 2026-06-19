"""Scrape Star Cinemas showtimes into the ``movie_showtimes`` table (twice daily).

Movies live in their own table, NOT the events/contributions pipeline, so they
never touch auto-approve and can't leak into the general events feed. Idempotent
upsert on (source, source_stable_id), then prune past showings to keep the table
bounded.

Usage:
  python scripts/scrape_movies.py --dry-run     # fetch + show counts, no writes
  python scripts/scrape_movies.py               # upsert + prune
  python scripts/scrape_movies.py --no-prune    # upsert only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.movies.store import fetch_star_cinemas, prune_past, upsert_showtimes  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape Star Cinemas showtimes")
    parser.add_argument("--dry-run", action="store_true", help="fetch only; no DB writes")
    parser.add_argument("--no-prune", action="store_true", help="skip pruning past showings")
    args = parser.parse_args(argv)

    records = fetch_star_cinemas()
    films = {r.film_title for r in records}
    dates = sorted({r.show_date.isoformat() for r in records})
    span = f"{dates[0]}..{dates[-1]}" if dates else "(none)"
    print(f"fetched {len(records)} showtimes, {len(films)} films, dates {span}")

    if args.dry_run:
        print("DRY RUN: no writes")
        return 0

    with SessionLocal() as db:
        counts = upsert_showtimes(db, records)
        pruned = 0 if args.no_prune else prune_past(db)
    print(f"created: {counts['created']}  updated: {counts['updated']}  pruned_past: {pruned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
