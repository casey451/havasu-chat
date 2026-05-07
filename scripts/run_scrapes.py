"""
Top-level scrape orchestrator. Runs every registered source, writes
timestamped JSON snapshots under ``data/scrapes/<source>/``, and updates
``data/scrapes/manifest.json``.

Usage
-----
  # Run every source (production cadence):
  python scripts/run_scrapes.py

  # Run a subset:
  python scripts/run_scrapes.py --only webtrac

  # Print summary as JSON for downstream piping:
  python scripts/run_scrapes.py --json

Exit code is non-zero if any source failed; downstream schedulers can use
this to drive paging or retries. See ``docs/scrapes.md`` for cron /
Procfile / GitHub Actions wiring.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib import webtrac  # noqa: E402
from app.contrib.scrape_runner import PullFn, run_all  # noqa: E402


# ---------------------------------------------------------------------------
# Source adapters: each returns a list[dict] for the snapshot runner.
# ---------------------------------------------------------------------------

def _pull_webtrac() -> list[dict[str, Any]]:
    sections = webtrac.fetch_all_sections()
    return [s.to_dict() for s in sections]


def _pull_lhcaz_aquatic() -> list[dict[str, Any]]:
    # Imported lazily so the runner still works before this module lands.
    try:
        from app.contrib import lhcaz_aquatic  # type: ignore
    except ModuleNotFoundError:
        raise RuntimeError(
            "lhcaz_aquatic scraper is not implemented yet — capture HTML via "
            "tmp/aquatic_sample.html and add app/contrib/lhcaz_aquatic.py"
        )
    return lhcaz_aquatic.pull_snapshot()  # type: ignore[no-any-return]


SOURCES: dict[str, PullFn] = {
    "webtrac": _pull_webtrac,
    "lhcaz_aquatic": _pull_lhcaz_aquatic,
}


def main() -> int:
    p = argparse.ArgumentParser(description="Run all parks-and-rec scrapers")
    p.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="SOURCE",
        help="Restrict to one or more sources (repeatable)",
    )
    p.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON summary")
    args = p.parse_args()

    selected: dict[str, PullFn]
    if args.only:
        unknown = [s for s in args.only if s not in SOURCES]
        if unknown:
            print(f"error: unknown source(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"known: {', '.join(SOURCES)}", file=sys.stderr)
            return 2
        selected = {s: SOURCES[s] for s in args.only}
    else:
        selected = SOURCES

    run = run_all(selected)
    failures = [r for r in run.results if not r.ok]

    if args.as_json:
        print(
            json.dumps(
                {
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "results": [
                        {
                            "source": r.source,
                            "ok": r.ok,
                            "record_count": r.record_count,
                            "snapshot_path": r.snapshot_path,
                            "error": r.error,
                        }
                        for r in run.results
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"scrape run {run.started_at} → {run.finished_at}")
        for r in run.results:
            status = "OK" if r.ok else "FAIL"
            tail = f" ({r.record_count} records, {r.snapshot_path})" if r.ok else ""
            print(f"  [{status}] {r.source}{tail}")
            if r.error:
                first_line = r.error.splitlines()[0] if r.error else ""
                print(f"         {first_line}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
