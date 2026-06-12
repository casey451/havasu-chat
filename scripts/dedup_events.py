"""Deduplicate EXACT-duplicate event occurrences (DRY-RUN by default; gated).

Sibling to ``dedup_entities.py`` (which deliberately excludes events). Events are
date-aware: a recurring "Lap Swim" or weekly Farmers Market legitimately exists
as many rows that share name + venue but differ by **date** — those must NEVER be
collapsed. This tool only removes *exact-duplicate occurrences*: two event rows
with the **same name + same venue/address + same start_date + same start_time**
(i.e. the same scraper imported the same session twice). It keeps one and
soft-deactivates the rest (``is_active = False``, reversible).

It also REPORTS (never touches) "recurring-series" clusters — same name + venue
but multiple distinct dates. Whether to collapse a series into one card with a
recurrence rule is a product/display decision, not a dedup, so it is surfaced for
a human, not acted on.

Only ``entity_type = 'event'`` rows that have a schedule with a ``start_date``
participate; an event with no dated schedule is too ambiguous to dedup and is
left alone.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``, wraps writes in ONE
transaction, and first writes a rollback snapshot of the deactivated ids. Prints
the sanitized DB target every run.

    .venv\\Scripts\\python.exe scripts\\dedup_events.py --csv event_dedup_plan.csv     # DRY RUN
    .venv\\Scripts\\python.exe scripts\\dedup_events.py --apply --confirm               # writes

PROD GATE (CLAUDE.md): dry-run → show Casey the plan + counts → approval → apply.
The agent never runs --apply against prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Location, Schedule  # noqa: E402

EVENT_TYPE = "event"


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def exact_occurrence_key(
    name: str | None, address: str | None, start_date: Any, start_time: Any
) -> str | None:
    """Key identifying the SAME event occurrence, or ``None`` if undatable.

    Requires a name and a ``start_date`` — without a concrete date two same-named
    events can't be proven to be the same occurrence, so they are never merged."""
    n = _norm(name)
    if not n or start_date in (None, ""):
        return None
    a = _norm(address)
    return f"{n}|{a}|{start_date}|{start_time or ''}"


def series_key(name: str | None, address: str | None) -> str | None:
    """Key grouping a recurring series (same name + venue), or ``None``."""
    n = _norm(name)
    if not n:
        return None
    return f"{n}|{_norm(address)}"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _load_event_rows(session) -> list[dict[str, Any]]:
    """One row per (event entity × its earliest dated schedule)."""
    rows: list[dict[str, Any]] = []
    q = (
        session.query(Entity, Schedule, Location)
        .join(Schedule, Schedule.entity_id == Entity.id)
        .outerjoin(Location, Location.entity_id == Entity.id)
        .filter(
            Entity.is_active.is_(True),
            Entity.entity_type == EVENT_TYPE,
            Schedule.start_date.isnot(None),
        )
    )
    # keep the earliest schedule per entity (deterministic occurrence key)
    best: dict[str, dict[str, Any]] = {}
    for ent, sch, loc in q.all():
        address = (getattr(loc, "address", None) if loc else None) or ""
        rec = {
            "entity_id": ent.id,
            "name": ent.name,
            "slug": ent.slug,
            "address": address,
            "start_date": str(sch.start_date) if sch.start_date else None,
            "start_time": str(sch.start_time) if sch.start_time else None,
            "recurrence_rule": sch.recurrence_rule,
            "created_at": ent.created_at,
        }
        prev = best.get(ent.id)
        if prev is None or (rec["start_date"] or "") < (prev["start_date"] or ""):
            best[ent.id] = rec
    rows.extend(best.values())
    return rows


def _score(row: dict[str, Any]) -> tuple:
    """Survivor preference: a recurrence_rule (canonical series row) first, then
    the oldest created (most likely the original import). Higher tuple kept."""
    return (1 if row.get("recurrence_rule") else 0, -_created_ord(row), )


def _created_ord(row: dict[str, Any]) -> float:
    c = row.get("created_at")
    try:
        return c.timestamp()
    except Exception:
        return 0.0


def plan(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """``(deactivate_rows, series_clusters)``.

    ``deactivate_rows`` are exact-duplicate occurrences beyond the survivor in
    each exact-key cluster. ``series_clusters`` are same-name+venue groups with
    >1 distinct date (recurring series) — reported only, never deactivated."""
    by_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_series: dict[str, set[str]] = defaultdict(set)
    by_series_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        ek = exact_occurrence_key(r["name"], r["address"], r["start_date"], r["start_time"])
        if ek is not None:
            by_exact[ek].append(r)
        sk = series_key(r["name"], r["address"])
        if sk is not None:
            by_series[sk].add(r["start_date"] or "")
            by_series_rows[sk].append(r)

    deactivate: list[dict[str, Any]] = []
    for members in by_exact.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (_score(r), str(r["entity_id"])), reverse=True)
        deactivate.extend(ordered[1:])  # keep the top, drop exact-duplicate rest

    series = [
        by_series_rows[sk]
        for sk, dates in by_series.items()
        if len([d for d in dates if d]) > 1
    ]
    return deactivate, series


def run(*, apply: bool = False, confirm: bool = False, csv_path: Path | None = None,
        snapshot_dir: Path | None = None, session=None) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        rows = _load_event_rows(session)
        counts["dated_event_rows"] = len(rows)
        deactivate, series = plan(rows)
        counts["exact_duplicates_to_deactivate"] = len(deactivate)
        counts["recurring_series_clusters"] = len(series)

        print("event dedup plan:")
        print(f"  {len(deactivate):>5}  EXACT-duplicate occurrences to deactivate (reversible)")
        print(f"  {len(series):>5}  recurring-series clusters (REPORTED ONLY — not touched)")
        print(f"  {counts['dated_event_rows']:>5}  dated event rows scanned\n")
        for r in deactivate[:25]:
            print(f"  drop  {r['name'][:40]:40s} {r['start_date']} {r['start_time'] or ''}")
        if series:
            print("\n  recurring series (for your review — collapse into one card is a product call):")
            for cl in sorted(series, key=lambda c: -len(c))[:15]:
                print(f"    {len(cl):3d}x  {cl[0]['name'][:48]}")

        if csv_path:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["kind", "entity_id", "name", "slug", "start_date", "start_time", "address"])
                for r in deactivate:
                    w.writerow(["exact-dup-deactivate", r["entity_id"], r["name"], r["slug"],
                                r["start_date"], r["start_time"], r["address"]])
                for cl in series:
                    for r in cl:
                        w.writerow(["series-review", r["entity_id"], r["name"], r["slug"],
                                    r["start_date"], r["start_time"], r["address"]])
            print(f"\nwrote plan to {csv_path}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        ids = [r["entity_id"] for r in deactivate]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap = snapshot_dir / f"event_dedup_snapshot_{stamp}.json"
        snap.write_text(json.dumps([{"entity_id": i, "is_active": True} for i in ids], indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap} ({len(ids)} ids)")
        changed = 0
        for ent in session.query(Entity).filter(Entity.id.in_(ids)):
            ent.is_active = False
            changed += 1
        session.commit()
        counts["deactivated"] = changed
        print(f"\nAPPLIED — {changed} exact-duplicate event occurrences deactivated.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dedup exact-duplicate event occurrences (dry-run by default).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, csv_path=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
