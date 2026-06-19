"""Audit the 'Fitness & classes' mislabel — read-only, LLM-free.

Phase E §3.2 separate finding: the events calendar's "Fitness & classes" group
(``_group_for`` key ``classes``) collects far more than fitness classes. The
cause is the intentional *recurring = class* rule in
``app.home.events_views._group_for_tier``::

    if recurring or tier == _TIER_CLASS:
        return "classes"

so EVERY recurring row lands in "classes" regardless of whether its title reads
as community / music / on-the-water. This script isolates exactly which rows are
mislabeled by that rule, so a fix can be tuned against real titles instead of
guesses.

Method (precise, no heuristics beyond the live classifier): for every live
recurring event that currently lands in ``classes``, recompute its tier *as if
it were a one-off* (``recurring=False``). If that one-off tier is anything other
than ``_TIER_CLASS``, the row is in "classes" ONLY because of the recurring rule
— i.e. a mislabel candidate — and we report what group it *would* join as a
one-off (community → "Around town", music → "Music & nightlife", etc.).

READ-ONLY — opens a session, runs SELECTs, writes nothing. Safe against prod.

Usage:
    python scripts/audit_classes_mislabel.py            # summary + full list
    python scripts/audit_classes_mislabel.py --limit 40 # cap the printed list
    python scripts/audit_classes_mislabel.py --csv out.csv  # also dump a CSV
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.home.events_views import _group_for  # noqa: E402
from app.home.sandstone import (  # noqa: E402
    _TIER_CLASS,
    _TIER_COMMUNITY,
    _TIER_MUSIC,
    _TIER_OTHER,
    _TIER_SPECIAL,
    _TIER_WATER,
    _event_tier,
)

# What the one-off tier maps to in plain English (for the report only).
_TIER_NAME = {
    _TIER_SPECIAL: "special → Around town",
    _TIER_COMMUNITY: "community → Around town",
    _TIER_MUSIC: "music → Music & nightlife",
    _TIER_WATER: "water → Lake Life",
    _TIER_OTHER: "other one-off → Around town",
    _TIER_CLASS: "class (genuine)",
}


def _live_recurring_events(db) -> list[Event]:
    stmt = select(Event).where(
        Event.status == "live",
        or_(Event.is_recurring.is_(True), Event.rrule.isnot(None), Event.rdate.isnot(None)),
    )
    return list(db.scalars(stmt).unique().all())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="cap printed rows (0 = all)")
    ap.add_argument("--csv", type=str, default="", help="also write a CSV here")
    args = ap.parse_args()

    with SessionLocal() as db:
        events = _live_recurring_events(db)

        in_classes = 0
        mislabeled: list[tuple[str, str, str]] = []  # (title, would_be, venue)
        for ev in events:
            title = ev.title or ""
            tags = ev.tags
            group = _group_for(
                title=title, tags=tags, featured=bool(ev.featured), recurring=True
            )
            if group != "classes":
                continue
            in_classes += 1
            oneoff_tier = _event_tier(
                title=title, tags=tags, featured=bool(ev.featured), recurring=False
            )
            if oneoff_tier != _TIER_CLASS:
                mislabeled.append(
                    (title, _TIER_NAME.get(oneoff_tier, str(oneoff_tier)), ev.location_name or "")
                )

    mislabeled.sort(key=lambda r: (r[1], r[0].lower()))

    print(f"Live recurring events landing in 'Fitness & classes': {in_classes}")
    print(f"  …of those, MISLABELED (only there via the recurring rule): {len(mislabeled)}")
    by_dest = Counter(r[1] for r in mislabeled)
    for dest, n in by_dest.most_common():
        print(f"    {n:>4}  would be {dest}")
    print()

    shown = mislabeled if args.limit <= 0 else mislabeled[: args.limit]
    for title, would_be, venue in shown:
        venue_s = f"  [{venue}]" if venue else ""
        print(f"  • {title}  →  {would_be}{venue_s}")
    if args.limit and len(mislabeled) > args.limit:
        print(f"  … and {len(mislabeled) - args.limit} more (raise --limit to see all)")

    if args.csv:
        out = Path(args.csv)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["title", "would_be_group", "venue"])
            w.writerows(mislabeled)
        print(f"\nWrote {len(mislabeled)} rows to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
