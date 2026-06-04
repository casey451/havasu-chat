"""
CLI: dry-run Mohave County Sheriff press releases (HTML scrape).

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.

  python scripts/mcso_press_pull.py
  python scripts/mcso_press_pull.py --apply       # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import mcso_press  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(mcso_press.SOURCE)

    items = mcso_press.fetch_press_releases()
    print_dry_run_report(
        mcso_press.SOURCE,
        items,
        sample_fn=mcso_press.press_sample,
        notes=["NEEDS_PROD_VERIFY: HTML selectors parsed defensively; confirm vs live markup."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
