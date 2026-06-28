"""Batch-8 dedup: retract thin 0-review mirrors in the priority cluster (dry-run default; --apply gated).

Directory-audit follow-up. Operator-approved 2026-06-27 (the AUTO clusters from
``audit_directory_batch8_dedup_2026_06_27.py``). For each cluster of same-business
listings, KEEP the best-reviewed active member and RETRACT the thin mirrors —
defined conservatively as *active, non-keeper members with ZERO reviews*. That
0-review rule is what makes distinct reviewed sub-entities auto-safe (e.g. "Lake
Havasu Marina Fuel Dock" at 27 reviews is never touched).

Retraction = ``Entity.is_active = False`` + deactivating that entity's active
Providers. Fully reversible; a before snapshot of every flipped id is printed.

HOLD clusters from the probe (Ambient Edge/Fayette merger, TNT/Dynamite Roofing,
Mohave Roofing) are intentionally EXCLUDED — they need human judgment.

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/dedup_directory_batch8_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/dedup_directory_batch8_2026_06_27.py --apply
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
from app.db.models import Entity, Provider  # noqa: E402

# AUTO clusters only (HOLD clusters excluded). (label, match substrings).
_CLUSTERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Boat Broker", ("boat broker",)),
    ("Lake Havasu Marina", ("lake havasu marina",)),  # Fuel Dock (rev>0) auto-safe
    ("Paradise Wild Wave", ("paradise wild wave",)),
    ("TikiToons", ("tikitoons",)),
    ("WACKO / Western Arizona Canoe & Kayak", ("wacko", "western arizona canoe")),
    ("Lake Havasu Airboat", ("airboat",)),
    ("J C Marine", ("j c marine", "jc marine")),
    ("Pro Marine", ("pro-marine", "pro marine")),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-8 priority-cluster dedup (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: retract thin 0-review mirrors (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 78)
    print(f"BATCH-8 PRIORITY-CLUSTER DEDUP — {mode}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        def rev(e: Entity) -> int:
            return max((p.google_review_count or 0) for p in provs_by_entity.get(e.id, [])) \
                if provs_by_entity.get(e.id) else 0

        ents = db.query(Entity).filter(
            Entity.entity_type.in_(("commercial", "place"))
        ).all()

        drops: list[tuple[str, Entity, Entity]] = []  # (cluster, keeper, drop)
        for label, subs in _CLUSTERS:
            active = [
                e for e in ents
                if e.is_active and any(s in (e.name or "").lower() for s in subs)
            ]
            if len(active) < 2:
                print(f"  OK    {label}: {len(active)} active member — nothing to drop")
                continue
            keeper = max(active, key=rev)
            if rev(keeper) == 0:
                print(f"  SKIP  {label}: no reviewed keeper — needs manual review")
                continue
            cluster_drops = [e for e in active if e.id != keeper.id and rev(e) == 0]
            protected = [e for e in active if e.id != keeper.id and rev(e) > 0]
            for e in protected:
                print(f"  KEEP  {label}: '{e.name[:34]}' has rev={rev(e)} — distinct, not dropped")
            for e in cluster_drops:
                drops.append((label, keeper, e))

        print(f"\nretractions planned: {len(drops)}\n")
        print("--- retract thin mirror (keep reviewed) ---")
        for label, keeper, e in drops:
            print(f"  DROP  {e.name[:30]:30s} (rev=0, {e.source[:12]:12s}) "
                  f"-> keep '{keeper.name[:26]}' (rev={rev(keeper)}) [{label}]")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot (entity_id is_active=True -> False; + provider ids) ---")
        for _label, _keeper, e in drops:
            pids = [p.id for p in provs_by_entity.get(e.id, []) if p.is_active]
            print(f"  {e.id}  '{e.name[:30]}'  providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: retracted {len(drops)} thin mirrors. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
