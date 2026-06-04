"""
CLI: dry-run Today's News-Herald (havasunews.com) news sitemap + fishing column.

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.
Paywall rule 6: only headline/date/keywords/free-lede are ever ingested.

  python scripts/news_herald_pull.py                 # news sitemap
  python scripts/news_herald_pull.py --feed fishing  # weekly fishing column RSS
  python scripts/news_herald_pull.py --apply         # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import news_herald  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feed", choices=["news", "fishing"], default="news")
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(news_herald.SOURCE)

    if args.feed == "fishing":
        items = news_herald.fetch_fishing_column()
        name = f"{news_herald.SOURCE}:fishing"
    else:
        items = news_herald.fetch_news_sitemap()
        name = f"{news_herald.SOURCE}:news"

    print_dry_run_report(
        name,
        items,
        sample_fn=news_herald.article_sample,
        notes=["Rule 6: headline/date/keywords/free-lede only; paywalled body never decoded."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
