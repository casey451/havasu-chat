"""Batch-10: split vacation rentals out of Hotels & Motels (dry-run default; --apply gated).

Directory-audit follow-up. The `hotels-and-motels` leaf is ~half short-term
vacation-rental homes (the `vacation-rentals` leaf already exists — this is a
re-home, not a new leaf). Plus one out-of-area resort to retract.

Classifier (tightened after the probe found 2 bugs):
  is_real_hotel = has a street number AND name matches a hotel/motel/inn/resort/
                  suites/lodge keyword (the KEEP guard — protects real chains
                  whose OTA-looking domain like choicehotels.com tripped the
                  earlier regex).
  is_vr         = primary leaf is hotels-and-motels AND NOT is_real_hotel AND
                  (an OTA/booking site  OR  a descriptive rental-home name  OR
                   no street number).
Re-home = repoint the primary entity_categories row to `vacation-rentals`
(swap is_primary flag if it's already a secondary link). Reversible.

OOA retract = Entity.is_active=False + deactivate providers, for hotels-leaf rows
that are is_local=False or addressed to Parker/Kingman/Needles. Reversible.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/rehome_vacation_rentals_batch10_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_vacation_rentals_batch10_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
import re
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

_HOTELS_SLUG = "hotels-and-motels"
_VR_SLUG = "vacation-rentals"

_STREET_NUM_RE = re.compile(r"\b\d{2,6}\s+[A-Za-z]")
# Explicit OTA/booking hosts (NO bare "hotels.com" — that matched chain domains).
_OTA_RE = re.compile(
    r"(vrbo|airbnb|expedia|bluepillow|despegar|booking\.com|rentalsunited|"
    r"vacasa|evolve|furnishedfinder|agoda|express-getaway|avrhavasu|"
    r"havasuvacationrentals)", re.IGNORECASE)
_VR_NAME_RE = re.compile(
    r"(retreat|oasis|villa|getaway|hideaway|casita|\bmi to\b|w/\s|home w/|"
    r"poolside|private pool|hot tub|swim spa|sleeps|game room|fire ?pit|"
    r"putting green|pet-friendly|vacation rental|xanadu|hacienda|home in la|"
    r"home with|home:|house with|luxury home|mtn view|water views|!)",
    re.IGNORECASE)
# KEEP guard: a real hotel/motel keyword. Note: NO bare "london bridge".
_HOTEL_NAME_RE = re.compile(
    r"(hotel|motel|\binn\b|resort|suites|lodge|hampton|holiday inn|hilton|"
    r"marriott|days inn|super 8|travelodge|quality|comfort|rodeway|knights|"
    r"nautical|studio 6|microtel|best western|island suites|olina|sway|home2|"
    r"queens bay|hidden palms|lake place|beachcomber|islander|lakeside|"
    r"twin palms|havasu suites|havasu dunes|havasu inn)", re.IGNORECASE)
_OOA_RE = re.compile(r"\b(parker|kingman|needles|topock)\b", re.IGNORECASE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-10 vacation-rental split (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 84)
    print(f"BATCH-10 VACATION-RENTAL SPLIT — {mode}")
    print("=" * 84)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        hotels = db.query(Category).filter(Category.slug == _HOTELS_SLUG).one()
        vr = db.query(Category).filter(Category.slug == _VR_SLUG).one()
        prim_by_ent = {
            ec.entity_id: ec for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == hotels.id,
                EntityCategory.is_primary.is_(True),
            ).all()
        }
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        ents = [
            e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            ).all()
            if e.id in prim_by_ent
        ]

        vr_moves: list[tuple[Entity, EntityCategory, EntityCategory | None]] = []
        ooa: list[Entity] = []
        kept = 0
        for e in ents:
            provs = sorted(provs_by_entity.get(e.id, []),
                           key=lambda p: -(p.google_review_count or 0))
            pr = provs[0] if provs else None
            addr = (pr.address if pr else "") or ""
            site = (pr.website if pr else "") or ""
            local = pr.is_local if pr else None
            name = e.name or ""

            if local is False or _OOA_RE.search(addr) or _OOA_RE.search(name):
                ooa.append(e)
                continue
            has_num = bool(_STREET_NUM_RE.search(addr))
            is_real_hotel = has_num and bool(_HOTEL_NAME_RE.search(name))
            is_vr = (not is_real_hotel) and (
                bool(_OTA_RE.search(site)) or bool(_OTA_RE.search(addr))
                or bool(_VR_NAME_RE.search(name)) or not has_num
            )
            if is_vr:
                existing = db.query(EntityCategory).filter(
                    EntityCategory.entity_id == e.id,
                    EntityCategory.category_id == vr.id,
                ).one_or_none()
                vr_moves.append((e, prim_by_ent[e.id], existing))
            else:
                kept += 1

        print(f"hotels-and-motels active: {len(ents)}   "
              f"-> VR: {len(vr_moves)}   OOA retract: {len(ooa)}   kept hotels: {kept}\n")
        print("--- re-home to vacation-rentals ---")
        for e, _ec, existing in sorted(vr_moves, key=lambda t: t[0].name.lower()):
            m = "swap-flag" if existing is not None else "repoint"
            print(f"  VR    [{m:9s}] {e.name[:58]}")
        print("\n--- retract out-of-area ---")
        for e in ooa:
            print(f"  DROP  {e.name[:58]}")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot ---")
        for e, ec, existing in vr_moves:
            print(f"  REHOME {e.id} ec={ec.id} {ec.category_id} -> {vr.id} "
                  f"({'swap' if existing else 'repoint'})")
            if existing is not None:
                ec.is_primary = False
                existing.is_primary = True
            else:
                ec.category_id = vr.id
        for e in ooa:
            pids = [p.id for p in provs_by_entity.get(e.id, []) if p.is_active]
            print(f"  RETRACT {e.id} '{e.name[:40]}' providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: re-homed {len(vr_moves)} to vacation-rentals, "
              f"retracted {len(ooa)} OOA. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
