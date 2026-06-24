"""Correct known scraped venue/title misspellings on Event rows (gated DB op).

The display layer already corrects these for the calendar via
``app.events.title_clean.fix_venue_spelling`` (so a re-scrape can't un-fix the
/events-ui view), but the underlying ``Event.location_name`` / ``Event.title``
still carry the typo — which leaks on the event detail page and anywhere the raw
value is shown. This repairs the rows in place.

Scope is deliberately tiny and exact: only the verified misspellings in
``app.events.title_clean._VENUE_SPELLING_FIXES`` (currently just
"Roatary" → "Rotary", the Splash Bash venue). Whole-word, case-insensitive; every
other row is untouched.

Per CLAUDE.md this is a production DB write: it is **--dry-run by default** —
it prints the exact rows and counts and changes nothing. Re-run with ``--apply``
ONLY after Casey approves the shown counts.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\fix_venue_typos.py            # dry-run (default)
    .venv\\Scripts\\python.exe scripts\\fix_venue_typos.py --apply    # after approval
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.title_clean import _VENUE_SPELLING_FIXES, fix_venue_spelling  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Correct known scraped venue typos on Event rows")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write the corrections (default is a read-only dry-run).",
    )
    args = ap.parse_args(argv)
    dry_run = not args.apply

    # Build a case-insensitive OR over every known misspelling, on both columns.
    misspellings = list(_VENUE_SPELLING_FIXES.keys())
    if not misspellings:
        print("No known misspellings configured — nothing to do.")
        return 0

    changed_loc = 0
    changed_title = 0
    with SessionLocal() as db:
        conds = []
        for m in misspellings:
            conds.append(Event.location_name.ilike(f"%{m}%"))
            conds.append(Event.title.ilike(f"%{m}%"))
        rows = list(db.scalars(select(Event).where(or_(*conds))).all())
        print(f"Matched {len(rows)} event row(s) carrying a known venue typo:")
        for ev in rows:
            new_loc = fix_venue_spelling(ev.location_name or "")
            new_title = fix_venue_spelling(ev.title or "")
            loc_diff = bool(ev.location_name) and new_loc != ev.location_name
            title_diff = bool(ev.title) and new_title != ev.title
            if not loc_diff and not title_diff:
                continue
            print(f"  [{ev.id}] source={ev.source} date={ev.date}")
            if loc_diff:
                print(f"      location_name: {ev.location_name!r} -> {new_loc!r}")
                ev.location_name = new_loc
                changed_loc += 1
            if title_diff:
                print(f"      title:         {ev.title!r} -> {new_title!r}")
                ev.title = new_title
                changed_title += 1
        print(
            f"\nWould change {changed_loc} location_name + {changed_title} title value(s)."
            if dry_run
            else f"\nApplied {changed_loc} location_name + {changed_title} title correction(s)."
        )
        if dry_run:
            db.rollback()
            print("DRY-RUN: no rows written. Re-run with --apply after approval.")
        else:
            db.commit()
            print("COMMITTED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
