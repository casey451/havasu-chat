"""
CLI: source-expansion event sources — dry-run by default, ``--apply`` ingests.

Dry-run (default): fetch + parse, print the dry-run contract, write nothing.
``--apply``: route the fetched records through the shared ingestion path
(``app.contrib.event_ingest`` -> reconcile -> contribution -> trust-tiered
approval). These aggregator sources are NOT in the auto-approve registry, so on
``--apply`` they land PENDING in the review queue (human go/no-go), not live.

  python scripts/events_pull.py --source allevents
  python scripts/events_pull.py --source bandsintown      # needs BANDSINTOWN_APP_ID
  python scripts/events_pull.py --source eventbrite        # needs EVENTBRITE_API_TOKEN
  python scripts/events_pull.py --source senior_center
  python scripts/events_pull.py --source movies
  python scripts/events_pull.py --source allevents --apply # ingests (lands pending)
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
from app.contrib.scrape_dryrun import print_dry_run_report  # noqa: E402

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
    p.add_argument("--apply", action="store_true", help="ingest (aggregators land pending)")
    args = p.parse_args(argv)

    name, fetch, sample_fn, notes = _SOURCES[args.source]
    records = fetch()

    if args.apply:
        from app.contrib.event_ingest import ingest_event_records, print_ingest_report

        counts = ingest_event_records(records, source=name, dry_run=False)
        print_ingest_report(name, counts, dry_run=False)
        return 0

    print_dry_run_report(name, records, sample_fn=sample_fn, notes=notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
