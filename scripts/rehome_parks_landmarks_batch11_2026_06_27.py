"""Batch-11: clean Parks & Playgrounds + Landmarks (dry-run default; --apply gated).

Directory-audit follow-up (Parks & Playgrounds = the audit's worst single leaf).
A CURATED set (not heuristic) of moves + retracts, each restricted to entities
whose primary leaf is parks-and-playgrounds or landmarks-and-sights, single-match
guarded (0 or >1 match -> SKIP). Surfaced by audit_directory_batch11_parks_*.py;
operator-approved 2026-06-28.

  MOVE   = repoint the primary entity_categories row to the right Things-to-Do
           sub-leaf (trails -> hiking; billiards -> family-fun; rentals -> boat
           rentals; wedding/party/event cos -> event-planning; tour op -> tours).
  RETRACT= Entity.is_active=False + provider deactivate, for generic non-listings
           and out-of-area day-trips. Reversible.

HELD (judgment — excluded): Lake Havasu Rodeo Grounds (no clean leaf), Bill
Williams River NWR (real nearby refuge), London Bridge Shops (placeholder),
Crossroads OHV (placeholder).

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/rehome_parks_landmarks_batch11_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/rehome_parks_landmarks_batch11_2026_06_27.py --apply
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

_SOURCE_SLUGS = ("parks-and-playgrounds", "landmarks-and-sights")

# (name substring, target leaf slug, note)
_MOVES: tuple[tuple[str, str, str], ...] = (
    ("mr lucky's billiard", "family-fun-and-arcades", "billiards hall, not a park"),
    ("sara park hiking trail", "hiking-trails", "trail"),
    ("crack in the mountain", "hiking-trails", "trail"),
    ("cupcake mountain", "hiking-trails", "trail"),
    ("crossman peak", "hiking-trails", "trail"),
    ("arch rock loop", "hiking-trails", "trail"),
    ("island trail", "hiking-trails", "trail"),
    ("lizard peak", "hiking-trails", "trail"),
    ("chemehuevi wash", "hiking-trails", "trail"),
    ("mockingbird wash", "hiking-trails", "trail"),
    ("three dunes trail", "hiking-trails", "trail"),
    ("shoreline trail", "hiking-trails", "trail"),
    ("bison falls", "off-road-and-ohv", "offroad trail"),
    ("beach shack rentals", "boat-and-watercraft-rentals", "boat/beach rentals"),
    ("hooks boat rentals", "boat-and-watercraft-rentals", "boat rentals"),
    ("london bridge beach boat rental", "boat-and-watercraft-rentals", "boat rentals"),
    ("az party express", "event-planning", "party bus"),
    ("the wedding specialist", "event-planning", "wedding planner"),
    ("high end productions", "event-planning", "event company"),
    ("london bridge tours by havasu discovery", "tours-and-sightseeing", "tour operator"),
)

# exact-ish name substrings to retract (generic non-listing / out-of-area)
_RETRACT: tuple[tuple[str, str], ...] = (
    ("copper basin dunes", "OOA — Parker Strip"),
    ("desert bar", "OOA — ~1hr near Parker"),
    ("lighthouses", "generic non-listing (PO Box)"),
    ("keepers of the wild", "OOA — Valentine/Kingman"),
    ("oatman", "OOA — town ~1hr"),
    ("grand canyon west", "OOA — Peach Springs"),
    ("grand canyon caverns", "OOA — Route 66"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-11 parks/landmarks cleanup (gated).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-11 PARKS / LANDMARKS CLEANUP — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        source_ids = {leaf_by_slug[s].id for s in _SOURCE_SLUGS}
        prim_by_ent = {
            ec.entity_id: ec for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id.in_(source_ids),
                EntityCategory.is_primary.is_(True),
            ).all()
        }
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        src_ents = [
            e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            ).all()
            if e.id in prim_by_ent
        ]

        def match(key: str) -> list[Entity]:
            return [e for e in src_ents if key in (e.name or "").lower()]

        moves: list[tuple[Entity, EntityCategory, Category, EntityCategory | None, str]] = []
        for key, tslug, note in _MOVES:
            cands = match(key)
            target = leaf_by_slug.get(tslug)
            if target is None:
                print(f"  SKIP move '{key}': target '{tslug}' missing")
                continue
            if len(cands) != 1:
                print(f"  SKIP move '{key}': {len(cands)} matches")
                continue
            e = cands[0]
            existing = db.query(EntityCategory).filter(
                EntityCategory.entity_id == e.id,
                EntityCategory.category_id == target.id,
            ).one_or_none()
            moves.append((e, prim_by_ent[e.id], target, existing, note))

        retracts: list[Entity] = []
        for key, _note in _RETRACT:
            cands = match(key)
            if len(cands) != 1:
                print(f"  SKIP retract '{key}': {len(cands)} matches")
                continue
            retracts.append(cands[0])

        print(f"\nmoves: {len(moves)}   retracts: {len(retracts)}\n")
        print("--- re-home ---")
        for e, _ec, target, existing, note in moves:
            m = "swap" if existing is not None else "repoint"
            print(f"  MOVE [{m:7s}] {e.name[:40]:40s} -> {target.slug:26s} ({note})")
        print("\n--- retract ---")
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
            print(f"  DROP {e.id} '{e.name[:36]}' providers={pids}")
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: {len(moves)} moves, {len(retracts)} retracts. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
