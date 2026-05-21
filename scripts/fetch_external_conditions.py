"""
Fetch external conditions into external_conditions_cache.

Usage:
  python -m scripts.fetch_external_conditions --source airnow_86403
  python -m scripts.fetch_external_conditions --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.conditions.fetcher import all_source_keys, fetch_sources  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch external conditions sources")
    parser.add_argument("--source", action="append", dest="sources", metavar="SOURCE")
    parser.add_argument("--all", action="store_true", help="Fetch every known source")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Bypass should_skip_fetch circuit-breaker (Phase 8a.3). "
            "Use after deploying an API-rename fix to unmask the next fetch "
            "attempt without waiting for the up-to-6-hour cooldown."
        ),
    )
    args = parser.parse_args(argv)

    if args.all:
        sources = list(all_source_keys())
    elif args.sources:
        sources = args.sources
    else:
        parser.error("Specify --source SOURCE or --all")

    with SessionLocal() as db:
        results = fetch_sources(db, sources, force=args.force)
        db.commit()

    failed = [s for s, ok in results.items() if not ok]
    if failed:
        print(f"failed sources: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed and len(failed) == len(sources) else 0


if __name__ == "__main__":
    raise SystemExit(main())
