"""Batch-12: de-bury specialists from Primary Care + pharmacy dedup (dry-run default; --apply gated).

Directory-audit follow-up. The specialty leaves already exist, so the Primary-Care
dumping ground is fixable as a re-home. CURATED, single-match guarded, restricted
to the named source leaf. Operator-approved 2026-06-28.

  MOVE    = repoint primary entity_categories row to the existing specialty leaf.
  RETRACT = Entity.is_active=False + provider deactivate (same-address pharmacy
            mirrors; literal placeholders / a blog / a bare LLC). Reversible.

HELD for Batch 14+ (need NO new leaf — but dental labs have no clean B2B leaf):
  Foster's / New West / Mohave / Justt dental labs (B2B), Rodney Koenig PAC, etc.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/rehome_health_batch12_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_health_batch12_2026_06_27.py --apply
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

# (source leaf slug, name substring, target leaf slug, note)
_MOVES: tuple[tuple[str, str, str, str], ...] = (
    ("primary-care", "haven health", "senior-care-and-assisted-living", "nursing"),
    ("primary-care", "the views at lake havasu", "senior-care-and-assisted-living", "assisted living"),
    ("primary-care", "comfort keepers", "senior-care-and-assisted-living", "in-home care"),
    ("primary-care", "havasu nursing center", "senior-care-and-assisted-living", "nursing"),
    ("primary-care", "vista pointe", "senior-care-and-assisted-living", "assisted living"),
    ("primary-care", "reflections at oro grande", "senior-care-and-assisted-living", "assisted living"),
    ("primary-care", "regional medical center home health", "senior-care-and-assisted-living", "home health"),
    ("primary-care", "affordable hearing", "hearing-and-audiology", "audiology"),
    ("primary-care", "pro therapy", "physical-therapy", "PT clinic"),
    ("primary-care", "fyzical", "physical-therapy", "PT clinic"),
    ("primary-care", "certified personal training", "personal-training", "trainer, not a doctor"),
    ("primary-care", "phillipsfit", "personal-training", "trainer, not a doctor"),
    ("primary-care", "trevor the trainer", "personal-training", "trainer, not a doctor"),
)

# (source leaf slug, name key, exact?, note)
_RETRACT: tuple[tuple[str, str, bool, str], ...] = (
    ("pharmacies", "walgreens pharmacy", True, "same-addr mirror of Walgreens"),
    ("pharmacies", "covid-19 drive-thru testing at walgreens", True, "a service, not a business"),
    ("pharmacies", "cvs pharmacy", True, "same-addr mirror of CVS"),
    ("primary-care", "edify and elevate", True, "bare LLC, not real health"),
    ("chiropractic", "mychiroblog", True, "a blog, not a clinic"),
    ("physical-therapy", "physical therapy", True, "literal placeholder"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-12 health de-bury/dedup (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-12 HEALTH DE-BURY / DEDUP — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        def leaf_members(slug: str) -> list[Entity]:
            cat = leaf_by_slug[slug]
            ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
            return [e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place"))).all() if e.id in ids]

        cache: dict[str, list[Entity]] = {}

        def src(slug: str) -> list[Entity]:
            if slug not in cache:
                cache[slug] = leaf_members(slug)
            return cache[slug]

        def primary_ec(eid: str) -> EntityCategory | None:
            return db.query(EntityCategory).filter(
                EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True)).one_or_none()

        moves = []
        for sslug, key, tslug, note in _MOVES:
            cands = [e for e in src(sslug) if key in (e.name or "").lower()]
            target = leaf_by_slug.get(tslug)
            if target is None or len(cands) != 1:
                print(f"  SKIP move '{key}': target={tslug} matches={len(cands)}")
                continue
            e = cands[0]
            ec = primary_ec(e.id)
            existing = db.query(EntityCategory).filter(
                EntityCategory.entity_id == e.id, EntityCategory.category_id == target.id).one_or_none()
            moves.append((e, ec, target, existing, note))

        retracts = []
        for sslug, key, exact, note in _RETRACT:
            cands = [e for e in src(sslug)
                     if ((e.name or "").lower() == key if exact else key in (e.name or "").lower())]
            if len(cands) != 1:
                print(f"  SKIP retract '{key}': matches={len(cands)}")
                continue
            retracts.append((cands[0], note))

        print(f"\nmoves: {len(moves)}   retracts: {len(retracts)}\n")
        print("--- re-home ---")
        for e, _ec, target, existing, note in moves:
            m = "swap" if existing is not None else "repoint"
            print(f"  MOVE [{m:7s}] {e.name[:44]:44s} -> {target.slug:32s} ({note})")
        print("\n--- retract ---")
        for e, note in retracts:
            print(f"  DROP  {e.name[:44]:44s} ({note})")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot ---")
        for e, ec, target, existing, _note in moves:
            print(f"  MOVE {e.id} ec={ec.id} {ec.category_id} -> {target.id} "
                  f"({'swap' if existing else 'repoint'})")
            if existing is not None:
                ec.is_primary = False
                existing.is_primary = True
            else:
                ec.category_id = target.id
        for e, _note in retracts:
            pids = [p.id for p in provs_by_entity.get(e.id, []) if p.is_active]
            print(f"  DROP {e.id} '{e.name[:34]}' providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: {len(moves)} moves, {len(retracts)} retracts. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
