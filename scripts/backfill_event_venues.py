"""Backfill B-08 / E-4: drop description-shaped venue names from existing events.

Some ingested events (notably the Go Lake Havasu JSON-LD feed before the WP-4
shape gate landed) stored a *paragraph of description prose*, a stringified
``PostalAddress`` dict, or the organizer suite address block in their venue field
(``Event.location_name``). This backfill re-runs the single shared venue shape gate
(:func:`app.events.scrapers.base.is_valid_venue_shape`) over every event and, for
rows whose venue fails the gate, drops the venue to NULL rather than leave a
description blob masquerading as a venue.

It is deliberately CONSERVATIVE: it only ever NULLs a venue that fails shape
validation -- it never invents a venue. (Recovering a real venue from the
description body is the separate ``backfill_event_fields.py`` job; this script is
the shape-hygiene pass that runs after it.)

**Dry-run is the default.** This rewrites a human-visible column on prod, so it
follows the repo's prod-data discipline: report per-change counts + write a CSV of
proposed changes, and only mutate the DB when invoked with ``--apply``. Re-running
after ``--apply`` is a no-op (idempotent): a NULLed venue no longer fails the gate.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\backfill_event_venues.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\backfill_event_venues.py --apply    # write (gated)
    .venv\\Scripts\\python.exe scripts\\backfill_event_venues.py --source go_lake_havasu
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.scrapers.base import is_valid_venue_shape  # noqa: E402

_REPORT_PATH = _ROOT / "event_venue_shape_backfill_report.csv"


def run(*, apply: bool = False, source: str | None = None) -> Counter:
    """Scan events; NULL any venue that fails the shape gate. Returns counts."""
    db = SessionLocal()
    counts: Counter = Counter()
    rows_out: list[dict[str, str]] = []
    try:
        q = db.query(Event)
        if source:
            q = q.filter(Event.source == source)
        for event in q.yield_per(500):
            counts["scanned"] += 1
            venue = (event.location_name or "").strip()
            if not venue:
                continue
            if is_valid_venue_shape(venue, description=event.description):
                continue
            counts["would_null"] += 1
            rows_out.append(
                {
                    "id": event.id,
                    "title": event.title,
                    "source": event.source or "",
                    "bad_location_name": venue[:300],
                    "location_len": str(len(venue)),
                }
            )
            if apply:
                # location_name / location_normalized are NOT NULL; the catalog's
                # "no venue" sentinel is the empty string (see the `or ""` reads
                # across admin/digest), so drop to "" rather than NULL.
                event.location_name = ""
                event.location_normalized = ""
        if apply:
            db.commit()
    finally:
        db.close()

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "title",
                "source",
                "bad_location_name",
                "location_len",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_out)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to the DB. Omit for a dry-run (default).",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Limit to one Event.source (e.g. go_lake_havasu).",
    )
    args = parser.parse_args()

    counts = run(apply=args.apply, source=args.source)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\nEvent venue-shape backfill -- {mode}")
    print(f"  scanned:               {counts['scanned']}")
    print(f"  venues failing shape:  {counts['would_null']}")
    print(f"  report written:        {_REPORT_PATH}")
    if not args.apply and counts["would_null"]:
        print("\n  Review the CSV, then re-run with --apply to write (prod-data gate).")


if __name__ == "__main__":
    main()
