"""Scrape Havasu Lanes and refresh the dated "Cosmic Bowling" calendar events.

Replaces the one-time hand-load of static Rock & Bowl rows (which expire 2026-08-07)
with a live, cron-driven scrape: each run pulls havasulanesaz.com/SPECIALS,
confirms the Rock & Bowl night is still published, and ingests dated "Cosmic
Bowling" occurrences for the upcoming Fri/Sat window. The ``source_url`` matches
the existing catalog rows, so re-runs dedupe (only NEW future dates are added),
and aged rows are pruned so the window rolls forward forever.

Honesty contract: a parse miss / network failure publishes nothing — the
last-good rows stand until they age out — and a freshness warning is logged.

Usage::

    python -m scripts.havasu_lanes_load --dry-run
    python -m scripts.havasu_lanes_load
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.approval_service import approve_contribution_as_event  # noqa: E402
from app.contrib.havasu_lanes import (  # noqa: E402
    EVENT_TAGS,
    SOURCE_NAME,
    SPECIALS_URL,
    FunEventSpec,
    scrape_specs,
)
from app.db import contribution_store as cs  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Event  # noqa: E402
from app.schemas.contribution import ContributionCreate, EventApprovalFields  # noqa: E402

logger = logging.getLogger(__name__)

# Auto-approve tier — official venue data, same trust level as the golf/funzone
# loaders. The honesty gate is upstream (a night is only emitted if the SPECIALS
# page still publishes it).
CONTRIBUTION_SOURCE = "operator_backfill"
PRUNE_GRACE_DAYS = 2


def _existing(db: Any, url: str) -> bool:
    if db.scalar(select(Contribution.id).where(Contribution.source_url == url).limit(1)) is not None:
        return True
    return db.scalar(select(Event.id).where(Event.source_url == url).limit(1)) is not None


def _hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def ingest_events(specs: list[FunEventSpec], *, db: Any, dry_run: bool) -> dict[str, int]:
    counts = {"found": len(specs), "imported": 0, "skipped_duplicate": 0,
              "skipped_invalid": 0, "approval_failed": 0}
    for spec in specs:
        # source_url IS the canonical occ URL (no #anchor) so it matches the rows
        # already in the catalog -> idempotent dedupe.
        src_url = cs.normalize_submission_url(spec.event_url)
        if not src_url:
            counts["skipped_invalid"] += 1
            continue
        if _existing(db, src_url):
            counts["skipped_duplicate"] += 1
            continue
        start = _hhmm(spec.start_time) if spec.start_time else time(18, 0)
        end = _hhmm(spec.end_time) if spec.end_time else None
        try:
            create = ContributionCreate(
                entity_type="event",
                submission_name=spec.title[:200],
                submission_url=spec.event_url,
                source_url=src_url,
                submission_category_hint=SOURCE_NAME,
                submission_notes=spec.description,
                event_date=spec.date,
                event_end_date=spec.end_date,
                event_time_start=start,
                event_time_end=end,
                source=CONTRIBUTION_SOURCE,
            )
            approve = EventApprovalFields(
                title=spec.title,
                description=spec.description,
                date=spec.date,
                end_date=spec.end_date,
                start_time=start,
                end_time=end,
                location_name=spec.location_name,
                event_url=spec.event_url,
                source_url=src_url,
            )
        except Exception as e:  # noqa: BLE001
            counts["skipped_invalid"] += 1
            logger.warning("invalid havasu_lanes spec %s %s: %s", spec.title, spec.date, e)
            continue
        if dry_run:
            counts["imported"] += 1
            continue
        try:
            created = cs.create_contribution(db, create)
            approve_contribution_as_event(db, created.id, approve, spec.tags or list(EVENT_TAGS))
            db.commit()
            counts["imported"] += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            counts["approval_failed"] += 1
            logger.warning("approve havasu_lanes event %s %s failed: %s", spec.title, spec.date, e)
    return counts


def prune_aged(*, db: Any, today: date | None = None, grace_days: int = PRUNE_GRACE_DAYS) -> int:
    """Hard-delete Cosmic Bowling rows older than ``today - grace`` (the rolling
    window republishes upcoming ones; mirrors the funzone/golf pruners)."""
    today = today or date.today()
    cutoff = today - timedelta(days=max(0, grace_days))
    deleted = (
        db.query(Event)
        .filter(Event.source_url.like("%rock-and-bowl%"), Event.date < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)


def run(*, dry_run: bool, today: date | None = None) -> dict[str, int]:
    specs = scrape_specs(today=today)
    if not specs:
        # Honesty contract: nothing parsed -> publish nothing, keep last-good.
        logger.warning(
            "havasu_lanes: SPECIALS page did not yield the Rock & Bowl night "
            "(%s) — publishing nothing this run (last-good rows stand).", SPECIALS_URL
        )
        return {"found": 0, "imported": 0, "skipped_duplicate": 0,
                "skipped_invalid": 0, "approval_failed": 0, "pruned": 0}
    with SessionLocal() as db:
        counts = ingest_events(specs, db=db, dry_run=dry_run)
        counts["pruned"] = 0 if dry_run else prune_aged(db=db, today=today)
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Scrape Havasu Lanes -> Cosmic Bowling events")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    counts = run(dry_run=bool(args.dry_run))
    print("--- havasu_lanes_load summary ---")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("[havasu_lanes_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
