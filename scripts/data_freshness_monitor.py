"""Comprehensive data-freshness monitor (events + movies + gas).

The P6 staleness alert. ``scripts/freshness_check.py`` is the original event-only
heartbeat; this is the superset that also guards the feeds whose silent staleness
produced the P0 sitewide date-desync bug (gas, movies). Backed by
``app/monitoring/freshness.py`` so the same grading drives the admin
"Data freshness" table.

Usage
-----
    python scripts/data_freshness_monitor.py
    python scripts/data_freshness_monitor.py --json

Exit code: 0 if every feed is fresh; 1 if any is STALE (older than its
cadence-derived budget) or MISSING (no rows — usually a source-string drift or a
pipeline that never ran). Drop into a daily GitHub Actions workflow; a non-zero
exit fails the run and the Actions failure email is the page.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.monitoring.freshness import FeedStatus, fmt_age, run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check every scheduled feed for silent staleness")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    now = datetime.now(UTC).replace(tzinfo=None)
    results: list[FeedStatus] = run(now=now)
    failed = [r for r in results if not r.ok]

    if args.as_json:
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "checked_at": now.isoformat(),
                    "results": [
                        {
                            "label": r.label,
                            "key": r.key,
                            "status": r.status,
                            "freshest": r.freshest.isoformat() if r.freshest else None,
                            "age_hours": round(r.age_hours, 2) if r.age_hours is not None else None,
                            "max_age_hours": r.max_age_hours,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
    else:
        width = max(len(r.label) for r in results)
        print("Data-freshness monitor\n" + "-" * (width + 42))
        for r in results:
            mark = {"OK": "OK   ", "STALE": "STALE", "MISSING": "MISS "}[r.status]
            budget = f"budget {r.max_age_hours / 24:.0f}d" if r.max_age_hours >= 24 else (
                f"budget {r.max_age_hours:.0f}h"
            )
            print(f"  [{mark}] {r.label.ljust(width)}  {fmt_age(r.age_hours).ljust(10)} ({budget})")
        print("-" * (width + 42))
        if failed:
            print("  STALE/MISSING feeds: " + ", ".join(r.label for r in failed))
            print("  -> a feed may be silently stale (the P0 date-desync class); check its workflow.")
        else:
            print(f"  all {len(results)} feeds fresh")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
