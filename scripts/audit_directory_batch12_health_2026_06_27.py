"""Batch-12 read-only probe: de-bury specialists from Primary Care + pharmacy dupes.

READ-ONLY. SELECT-only, ZERO writes. The destination leaves already exist
(senior-care-and-assisted-living, dermatology-and-skin, hearing-and-audiology,
urgent-care-and-er, physical-therapy, personal-training), so the audit's "Doctors
is a 174-row dumping ground" is fixable as a re-home, not a leaf-create.

Sections:
  1. PRIMARY-CARE MISFILES — members of `primary-care` whose name signals a
     specialty leaf. Tagged SENIOR / DERM / HEARING / URGENT / PT / TRAINER.
     (untagged primary-care members are left alone.)
  2. PHARMACY DUPES — Walgreens / CVS clusters (real + "...Pharmacy" / COVID-testing mirror).
  3. RETRACT CANDIDATES — literal placeholders / blogs / services-not-businesses.

Nothing is moved or retracted.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch12_health_2026_06_27.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
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

_SPECIALTY = (
    ("SENIOR", re.compile(
        r"(nursing|assisted living|senior|haven health|vista pointe|reflections|"
        r"the views|comfort keepers|claremont|heritage bridge|serenity|lake house|"
        r"neighbors|gems|memory care|hospice|home health|home care|in-home)", re.I)),
    ("DERM", re.compile(r"(dermatolog|skin & cancer|skin and cancer|frontier skin|thomas derm)", re.I)),
    ("HEARING", re.compile(r"(hearing|audiolog|miracle-?ear|cleartone|audibel|soundpoint)", re.I)),
    ("URGENT", re.compile(r"(urgent care|nextcare|truecare|walk-?in clinic)", re.I)),
    ("PT", re.compile(r"(physical therapy|fyzical|pro therapy|rehab(ilitation)?\b)", re.I)),
    ("TRAINER", re.compile(r"(personal train|\btrainer\b|phillipsfit|fitness coach)", re.I)),
)
_TARGET_SLUG = {
    "SENIOR": "senior-care-and-assisted-living",
    "DERM": "dermatology-and-skin",
    "HEARING": "hearing-and-audiology",
    "URGENT": "urgent-care-and-er",
    "PT": "physical-therapy",
    "TRAINER": "personal-training",
}
_RETRACT_RE = re.compile(
    r"^(physical therapy|mychiroblog|covid-?19 drive-?thru|covid testing|"
    r"edify and elevate)$", re.I)
_DUPE_BRANDS = ("walgreens", "cvs")


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 84)
    print("BATCH-12 HEALTH DE-BURY / DEDUP PROBE  (READ-ONLY — no rows written)")
    print("=" * 84)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        cat_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        def members(slug: str) -> list[Entity]:
            cat = cat_by_slug[slug]
            ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
            return [e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place"))).all() if e.id in ids]

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        # 1. PRIMARY-CARE MISFILES
        pc = members("primary-care")
        print(f"primary-care active members: {len(pc)}\n")
        print("-" * 84)
        print("1. SPECIALTY MISFILES IN PRIMARY-CARE (-> existing specialty leaf)")
        buckets: dict[str, list[Entity]] = defaultdict(list)
        for e in pc:
            for tag, rx in _SPECIALTY:
                if rx.search(e.name or ""):
                    buckets[tag].append(e)
                    break
        total_mis = 0
        for tag, _rx in _SPECIALTY:
            rows = buckets.get(tag, [])
            total_mis += len(rows)
            print(f"\n  {tag} -> {_TARGET_SLUG[tag]}  ({len(rows)})")
            for e in sorted(rows, key=lambda e: -rev(e)):
                print(f"     rev={rev(e):>4d}  {e.name[:54]}")
        print(f"\n  total primary-care misfiles: {total_mis}")

        # 2. PHARMACY DUPES
        print("\n" + "-" * 84)
        print("2. PHARMACY DUPES (walgreens / cvs clusters)")
        ph = members("pharmacies")
        for brand in _DUPE_BRANDS:
            rows = [e for e in ph if brand in (e.name or "").lower()]
            print(f"\n  {brand}  ({len(rows)})")
            for e in sorted(rows, key=lambda e: -rev(e)):
                pr = sorted(provs_by_entity.get(e.id, []), key=lambda p: -(p.google_review_count or 0))
                addr = (pr[0].address[:28] if pr and pr[0].address else "")
                print(f"     rev={rev(e):>4d} src={e.source[:12]:12s} {e.name[:34]:34s} | {addr}")

        # 3. RETRACT CANDIDATES
        print("\n" + "-" * 84)
        print("3. RETRACT CANDIDATES (placeholder / blog / service-not-business)")
        for slug in ("primary-care", "chiropractic", "physical-therapy", "pharmacies"):
            for e in members(slug):
                if _RETRACT_RE.match((e.name or "").strip()):
                    print(f"     [{slug:16s}] {e.name[:40]}  (rev={rev(e)})")
        print("\n" + "=" * 84)
        print("READ-ONLY. Proposed: re-home misfiles -> specialty leaves; dedup pharmacy "
              "mirrors; retract the placeholders. Your eyeball before apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
