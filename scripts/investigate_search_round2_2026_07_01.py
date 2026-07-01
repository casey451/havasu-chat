"""READ-ONLY investigation for search-audit round-2 N3/N4 (2026-07-01).

Pulls the exact rows the addendum names so a targeted, reversible data-op
dry-run can be built with real entity_ids and current primary leaves. Writes
nothing. Run against prod (default DATABASE_URL).

Usage:
    .venv\\Scripts\\python.exe scripts/investigate_search_round2_2026_07_01.py
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

from sqlalchemy import func, or_  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402


def _primary_leaf(db, eid: str) -> tuple[str, str] | None:
    prim = db.query(EntityCategory).filter_by(entity_id=eid, is_primary=True).one_or_none()
    if prim is None:
        return None
    c = db.get(Category, prim.category_id)
    return (c.slug, c.name) if c else ("?", "?")


def _all_leaves(db, eid: str) -> list[str]:
    rows = db.query(EntityCategory).filter_by(entity_id=eid).all()
    out = []
    for r in rows:
        c = db.get(Category, r.category_id)
        tag = f"{c.slug if c else r.category_id}{'*' if r.is_primary else ''}"
        out.append(tag)
    return out


def _find(db, *name_likes: str) -> list[Entity]:
    conds = [func.lower(Entity.name).like(f"%{n.lower()}%") for n in name_likes]
    return (
        db.query(Entity)
        .filter(Entity.is_active.is_(True), or_(*conds))
        .order_by(Entity.name)
        .all()
    )


def _addr(db, eid: str) -> str:
    p = db.query(Provider).filter_by(entity_id=eid).first()
    if p and p.address:
        return p.address.split(",")[0].strip()
    loc = db.query(Location).filter_by(entity_id=eid).first()
    return (loc.address_line1 or "") if loc else ""


def _show(db, title: str, ents: list[Entity]) -> None:
    print(f"\n### {title}  ({len(ents)})")
    for e in ents:
        leaf = _primary_leaf(db, e.id)
        leaves = _all_leaves(db, e.id)
        print(f"  {e.name[:44]:44s} | id={e.id}")
        print(f"       primary={leaf} | all_leaves={leaves} | addr={_addr(db, e.id)[:40]}")


def _leaf_provider_count(db, slug: str) -> int:
    c = db.query(Category).filter_by(slug=slug).first()
    if c is None:
        return -1
    return (
        db.query(func.count(EntityCategory.id))
        .filter(EntityCategory.category_id == c.id, EntityCategory.is_primary.is_(True))
        .scalar()
    )


def main() -> int:
    with SessionLocal() as db:
        print("=" * 72)
        print("SEARCH ROUND-2 INVESTIGATION (READ-ONLY) — N3/N4")
        print("=" * 72)

        # --- candidate target leaves (does a sensible home exist?) ---
        print("\n## CANDIDATE TARGET LEAVES (slug -> primary-count)")
        for slug in (
            "auto-repair", "auto-repair-shops", "appliance-repair", "appliances",
            "musical-instruments", "music-stores", "nurseries", "garden-centers",
            "nurseries-and-garden", "landscaping", "restaurants",
            "family-fun-and-arcades", "family-fun", "government-offices",
            "government-offices-and-mvd", "urgent-care", "dentists-and-orthodontists",
            "dentists", "optometrists-and-eye-care", "eye-doctors", "real-estate-agents",
            "real-estate",
        ):
            n = _leaf_provider_count(db, slug)
            mark = "MISSING" if n < 0 else str(n)
            print(f"  {slug:34s} -> {mark}")

        # --- N4 targeted rows ---
        print("\n" + "=" * 72)
        print("N4 — keyword-collision miscategorizations")
        print("=" * 72)
        _show(db, "Phil's Band Instrument Repair", _find(db, "phil's band", "band instrument"))
        _show(db, "Sears Appliance Repair", _find(db, "sears"))
        _show(db, "Serrano's / Caley Nursery", _find(db, "serrano", "caley"))
        _show(db, "The Spot", _find(db, "the spot"))
        _show(db, "Lake Havasu VA Clinic", _find(db, "va clinic", "veterans"))

        # --- N3a clear-cut removals ---
        print("\n" + "=" * 72)
        print("N3a — non-matching rows to drop from a leaf")
        print("=" * 72)
        _show(db, "Dental labs / prosthetics (in Dentists?)",
              _find(db, "dental lab", "prosthetic"))
        _show(db, "Real-estate non-agents",
              _find(db, "pixeopro", "watercraft rental", "board of realtors",
                    "realtor convention"))
        _show(db, "Retail optical (in eye doctor?)",
              _find(db, "walmart vision", "jcpenney optical", "us vision", "pearle"))

        # --- N3b practitioner clustering (judgment) ---
        print("\n" + "=" * 72)
        print("N3b — practitioner clustering (SAMPLE, needs Casey's call)")
        print("=" * 72)
        eye = _find(db, "eyecare", "optometr", "eye care", "vision center")
        _show(db, "Eye-care rows (address-cluster check)", eye)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
