"""Collapse residual duplicate Event rows (calendar-classification fix-up,
2026-06-23). Existing-row DB write — DRY-RUN by default; ``--apply --confirm``
to write, snapshot first (per CLAUDE.md prod-DB rules).

It marks as ``status='duplicate'`` exactly the rows that the RENDER-time
cross-source matcher (:func:`app.events.dedup._group_survivor_positions`) already
drops, and folds each dropped row's provenance into the survivor — so the DB
ends up matching what /events-ui shows, instead of carrying hidden twins. Because
it reuses the live matcher (incl. the new pre-dawn placeholder guard), it catches
both the same-time cross-source twins (Top Goons, Star Search, Heroes Concert,
LB Days Parade) AND the AM/PM parse-error twin (Troy's Alligator Feed 3 AM/3 PM).

Genuine separate sessions (matinee/evening of the same title) are kept apart by
the matcher's 120-min session-gap clustering — they are NOT collapsed.

    .venv\\Scripts\\python.exe scripts\\collapse_event_dups_2026_06_23.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\collapse_event_dups_2026_06_23.py --apply --confirm  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.dedup import (  # noqa: E402
    _group_survivor_positions,
    _render_title_key,
    _survivor_rank,
)


def _sanitized_target() -> str:
    url = DATABASE_URL or ""
    return "..." + url.split("@", 1)[1] if "@" in url else (url or "(unset)")


def _find_collapses(events: list[Event]) -> list[tuple[Event, list[Event]]]:
    """Return [(survivor, [duplicates...]), ...] for each (title, date) group
    where the live matcher drops at least one row."""
    groups: dict[tuple[str, date], list[Event]] = defaultdict(list)
    for ev in events:
        groups[(_render_title_key(ev), ev.date)].append(ev)

    out: list[tuple[Event, list[Event]]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        indexed = list(enumerate(members))
        survivor_positions = _group_survivor_positions(indexed)
        dups = [m for i, m in indexed if i not in survivor_positions]
        if not dups:
            continue
        # The survivor for a collapsed group = best-ranked survivor overall.
        survivor = min(
            (m for i, m in indexed if i in survivor_positions),
            key=_survivor_rank,
        )
        out.append((survivor, dups))
    return out


def run(*, apply: bool, confirm: bool) -> int:
    print(f"target: {_sanitized_target()}")
    with SessionLocal() as db:
        events = (
            db.query(Event)
            .filter(Event.status == "live", Event.date >= date.today())
            .all()
        )
        collapses = _find_collapses(events)
        n_dups = sum(len(d) for _s, d in collapses)
        print(f"scanned live upcoming events: {len(events)}")
        print(f"collapse groups: {len(collapses)}  | rows to mark duplicate: {n_dups}\n")
        for survivor, dups in sorted(collapses, key=lambda c: (c[0].date, c[0].title)):
            print(f"  KEEP  {survivor.date} {survivor.start_time}  {survivor.title!r} "
                  f"[{survivor.source}]")
            for d in dups:
                print(f"   dup  {d.date} {d.start_time}  {d.title!r} [{d.source}]")

        report = _ROOT / "event_dup_collapse_candidates_20260623.csv"
        with report.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["keep_id", "keep_title", "keep_time", "keep_source",
                        "dup_id", "dup_title", "dup_time", "dup_source", "date"])
            for survivor, dups in collapses:
                for d in dups:
                    w.writerow([survivor.id, survivor.title, survivor.start_time,
                                survivor.source, d.id, d.title, d.start_time,
                                d.source, survivor.date])
        print(f"\ncandidate CSV: {report}")

        if not apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply --confirm to collapse.")
            return 0
        if not confirm:
            print("\nREFUSING to write without --confirm.")
            return 2

        from datetime import datetime

        from app.contrib.event_reconciler import combine_sources

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005 (local stamp)
        snap = _ROOT / f"event_dup_collapse_undo_{stamp}.csv"
        with snap.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "old_status", "old_source"])
            for survivor, dups in collapses:
                w.writerow([survivor.id, survivor.status, survivor.source])
                for d in dups:
                    w.writerow([d.id, d.status, d.source])
        for survivor, dups in collapses:
            for d in dups:
                survivor.source = combine_sources(survivor.source, d.source or "")
                d.status = "duplicate"
        db.commit()
        print(f"\nAPPLIED. undo snapshot: {snap}")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    return run(apply=args.apply, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
