"""Retire 3 duplicate backfill inserts the nightly integrity check caught (gated).

The 2026-07-01 Phase-4/5 backfills inserted three operators whose EXISTING rows
hid behind name variants the recon patterns missed — caught minutes later by
the Phase-9 same-phone check (its first live save):

  * "VIP Cabana Boats" (insert)            = "Cabana Boat Rentals" (go_lake_havasu,
    has address, already on boat-and-watercraft-rentals)
  * "Lake Havasu RV & Boat Rentals" (ins.) = "Lake Havasu RV and Boat Rentals"
    (google_places, has address) — the survivor's PRIMARY moves to
    rv-sales-and-service per the approved [ASK #5] fold (boat leaf kept as a
    secondary link)
  * "Havasu Rental Homes" (insert)         = "Lake Havasu Property Management"
    (google_places, 4.8 stars / 508 reviews) — the plan itself listed them as one
    company ("Lake Havasu PM / Havasu Rental Homes", same phone)

Fix: deactivate the three fresh inserts (they carry the backfill source tags —
this IS the documented undo path), repoint the RV survivor's primary.

Usage:
    .venv\\Scripts\\python.exe scripts/fix_backfill_dup_inserts_2026_07_02.py
    .venv\\Scripts\\python.exe scripts/fix_backfill_dup_inserts_2026_07_02.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

_SNAP_DIR = _ROOT / "scripts" / "_snapshots"

# (exact provider_name of the fresh insert, required source substring)
_RETIRE: tuple[tuple[str, str], ...] = (
    ("VIP Cabana Boats", "rentals_backfill_2026_07_01"),
    ("Lake Havasu RV & Boat Rentals", "rentals_backfill_2026_07_01"),
    ("Havasu Rental Homes", "search_gaps_backfill_2026_07_01"),
)

# Survivor primary repoint per the approved plan.
_SURVIVOR_REHOME = ("Lake Havasu RV and Boat Rentals", "rv-sales-and-service")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retire dup backfill inserts (gated).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"DUP-INSERT FIX — {'APPLY' if writing else 'DRY RUN'} — …@{redacted}\n")

    snap: dict = {"generated_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  "retired": [], "rehomed": None}
    with SessionLocal() as db:
        retire_rows = []
        for name, src in _RETIRE:
            row = db.query(Provider).filter(
                Provider.provider_name == name, Provider.is_active.is_(True)).first()
            if row is None or src not in (row.source or ""):
                print(f"  SKIP  {name!r}: not found / source mismatch")
                continue
            print(f"  DEACTIVATE  {name!r} (dup of the existing name-variant row)")
            retire_rows.append(row)
        snap["retired"] = [r.id for r in retire_rows]

        surv_name, target_slug = _SURVIVOR_REHOME
        surv = db.query(Provider).filter(
            Provider.provider_name == surv_name, Provider.is_active.is_(True)).first()
        target = db.query(Category).filter(
            Category.slug == target_slug, Category.level == 1).first()
        prim = None
        if surv is not None and surv.entity_id and target is not None:
            prim = db.query(EntityCategory).filter_by(
                entity_id=surv.entity_id, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            if cur is not None and cur.slug == target_slug:
                print(f"  OK  {surv_name!r}: already on {target_slug}")
                prim = None
            else:
                print(f"  MOVE  {surv_name!r} | {(cur.slug if cur else '(none)')} -> "
                      f"{target_slug} (old membership kept as secondary)")
                snap["rehomed"] = {"entity_id": surv.entity_id,
                                   "from": cur.slug if cur else None, "to": target_slug}
        else:
            print(f"  SKIP rehome: {surv_name!r} or leaf {target_slug!r} missing")

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        tag = "apply" if writing else "dryrun"
        path = _SNAP_DIR / f"fix_dup_inserts_2026_07_02_snapshot_{tag}_{snap['generated_utc']}.json"
        path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot: {path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written.")
            return 0

        for row in retire_rows:
            row.is_active = False
            ent = db.get(Entity, row.entity_id) if row.entity_id else None
            if ent is not None:
                ent.is_active = False
        if prim is not None and target is not None and surv is not None:
            prim.is_primary = False
            existing = db.query(EntityCategory).filter_by(
                entity_id=surv.entity_id, category_id=target.id).one_or_none()
            if existing is not None:
                existing.is_primary = True
            else:
                db.add(EntityCategory(entity_id=surv.entity_id,
                                      category_id=target.id, is_primary=True))
        db.commit()
        print("\nAPPLIED.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
