"""GATED prod-data backfill: stamp Family Night Golf with venue-kind:range +
facet:special so it nests inline under Things to Do → Golf — simulators & Top
Tracer → Top Tracer driving range (calendar reorg Phase 4c).

The row "Toptracer Range — Family Night Golf" (Iron Wolf Toptracer Range) carries
``activity:golf`` + audience:youth but NO ``venue-kind`` and NO ``facet:special``,
so today it lands in Sports & Fitness → "Golf — courses" instead of as a Top
Tracer inline special. This adds the two missing tags (idempotent; never removes
or rewrites other tags).

Read-only by default. ``--apply`` writes and saves an undo CSV (id,old_tags).

Usage (PowerShell, repo root):
    .venv\\Scripts\\python.exe -m scripts.backfill_family_night_golf_tags_2026_06_26            # dry-run
    .venv\\Scripts\\python.exe -m scripts.backfill_family_night_golf_tags_2026_06_26 --apply    # write
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import or_  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_ADD_TAGS = ["venue-kind:range", "facet:special"]


def _matches(ev: Event) -> bool:
    """A Family Night Golf row: an activity:golf row whose title is the Toptracer
    family-night session. Title-anchored + activity-tag-guarded so we never touch
    an unrelated row."""
    title = (ev.title or "").lower()
    tags = {str(t).strip().lower() for t in (ev.tags or [])}
    return "family night golf" in title and "activity:golf" in tags


def _new_tags(ev: Event) -> list[str]:
    tags = list(ev.tags or [])
    have = {str(t).strip().lower() for t in tags}
    for t in _ADD_TAGS:
        if t not in have:
            tags.append(t)
    return tags


def run(apply: bool) -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(Event)
            .filter(or_(Event.title.ilike("%family night golf%"),
                        Event.normalized_title.ilike("%family night golf%")))
            .all()
        )
        targets = [ev for ev in rows if _matches(ev)]
        would_change = [ev for ev in targets if _new_tags(ev) != list(ev.tags or [])]

        print(f"matched Family Night Golf rows: {len(targets)}")
        print(f"  of those, MISSING ≥1 of {_ADD_TAGS}: {len(would_change)}")
        by_src = Counter((ev.source or "?") for ev in targets)
        by_date = Counter(str(ev.date) for ev in targets)
        print(f"  sources: {dict(by_src)}")
        print(f"  distinct dates: {len(by_date)} (e.g. {sorted(by_date)[:5]})")
        for ev in targets[:3]:
            print(f"  e.g. id={ev.id} {ev.title!r} @ {ev.location_name!r}")
            print(f"       before={list(ev.tags or [])}")
            print(f"       after ={_new_tags(ev)}")

        if not apply:
            print("\nDRY-RUN — no writes. Re-run with --apply to write (saves undo CSV).")
            return

        if not would_change:
            print("\nNothing to change (already tagged). No write.")
            return

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ003
        undo = _ROOT / f"undo_family_night_golf_tags_{stamp}.csv"
        with undo.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["event_id", "old_tags_json"])
            for ev in would_change:
                w.writerow([ev.id, json.dumps(list(ev.tags or []))])
        for ev in would_change:
            ev.tags = _new_tags(ev)
        db.commit()
        print(f"\nAPPLIED: tagged {len(would_change)} rows. Undo CSV: {undo.name}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    run(ap.parse_args().apply)
