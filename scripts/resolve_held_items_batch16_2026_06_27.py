"""Batch-16: resolve web-verified HELD judgment items (dry-run default; --apply gated).

Directory-audit follow-up. Each action below was confirmed by a web check on
2026-06-28 (operator delegated "look into it and do what you think is best"):

  MOVE:
    Quick Stop Title and Registration  nonprofits -> government-and-mvd
      (a real for-profit MVD/registration service; not a nonprofit; MVD leaf is
       the discovery-intent home)

  FIELD FIX:
    Havasu Tropical Oasis Floating Rentals  address -> "Lake Havasu City, AZ 86403"
      (real floating-rental biz w/ NO street address; "Bobbi Jo 303.909.0056" is a
       booking contact, not an address — golakehavasu.com directory)

  RETRACT (web-verified duplicate / phantom):
    TNT Roofing            (shares 928-453-3925 w/ Dynamite Roofing; 0-rev shadow;
                            Dynamite is the active BBB-rated brand — keep Dynamite)
    Goodwill 3273 Maricopa (same facility as 3269 Maricopa "Retail Store and
                            Donation Center"; keep the higher-reviewed 3269)
    Sweet Peas & Sage      (the real one is a PHOENIX florist; no LHC storefront at
                            2129 McCulloch; 0-rev phantom under Attorneys)
    The Broken Yolk        (Broken Yolk Cafe is a single LHC location at 440 El
                            Camino Way; this ★1 row is the mirror — keep the cafe)

STILL HELD (not resolved here): Lakeside Appliances (possibly defunct — unverified),
Greg's Trimmings address, Mohave Roofing (kept both — distinct phone+addr), the
b11 placement calls (Rodeo Grounds, Bill Williams NWR, London Bridge Shops,
Crossroads OHV), Guild Mortgage dup, and the leaf-dependent items (paralegals,
mortgage brokers, Dek X — need new leaves).

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/resolve_held_items_batch16_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/resolve_held_items_batch16_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
import sys
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-16 held-item resolution (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-16 HELD-ITEM RESOLUTION — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        active = db.query(Entity).filter(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(("commercial", "place"))).all()

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        def best_provider(e: Entity) -> Provider | None:
            ps = sorted(provs_by_entity.get(e.id, []), key=lambda p: -(p.google_review_count or 0))
            return ps[0] if ps else None

        def find(pred, label: str) -> Entity | None:
            hits = [e for e in active if pred(e)]
            if len(hits) != 1:
                print(f"  SKIP {label}: {len(hits)} matches")
                return None
            return hits[0]

        def primary_ec(eid: str) -> EntityCategory | None:
            return db.query(EntityCategory).filter(
                EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True)).one_or_none()

        moves: list[tuple[Entity, EntityCategory, Category, EntityCategory | None]] = []
        fixes: list[tuple[Entity, Provider, str, str]] = []
        retracts: list[tuple[Entity, str]] = []

        # --- MOVE: Quick Stop -> government-and-mvd
        qs = find(lambda e: "quick stop" in (e.name or "").lower(), "Quick Stop")
        gov = leaf_by_slug.get("government-and-mvd")
        if qs and gov:
            existing = db.query(EntityCategory).filter(
                EntityCategory.entity_id == qs.id,
                EntityCategory.category_id == gov.id).one_or_none()
            moves.append((qs, primary_ec(qs.id), gov, existing))

        # --- FIELD FIX: Havasu Tropical Oasis address
        to = find(lambda e: "havasu tropical oasis" in (e.name or "").lower(), "Tropical Oasis")
        if to:
            pr = best_provider(to)
            new_addr = "Lake Havasu City, AZ 86403"
            if pr and (pr.address or "").strip() != new_addr:
                fixes.append((to, pr, pr.address or "", new_addr))

        # --- RETRACT: TNT Roofing (expect 0-rev; Dynamite kept)
        tnt = find(lambda e: "tnt roofing" in (e.name or "").lower(), "TNT Roofing")
        if tnt:
            if rev(tnt) == 0:
                retracts.append((tnt, "shadow of Dynamite Roofing (shared phone)"))
            else:
                print(f"  SKIP TNT Roofing: has rev={rev(tnt)} (expected 0)")

        # --- RETRACT: Goodwill 3273 Maricopa (keep 3269)
        def is_gw_3273(e: Entity) -> bool:
            if "goodwill" not in (e.name or "").lower():
                return False
            pr = best_provider(e)
            return bool(pr and "3273" in (pr.address or ""))
        gw = find(is_gw_3273, "Goodwill 3273")
        gw_keep = [e for e in active if "goodwill" in (e.name or "").lower()
                   and (best_provider(e).address if best_provider(e) else "") and "3269" in best_provider(e).address]
        if gw and gw_keep:
            retracts.append((gw, "same facility as 3269 Maricopa (kept)"))
        elif gw:
            print("  SKIP Goodwill 3273: no 3269 sibling found (safety)")

        # --- RETRACT: Sweet Peas & Sage (phantom; expect 0-rev)
        sp = find(lambda e: "sweet peas" in (e.name or "").lower(), "Sweet Peas")
        if sp:
            if rev(sp) == 0:
                retracts.append((sp, "phantom — real Sweet Peas is a Phoenix florist"))
            else:
                print(f"  SKIP Sweet Peas: has rev={rev(sp)} (expected 0)")

        # --- RETRACT: The Broken Yolk (mirror; keep Broken Yolk Cafe)
        tby = find(lambda e: (e.name or "").strip().lower() == "the broken yolk", "The Broken Yolk")
        cafe = [e for e in active if "broken yolk cafe" in (e.name or "").lower()]
        if tby and cafe and rev(cafe[0]) > rev(tby):
            retracts.append((tby, f"mirror of Broken Yolk Cafe (rev {rev(cafe[0])})"))
        elif tby:
            print("  SKIP The Broken Yolk: no higher-reviewed cafe sibling (safety)")

        # --- report
        print(f"\nmoves: {len(moves)}   field-fixes: {len(fixes)}   retracts: {len(retracts)}\n")
        for e, _ec, target, existing in moves:
            m = "swap-flag" if existing is not None else "repoint"
            print(f"  MOVE  {e.name[:40]:40s} -> {target.slug} ({m})")
        for e, _pr, old, new in fixes:
            print(f"  FIX   {e.name[:34]:34s} addr: {old[:32]} -> {new}")
        for e, why in retracts:
            print(f"  DROP  {e.name[:40]:40s} ({why})")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot ---")
        for e, ec, target, existing in moves:
            m = "swap-flag" if existing is not None else "repoint"
            print(f"  MOVE {e.id} ec={ec.id} {ec.category_id} -> {target.id} ({m})")
            if existing is not None:
                ec.is_primary = False
                existing.is_primary = True
            else:
                ec.category_id = target.id
        for e, pr, old, new in fixes:
            print(f"  FIX  {pr.id} address {old!r} -> {new!r}")
            pr.address = new
        for e, _why in retracts:
            pids = [p.id for p in provs_by_entity.get(e.id, []) if p.is_active]
            print(f"  DROP {e.id} '{e.name[:34]}' providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: {len(moves)} moves, {len(fixes)} fixes, {len(retracts)} retracts. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
