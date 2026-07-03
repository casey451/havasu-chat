"""DRY-RUN / READ-ONLY: size the "same session, different title" dedup gap.

Background: every event dedup path is title-keyed or URL-keyed, so the same
real-world session surfaced by multiple sources under different titles (the
"Free Family Swim" / "Open Swim" / "Free Swim Day!" case) is never collapsed.
Before changing the matcher (a behavior change that risks over-merging genuinely
distinct sessions), this script measures how prevalent the gap actually is.

It clusters LIVE events by (normalized venue string, date) and flags clusters
that hold 2+ events whose titles are NOT near-duplicates (token_sort_ratio below
the dedup threshold) — i.e. exactly the rows the title-keyed dedup leaves behind.

READ-ONLY: opens a session, only SELECTs, never adds/commits/deletes. Safe to run
against any environment. It prints counts + a sample; it changes nothing.

Caveat: grouping is by the *normalized venue string*, so venue-name variants
("Aquatic Center" vs "Lake Havasu City Aquatic Center") fall into different
clusters — this UNDERcounts. Treat the number as a lower bound.

Usage:
    python -m scripts.dryrun_venue_title_dup_prevalence_2026_06_28 [--threshold 85] [--sample 25]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

# Event titles carry emoji/accents; force UTF-8 so the sample print never dies
# under a cp1252 Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

from rapidfuzz import fuzz
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Event
from app.events.scrapers.base import normalize_event_title


def _title_key(ev: Event) -> str:
    return normalize_event_title(ev.normalized_title or ev.title or "")


def _venue_key(ev: Event) -> str:
    return normalize_event_title(ev.location_name or "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="token_sort_ratio below which two titles count as DIFFERENT (dedup default 85)",
    )
    ap.add_argument("--sample", type=int, default=25, help="max example clusters to print")
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = list(db.scalars(select(Event).where(Event.status == "live")).all())

    # Cluster by (normalized venue, date); skip rows with no usable venue/title.
    clusters: dict[tuple[str, object], list[Event]] = defaultdict(list)
    for ev in rows:
        vk, tk = _venue_key(ev), _title_key(ev)
        if vk and tk and ev.date is not None:
            clusters[(vk, ev.date)].append(ev)

    flagged: list[tuple[tuple[str, object], list[Event]]] = []
    for key, members in clusters.items():
        if len(members) < 2:
            continue
        # Does this cluster contain at least one pair of NON-duplicate titles?
        titles = [_title_key(m) for m in members]
        has_distinct = any(
            fuzz.token_sort_ratio(titles[i], titles[j]) < args.threshold
            for i in range(len(titles))
            for j in range(i + 1, len(titles))
        )
        if has_distinct:
            flagged.append((key, members))

    total_events_in_flagged = sum(len(m) for _k, m in flagged)
    print(f"live events scanned:            {len(rows)}")
    print(f"(venue, date) clusters w/ 2+:   {sum(1 for m in clusters.values() if len(m) >= 2)}")
    print(f"clusters with distinct titles:  {len(flagged)}   <-- the dedup gap")
    print(f"events sitting in those:        {total_events_in_flagged}")
    print()
    print(f"Sample (up to {args.sample}; venue | date -> titles @ time, source):")
    for (venue, day), members in sorted(flagged, key=lambda x: -len(x[1]))[: args.sample]:
        print(f"\n  {venue} | {day}")
        for m in members:
            t = m.start_time.strftime("%H:%M") if m.start_time else "TBD"
            print(f"      - {m.title!r}  @ {t}  [{m.source}]  (location_name={m.location_name!r})")


if __name__ == "__main__":
    main()
