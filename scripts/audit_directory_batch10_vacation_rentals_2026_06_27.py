"""Batch-10 read-only probe: vacation rentals mis-filed under Hotels & Motels.

READ-ONLY. SELECT-only, ZERO writes. Classifies every active listing whose
PRIMARY leaf is `hotels-and-motels` into:

  * VR      — short-term vacation rental (re-home -> `vacation-rentals` leaf).
              Signal: an OTA/booking website (vrbo/airbnb/expedia/bluepillow/
              despegar/booking/tripadvisor), OR (no street number in the address
              AND a descriptive "rental home" name token).
  * HOTEL   — looks like a real hotel/motel (street number + chain/motel/inn/
              resort/suites keyword). Left in place.
  * OOA     — out-of-area (is_local=False, or a known OOA name). Retract candidate.
  * REVIEW  — neither signal fired; needs a human eyeball.

Counts + capped samples per bucket. Nothing is moved or retracted.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch10_vacation_rentals_2026_06_27.py --sample 60
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

_OTA_RE = re.compile(
    r"(vrbo|airbnb|expedia|bluepillow|despegar|booking\.com|tripadvisor|hotels\.com|"
    r"hopper|agoda|trip\.com|vacasa|evolve|furnishedfinder)", re.IGNORECASE)
_STREET_NUM_RE = re.compile(r"\b\d{2,6}\s+[A-Za-z]")  # "1420 McCulloch"
# descriptive vacation-rental name tells
_VR_NAME_RE = re.compile(
    r"(\bBR\b|\bbed(room)?\b|retreat|oasis|villa|getaway|casita|hideaway|paradise|"
    r"poolside|lakeview|lake view|w/\s|private pool|home|house|condo|cottage|"
    r"luxury|escape|haven|!|\bmi to\b)", re.IGNORECASE)
_HOTEL_NAME_RE = re.compile(
    r"(hotel|motel|inn|resort|suites|lodge|hampton|holiday|hilton|marriott|"
    r"days inn|super 8|travelodge|quality|comfort|nautical|heat|london bridge|"
    r"island|beachcomber|hampton|best western|microtel|motel 6|studio 6)",
    re.IGNORECASE)
_OOA_NAMES = ("black meadow", "havasu springs", "parker", "kingman", "needles")


def _domain(url: str | None) -> str:
    if not url:
        return ""
    m = re.search(r"https?://([^/]+)", url)
    return (m.group(1) if m else url)[:30]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    args = ap.parse_args()
    cap = max(args.sample, 1)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 88)
    print("BATCH-10 VACATION-RENTAL CLASSIFIER PROBE  (READ-ONLY — no rows written)")
    print("=" * 88)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        hotels = db.query(Category).filter(Category.slug == _HOTELS_SLUG).one()
        prim_ent_ids = {
            ec.entity_id for ec in db.query(EntityCategory).filter(
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
            if e.id in prim_ent_ids
        ]

        buckets: dict[str, list[tuple]] = {"VR": [], "HOTEL": [], "OOA": [], "REVIEW": []}
        for e in ents:
            provs = sorted(provs_by_entity.get(e.id, []),
                           key=lambda p: -(p.google_review_count or 0))
            pr = provs[0] if provs else None
            addr = (pr.address if pr else "") or ""
            site = (pr.website if pr else "") or ""
            rev = (pr.google_review_count or 0) if pr else 0
            local = pr.is_local if pr else None
            name = e.name or ""

            has_num = bool(_STREET_NUM_RE.search(addr))
            ota = bool(_OTA_RE.search(site)) or bool(_OTA_RE.search(addr))
            vr_name = bool(_VR_NAME_RE.search(name))
            hotel_name = bool(_HOTEL_NAME_RE.search(name))
            ooa = local is False or any(n in name.lower() for n in _OOA_NAMES) \
                or any(n in addr.lower() for n in _OOA_NAMES)

            row = (name[:40], addr[:34], _domain(site), rev, has_num)
            if ooa:
                buckets["OOA"].append(row)
            elif ota or (not has_num and vr_name):
                buckets["VR"].append(row)
            elif has_num and hotel_name:
                buckets["HOTEL"].append(row)
            else:
                buckets["REVIEW"].append(row)

        print(f"hotels-and-motels active primary listings: {len(ents)}")
        for b in ("VR", "HOTEL", "OOA", "REVIEW"):
            print(f"  {b:7s}: {len(buckets[b])}")
        print()
        for b in ("VR", "OOA", "REVIEW", "HOTEL"):
            rows = buckets[b]
            print("-" * 88)
            print(f"[{b}]  ({len(rows)})")
            for name, addr, dom, rev, has_num in sorted(rows, key=lambda r: (r[4], -r[3])):
                flag = "num" if has_num else "NOADDR"
                print(f"   rev={rev:>4d} {flag:6s} {name:40s} | {addr:34s} | {dom}")
                if rows.index((name, addr, dom, rev, has_num)) + 1 >= cap:
                    print(f"   … (capped at {cap})")
                    break
        print("-" * 88)
        print("\nREAD-ONLY. Proposed: re-home VR -> vacation-rentals; retract OOA; "
              "REVIEW needs your eyeball before anything moves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
