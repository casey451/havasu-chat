"""Backfill: clean cost tokens bled into existing Event.location_name (DRY-RUN default; --apply gated).

Companion to the ingest fix (app/contrib/event_ingest._location_name now calls
strip_cost_prefix). That guard only protects NEW ingests; this repairs the rows
already stored as e.g. ``location_name = "$45 - Aquatic Center"``.

For each LIVE event whose ``strip_cost_prefix(location_name)`` differs from the
stored value:
  * the cleaned venue replaces ``location_name`` (a pure-price venue strips to
    nothing -> the "Lake Havasu City" default, matching the ingest path);
  * if ``Event.cost`` is empty, the PEELED price (extract_cost_from_text on the
    original venue) is written to ``cost`` so the "$45" lands there instead of
    being dropped.

DEFAULT IS DRY-RUN: prints the count + a 25-row before/after sample and writes
nothing. ``--apply`` is required to mutate; it snapshots the affected rows first.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply. The agent
never runs --apply against prod.

    .venv\\Scripts\\python.exe scripts/backfill_event_venue_cost_bleed_2026_06_28.py
    .venv\\Scripts\\python.exe scripts/backfill_event_venue_cost_bleed_2026_06_28.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.event_record import extract_cost_from_text, strip_cost_prefix  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

# Matches the ingest fallback when a venue strips to nothing (event_ingest).
_CITY_DEFAULT = "Lake Havasu City"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill cost-bled event venues (dry-run by default).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BACKFILL EVENT VENUE COST-BLEED — {mode}")
    print("=" * 80)
    print(f"DB target: …@{_sanitized_target()}\n")

    with SessionLocal() as db:
        live = db.query(Event).filter(Event.status == "live").all()
        planned: list[tuple[Event, str, str, str | None, str | None]] = []
        for ev in live:
            old = ev.location_name or ""
            cleaned = strip_cost_prefix(old)
            if cleaned == old:
                continue  # not the bug shape (no leading price+separator)
            new_venue = cleaned or _CITY_DEFAULT
            new_cost = ev.cost
            if not (ev.cost or "").strip():
                peeled = extract_cost_from_text(old)
                if peeled:
                    new_cost = peeled
            planned.append((ev, old, new_venue, ev.cost, new_cost))

        print(f"live events scanned:        {len(live)}")
        print(f"cost-bled rows to fix:      {len(planned)}\n")
        print(f"{'before location_name':38s} -> {'after':26s} | cost: before -> after")
        print("-" * 92)
        for ev, old, new_venue, old_cost, new_cost in planned[:25]:
            cost_clause = (f"{old_cost!r} -> {new_cost!r}"
                           if old_cost != new_cost else f"{old_cost!r} (unchanged)")
            print(f"  {old[:36]:36s} -> {new_venue[:24]:24s} | {cost_clause}")
        if len(planned) > 25:
            print(f"  … +{len(planned) - 25} more")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply --confirm (after approval).")
            return 0
        if not args.confirm:
            print(f"REFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return 0

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap = _ROOT / f"backfill_cost_bleed_snapshot_{stamp}.json"
        snap.write_text(
            json.dumps(
                [{"event_id": ev.id, "location_name": old, "cost": old_cost}
                 for ev, old, _nv, old_cost, _nc in planned],
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"rollback snapshot: {snap} ({len(planned)} rows)")
        for ev, _old, new_venue, _old_cost, new_cost in planned:
            ev.location_name = new_venue
            ev.cost = new_cost
        db.commit()
        print(f"\nAPPLIED — cleaned {len(planned)} cost-bled venues. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
