"""Batch-11 read-only probe: remaining misfiles in Parks & Playgrounds + Landmarks.

READ-ONLY. SELECT-only, ZERO writes. Lists the CURRENT active primary members of
the `parks-and-playgrounds` and `landmarks-and-sights` leaves (after earlier
batches already pulled several out), with signals so the operator can curate:
review count, source, is_local, address. Heuristic tags:

  BIZ   — name looks like a commercial business (pool/boat/billiards/etc.), not a park
  GEN   — generic non-listing ("Bird Watching", "Splash Pads", "Outdoor Enthusiasts")
  OOA   — out-of-area (is_local=False, or Parker/Kingman/Needles/Hoover/Blythe/Topock)
  TRAIL — looks like a trail (could move to hiking-trails)
  (untagged = plausibly a real park / landmark — leave)

Nothing is moved or retracted.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch11_parks_2026_06_27.py
"""

from __future__ import annotations

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

_LEAVES = ("parks-and-playgrounds", "landmarks-and-sights")

_BIZ_RE = re.compile(
    r"(pool|spa|billiard|boat|powersport|motorsport|golf cart|cart|grill|"
    r"restaurant|bar\b|saloon|stogies|rodeo|storage|salon|wedding|party|"
    r"productions|event|rental|shop|store|market|llc|inc\b|services|repair)",
    re.IGNORECASE)
_GEN_RE = re.compile(
    r"^(bird watching|splash pads?|outdoor enthusiasts|lighthouses|"
    r"boat-?in beaches|picnic|playgrounds?)$", re.IGNORECASE)
_OOA_NAME_RE = re.compile(
    r"(hoover|blythe|topock|mystic maze|needles|parker|kingman|"
    r"national wildlife|copper basin|oatman|havasu lake)", re.IGNORECASE)
_TRAIL_RE = re.compile(r"(trail|peak|crack in the|arch rock|dunes|wash|mountain)", re.IGNORECASE)


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 86)
    print("BATCH-11 PARKS / LANDMARKS MISFILE PROBE  (READ-ONLY — no rows written)")
    print("=" * 86)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        for slug in _LEAVES:
            cat = db.query(Category).filter(Category.slug == slug).one()
            ent_ids = {
                ec.entity_id for ec in db.query(EntityCategory).filter(
                    EntityCategory.category_id == cat.id,
                    EntityCategory.is_primary.is_(True),
                ).all()
            }
            ents = [
                e for e in db.query(Entity).filter(
                    Entity.is_active.is_(True),
                    Entity.entity_type.in_(("commercial", "place")),
                ).all()
                if e.id in ent_ids
            ]
            print("=" * 86)
            print(f"[{slug}]  active primary members: {len(ents)}")
            print("=" * 86)
            tagged = {"BIZ": [], "GEN": [], "OOA": [], "TRAIL": [], "OK": []}
            for e in ents:
                provs = sorted(provs_by_entity.get(e.id, []),
                               key=lambda p: -(p.google_review_count or 0))
                pr = provs[0] if provs else None
                addr = (pr.address if pr else "") or ""
                rev = (pr.google_review_count or 0) if pr else 0
                local = pr.is_local if pr else None
                name = e.name or ""
                if local is False or _OOA_NAME_RE.search(name) or _OOA_NAME_RE.search(addr):
                    tag = "OOA"
                elif _GEN_RE.match(name.strip()):
                    tag = "GEN"
                elif _BIZ_RE.search(name):
                    tag = "BIZ"
                elif _TRAIL_RE.search(name):
                    tag = "TRAIL"
                else:
                    tag = "OK"
                tagged[tag].append((name[:46], rev, e.source[:12], addr[:26]))
            for tag in ("BIZ", "GEN", "OOA", "TRAIL", "OK"):
                rows = tagged[tag]
                print(f"\n  --- {tag} ({len(rows)}) ---")
                for name, rev, src, addr in sorted(rows, key=lambda r: -r[1]):
                    print(f"    rev={rev:>4d} {name:46s} | {src:12s} | {addr}")
            print()
        print("=" * 86)
        print("READ-ONLY. I'll curate BIZ -> real leaves, GEN/OOA -> retract, TRAIL -> "
              "hiking (after your eyeball).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
