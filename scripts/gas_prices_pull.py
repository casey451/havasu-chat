"""
CLI: pull per-station Lake Havasu City gas prices into the conditions cache.

  python scripts/gas_prices_pull.py --dry-run   # fetch + print, no DB write
  python scripts/gas_prices_pull.py             # fetch + write cache row

Primary source GasBuddy (set GAS_SCRAPE_PROXY_URL to a Bright Data / Nimble
unblocker proxy so it survives Cloudflare from a server IP). Google Places
fuelOptions fills gaps when GOOGLE_PLACES_API_KEY is set.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.gas_prices import run_pull  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Pull Lake Havasu City per-station gas prices")
    p.add_argument("--dry-run", action="store_true", help="Do not write to the database")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run_pull(dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
