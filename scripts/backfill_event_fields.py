"""Backfill ED-1: repair events whose venue/address/description were scrambled.

Applies the shared :func:`app.events.field_recovery.recover_event_fields` pass to
existing ``Event`` rows — recovering the real venue/address from the ``LOCATION:``
line buried in the description, peeling ingest noise, and capturing any image URL.

**Dry-run is the default.** This rewrites human-visible text columns on prod, so it
follows the repo's prod-data discipline: report counts + a sample diff, write a full
CSV of proposed changes, and only mutate the DB when invoked with ``--apply``.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\backfill_event_fields.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\backfill_event_fields.py --apply    # write (gated)
    .venv\\Scripts\\python.exe scripts\\backfill_event_fields.py --source go_lake_havasu
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
from app.events.field_recovery import recover_event_fields  # noqa: E402

_REPORT_PATH = _ROOT / "event_field_backfill_report.csv"


def run(*, apply: bool = False, source: str | None = None) -> Counter:
    db = SessionLocal()
    counts: Counter = Counter()
    rows_out: list[dict[str, str]] = []
    try:
        q = db.query(Event)
        if source:
            q = q.filter(Event.source == source)
        for event in q.yield_per(500):
            counts["scanned"] += 1
            recovered = recover_event_fields(
                location_name=event.location_name,
                description=event.description,
            )
            if not recovered.changed:
                continue
            counts["changed"] += 1
            rows_out.append(
                {
                    "id": event.id,
                    "title": event.title,
                    "source": event.source or "",
                    "old_location_name": (event.location_name or "")[:200],
                    "new_location_name": recovered.location_name[:200],
                    "new_address": recovered.address or "",
                    "new_image_url": recovered.image_url or "",
                    "old_desc_len": str(len(event.description or "")),
                    "new_desc_len": str(len(recovered.description)),
                }
            )
            if recovered.location_name == "Location TBD":
                counts["location_tbd"] += 1
            if recovered.address:
                counts["address_recovered"] += 1
            if recovered.image_url:
                counts["image_recovered"] += 1
            if apply:
                event.location_name = recovered.location_name
                event.location_normalized = recovered.location_name.lower().strip()
                event.description = recovered.description
                # image_url assignment is guarded so this script also runs before
                # the column migration lands (older schema simply skips it).
                if recovered.image_url and hasattr(event, "image_url"):
                    event.image_url = recovered.image_url
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
                "old_location_name",
                "new_location_name",
                "new_address",
                "new_image_url",
                "old_desc_len",
                "new_desc_len",
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
    print(f"\nEvent field backfill — {mode}")
    print(f"  scanned:            {counts['scanned']}")
    print(f"  would change:       {counts['changed']}")
    print(f"  address recovered:  {counts['address_recovered']}")
    print(f"  image recovered:    {counts['image_recovered']}")
    print(f"  location -> TBD:    {counts['location_tbd']}")
    print(f"  report written:     {_REPORT_PATH}")
    if not args.apply and counts["changed"]:
        print("\n  Review the CSV, then re-run with --apply to write (prod-data gate).")


if __name__ == "__main__":
    main()
