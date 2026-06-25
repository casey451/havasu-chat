"""One-time backfill: auto-approve the already-PENDING CLEAN vision events.

#514 made the Parks & Rec calendar/flyer + senior-center flyer vision sources
auto-publish CLEAN rows to the live calendar — but only for FUTURE ingests. A real
``--apply`` run before #514 deployed (or any run on pre-#514 code) left its rows as
``inserted_pending`` in ``/admin``; this backfill applies the **same #514 gate** to
those existing pending rows: auto-approve the clean ones, leave the flagged ones
pending. It reuses the production decision (``backfill_pending_vision_contribution``
in ``app.contrib.event_ingest``) rather than reimplementing it, so a backfilled
event is identical to one auto-published on ingest.

PROD DB WRITE — defaults to dry-run; ``--apply`` writes (CLAUDE.md: dry-run -> show
counts -> Casey approves -> apply). Idempotent: already-approved rows are no longer
``pending`` and so are skipped; a re-run approves nothing new. Non-vision pending
rows are never selected, so they are untouched.

    .venv\\Scripts\\python.exe scripts/backfill_vision_auto_approve.py            # dry-run
    .venv\\Scripts\\python.exe scripts/backfill_vision_auto_approve.py --apply    # writes

A held row's reason is one of: ``weekday_mismatch`` (listed weekday contradicts the
body), ``reconcile:<action>`` (now a duplicate/ambiguous against a live event),
``engine_hold`` (vision confidence/self-check hold — note this signal was not
persisted on the contribution, so it is effectively unavailable post-hoc), or
``not registry-eligible`` (incomplete row).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.event_ingest import (  # noqa: E402
    VISION_EVENT_SOURCES,
    VisionBackfillResult,
    backfill_pending_vision_contribution,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution  # noqa: E402


def _select_pending_vision(db, *, limit: int | None) -> list[Contribution]:
    q = (
        db.query(Contribution)
        .filter(
            Contribution.status == "pending",
            Contribution.entity_type == "event",
            Contribution.source.in_(tuple(VISION_EVENT_SOURCES)),
        )
        .order_by(Contribution.source, Contribution.id)
    )
    if limit is not None:
        q = q.limit(limit)
    return list(q.all())


def _print_report(
    results: list[VisionBackfillResult], *, dry_run: bool, by_source: Counter
) -> None:
    approve = [r for r in results if r.action == "approve"]
    held = [r for r in results if r.action == "hold"]
    approve_label = "would_auto_approve" if dry_run else "approved"
    hold_label = "would_hold" if dry_run else "held"

    print("backfill vision pending -> live (clean only)")
    print(f"  selected (pending vision)  {len(results)}")
    for src, n in sorted(by_source.items()):
        print(f"    {src:<24} {n}")
    print(f"  {approve_label:<24} {len(approve)}")
    print(f"  {hold_label:<24} {len(held)}")
    if held:
        reasons = Counter(r.reason for r in held)
        print("  held breakdown:")
        for reason, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"    {reason:<24} {n}")

    sample = approve[:3]
    if sample:
        print(f"  sample {approve_label} (first {len(sample)}):")
        for r in sample:
            suffix = f" -> event {r.event_id}" if r.event_id else ""
            print(f"    #{r.contribution_id} {r.title!r}{suffix}")

    if dry_run:
        print("  (dry run -- no database writes)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="approve the clean pending rows (writes); default is read-only dry-run",
    )
    p.add_argument(
        "--limit", type=int, default=None, help="cap how many pending rows to process"
    )
    args = p.parse_args(argv)
    dry_run = not args.apply

    results: list[VisionBackfillResult] = []
    by_source: Counter = Counter()
    with SessionLocal() as db:
        pending = _select_pending_vision(db, limit=args.limit)
        for c in pending:
            by_source[c.source] += 1
            results.append(
                backfill_pending_vision_contribution(db, c, dry_run=dry_run)
            )

    _print_report(results, dry_run=dry_run, by_source=by_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
