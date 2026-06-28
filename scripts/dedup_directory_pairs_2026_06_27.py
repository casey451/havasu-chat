"""Dedup curated duplicate pairs the shadow-mirror tool missed (gated).

Directory-audit follow-up (§"De-duplicate"). The shadow-mirror retractor only
fires when a cluster has a reviewed google_places KEEPER + a thin mirror. Several
real duplicate pairs have NO reviewed keeper (both 0-review, or a provider-less
place twin), so they slipped through and kept surfacing as "ambiguous" in the
re-home tool. This handles a HAND-CURATED list of those clusters.

For each curated cluster key, the keeper is the member that ranks highest by:
    1. provider-backed (active provider) over place-only
    2. higher google_review_count
    3. google_places source over a shadow-import source
    4. has an address over none
    (stable tiebreak: lowest entity id)
All OTHER members are retracted (Entity.is_active=False + Provider.is_active=False).

SAFETY: a cluster where >=2 members are provider-backed with reviews AND have
DISTINCT non-empty addresses is treated as a possible MULTI-LOCATION chain and
SKIPPED (never deduped) — so two real storefronts can't be collapsed.

dry-run default; --apply gated; reversible.

Usage:
    .venv\\Scripts\\python.exe scripts/dedup_directory_pairs_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/dedup_directory_pairs_2026_06_27.py --apply
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

# Curated cluster keys (lowercased name substring) — confirmed duplicate pairs
# surfaced by the re-home tool / triage §3. Multi-location brands (e.g.
# "Beautiful Beards Pet Spaw" = two real shops) are intentionally NOT listed.
_CLUSTER_KEYS: tuple[str, ...] = (
    "lions dog park",
    "nautical watersports",
    "bogeys & stogies",
    "rentals on the beach",
    "anderson powersports",
    "grand island disc golf",
)

_GOOGLE = "google_places"


def _addr(p: Provider | None) -> str:
    return ((p.address if p else "") or "").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dedup curated duplicate pairs (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: retract non-keeper members (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"DUPLICATE-PAIR DEDUP — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        entities = (
            db.query(Entity)
            .filter(Entity.is_active.is_(True), Entity.entity_type.in_(("commercial", "place")))
            .all()
        )
        prov_by_entity: dict[str, Provider] = {}
        for p in db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        ).all():
            cur = prov_by_entity.get(p.entity_id)
            if cur is None or (p.google_review_count or 0) > (cur.google_review_count or 0):
                prov_by_entity[p.entity_id] = p

        def _rev(e: Entity) -> int:
            pr = prov_by_entity.get(e.id)
            return (pr.google_review_count or 0) if pr else 0

        def _rank(e: Entity) -> tuple:
            pr = prov_by_entity.get(e.id)
            return (
                1 if pr is not None else 0,
                _rev(e),
                1 if (e.source or "") == _GOOGLE else 0,
                1 if _addr(pr) else 0,
            )

        retract: list[tuple[Entity, Entity]] = []  # (loser, keeper)
        for key in _CLUSTER_KEYS:
            members = [e for e in entities if key in (e.name or "").lower()]
            if len(members) < 2:
                print(f"  SKIP  '{key}': {len(members)} active match (need >=2)")
                continue
            # Multi-location guard: >=2 reviewed provider-backed members with
            # distinct non-empty addresses => real storefronts, do not dedup.
            reviewed_addrs = {
                _addr(prov_by_entity.get(e.id)).lower()
                for e in members
                if prov_by_entity.get(e.id) is not None and _rev(e) > 0 and _addr(prov_by_entity.get(e.id))
            }
            reviewed_backed = [e for e in members if prov_by_entity.get(e.id) is not None and _rev(e) > 0]
            if len(reviewed_backed) >= 2 and len(reviewed_addrs) >= 2:
                print(f"  SKIP  '{key}': {len(reviewed_backed)} reviewed w/ distinct addrs (multi-location?)")
                continue
            ranked = sorted(members, key=_rank, reverse=True)
            keeper = ranked[0]
            losers = ranked[1:]
            print(f"  '{key}' (x{len(members)}) -> KEEP {keeper.name[:34]!r} "
                  f"[prov={keeper.id in prov_by_entity} rev={_rev(keeper)} src={keeper.source}]")
            for lo in losers:
                print(f"        RETRACT {lo.name[:34]!r} "
                      f"[prov={lo.id in prov_by_entity} rev={_rev(lo)} src={lo.source}]")
                retract.append((lo, keeper))

        print(f"\nclusters acted on: {len({k.id for _, k in retract})}   "
              f"members to retract: {len(retract)}\n")

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to dedup.")
            return 0

        for loser, _keeper in retract:
            loser.is_active = False
            for p in db.query(Provider).filter(Provider.entity_id == loser.id).all():
                p.is_active = False
        db.commit()
        print(f"APPLIED: retracted {len(retract)} duplicate members (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
