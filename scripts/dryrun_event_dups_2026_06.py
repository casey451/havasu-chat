"""P1 cleanup (b) — collapse confirmed same-venue / same-time / same-title event dups.

The cross-source dedup (``app/events/dedup.py`` + ``dedupe_events_cross_source.py``)
only collapses on an *exact* normalized-title/venue match or a shared canonical
URL. The confirmed misses slip through small normalization gaps. Example
(Casey's anchor case): the Tue Jun 23 game night is two live rows —

  keep : Hav-A-Sis Game Night   (go_lake_havasu, desc 295, image, ends 6:30pm)
  dup  : HAVASIS GAME NIGHT      (river_scene_import, desc 0, no image, no end)

— same date, same 4:30pm start, same venue (one appends "2187 McCulloch Blvd"),
fuzzy-same title ("hav-a-sis" vs "havasis"). The exact matcher misses it because
the normalized titles and venues differ.

This script catches that class **conservatively**:

  * hard guard: identical ``date`` AND identical ``start_time`` (so a matinee and
    an evening show of the same film are never merged — distinct sessions stay
    distinct);
  * fuzzy guard: ``token_set_ratio`` >= 88 on title AND >= 90 on venue (the latter
    absorbs an appended street address); and
  * keeper = the **richer** record (has end time / image / real source / longer
    description); the thin twin is retired (``status='duplicate'``), and the
    keeper inherits the dup's source provenance via ``combine_sources``.

Each pair's similarity scores are printed so the over-merge risk is visible.

**Dry-run is the default — no DB writes.** Following repo prod-data discipline:
print counts + the kept-vs-retired CSV; mutate only under ``--apply`` (gated on
Casey's approval), writing a timestamped undo snapshot first.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\dryrun_event_dups_2026_06.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\dryrun_event_dups_2026_06.py --apply     # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rapidfuzz import fuzz  # noqa: E402

TITLE_THRESHOLD = 88
VENUE_THRESHOLD = 90

_REPORT_PATH = _ROOT / "event_dup_collapse_candidates.csv"


@dataclass(frozen=True)
class EventLite:
    id: str
    title: str
    source: str | None
    date: date
    start_time: time | None
    end_time: time | None
    location_name: str | None
    source_url: str | None
    has_image: bool
    desc_len: int


@dataclass(frozen=True)
class Pair:
    keep: EventLite
    dup: EventLite
    title_score: float
    venue_score: float


def _richness(e: EventLite) -> tuple:
    """Higher tuple = richer = preferred keeper. (Casey: 'retire the thin twin'.)"""
    has_real_source = bool(e.source_url and "#" not in (e.source_url or ""))
    return (
        1 if e.end_time is not None else 0,
        1 if e.has_image else 0,
        1 if has_real_source else 0,
        e.desc_len,
    )


def _order_keep_dup(a: EventLite, b: EventLite) -> tuple[EventLite, EventLite]:
    """Richer wins; tie-broken by stable id so re-runs agree."""
    ka, kb = _richness(a), _richness(b)
    if ka > kb:
        return a, b
    if kb > ka:
        return b, a
    return (a, b) if a.id <= b.id else (b, a)


def find_pairs(rows: list[EventLite]) -> list[Pair]:
    """Pure: confirmed same-(date, start_time, ~venue, ~title) collapses.

    Each dup is assigned to exactly one keeper. Hard-bucketed on (date,
    start_time) — a NULL/00:00 start is excluded (those are 'Time TBD' rows, not a
    same-time signal). Within a bucket, transitively-similar rows form one group
    with a single richest keeper.
    """
    buckets: dict[tuple, list[EventLite]] = defaultdict(list)
    for e in rows:
        if e.start_time is None or e.start_time == time(0, 0):
            continue  # TBD / unknown time is not a "same-time" match signal
        buckets[(e.date, e.start_time)].append(e)

    out: list[Pair] = []
    assigned: set[str] = set()
    for _key, members in buckets.items():
        if len(members) < 2:
            continue
        # Group transitively-similar members; pick one richest keeper per group.
        groups: list[list[EventLite]] = []
        scores: dict[tuple[str, str], tuple[float, float]] = {}
        for e in members:
            placed = False
            for g in groups:
                rep = g[0]
                ts = fuzz.token_set_ratio(
                    (e.title or "").lower(), (rep.title or "").lower()
                )
                vs = fuzz.token_set_ratio(
                    (e.location_name or "").lower(), (rep.location_name or "").lower()
                )
                if ts >= TITLE_THRESHOLD and vs >= VENUE_THRESHOLD:
                    g.append(e)
                    scores[(e.id, rep.id)] = (ts, vs)
                    placed = True
                    break
            if not placed:
                groups.append([e])
        for g in groups:
            if len(g) < 2:
                continue
            keeper = g[0]
            for cand in g[1:]:
                keeper, _ = _order_keep_dup(keeper, cand)
            for dup in g:
                if dup.id == keeper.id or dup.id in assigned:
                    continue
                assigned.add(dup.id)
                ts = fuzz.token_set_ratio(
                    (dup.title or "").lower(), (keeper.title or "").lower()
                )
                vs = fuzz.token_set_ratio(
                    (dup.location_name or "").lower(), (keeper.location_name or "").lower()
                )
                out.append(Pair(keep=keeper, dup=dup, title_score=ts, venue_score=vs))
    return out


def _load_live_events() -> list[EventLite]:
    from app.db.database import SessionLocal
    from app.db.models import Event

    out: list[EventLite] = []
    with SessionLocal() as session:
        for e in session.query(Event).filter(Event.status == "live").yield_per(500):
            out.append(
                EventLite(
                    id=e.id,
                    title=e.title,
                    source=e.source,
                    date=e.date,
                    start_time=e.start_time,
                    end_time=e.end_time,
                    location_name=e.location_name,
                    source_url=e.source_url,
                    has_image=bool(e.image_url),
                    desc_len=len(e.description or ""),
                )
            )
    return out


def run(*, apply: bool = False) -> tuple[Counter, list[Pair]]:
    rows = _load_live_events()
    pairs = find_pairs(rows)
    counts: Counter = Counter()
    counts["scanned"] = len(rows)
    counts["collapses"] = len(pairs)

    if apply and pairs:
        from app.contrib.event_reconciler import combine_sources
        from app.db.database import SessionLocal
        from app.db.models import Event

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _ROOT / f"event_dup_collapse_undo_{stamp}.csv"
        dup_ids = {p.dup.id: p for p in pairs}
        keep_ids = {p.keep.id: p for p in pairs}
        with SessionLocal() as session:
            touched = list(
                session.query(Event).filter(Event.id.in_(set(dup_ids) | set(keep_ids)))
            )
            with snap.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "old_status", "old_source"])
                for ev in touched:
                    w.writerow([ev.id, ev.status, ev.source])
            for ev in touched:
                if ev.id in dup_ids:
                    ev.status = "duplicate"
                elif ev.id in keep_ids:
                    ev.source = combine_sources(ev.source, keep_ids[ev.id].dup.source or "")
            session.commit()
        print(f"  undo snapshot written: {snap}")

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "date",
                "start_time",
                "keep_id",
                "keep_title",
                "keep_source",
                "dup_id",
                "dup_title",
                "dup_source",
                "title_score",
                "venue_score",
            ]
        )
        for p in sorted(pairs, key=lambda x: (x.keep.date, str(x.keep.start_time))):
            w.writerow(
                [
                    p.keep.date,
                    p.keep.start_time,
                    p.keep.id,
                    p.keep.title,
                    p.keep.source or "",
                    p.dup.id,
                    p.dup.title,
                    p.dup.source or "",
                    f"{p.title_score:.0f}",
                    f"{p.venue_score:.0f}",
                ]
            )
    return counts, pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (omit = dry-run).")
    args = parser.parse_args()

    counts, pairs = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\nEvent dup collapse (same date+time, fuzzy venue+title) -- {mode}")
    print(f"  live events scanned: {counts['scanned']}")
    print(f"  collapses (rows retired): {counts['collapses']}")
    print(f"  candidate CSV: {_REPORT_PATH}")
    if pairs:
        print("\n  KEEP  <-  RETIRE  (date start | title-score / venue-score):")
        for p in sorted(pairs, key=lambda x: (x.keep.date, str(x.keep.start_time))):
            print(f"    {p.keep.date} {p.keep.start_time}  t={p.title_score:.0f} v={p.venue_score:.0f}")
            print(f"      KEEP   {p.keep.id[:8]} [{p.keep.source}] {p.keep.title[:50]!r} (venue {p.keep.location_name[:30]!r})")
            print(f"      RETIRE {p.dup.id[:8]} [{p.dup.source}] {p.dup.title[:50]!r} (venue {p.dup.location_name[:30]!r})")
    if not args.apply and counts["collapses"]:
        print("\n  Review, then re-run with --apply to write (prod-data gate; undo snapshot saved first).")


if __name__ == "__main__":
    main()
