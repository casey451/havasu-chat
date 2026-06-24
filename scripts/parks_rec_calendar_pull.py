"""CLI: Parks & Rec calendar/flyer vision scraper (dry-run default; --apply ingests).

Reads the Lake Havasu City Parks & Recreation monthly calendar IMAGE (and,
optionally, the individual event-flyer images) on ``/185/Parks-Recreation`` into
structured events via a vision model.

Dry-run (default): fetch + transcribe, print the dry-run contract, write nothing.
``--apply``: ingest the rows through the shared event funnel
(``app.contrib.event_ingest.ingest_event_records``). parks_rec_calendar /
parks_rec_flyers are NOT in the auto-approve registry, so every row lands as a
PENDING contribution for admin review -- vision output never reaches users
unreviewed. Needs ``OPENAI_API_KEY`` for the vision call; with no key the source
fetches 0 (graceful no-op) and ``--apply`` ingests nothing.

  # Dry-run the monthly calendar image (the primary gap this closes):
  .venv\\Scripts\\python.exe scripts/parks_rec_calendar_pull.py

  # Event flyers (Task B):
  .venv\\Scripts\\python.exe scripts/parks_rec_calendar_pull.py --source flyers

  # Ingest (lands pending in the review queue):
  .venv\\Scripts\\python.exe scripts/parks_rec_calendar_pull.py --apply

"Good dry-run output": a ``=== parks_rec_calendar — DRY RUN ===`` banner, a sane
``fetched`` count, would-insert/skip, the held-hidden + confidence lines, and 3
sample records whose titles/dates/venues look right.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.event_record import EventRecord, event_sample  # noqa: E402
from app.contrib.lhc_parks_rec_calendar import (  # noqa: E402
    FLYER_SOURCE,
    SOURCE,
    CalendarPullResult,
    pull_calendars,
    pull_flyers,
)
from app.contrib.scrape_dryrun import INSERT, SKIP, print_dry_run_report  # noqa: E402


def _classify_against_db(records: list[EventRecord]) -> dict[int, str] | None:
    """Read-only insert/skip decision per record, or ``None`` if no DB reachable.

    A record is a SKIP when its synthetic source_url is already loaded
    (idempotent re-run) or an existing event already carries the same
    (title, date, venue) -- that source (WebTrac/aquatic/civic) is richer, so the
    calendar scraper defers (build brief §7). Otherwise it is a would-insert.
    No writes; only reads.
    """
    try:
        from app.contrib.event_ingest import _persisted_duplicate_event
        from app.contrib.parks_rec_loader import _has_existing_source_url
        from app.db import contribution_store as cs
        from app.db.database import SessionLocal

        decisions: dict[int, str] = {}
        with SessionLocal() as db:
            for rec in records:
                normalized = cs.normalize_submission_url(rec.url)
                if _has_existing_source_url(db, normalized):
                    decisions[id(rec)] = SKIP
                elif _persisted_duplicate_event(db, rec) is not None:
                    decisions[id(rec)] = SKIP
                else:
                    decisions[id(rec)] = INSERT
        return decisions
    except Exception as e:  # noqa: BLE001 -- no DB in this env is expected
        print(f"note: read-only dedup classification unavailable ({e}); counting all as insert")
        return None


def _confidence_histogram(records: list[EventRecord]) -> str:
    buckets: Counter[str] = Counter()
    for rec in records:
        c = (rec.raw or {}).get("confidence")
        try:
            cf = float(c)
        except (TypeError, ValueError):
            cf = 0.0
        if cf >= 0.9:
            buckets["0.90-1.00"] += 1
        elif cf >= 0.75:
            buckets["0.75-0.89"] += 1
        elif cf >= 0.5:
            buckets["0.50-0.74"] += 1
        else:
            buckets["0.00-0.49"] += 1
    if not records:
        return "confidence: (no records)"
    order = ["0.90-1.00", "0.75-0.89", "0.50-0.74", "0.00-0.49"]
    return "confidence: " + ", ".join(f"{k}={buckets.get(k, 0)}" for k in order)


def _notes(name: str, result: CalendarPullResult, records: list[EventRecord]) -> list[str]:
    held = sum(1 for r in records if (r.raw or {}).get("should_hide"))
    return [
        f"images considered={result.images_considered} extracted={result.images_extracted}",
        f"would-hold-hidden (confidence<0.75 -> draft+pending_review): {held}",
        _confidence_histogram(records),
        (
            f"guards dropped: out_of_month={result.dropped_out_of_month} "
            f"no_provenance={result.dropped_no_provenance} "
            f"bad_title={result.dropped_bad_title} bad_date={result.dropped_bad_date}"
        ),
        *([f"fetch errors: {len(result.errors)} ({'; '.join(result.errors[:3])})"] if result.errors else []),
        "NEEDS_PROD_VERIFY: a datacenter IP may not reach lhcaz.gov/ImageRepository.",
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=("calendar", "flyers"), default="calendar")
    p.add_argument("--self-check", action="store_true", help="cheap confirm-dates second pass")
    p.add_argument("--max-flyers", type=int, default=None, help="cap flyer vision calls")
    p.add_argument(
        "--apply",
        action="store_true",
        help="ingest the rows (they land PENDING in the review queue, never live)",
    )
    args = p.parse_args(argv)

    name = SOURCE if args.source == "calendar" else FLYER_SOURCE

    if args.source == "calendar":
        result = pull_calendars(self_check=args.self_check)
    else:
        result = pull_flyers(max_flyers=args.max_flyers)

    records = result.records

    if args.apply:
        # parks_rec_calendar / parks_rec_flyers are NOT in the auto-approve
        # registry, so every ingested row lands as a PENDING contribution for
        # admin review -- vision output never reaches users unreviewed.
        from app.contrib.event_ingest import ingest_event_records, print_ingest_report

        counts = ingest_event_records(records, source=name, dry_run=False)
        print_ingest_report(name, counts, dry_run=False)
        return 0 if counts.errors == 0 else 1

    decisions = _classify_against_db(records)
    classify = (lambda rec: decisions[id(rec)]) if decisions is not None else None

    print_dry_run_report(
        name,
        records,
        classify=classify,
        sample_fn=event_sample,
        notes=_notes(name, result, records),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
