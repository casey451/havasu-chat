"""Apply the 2026-06-30 search-audit Phase-2 data ops (dry-run default; gated).

Scope = the CLEAR-CUT, reversible subset only (Casey-approved 2026-06-30):

  2A-remove   Deactivate the active "Lake Havasu Marine Association Designated
              Operator Program" row — a safety program, not a rental business.
  2A-reclass  Re-home two miscategorized listings by repointing their PRIMARY
              entity_categories link (the leaf pages read that link):
                * Lake Havasu VA Clinic: urgent-care-and-er -> government-and-mvd
                  (swap the is_primary flag onto the government link it already
                  carries).
                * Capt Kenne Charters LLC: boat-and-watercraft-rentals ->
                  fishing-charters-and-guides.
  2B-address  Neutralize the "Go Lake Havasu Visitor Center" placeholder address
              so it never renders as a business location: null it on Provider
              and Location. Businesses stay ACTIVE (display-only fix).

DELIBERATELY NOT here (need a separate decision — see the session report):
  * Scuba Training & Technology reclass — no `scuba` destination leaf exists.
  * Copper Canyon — already on beaches-and-swim-areas (fine for a cove); its
    only issue is the legacy Provider.category='boat_rental' chat label.
  * Islander / The Spot / Capt Kenne shadow-row DEDUP.
  * 2C backfill of verified-missing businesses (Havasu Parasail, VR Escape...).
  * lat/lng of the placeholder rows (still point at the visitor center).

Targets the 2A rows by explicit prod entity id WITH a name guard, so running
against a different DB (mismatched id) SKIPS rather than mutating the wrong row.
Every change is snapshotted to scripts/_snapshots/ for a full manual undo.

Usage:
    .venv\\Scripts\\python.exe scripts/apply_search_data_ops_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/apply_search_data_ops_2026_06_30.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import re
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
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"go\s+lake\s+havasu\s+visitor\s+center", re.IGNORECASE)
_SNAP_DIR = _ROOT / "scripts" / "_snapshots"

# 2A deactivation — (entity_id, name-guard substring).
_DEACTIVATE = ("6372a690-ee2e-4d6d-96cb-abea8a4609d3", "designated operator program")

# 2A reclass — (entity_id, name-guard, from-leaf-slug, to-leaf-slug, note).
_RECLASS: tuple[tuple[str, str, str, str, str], ...] = (
    ("3899931b-4046-46f7-a8da-d1897457f73a", "va clinic",
     "urgent-care-and-er", "government-and-mvd", "VA clinic, not urgent care"),
    ("75a51c0d-af64-4211-a8fc-1a31fbac0dcf", "capt kenne",
     "boat-and-watercraft-rentals", "fishing-charters-and-guides",
     "fishing charter, not a boat rental"),
)


def _leaf_by_slug(db) -> dict[str, Category]:
    return {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}


def _plan_deactivate(db) -> dict | None:
    eid, guard = _DEACTIVATE
    ent = db.get(Entity, eid)
    if ent is None or guard not in (ent.name or "").lower():
        print(f"  SKIP deactivate: entity {eid} missing or name mismatch")
        return None
    provs = db.query(Provider).filter(Provider.entity_id == eid).all()
    return {
        "entity_id": eid,
        "name": ent.name,
        "was_active": ent.is_active,
        "provider_ids": [p.id for p in provs],
        "provider_was_active": {p.id: p.is_active for p in provs},
    }


def _plan_reclass(db, leaf_by_slug) -> list[dict]:
    plans: list[dict] = []
    for eid, guard, from_slug, to_slug, note in _RECLASS:
        ent = db.get(Entity, eid)
        if ent is None or guard not in (ent.name or "").lower():
            print(f"  SKIP reclass: entity {eid} missing or name mismatch")
            continue
        target = leaf_by_slug.get(to_slug)
        if target is None:
            print(f"  SKIP reclass '{ent.name}': target leaf {to_slug!r} not found")
            continue
        prim = (
            db.query(EntityCategory)
            .filter(EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True))
            .one_or_none()
        )
        if prim is None:
            print(f"  SKIP reclass '{ent.name}': no primary entity_categories row")
            continue
        cur = db.get(Category, prim.category_id)
        if cur is not None and cur.id == target.id:
            print(f"  OK reclass '{ent.name}': already on {to_slug}")
            continue
        existing = (
            db.query(EntityCategory)
            .filter(EntityCategory.entity_id == eid, EntityCategory.category_id == target.id)
            .one_or_none()
        )
        plans.append({
            "entity_id": eid,
            "name": ent.name,
            "prim_ec_id": prim.id,
            "from_category_id": prim.category_id,
            "from_slug": cur.slug if cur else "(none)",
            "to_category_id": target.id,
            "to_slug": to_slug,
            "existing_ec_id": existing.id if existing else None,
            "mode": "swap-flag" if existing else "repoint",
            "note": note,
        })
    return plans


def _plan_addresses(db) -> dict:
    prov_hits = [
        p for p in db.query(Provider).all() if _PLACEHOLDER_RE.search(p.address or "")
    ]
    loc_hits = [
        loc for loc in db.query(Location).all()
        if _PLACEHOLDER_RE.search((loc.address_normalized or "") + " " + (loc.address or ""))
    ]
    return {
        "providers": [{"id": p.id, "entity_id": p.entity_id, "old_address": p.address}
                      for p in prov_hits],
        "locations": [{"id": loc.id, "entity_id": loc.entity_id,
                       "old_address": loc.address, "old_address_normalized": loc.address_normalized}
                      for loc in loc_hits],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply search-audit Phase-2 data ops (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE the changes (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required alongside --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"SEARCH-AUDIT PHASE-2 DATA OPS — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = _leaf_by_slug(db)
        deact = _plan_deactivate(db)
        reclass = _plan_reclass(db, leaf_by_slug)
        addrs = _plan_addresses(db)

        print("\n--- 2A remove (deactivate) ---")
        if deact:
            print(f"  DEACTIVATE  {deact['name'][:50]} "
                  f"(+{len(deact['provider_ids'])} provider rows)")
        print("\n--- 2A reclass (repoint primary entity_categories) ---")
        for p in reclass:
            print(f"  MOVE  {p['name'][:34]:34s} | {p['from_slug']:26s} -> "
                  f"{p['to_slug']:26s} | {p['mode']} | {p['note']}")
        print("\n--- 2B neutralize placeholder address ---")
        print(f"  provider rows: {len(addrs['providers'])}   "
              f"location rows: {len(addrs['locations'])}")

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tag = "apply" if writing else "dryrun"
        snap_path = _SNAP_DIR / f"search_data_ops_2026_06_30_snapshot_{tag}_{stamp}.json"
        snap = {"generated_utc": stamp, "db": redacted,
                "deactivate": deact, "reclass": reclass, "addresses": addrs}
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {snap_path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written to the DB. "
                  "Re-run with --apply --confirm (after approval).")
            return 0

        # ---- write ----
        if deact:
            ent = db.get(Entity, deact["entity_id"])
            if ent is not None:
                ent.is_active = False
            for pid in deact["provider_ids"]:
                pr = db.get(Provider, pid)
                if pr is not None:
                    pr.is_active = False
        for p in reclass:
            prim = db.get(EntityCategory, p["prim_ec_id"])
            if prim is None:
                continue
            if p["existing_ec_id"] is not None:
                prim.is_primary = False
                other = db.get(EntityCategory, p["existing_ec_id"])
                if other is not None:
                    other.is_primary = True
            else:
                prim.category_id = p["to_category_id"]
        for row in addrs["providers"]:
            pr = db.get(Provider, row["id"])
            if pr is not None:
                pr.address = None
        for row in addrs["locations"]:
            loc = db.get(Location, row["id"])
            if loc is not None:
                loc.address = None
                loc.address_normalized = None
        db.commit()
        print("\nAPPLIED. Reversible from the snapshot above.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
