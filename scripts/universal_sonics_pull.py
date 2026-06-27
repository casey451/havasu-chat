"""Scrape the Universal Sonics class schedule and PROPOSE a refreshed roster.

Studio schedules are seasonal + tier-coded, so per the scraper plan
(docs/scraper/HAVASU_LANES_SCRAPER_PLAN_2026-06-24.md §3) they ship behind a
human review gate — this script never writes the DB or the live render data. It:

  1. fetches the live schedule (http) and LLM-extracts the recreational classes,
  2. writes a candidate JSON snapshot to ``data/scrapes/`` (an artifact a human or
     the cron can attach to a review),
  3. prints a DRIFT report vs the roster currently hardcoded in
     ``app/home/family_venues.py`` (added / removed classes) so a reviewer sees
     exactly what changed before promoting it.

Run live (needs OPENAI_API_KEY for the extraction)::

    python -m scripts.universal_sonics_pull
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.universal_sonics import (  # noqa: E402
    SOURCE_NAME,
    StudioClassRow,
    scrape_rows,
)
from app.home.family_venues import STUDIOS  # noqa: E402

logger = logging.getLogger(__name__)
_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "scrapes"


def _row_key(weekday: int, start: str, name: str) -> tuple[int, str, str]:
    return (weekday, start, name.strip().lower())


def _current_keys() -> set[tuple[int, str, str]]:
    studio = next((s for s in STUDIOS if SOURCE_NAME in s.short.lower().replace(" ", "_")
                   or "universal" in s.name.lower()), None)
    if studio is None:
        return set()
    return {
        _row_key(c.weekday, c.start.strftime("%H:%M"), c.name)
        for c in studio.classes
    }


def _candidate(rows: list[StudioClassRow]) -> list[dict]:
    return [
        {
            "name": r.name,
            "weekday": r.weekday,
            "start": r.start_time.strftime("%H:%M"),
            "end": r.end_time.strftime("%H:%M") if r.end_time else None,
            "age": r.age,
            "source_line": r.source_line,
        }
        for r in sorted(rows, key=lambda r: (r.weekday, r.start_time, r.name))
    ]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Propose a refreshed Universal Sonics roster")
    p.add_argument("--today", help="YYYY-MM-DD for the snapshot filename (default: today)")
    args = p.parse_args()

    rows = scrape_rows()
    if not rows:
        print("[universal_sonics] extracted 0 classes (no key, fetch miss, or parse "
              "failure) — proposing nothing; the hardcoded roster stands.")
        return 0

    candidate = _candidate(rows)
    stamp = args.today or date.today().isoformat()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"universal_sonics_{stamp}.json"
    out_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    new_keys = {_row_key(c["weekday"], c["start"], c["name"]) for c in candidate}
    cur = _current_keys()
    added = sorted(new_keys - cur)
    removed = sorted(cur - new_keys)

    print("--- universal_sonics_pull ---")
    print(f"  extracted recreational classes: {len(candidate)}")
    print(f"  candidate JSON: {out_path}")
    print(f"  drift vs hardcoded roster: +{len(added)} added / -{len(removed)} removed")
    for wd, start, name in added:
        print(f"    + day{wd} {start} {name}")
    for wd, start, name in removed:
        print(f"    - day{wd} {start} {name}")
    print("  REVIEW REQUIRED: studio schedules are not auto-published — promote "
          "the candidate into app/home/family_venues.py after a human check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
