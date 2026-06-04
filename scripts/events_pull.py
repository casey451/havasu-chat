"""
CLI: dry-run the source-expansion event sources.

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.
All event records are deduped within-batch on the normalised (title, date,
venue) key; cross-source dedup happens at ingestion via events.dedup.

  python scripts/events_pull.py --source allevents
  python scripts/events_pull.py --source bandsintown      # needs BANDSINTOWN_APP_ID
  python scripts/events_pull.py --source eventbrite        # needs EVENTBRITE_API_TOKEN
  python scripts/events_pull.py --source senior_center
  python scripts/events_pull.py --source movies
  python scripts/events_pull.py --source allevents --apply # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import (  # noqa: E402
    allevents,
    bandsintown,
    eventbrite_orgs,
    movies,
    senior_center,
)
from app.contrib.event_record import event_sample  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402

_SOURCES = {
    "allevents": (allevents.SOURCE, allevents.fetch_events, event_sample, []),
    "bandsintown": (
        bandsintown.SOURCE,
        bandsintown.fetch_events,
        event_sample,
        ["Needs BANDSINTOWN_APP_ID; tagged 'regional'. NEEDS_PROD_VERIFY response shape."],
    ),
    "eventbrite": (
        eventbrite_orgs.SOURCE,
        eventbrite_orgs.fetch_events,
        event_sample,
        ["Needs EVENTBRITE_API_TOKEN; worship listings excluded. RELEVANCE GATE — review samples."],
    ),
    "senior_center": (
        senior_center.SOURCE,
        senior_center.fetch_activities,
        senior_center.activity_sample,
        ["RELEVANCE GATE — review samples. NEEDS_PROD_VERIFY selectors."],
    ),
    "movies": (
        movies.SOURCE,
        movies.fetch_movies_havasu,
        event_sample,
        ["Movies Havasu via Webedia XHR. NEEDS_PROD_VERIFY endpoint/shape. Kids summer movies: see module docstring."],
    ),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=sorted(_SOURCES), required=True)
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    name, fetch, sample_fn, notes = _SOURCES[args.source]
    if args.apply:
        apply_guard(name)

    records = fetch()
    print_dry_run_report(name, records, sample_fn=sample_fn, notes=notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
