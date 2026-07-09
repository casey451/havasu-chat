"""Batch-15: dedup shadow mirrors in the Restaurants leaf (dry-run default; --apply gated).

Directory-audit follow-up (Restaurants ≈40 "New/few reviews" shadow mirrors). SELF-
DERIVING (no curated list): clusters active restaurants-leaf listings by an EXACT
normalized name, and — per the proven Batch-8 rule — retracts only NON-keeper members
with ZERO reviews when the cluster has a reviewed keeper. The 0-review rule protects
genuinely-distinct restaurants (they keep their reviews, so they are never dropped).

Near-name pairs (Lin's vs Lina, Montana vs Montana's) are NOT auto-touched — they are
listed under "NEAR-DUP (manual)" for an operator decision.

Retract = Entity.is_active=False + provider deactivate. Per-id snapshot. Reversible.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/dedup_restaurants_batch15_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/dedup_restaurants_batch15_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
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

_RESTAURANTS_SLUG = "restaurants"


def _norm(name: str | None) -> str:
    n = (name or "").lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\b(the|llc|inc|co|restaurant|grill|cafe|kitchen)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-15 restaurants dedup (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-15 RESTAURANTS SHADOW-MIRROR DEDUP — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        cat = db.query(Category).filter(Category.slug == _RESTAURANTS_SLUG).one()
        ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
            EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        ents = [e for e in db.query(Entity).filter(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(("commercial", "place"))).all() if e.id in ids]

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        clusters: dict[str, list[Entity]] = defaultdict(list)
        for e in ents:
            k = _norm(e.name)
            if k:
                clusters[k].append(e)

        drops: list[tuple[Entity, Entity]] = []
        protected: list[tuple[str, list[Entity]]] = []
        for k, rows in clusters.items():
            if len(rows) < 2:
                continue
            keeper = max(rows, key=rev)
            if rev(keeper) == 0:
                protected.append((k, rows))  # no reviewed keeper -> manual
                continue
            zero = [e for e in rows if e.id != keeper.id and rev(e) == 0]
            reviewed_others = [e for e in rows if e.id != keeper.id and rev(e) > 0]
            for e in zero:
                drops.append((keeper, e))
            if reviewed_others:
                protected.append((k, rows))  # 2+ reviewed -> manual, don't auto-drop

        print(f"restaurants active: {len(ents)}   exact-name clusters>1: "
              f"{sum(1 for r in clusters.values() if len(r) > 1)}\n")
        print(f"--- AUTO retract (0-rev mirror, reviewed keeper): {len(drops)} ---")
        for keeper, e in sorted(drops, key=lambda t: t[1].name.lower()):
            print(f"  DROP  {e.name[:34]:34s} (rev=0, {e.source[:11]:11s}) "
                  f"-> keep '{keeper.name[:24]}' (rev={rev(keeper)})")
        print(f"\n--- NEAR/AMBIGUOUS clusters (manual, NOT touched): {len(protected)} ---")
        for k, rows in sorted(protected):
            tag = "no-reviewed-keeper" if max(rows, key=rev) and rev(max(rows, key=rev)) == 0 else "2+ reviewed"
            print(f"  '{k[:30]}' x{len(rows)} [{tag}]: "
                  + ", ".join(f"{e.name[:20]}({rev(e)})" for e in rows[:4]))
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot ---")
        for _keeper, e in drops:
            pids = [p.id for p in provs_by_entity.get(e.id, []) if p.is_active]
            print(f"  DROP {e.id} '{e.name[:30]}' providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: retracted {len(drops)} shadow mirrors. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
