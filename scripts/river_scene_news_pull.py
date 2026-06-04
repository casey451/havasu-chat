"""
CLI: dry-run RiverScene Magazine news articles (WordPress REST).

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.

  python scripts/river_scene_news_pull.py
  python scripts/river_scene_news_pull.py --after 2026-05-01T00:00:00
  python scripts/river_scene_news_pull.py --apply      # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import river_scene_news  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--after", default=None, help="ISO8601 datetime; only posts after this")
    p.add_argument("--categories", default=None, help="comma-separated WP category IDs")
    p.add_argument("--per-page", type=int, default=20)
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(river_scene_news.SOURCE)

    items = river_scene_news.fetch_posts(
        after=args.after, categories=args.categories, per_page=args.per_page
    )
    print_dry_run_report(river_scene_news.SOURCE, items, sample_fn=river_scene_news.post_sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
