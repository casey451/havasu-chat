"""READ-ONLY diagnostic for the 2026-06-30 search-audit Phase-2 data ops.

Never writes. Locates every Phase-2 target row in prod and prints its current
state (entity id, active flag, primary category, address, category memberships)
so the actual dry-run mutation scripts can be scoped against REAL data — several
audit items may already be resolved by the 2026-06-27 directory-audit passes
(e.g. retract_directory_bulk_import_junk retracted "Outdoor Enthusiasts").

Usage:
    .venv\\Scripts\\python.exe scripts/audit_search_data_ops_2026_06_30.py
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
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"go\s+lake\s+havasu\s+visitor\s+center", re.IGNORECASE)

# Named 2A targets — (label, lowercase name substrings that identify the row).
_NAMED_TARGETS: list[tuple[str, tuple[str, ...]]] = [
    ("REMOVE: Designated Operator Program", ("designated operator program",)),
    ("RECLASS: Scuba Training & Technology", ("scuba training",)),
    ("RECLASS: Lake Havasu VA Clinic", ("va clinic", "veterans affairs")),
    ("RECLASS: The Spot (restaurant)", ("the spot",)),
    ("RECLASS: Capt Kenne Charters", ("capt kenne", "captain kenne")),
    ("RECLASS/landmark: Copper Canyon", ("copper canyon",)),
    ("VERIFY/dormant: Wake Surf Adventures", ("wake surf adventures",)),
    ("VERIFY: Outdoor Enthusiasts", ("outdoor enthusiasts",)),
    ("DEDUP: Islander Resort / Islander Rv Resort", ("islander resort", "islander rv")),
    ("MISSING?: Havasu Parasail", ("havasu parasail",)),
    ("MISSING?: VR Escape Reality", ("vr escape", "escape reality")),
]


def _cats_for(db, entity_id: str) -> str:
    rows = (
        db.query(Category.slug, EntityCategory.is_primary)
        .join(EntityCategory, EntityCategory.category_id == Category.id)
        .filter(EntityCategory.entity_id == entity_id)
        .all()
    )
    if not rows:
        return "(no EntityCategory rows)"
    return ", ".join(f"{slug}{'*' if prim else ''}" for slug, prim in rows)


def _addr_for(db, entity_id: str, prov: Provider | None) -> str:
    if prov is not None and (prov.address or "").strip():
        return prov.address
    loc = db.query(Location).filter(Location.entity_id == entity_id).first()
    if loc is not None:
        return loc.address_normalized or loc.address or ""
    return ""


def _describe(db, ent: Entity) -> str:
    prov = db.query(Provider).filter(Provider.entity_id == ent.id).first()
    addr = _addr_for(db, ent.id, prov)
    placeholder = " [PLACEHOLDER-ADDR]" if _PLACEHOLDER_RE.search(addr or "") else ""
    pcat = ent.primary_category or (prov.primary_category if prov else None)
    active = "active" if ent.is_active else "INACTIVE"
    prov_bits = ""
    if prov is not None:
        prov_bits = (
            f"\n      provider: is_active={prov.is_active} draft={prov.draft} "
            f"cat={prov.category!r} subcat={prov.subcategory!r} primary={prov.primary_category!r}"
        )
    return (
        f"  • {ent.name[:52]:52s} [{ent.entity_type}/{active}] eid={ent.id}\n"
        f"      primary_category={pcat!r}  cats=[{_cats_for(db, ent.id)}]\n"
        f"      address={(addr or '(none)')[:70]!r}{placeholder}{prov_bits}"
    )


def _find_by_name(db, subs: tuple[str, ...]) -> list[Entity]:
    out: dict[str, Entity] = {}
    for sub in subs:
        for ent in db.query(Entity).filter(Entity.name.ilike(f"%{sub}%")).all():
            out[ent.id] = ent
    return list(out.values())


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("SEARCH-AUDIT PHASE-2 DIAGNOSTIC — READ ONLY (no writes)")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        print("### 2A — named targets (remove / reclassify / verify / dedup) ###\n")
        for label, subs in _NAMED_TARGETS:
            print(f"[{label}]")
            hits = _find_by_name(db, subs)
            if not hits:
                print("  (no matching entity found)\n")
                continue
            for ent in sorted(hits, key=lambda e: e.name.lower()):
                print(_describe(db, ent))
            print()

        print("### 2B — every row carrying the 'Go Lake Havasu Visitor Center' "
              "placeholder address ###\n")
        # Providers with the placeholder in their address.
        prov_hits = [
            p for p in db.query(Provider).filter(Provider.is_active.is_(True)).all()
            if _PLACEHOLDER_RE.search(p.address or "")
        ]
        # Locations carrying the placeholder (entities without a provider address).
        loc_hits = [
            loc for loc in db.query(Location).all()
            if _PLACEHOLDER_RE.search((loc.address_normalized or "") + " " + (loc.address or ""))
        ]
        eids = {p.entity_id for p in prov_hits if p.entity_id} | {
            loc.entity_id for loc in loc_hits if loc.entity_id
        }
        print(f"active providers with placeholder address: {len(prov_hits)}")
        print(f"locations with placeholder address:        {len(loc_hits)}")
        print(f"distinct entities affected:                {len(eids)}\n")
        for eid in sorted(eids):
            ent = db.get(Entity, eid)
            if ent is not None:
                print(_describe(db, ent))
        print("\n(READ-ONLY — nothing written.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
