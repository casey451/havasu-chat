"""
CLI: pull the wired local-news sources into the news cache row.

Populates the home news ticker + the /news page (app.news.store). Writes ONE
cache row in external_conditions_cache (no schema migration). Run on a schedule
(e.g. hourly) so headlines stay fresh.

  python scripts/news_pull.py            # fetch + write the cache, print a summary
  python scripts/news_pull.py --dry-run  # fetch only; print counts, write nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.news import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull local news into the cache row.")
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch only; print counts, write nothing"
    )
    args = parser.parse_args()

    if args.dry_run:
        total = 0
        for key, fetch in store._SOURCES:
            try:
                items = fetch() or []
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  {key}: FAILED ({exc})")
                continue
            total += len(items)
            print(f"  {key}: {len(items)} item(s)")
        print(f"news_pull (dry-run): {total} item(s) across sources; cache NOT written")
        return 0

    db = SessionLocal()
    try:
        count = store.pull_local_news(db)
        db.commit()
    finally:
        db.close()
    print(f"news_pull: stored {count} headline(s) in the news cache")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
