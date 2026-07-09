"""One-time backfill: stamp canonical ``activity:*`` / facet / audience tags on
historical Event rows (calendar reorg Phase 6, 2026-06-25).

Phase 1 made ingest stamp the namespaced activity tags
(``activity:<slug>`` + ``facet:special|competition`` + ``audience:youth|senior``)
via :func:`app.events.activity_taxonomy.event_activity_tags`. Rows ingested
BEFORE that change carry no such tags. The render layer already works on them
(it falls back to the classifier — :func:`resolve_activity`), so this backfill is
**hygiene**: it makes the stored tags match what ingest would write today, so
every surface becomes a pure tag read and the iCal ``CATEGORIES`` feed is exact
for legacy rows too.

Behaviour:

  * Re-derives the canonical tags from each row's title (+ venue + existing tags)
    and **adds only the missing** namespaced tags — it never removes or rewrites
    an existing tag, so a hand-curated row is never clobbered. Idempotent: a
    second run finds nothing to change.
  * ``--dry-run`` (default OFF) reports the would-change counts and the histogram
    of tags that would be added, and writes nothing.
  * A real run writes an **undo snapshot CSV** (event_id, title, old_tags) for
    every changed row BEFORE committing, so the change is reversible.

Per ``CLAUDE.md`` this writes to PROD when run without ``--dry-run`` (the repo
``.env`` points ``DATABASE_URL`` at prod): **dry-run -> show counts -> Casey
approves -> apply.**

Usage::

    .venv\\Scripts\\python.exe -m scripts.backfill_event_activity_tags_2026_06_25 --dry-run
    .venv\\Scripts\\python.exe -m scripts.backfill_event_activity_tags_2026_06_25
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.activity_taxonomy import event_activity_tags  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT = "event_activity_backfill_snapshot.csv"


def added_activity_tags(
    title: str | None, venue: str | None, existing: list[str] | None
) -> list[str]:
    """The canonical namespaced tags missing from ``existing`` for this row.

    Re-derives via :func:`event_activity_tags` (the single ingest classifier) and
    returns only the tags not already present (case/space-insensitive compare),
    preserving the classifier's order. Never returns a tag the row already has, so
    applying it is purely additive and idempotent."""
    existing_norm = {str(t).strip().lower() for t in (existing or [])}
    desired = event_activity_tags(title or "", venue=venue, tags=existing)
    return [t for t in desired if t.lower() not in existing_norm]


def run(
    *,
    dry_run: bool,
    snapshot_path: str = DEFAULT_SNAPSHOT,
    include_all: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    scanned = 0
    changed = 0
    added_hist: Counter = Counter()
    snapshot_rows: list[tuple[str, str, str, str]] = []

    with SessionLocal() as db:
        q = db.query(Event)
        if not include_all:
            q = q.filter(Event.status == "live")
        if source is not None:
            q = q.filter(Event.source == source)
        for ev in q.yield_per(500):
            scanned += 1
            existing = list(ev.tags or [])
            added = added_activity_tags(ev.title, ev.location_name, existing)
            if not added:
                continue
            changed += 1
            for t in added:
                added_hist[t.split(":", 1)[0]] += 1
            snapshot_rows.append(
                (str(ev.entity_id), ev.title or "", "|".join(existing), "|".join(added))
            )
            if not dry_run:
                # Reassign a NEW list so SQLAlchemy detects the JSON-column change.
                ev.tags = [*existing, *added]
        if not dry_run:
            # Write the undo snapshot BEFORE committing, so a failed write leaves
            # an accurate record of what we were about to change.
            _write_snapshot(snapshot_path, snapshot_rows)
            db.commit()

    verb = "would change" if dry_run else "changed"
    print("--- event activity-tag backfill ---")
    print(f"scanned {scanned} live event rows; {verb} {changed}")
    for prefix, n in added_hist.most_common():
        print(f"  +{prefix}:* on {n} rows")
    if dry_run:
        print("[backfill] dry-run: no DB writes, no snapshot")
    else:
        print(f"[backfill] wrote undo snapshot -> {snapshot_path} ({len(snapshot_rows)} rows)")
    return {"scanned": scanned, "changed": changed, "added": dict(added_hist)}


def _write_snapshot(path: str, rows: list[tuple[str, str, str, str]]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# event activity-tag backfill snapshot {stamp}"])
        w.writerow(["event_id", "title", "old_tags", "added_tags"])
        w.writerows(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Backfill canonical activity:* tags on Event rows")
    p.add_argument("--dry-run", action="store_true", help="report without writing")
    p.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, help="undo-snapshot CSV path")
    p.add_argument("--all", action="store_true", help="include non-live rows")
    p.add_argument("--source", default=None, help="limit to one ingest source")
    args = p.parse_args()
    run(
        dry_run=bool(args.dry_run),
        snapshot_path=args.snapshot,
        include_all=bool(args.all),
        source=args.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
