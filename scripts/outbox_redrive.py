"""Outbox redrive sweep — Phase 4.1 must-not-lose-job recovery.

Polls the ``outbox`` table for rows in state ``pending`` whose
``created_at`` is older than ``--idle-seconds`` (default 30 — avoids
racing the hot-path BackgroundTasks invocation that fires right after
row insertion). For each row, calls
:func:`app.core.background.deliver_outbox_row`.

Phase 4.4 close-out wires this script to a Railway scheduled-job
service running every 5 minutes (per
``docs/maintainability/background_job_infrastructure_decision.md`` §6.2 +
``docs/operations/railway_scheduled_jobs_runbook.md``).

Usage::

    python -m scripts.outbox_redrive                 # default settings
    python -m scripts.outbox_redrive --dry-run       # print, don't deliver
    python -m scripts.outbox_redrive --max-rows 200  # cap per invocation
    python -m scripts.outbox_redrive --idle-seconds 60

Exit status:
    0 — completed normally (zero or more rows processed)
    1 — unexpected error (DB unreachable, etc.); operator inspects logs

Idempotency: safe to invoke concurrently — :func:`deliver_outbox_row`
claims each row via a state transition (``pending`` → ``in_flight``)
inside its own transaction; a second concurrent invocation will see
``in_flight`` and skip the row.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("scripts.outbox_redrive")


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep pending Outbox rows and invoke their handlers.",
    )
    parser.add_argument(
        "--idle-seconds",
        type=int,
        default=30,
        help=(
            "Minimum age (seconds) before a pending row is eligible for "
            "redrive. Default 30 avoids racing the hot-path BackgroundTasks "
            "invocation per design memo §6.2."
        ),
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=100,
        help=(
            "Cap on rows processed per invocation. Prevents a long sweep "
            "from blocking the next cron tick."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("Print the IDs of rows that would be redriven without invoking handlers."),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable INFO-level logging to stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    # Function-scope imports keep this script lightweight and preserve
    # the gotcha-#17 cure (app.core.background is careful about its
    # own import order).
    from app.core.background import (
        OUTBOX_STATE_PENDING,
        deliver_outbox_row,
    )
    from app.db.database import SessionLocal
    from app.db.models import Outbox

    cutoff = _utcnow_naive() - timedelta(seconds=args.idle_seconds)

    with SessionLocal() as session:
        rows = (
            session.query(Outbox)
            .filter(Outbox.state == OUTBOX_STATE_PENDING)
            .filter(Outbox.created_at <= cutoff)
            .order_by(Outbox.created_at.asc())
            .limit(args.max_rows)
            .all()
        )
        row_ids: list[str] = [str(r.id) for r in rows]

    if not row_ids:
        logger.info(
            "outbox_redrive.no_pending_rows",
            extra={"cutoff": cutoff.isoformat(), "max_rows": args.max_rows},
        )
        return 0

    logger.info(
        "outbox_redrive.start",
        extra={
            "candidate_count": len(row_ids),
            "cutoff": cutoff.isoformat(),
            "dry_run": args.dry_run,
        },
    )

    delivered = 0
    skipped = 0
    for row_id in row_ids:
        if args.dry_run:
            print(f"DRY-RUN would redrive outbox row {row_id}")
            continue
        try:
            ok = deliver_outbox_row(row_id)
        except Exception:
            logger.exception(
                "outbox_redrive.deliver_failed",
                extra={"outbox_id": row_id},
            )
            skipped += 1
            continue
        if ok:
            delivered += 1
        else:
            skipped += 1

    print(
        f"outbox_redrive: candidates={len(row_ids)} "
        f"delivered={delivered} skipped={skipped} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
