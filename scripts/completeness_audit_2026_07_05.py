"""Session 6d — directory completeness audit, PHASE 1 (READ-ONLY).

SELECTs + CSV only. No writes, no --apply. Scores every *renderable* directory
listing for the four click-through essentials — website / hours / address / phone
— using the exact leaf-page render contract (app/categories/leaf_pages.py):

  A listing renders on a leaf iff:
    * its Entity.is_active is True, AND
    * it has a PRIMARY entity_categories link to that (shipping) leaf, AND
    * either it is PROVIDER-BACKED — an active, non-draft Provider with
      is_local != False (renders the provider card) — or it is a PLACE (no
      active non-draft provider → renders a place card from Entity fields).
    * a backing provider with is_local == False drops the listing entirely.

Each shipping leaf hangs off a level-0 department; we roll the per-listing flags
up per department, worst-first, and dump a detailed gaps CSV for the two
priority departments (Eat & Drink, Home & Property Services).

Outputs (writes NOTHING to the DB):
  1. per-department scorecard  -> docs/audits/2026-07/completeness_scorecard_2026-07-05.csv (+ stdout)
  2. detailed gaps CSV         -> docs/audits/2026-07/completeness_gaps_eat-drink_home-services_2026-07-05.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    ContactPoint,
    Entity,
    EntityCategory,
    Hours,
    Location,
    Provider,
)

_OUT_DIR = _ROOT / "docs" / "audits" / "2026-07"
_PRIORITY_DEPTS = ("eat-and-drink", "home-and-property-services")

# Natural / civic leaves where a website or a phone legitimately may not apply
# (parks / landmarks / beaches / trails). These are EXCLUDED from the
# website/phone "missing" denominators and reported separately. Hours/address
# are still scored for them (a park can have posted hours + a location).
_NATURAL_LEAVES = frozenset({
    "parks-and-playgrounds",
    "dog-parks",
    "hiking-trails",
    "beaches-and-swim-areas",
    "wildlife-and-nature",
    "off-road-and-ohv",
    "landmarks-and-sights",
    "scenic-viewpoints",
    "scenic-overlooks",
    "lakes-and-waterways",
    "nature-preserves",
})

_WEB_KINDS = {"website", "web", "url"}
_PHONE_KINDS = {"phone", "telephone", "tel", "mobile", "call"}

_ADDR_PLACEHOLDER = {
    "", "address not listed", "no address listed", "not listed", "n/a", "na",
    "tbd", "none", "-", "unknown",
}
_HOURS_PLACEHOLDER = {
    "", "unknown", "n/a", "na", "hours not listed", "call for hours",
    "hours unknown", "varies", "none",
}


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def _real_address(s: str | None) -> bool:
    t = _norm(s)
    if t in _ADDR_PLACEHOLDER or t.startswith("address not"):
        return False
    # Street-address proxy: a real street carries a number (drops bare
    # "Lake Havasu City, AZ" city-only strings). PO boxes still count.
    return any(ch.isdigit() for ch in t)


def _real_provider_hours(s: str | None) -> bool:
    return _norm(s) not in _HOURS_PLACEHOLDER


def _has_real_hours_rows(rows: list[Hours]) -> bool:
    for h in rows:
        if h.is_24h or h.opens_at is not None or h.closes_at is not None:
            return True
    return False


def _cp_has(cps: list[ContactPoint], kinds: set[str]) -> bool:
    for cp in cps:
        if _norm(cp.kind) in kinds and (cp.value or "").strip():
            return True
    return False


def _cp_web_value(cps: list[ContactPoint]) -> str:
    for cp in cps:
        if _norm(cp.kind) in _WEB_KINDS and (cp.value or "").strip():
            return cp.value.strip()
    return ""


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        # Department + leaf maps.
        depts = {d.id: d for d in db.query(Category).filter(Category.level == 0).all()}
        leaves = db.query(Category).filter(Category.level == 1).all()
        leaf_dept: dict[int, Category] = {}
        for lf in leaves:
            dep = depts.get(lf.parent_id) if lf.parent_id else None
            if dep is not None:
                leaf_dept[lf.id] = dep

        # All PRIMARY links on active entities that point at a real leaf.
        rows = (
            db.query(EntityCategory.entity_id, EntityCategory.category_id)
            .join(Entity, EntityCategory.entity_id == Entity.id)
            .filter(EntityCategory.is_primary.is_(True), Entity.is_active.is_(True))
            .all()
        )

        # Preload entities + related for the ones we touch.
        eids = list({eid for eid, _ in rows})
        ents = {
            e.id: e
            for e in db.query(Entity).filter(Entity.id.in_(eids)).all()
        }
        # Active non-draft providers keyed by entity (the "backing" provider).
        prov_by_entity: dict[str, Provider] = {}
        for p in (
            db.query(Provider)
            .filter(Provider.entity_id.in_(eids), Provider.is_active.is_(True), Provider.draft.is_(False))
            .all()
        ):
            if p.entity_id:
                prov_by_entity[p.entity_id] = p
        loc_by_entity = {
            loc.entity_id: loc
            for loc in db.query(Location).filter(Location.entity_id.in_(eids)).all()
        }
        cps_by_entity: dict[str, list[ContactPoint]] = {}
        for cp in db.query(ContactPoint).filter(ContactPoint.entity_id.in_(eids)).all():
            cps_by_entity.setdefault(cp.entity_id, []).append(cp)
        hours_by_entity: dict[str, list[Hours]] = {}
        for h in db.query(Hours).filter(Hours.entity_id.in_(eids)).all():
            hours_by_entity.setdefault(h.entity_id, []).append(h)

        leaf_by_id = {lf.id: lf for lf in leaves}

        # Per-listing scoring.
        listings: list[dict] = []
        for eid, cid in rows:
            leaf = leaf_by_id.get(cid)
            dep = leaf_dept.get(cid)
            if leaf is None or dep is None:
                continue  # link to a non-leaf / orphan category — not renderable here
            ent = ents.get(eid)
            if ent is None:
                continue
            prov = prov_by_entity.get(eid)
            if prov is not None and prov.is_local is False:
                continue  # out-of-area backing provider → not renderable
            cps = cps_by_entity.get(eid, [])
            loc = loc_by_entity.get(eid)
            hrows = hours_by_entity.get(eid, [])

            if prov is not None:  # provider-backed
                has_website = bool((prov.website or "").strip()) or _cp_has(cps, _WEB_KINDS)
                has_phone = bool((prov.phone or "").strip()) or _cp_has(cps, _PHONE_KINDS)
                has_address = _real_address(prov.address) or _real_address(loc.address if loc else None)
                has_hours = _real_provider_hours(prov.hours) if (prov.hours or "").strip() else _has_real_hours_rows(hrows)
                current_website = (prov.website or "").strip() or _cp_web_value(cps)
                backing = "provider"
            else:  # place
                has_website = _cp_has(cps, _WEB_KINDS)
                has_phone = _cp_has(cps, _PHONE_KINDS)
                has_address = _real_address(loc.address if loc else None)
                has_hours = _has_real_hours_rows(hrows)
                current_website = _cp_web_value(cps)
                backing = "place"

            listings.append({
                "entity_id": eid,
                "name": ent.name,
                "dept_slug": dep.slug,
                "dept_name": dep.name,
                "leaf_slug": leaf.slug,
                "backing": backing,
                "web_phone_na": leaf.slug in _NATURAL_LEAVES,
                "has_website": has_website,
                "has_hours": has_hours,
                "has_address": has_address,
                "has_phone": has_phone,
                "current_website": current_website,
            })

        # ---- per-department scorecard ----
        by_dept: dict[str, list[dict]] = {}
        for r in listings:
            by_dept.setdefault(r["dept_slug"], []).append(r)

        scorecard = []
        for dslug, rs in by_dept.items():
            total = len(rs)
            na = [r for r in rs if r["web_phone_na"]]
            commercial = [r for r in rs if not r["web_phone_na"]]
            nc = len(commercial) or 1  # avoid /0
            miss_web = sum(1 for r in commercial if not r["has_website"])
            miss_phone = sum(1 for r in commercial if not r["has_phone"])
            miss_hours = sum(1 for r in rs if not r["has_hours"])
            miss_addr = sum(1 for r in rs if not r["has_address"])
            scorecard.append({
                "department": rs[0]["dept_name"],
                "dept_slug": dslug,
                "renderable": total,
                "place_type_excl": len(na),
                "miss_website": miss_web,
                "pct_website": round(100 * miss_web / nc),
                "miss_hours": miss_hours,
                "pct_hours": round(100 * miss_hours / total),
                "miss_address": miss_addr,
                "pct_address": round(100 * miss_addr / total),
                "miss_phone": miss_phone,
                "pct_phone": round(100 * miss_phone / nc),
            })
        # Worst-first: rank by the combined missing rate across all four.
        scorecard.sort(key=lambda s: (s["pct_website"] + s["pct_hours"] + s["pct_address"] + s["pct_phone"]), reverse=True)

        sc_path = _OUT_DIR / "completeness_scorecard_2026-07-05.csv"
        with sc_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(scorecard[0].keys()))
            w.writeheader()
            w.writerows(scorecard)

        # ---- detailed gaps CSV for the two priority departments ----
        gaps_path = _OUT_DIR / "completeness_gaps_eat-drink_home-services_2026-07-05.csv"
        prio = [r for r in listings if r["dept_slug"] in _PRIORITY_DEPTS]
        prio.sort(key=lambda r: (r["dept_slug"], r["leaf_slug"], r["name"].lower()))
        with gaps_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["entity_id", "name", "dept_slug", "leaf_slug", "backing",
                        "has_website", "has_hours", "has_address", "has_phone", "current_website"])
            for r in prio:
                w.writerow([r["entity_id"], r["name"], r["dept_slug"], r["leaf_slug"], r["backing"],
                            int(r["has_website"]), int(r["has_hours"]), int(r["has_address"]),
                            int(r["has_phone"]), r["current_website"]])

        # ---- stdout ----
        print("=" * 100)
        print("SESSION 6d — COMPLETENESS AUDIT (PHASE 1, READ-ONLY)")
        print("=" * 100)
        print(f"Renderable listings scored: {len(listings)}  across {len(by_dept)} departments")
        print(f"(website/phone 'missing' computed over COMMERCIAL listings; place-type "
              f"[{', '.join(sorted(_NATURAL_LEAVES))[:60]}…] excluded + counted separately)\n")
        hdr = (f"{'department':32s} {'rend':>5s} {'plc':>4s} "
               f"{'web?':>10s} {'hours?':>11s} {'addr?':>11s} {'phone?':>11s}")
        print(hdr)
        print("-" * len(hdr))
        for s in scorecard:
            print(f"{s['department'][:32]:32s} {s['renderable']:5d} {s['place_type_excl']:4d} "
                  f"{s['miss_website']:4d}/{s['pct_website']:3d}% "
                  f"{s['miss_hours']:4d}/{s['pct_hours']:3d}% "
                  f"{s['miss_address']:4d}/{s['pct_address']:3d}% "
                  f"{s['miss_phone']:4d}/{s['pct_phone']:3d}%")
        print()
        print(f"scorecard CSV : {sc_path.relative_to(_ROOT)}")
        print(f"gaps CSV      : {gaps_path.relative_to(_ROOT)}  ({len(prio)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
