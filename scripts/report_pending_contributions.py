"""Read-only report of PENDING event contributions in the review queue (WS12).

Presents what is waiting for human approval in /admin, grouped by source, as a
readable table (title, date/time, venue, source_ref). Used to review the batches
that the WS12 connectors (and the existing Phase-9b connectors) drop into the
review queue before anyone approves them. **Read-only — writes nothing.**

Usage:
    python scripts/report_pending_contributions.py            # all pending events
    python scripts/report_pending_contributions.py --source lhc_bmx --source havasu_youth
    python scripts/report_pending_contributions.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution  # noqa: E402


def _venue_from_notes(notes: str | None) -> str:
    """Contributions store the venue as a 'Venue: X' prefix on submission_notes."""
    if not notes:
        return ""
    first = notes.splitlines()[0].strip()
    if first.lower().startswith("venue:"):
        return first[len("venue:") :].strip()
    return ""


def _rows(
    sources: list[str] | None,
    *,
    sample: int | None = None,
    limit: int | None = None,
) -> list[dict]:
    from sqlalchemy import func

    with SessionLocal() as db:
        stmt = select(Contribution).where(
            Contribution.status == "pending", Contribution.entity_type == "event"
        )
        if sources:
            stmt = stmt.where(Contribution.source.in_(sources))
        # --sample draws N random rows (best with a single --source); --limit
        # takes the first N in the normal ordering. Otherwise ordered for review.
        if sample:
            stmt = stmt.order_by(func.random()).limit(sample)
        else:
            stmt = stmt.order_by(
                Contribution.source, Contribution.event_date, Contribution.event_time_start
            )
            if limit:
                stmt = stmt.limit(limit)
        out: list[dict] = []
        for c in db.scalars(stmt):
            out.append(
                {
                    "id": c.id,
                    "source": c.source,
                    "title": c.submission_name,
                    "date": c.event_date.isoformat() if c.event_date else None,
                    "time": c.event_time_start.strftime("%H:%M") if c.event_time_start else None,
                    "venue": _venue_from_notes(c.submission_notes),
                    "source_ref": c.source_url or "",
                }
            )
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report pending event contributions")
    ap.add_argument("--source", action="append", dest="sources", metavar="SOURCE")
    ap.add_argument("--sample", type=int, help="draw N random rows (best with one --source)")
    ap.add_argument("--limit", type=int, help="first N rows in review order")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    rows = _rows(args.sources, sample=args.sample, limit=args.limit)
    if args.as_json:
        print(json.dumps(rows, indent=2))
        return 0

    if not rows:
        print("No pending event contributions.")
        return 0

    by_source: dict[str, list[dict]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)

    print(f"PENDING event contributions: {len(rows)} across {len(by_source)} source(s)\n")
    for source, items in sorted(by_source.items()):
        print(f"### {source}  ({len(items)} pending)")
        print(f"{'id':>6}  {'date':<10} {'time':<5}  {'title':<44}  {'venue':<28}  source_ref")
        print("-" * 130)
        for r in items:
            print(
                f"{r['id']:>6}  {(r['date'] or '—'):<10} {(r['time'] or '—'):<5}  "
                f"{(r['title'] or '')[:44]:<44}  {(r['venue'] or '')[:28]:<28}  "
                f"{(r['source_ref'] or '')[:60]}"
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
