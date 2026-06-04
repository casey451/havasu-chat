"""Collapse cross-source duplicate events (M-12 / M-13 apply-half).

The read-only ``cross_source_dedup_audit.py`` *reports* duplicate event pairs but
writes nothing. This is the mutating companion: it collapses two classes of
*unambiguous* duplicate that the WP-4 dedup primitives identify --

  1. **Canonical-URL identity** -- two live events whose click-through URLs reduce
     to the same key via ``canonical_event_identity`` (same Facebook event id, or
     the same organizer URL with tracking params stripped). Routinely the same
     real event surfaced by both ``go_lake_havasu`` and ``river_scene_import``.
  2. **Recurring-series instance** -- two live events on the same calendar date
     sharing ``(venue, title, weekday)`` (a re-imported weekly occurrence that
     would otherwise double-book that day).

For each duplicate pair the survivor ("keep") is chosen by ``EVENT_SOURCE_PRIORITY``
(lower wins; the richer / more authoritative source), the loser ("dup") has its
``status`` flipped to ``"duplicate"`` (removed from the live feed) and the keeper's
``source`` gains the dup's provenance via ``combine_sources``. No field-level
content from the dup is otherwise merged -- the per-priority field reconcile lives
in ``app/contrib/event_reconciler.py`` and is intentionally NOT duplicated here.

**Dry-run is the default.** Mutating prod, so it follows repo prod-data discipline:
print per-change counts + write a CSV of proposed collapses, mutate only under
``--apply``. Idempotent: a collapsed dup is no longer ``status='live'`` so a
re-run finds nothing.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\dedupe_events_cross_source.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\dedupe_events_cross_source.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.event_reconciler import (  # noqa: E402
    EVENT_SOURCE_PRIORITY,
    combine_sources,
)
from app.events.dedup import (  # noqa: E402
    canonical_event_identity,
    recurring_series_key,
)

_REPORT_PATH = _ROOT / "event_cross_source_dedupe_report.csv"
_UNKNOWN_PRIORITY = 99


@dataclass(frozen=True)
class EventLite:
    """DB-free event record for the pure pairing core (mirrors the audit's EventRow)."""

    id: str
    title: str
    normalized_title: str | None
    source: str | None
    date: object  # datetime.date
    location_name: str | None
    event_url: str | None
    source_url: str | None


@dataclass(frozen=True)
class Collapse:
    reason: str  # canonical_url | recurring_series
    keep_id: str
    keep_source: str | None
    dup_id: str
    dup_source: str | None
    combined_source: str
    detail: str


def _min_priority(source: str | None) -> int:
    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return _UNKNOWN_PRIORITY
    return min(EVENT_SOURCE_PRIORITY.get(p, _UNKNOWN_PRIORITY) for p in parts)


def _order_keep_dup(a: EventLite, b: EventLite) -> tuple[EventLite, EventLite]:
    """Lower EVENT_SOURCE_PRIORITY wins; tie-broken by id for stability."""

    def key(e: EventLite) -> tuple:
        return (_min_priority(e.source), e.id)

    return (a, b) if key(a) <= key(b) else (b, a)


def find_collapses(rows: list[EventLite]) -> list[Collapse]:
    """Pure: find canonical-URL + recurring-series duplicate collapses among rows.

    Each event is collapsed at most once (onto its first-seen keeper) so the apply
    pass touches every dup exactly one time. Canonical-URL identity is checked
    first (strongest signal), then recurring-series instance.
    """
    out: list[Collapse] = []
    collapsed: set[str] = set()  # dup ids already assigned to a keeper

    # 1. Canonical-URL identity: bucket events by every canonical key they carry.
    by_url_key: dict[str, list[EventLite]] = {}
    for e in rows:
        seen: set[str] = set()
        for url in (e.event_url, e.source_url):
            k = canonical_event_identity(url)
            if k is not None and k not in seen:
                seen.add(k)
                by_url_key.setdefault(k, []).append(e)
    for k, members in by_url_key.items():
        uniq = {m.id: m for m in members}
        if len(uniq) < 2:
            continue
        ordered = sorted(uniq.values(), key=lambda e: (_min_priority(e.source), e.id))
        keep = ordered[0]
        for dup in ordered[1:]:
            if dup.id in collapsed or dup.id == keep.id:
                continue
            collapsed.add(dup.id)
            out.append(
                Collapse(
                    reason="canonical_url",
                    keep_id=keep.id,
                    keep_source=keep.source,
                    dup_id=dup.id,
                    dup_source=dup.source,
                    combined_source=combine_sources(keep.source, dup.source or ""),
                    detail=k,
                )
            )

    # 2. Recurring-series instance: same date + (venue, title, weekday).
    by_series: dict[tuple, list[EventLite]] = {}
    for e in rows:
        if e.id in collapsed:
            continue
        wd = e.date.weekday() if e.date is not None else None
        key = recurring_series_key(e.location_name, e.normalized_title or e.title, wd)
        if key is None:
            continue
        by_series.setdefault((e.date, *key), []).append(e)
    for _, members in by_series.items():
        uniq = {m.id: m for m in members}
        if len(uniq) < 2:
            continue
        ordered = sorted(uniq.values(), key=lambda e: (_min_priority(e.source), e.id))
        keep = ordered[0]
        for dup in ordered[1:]:
            if dup.id in collapsed or dup.id == keep.id:
                continue
            collapsed.add(dup.id)
            out.append(
                Collapse(
                    reason="recurring_series",
                    keep_id=keep.id,
                    keep_source=keep.source,
                    dup_id=dup.id,
                    dup_source=dup.source,
                    combined_source=combine_sources(keep.source, dup.source or ""),
                    detail=f"{keep.location_name} | {keep.title} | {keep.date}",
                )
            )
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
                    normalized_title=e.normalized_title,
                    source=e.source,
                    date=e.date,
                    location_name=e.location_name,
                    event_url=e.event_url,
                    source_url=e.source_url,
                )
            )
    return out


def run(*, apply: bool = False) -> tuple[Counter, list[Collapse]]:
    rows = _load_live_events()
    collapses = find_collapses(rows)
    counts: Counter = Counter()
    counts["scanned"] = len(rows)
    for c in collapses:
        counts["collapses"] += 1
        counts[c.reason] += 1

    if apply and collapses:
        from app.db.database import SessionLocal
        from app.db.models import Event

        keep_ids = {c.keep_id: c for c in collapses}
        dup_ids = {c.dup_id: c for c in collapses}
        with SessionLocal() as session:
            for ev in session.query(Event).filter(Event.id.in_(dup_ids)):
                ev.status = "duplicate"
            for ev in session.query(Event).filter(Event.id.in_(keep_ids)):
                ev.source = keep_ids[ev.id].combined_source
            session.commit()

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "reason",
                "keep_id",
                "keep_source",
                "dup_id",
                "dup_source",
                "combined_source",
                "detail",
            ]
        )
        for c in collapses:
            w.writerow(
                [
                    c.reason,
                    c.keep_id,
                    c.keep_source or "",
                    c.dup_id,
                    c.dup_source or "",
                    c.combined_source,
                    c.detail,
                ]
            )
    return counts, collapses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to the DB. Omit for a dry-run (default).",
    )
    args = parser.parse_args()

    counts, _ = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\nCross-source event dedupe -- {mode}")
    print(f"  live events scanned:   {counts['scanned']}")
    print(f"  collapses:             {counts['collapses']}")
    print(f"    canonical_url:       {counts['canonical_url']}")
    print(f"    recurring_series:    {counts['recurring_series']}")
    print(f"  report written:        {_REPORT_PATH}")
    if not args.apply and counts["collapses"]:
        print("\n  Review the CSV, then re-run with --apply to write (prod-data gate).")


if __name__ == "__main__":
    main()
