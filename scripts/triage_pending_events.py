"""Bulk-triage pending event contributions in the review queue (WS12 backlog).

Selects pending event contributions by source + optional date/year/id filters and
changes their status in bulk — the reviewed-then-quarantine path for the large
review-queue backlogs (parks_rec_calendar vision-OCR rows dated in the wrong
year, allevents past aggregator rows, etc.). Companion to
scripts/approve_pending_events.py (which publishes) and
scripts/reject_duplicate_pending.py (the older provider-dedup reject).

Gated: **dry-run by default**, --apply writes. Reversible: rejecting sets
status=rejected; to undo, re-run with ``--set-status pending --from-status
rejected`` (or pass the exact ``--ids`` the apply printed). Idempotent — a row
not in ``--from-status`` is skipped.

Examples:
    # quarantine the parks_rec OCR-year-error rows (dated 2027)
    python scripts/triage_pending_events.py --source parks_rec_calendar --year 2027 \
        --reason unverifiable                          # dry-run
    python scripts/triage_pending_events.py --source parks_rec_calendar --year 2027 \
        --reason unverifiable --apply                  # writes

    # drop past aggregator rows
    python scripts/triage_pending_events.py --source allevents --before 2026-07-09 \
        --reason unverifiable --apply

    # undo a reject (back to pending)
    python scripts/triage_pending_events.py --ids "101 102" --set-status pending \
        --from-status rejected --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import extract, select  # noqa: E402

from app.db.contribution_store import update_contribution_status  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution  # noqa: E402

_REASONS = {"duplicate", "out_of_area", "spam", "incomplete", "unverifiable", "other"}
_STATUSES = {"pending", "rejected", "needs_info", "approved"}


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(t) for t in re.split(r"[,\s]+", raw.strip()) if t]


def select_rows(
    db,
    *,
    sources: list[str] | None,
    ids: list[int],
    before: date | None,
    year: int | None,
    from_status: str,
) -> list[Contribution]:
    stmt = select(Contribution).where(
        Contribution.status == from_status,
        Contribution.entity_type == "event",
    )
    if ids:
        stmt = stmt.where(Contribution.id.in_(ids))
    if sources:
        stmt = stmt.where(Contribution.source.in_(sources))
    if before is not None:
        stmt = stmt.where(Contribution.event_date < before)
    if year is not None:
        stmt = stmt.where(extract("year", Contribution.event_date) == year)
    stmt = stmt.order_by(Contribution.source, Contribution.event_date, Contribution.id)
    return list(db.scalars(stmt))


def run(
    *,
    sources: list[str] | None,
    ids: list[int],
    before: date | None,
    year: int | None,
    from_status: str,
    set_status: str,
    reason: str | None,
    note: str | None,
    apply: bool,
) -> int:
    with SessionLocal() as db:
        rows = select_rows(
            db,
            sources=sources,
            ids=ids,
            before=before,
            year=year,
            from_status=from_status,
        )
        by_source: Counter = Counter(r.source for r in rows)
        verb = "APPLY" if apply else "DRY "
        print(
            f"{verb}: {len(rows)} '{from_status}' event rows -> '{set_status}'"
            + (f" (reason={reason})" if set_status == "rejected" else "")
        )
        for src, n in sorted(by_source.items()):
            print(f"  {src}: {n}")
        for r in rows[:60]:
            print(f"    {r.id:>6} {r.event_date} {(r.submission_name or '')[:52]}")
        if len(rows) > 60:
            print(f"    ... (+{len(rows) - 60} more)")

        if not apply:
            print(f"\nDRY-RUN: would change {len(rows)} rows. Re-run with --apply.")
            return 0

        changed = 0
        changed_ids: list[int] = []
        for r in rows:
            update_contribution_status(
                db,
                r.id,
                set_status,
                review_notes=note,
                rejection_reason=(reason if set_status == "rejected" else None),
            )
            changed += 1
            changed_ids.append(r.id)
        print(f"\nAPPLIED: changed {changed} rows to '{set_status}'.")
        print("  undo ids:", " ".join(str(i) for i in changed_ids))
        return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bulk-triage pending event contributions")
    ap.add_argument("--source", action="append", dest="sources", metavar="SOURCE")
    ap.add_argument("--ids", help="explicit ids (space/comma-separated)")
    ap.add_argument("--before", help="only rows with event_date < YYYY-MM-DD")
    ap.add_argument("--year", type=int, help="only rows whose event_date year == YYYY")
    ap.add_argument("--from-status", default="pending", choices=sorted(_STATUSES))
    ap.add_argument("--set-status", default="rejected", choices=sorted(_STATUSES))
    ap.add_argument("--reason", default="unverifiable", choices=sorted(_REASONS))
    ap.add_argument("--note", default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    ids = _parse_ids(args.ids)
    if not args.sources and not ids:
        ap.error("provide at least one --source or --ids (refusing to match everything)")
    before = date.fromisoformat(args.before) if args.before else None

    return run(
        sources=args.sources,
        ids=ids,
        before=before,
        year=args.year,
        from_status=args.from_status,
        set_status=args.set_status,
        reason=args.reason,
        note=args.note,
        apply=args.apply,
    )


if __name__ == "__main__":
    raise SystemExit(main())
