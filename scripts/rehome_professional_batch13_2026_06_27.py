"""Batch-13: Professional/Civic misfiles + dupes (dry-run default; --apply gated).

Directory-audit follow-up. CURATED, restricted to the named source leaf,
single-match guarded for moves. RETRACTS carry a rev==0 safety — a matched row
with reviews is reported and NEVER dropped. Operator-approved 2026-06-28.

  MOVE    = repoint primary entity_categories row to an EXISTING target leaf.
  RETRACT = Entity.is_active=False + provider deactivate, rev==0 only.

HELD (need a NEW leaf or a judgment call — excluded):
  * mortgage brokers out of Banks (no mortgage leaf)
  * paralegals/doc-prep out of Attorneys (no legal-doc-prep leaf): Affordable Legal
    Document Services, Infinity Legal, Legal Wizard, Zion Paralegal, TT's, Majestic's
  * Quick Stop Title & Registration (for-profit MVD — no clean leaf)
  * Sweet Peas & Sage (retract vs -> florist?)
  * Guild Mortgage company vs LO (both reviewed — ambiguous)

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/rehome_professional_batch13_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_professional_batch13_2026_06_27.py --apply
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
    ("insurance", "roc title", "title-and-escrow", "title agency, not insurance"),
    ("insurance", "premier title", "title-and-escrow", "title agency"),
    ("insurance", "pioneer title", "title-and-escrow", "title agency"),
    ("insurance", "chicago title", "title-and-escrow", "title agency"),
    ("insurance", "fidelity national title", "title-and-escrow", "title agency"),
    ("attorneys", "d tax", "accountants-and-tax", "tax service, not an attorney"),
    ("nonprofits-and-charities", "teri parcells", "notary", "notary, not a nonprofit"),
    ("financial-advisors", "hbc motors", "car-dealerships", "car/boat dealer, not an advisor"),
)

# (source leaf slug, name substring) — retract rev==0 matches only.
_RETRACT: tuple[tuple[str, str], ...] = (
    ("financial-advisors", "hard money lenders lake havasu"),
    ("financial-advisors", "commercial lending lake havasu"),
    ("photographers", "photoaid"),
    ("financial-advisors", "chase home lending"),
    ("banks-and-credit-unions", "primary residential mortgage"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-13 professional/civic cleanup (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-13 PROFESSIONAL / CIVIC — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        cache: dict[str, list[Entity]] = {}

        def members(slug: str) -> list[Entity]:
            if slug in cache:
                return cache[slug]
            cat = leaf_by_slug[slug]
            ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
            cache[slug] = [e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place"))).all() if e.id in ids]
            return cache[slug]

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        def primary_ec(eid: str) -> EntityCategory | None:
            return db.query(EntityCategory).filter(
                EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True)).one_or_none()

        moves = []
        for sslug, key, tslug, note in _MOVES:
            cands = [e for e in members(sslug) if key in (e.name or "").lower()]
            target = leaf_by_slug.get(tslug)
            if target is None or len(cands) != 1:
                print(f"  SKIP move '{key}': target={tslug} matches={len(cands)}")
                continue
            e = cands[0]
            existing = db.query(EntityCategory).filter(
                EntityCategory.entity_id == e.id, EntityCategory.category_id == target.id).one_or_none()
            moves.append((e, primary_ec(e.id), target, existing, note))

        retracts = []
        for sslug, key in _RETRACT:
            for e in members(sslug):
                if key in (e.name or "").lower():
                    if rev(e) > 0:
                        print(f"  SKIP retract '{e.name[:34]}': has rev={rev(e)} (safety)")
                        continue
                    retracts.append(e)

        print(f"\nmoves: {len(moves)}   retracts: {len(retracts)}\n")
        print("--- re-home ---")
        for e, _ec, target, existing, note in moves:
            m = "swap" if existing is not None else "repoint"
            print(f"  MOVE [{m:7s}] {e.name[:40]:40s} -> {target.slug:20s} ({note})")
        print("\n--- retract (rev==0 only) ---")
        for e in retracts:
            print(f"  DROP  {e.name[:46]}")
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
        for e in retracts:
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
