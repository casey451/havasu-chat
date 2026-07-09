"""Batch-7 read-only probe: priority-cluster (boats/pools/HVAC) re-home candidates.

READ-ONLY. SELECT-only, ZERO writes. The dry-run / show-counts step before any
operator-approved re-home. Surfaces the priority-cluster misfiles from the
directory audit that the shipped ``rehome_directory_miscategorized_2026_06_27.py``
did NOT already move (those were ambiguous, needed a dedup first, or were
uncurated). For each curated candidate it reports:

  * match count against active commercial/place entities (0 / 1 / >1=ambiguous);
  * the matched entity's CURRENT primary leaf (slug, level, "N Best" inflation);
  * its review count + source (real listing vs thin import);
  * whether the proposed TARGET leaf exists.

Nothing is moved here. The move pass is a separate, dated, --apply-gated script
the operator approves after eyeballing this output.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch7_priority_2026_06_27.py
"""

from __future__ import annotations

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

# Curated Batch-7 candidates: (name substring, proposed target leaf slug, note).
# Conservative — substring only; the probe reports ambiguity instead of guessing.
_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    # --- On the Water: boat dealers stranded in Self-Storage ---
    ("sandbar powersports", "boat-sales", "powersports/boat dealer, mis-filed Self-Storage"),
    ("horizon motorsports", "boat-sales", "DCB/Playcraft boat dealer, mis-filed Self-Storage"),
    # --- Pools: dealers stranded in Sporting Goods ---
    ("amici pools", "pools-and-spas", "pool retail+service, mis-filed Sporting Goods"),
    ("mohave mist", "pools-and-spas", "hot-tub/spa dealer, mis-filed Sporting Goods"),
    ("neat pool", "pools-and-spas", "pool supply/service — confirm current leaf/tag"),
    # --- HVAC: companies stranded off the HVAC leaf (target slug resolved below) ---
    ("all american air", "__HVAC__", "HVAC co reportedly stranded off the HVAC leaf"),
    ("air control", "__HVAC__", "HVAC co reportedly stranded off the HVAC leaf"),
    ("ac pro", "__HVAC__", "NB: wholesale supply house — verify, may be relabel not move"),
)


def _erev(p: Provider | None) -> int:
    return (p.google_review_count or 0) if p else 0


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("BATCH-7 PRIORITY-CLUSTER RE-HOME PROBE  (READ-ONLY — no rows written)")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaves = db.query(Category).filter(Category.level == 1).all()
        leaf_by_slug = {c.slug: c for c in leaves}
        cat_by_id = {c.id: c for c in db.query(Category).all()}

        # Resolve the HVAC leaf slug (don't guess) — show candidates.
        hvac_like = sorted(
            c.slug for c in leaves
            if any(k in c.slug for k in ("hvac", "cool", "heat", "air-cond"))
        )
        print("HVAC-like leaf slugs present:", hvac_like or "(none found)")
        hvac_slug = hvac_like[0] if hvac_like else None
        print()

        # Provider lookup by entity (best-reviewed) for the real-vs-thin signal.
        prov_by_entity: dict[str, Provider] = {}
        for p in db.query(Provider).filter(Provider.is_active.is_(True)).all():
            cur = prov_by_entity.get(p.entity_id)
            if cur is None or (p.google_review_count or 0) > (cur.google_review_count or 0):
                prov_by_entity[p.entity_id] = p

        ents = (
            db.query(Entity)
            .filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            )
            .all()
        )

        print("-" * 78)
        print(f"{'candidate':22s} {'matches':7s} {'current leaf':24s} {'-> target':22s} status")
        print("-" * 78)
        for key, target_slug, note in _CANDIDATES:
            if target_slug == "__HVAC__":
                target_slug = hvac_slug or "(hvac-unresolved)"
            cands = [e for e in ents if key in (e.name or "").lower()]
            target = leaf_by_slug.get(target_slug)

            if not cands:
                print(f"{key:22s} {'0':>7s} {'—':24s} {target_slug:22s} NO MATCH (already moved/retracted?)")
                continue
            if len(cands) > 1:
                names = "; ".join(e.name for e in cands[:4])
                print(f"{key:22s} {len(cands):>7d} {'(ambiguous)':24s} {target_slug:22s} SKIP — {names}")
                continue

            ent = cands[0]
            prim = (
                db.query(EntityCategory)
                .filter(EntityCategory.entity_id == ent.id, EntityCategory.is_primary.is_(True))
                .one_or_none()
            )
            cur_cat = cat_by_id.get(prim.category_id) if prim else None
            cur_slug = cur_cat.slug if cur_cat else "(no primary)"
            pr = prov_by_entity.get(ent.id)

            if target is None:
                status = "TARGET LEAF MISSING — needs Batch-14 create"
            elif cur_cat is not None and cur_cat.id == target.id:
                status = "already on target (no-op)"
            else:
                status = "MOVE candidate"
            print(f"{key:22s} {'1':>7s} {cur_slug:24s} {target_slug:22s} {status}")
            print(f"{'':22s} └ {ent.name[:40]:40s} rev={_erev(pr):<5d} src={ent.source} | {note}")
        print("-" * 78)
        print("\nREAD-ONLY — nothing written. Approve the moves you want and I'll build the")
        print("dated --apply-gated re-home script for them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
