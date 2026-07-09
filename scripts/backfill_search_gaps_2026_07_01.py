"""Phase-5 search-gap backfills: re-homes, inserts, dedups, enrichment (gated).

Consolidated plan Phase 5 (items 1-13) run through the Amendment-1 CROSS-CHECK
guard first — a full prod recon (2026-07-01 PM) showed most planned "adds"
already exist mis-homed, so the bulk of this op is RE-HOMES, not inserts:

  * RV repair: Pro Tech / First Class / Sunshine / Desert RV Werks all live on
    auto-repair or car-dealerships -> rv-sales-and-service. Byrd's is a x2
    same-phone dup (keeper re-homed, twin retired).
  * Music lessons: River City / Bump City / Grand Piano live on
    gifts-and-boutiques / k-12-schools -> music-lessons (a leaf that renders
    ZERO provider profiles today).
  * Tires: Big O + Everything Tire -> tires (old auto-repair membership kept
    as a secondary link, as with every re-home here).
  * Firearms: "Sam's Shooters Emporium (928) 680-7000" from the plan IS the
    catalog's Shooters Outpost row (samsguns.com serves both names — verified
    live 2026-07-01) — ENRICHED, not duplicated. The four other gun stores are
    genuinely absent and insert.
  * Vacation rentals: First Choice of Mohave County already sits on the
    vacation-rentals leaf, so its phoneless VR-named twin is a pure dup
    (retired). Integrity Arizona VR + PMI get the leaf + their phones.
  * WAHS: the Humane Society proper is already on nonprofits-and-charities
    (plan item 11 satisfied); its zero-leaf Medical Clinic row -> veterinarians.
  * Aqua Beginnings (orphan) -> kids-classes-and-camps; Steelhead Aquatics
    (verified active, FB/email contact) inserts beside it. [ASK #6 defaults:
    swim = recat+programs; farmers market = recurring event (Phase 7); weight
    loss -> med-spas-and-aesthetics.]
  * Pool-supply trio (master audit §1): Reinhard / KRT / Bliss orphans ->
    pools-and-spas; Leslie's Pool Supplies inserts.
  * Good Vibez Havasu (master §2) inserts on jet-ski-and-watersports.

DEPENDENCY: the firearms + medical-specialists inserts/links target leaves the
Phase-3 apply script creates — run apply_search_data_ops_2026_07_01.py FIRST;
this script SKIPs (with a note) any item whose leaf is still absent.

Usage:
    .venv\\Scripts\\python.exe scripts/backfill_search_gaps_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/backfill_search_gaps_2026_07_01.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402
from app.utils.slug import slugify  # noqa: E402

BACKFILL_SOURCE = "search_gaps_backfill_2026_07_01"
_SNAP_DIR = _ROOT / "scripts" / "_snapshots"

# --- re-homes / primary links: (entity_id, name guard, target leaf) -----------
_REHOME: tuple[tuple[str, str, str], ...] = (
    ("828634b1-f1cb-44d7-a549-f838b74488dd", "shooters outpost", "firearms-and-shooting-sports"),
    ("d92b35ad-561d-49f3-82e4-40ee5a0b9e7d", "pro tech rv", "rv-sales-and-service"),
    ("3d0f1bb3-f2bc-44c1-b338-e7046793084d", "first class rv", "rv-sales-and-service"),
    ("c2bc1af6-4f62-468e-b181-9ee83a5b3115", "sunshine rv", "rv-sales-and-service"),
    ("293c5ffe-2db4-4101-b1f6-69f159c7e10f", "desert rv werks", "rv-sales-and-service"),
    ("47535c83-2646-4a73-a27c-2045449dd466", "byrd", "rv-sales-and-service"),
    ("124f4450-9ab8-4fdc-ad8d-e2eb0c278438", "bartlett", "handyman"),
    ("4e8ae129-59fc-4d02-bbab-64f9eb855182", "shaver", "garage-doors"),
    ("a522df02-31ce-4996-b2ab-62576a7b5c9a", "integrity garage door", "garage-doors"),
    ("42f25728-4baa-474a-8e27-220fdfbfb36c", "river city music", "music-lessons"),
    ("4aababfb-2739-4ac2-b3e1-4b9a0ff8362a", "bump city", "music-lessons"),
    ("b7bb18a1-bdf4-4921-85d8-51ebbe2d4d18", "grand piano", "music-lessons"),
    ("b271afca-d5d1-4057-81ab-683dbccdd31b", "big o tire", "tires"),
    ("1fd0961c-d67a-4967-84e9-a3b92732b75b", "everything tire", "tires"),
    ("7800dc5c-1fb7-46a1-b7ec-4ba4f7d412ab", "aqua beginnings", "kids-classes-and-camps"),
    ("a22385a0-0c35-47e2-94a6-0e87fc1dbadf", "integrity arizona vacation", "vacation-rentals"),
    ("cd7b96f2-0e93-439a-b486-44ba5dbfda4f", "pmi lake havasu", "vacation-rentals"),
    ("70d4cfb7-da78-4a26-b13e-706e4568512e", "havasu realty property management",
     "property-management"),
    ("e36a0b71-a2a5-4464-becf-e8c1a64e40e3", "humane society medical clinic", "veterinarians"),
    ("0f686ef8-8924-47d8-b58a-3b98976313c4", "lighthouses", "landmarks-and-sights"),
)

# Pool-supply orphans, matched by name pattern (guard = same string lowered).
_REHOME_BY_NAME: tuple[tuple[str, str], ...] = (
    ("Reinhard Pool & Spa", "pools-and-spas"),
    ("KRT Pool Care", "pools-and-spas"),
    ("Bliss Pool Care", "pools-and-spas"),
)

# --- dup twins to retire: (provider_id prefix, name guard, reason) ------------
_DEACTIVATE_DUPS: tuple[tuple[str, str, str], ...] = (
    ("54fd3779", "byrd's mobile rv & marine repair", "same-phone twin of the kept Byrd's row"),
    ("16aaaecf", "integrity garage door repair", "phoneless twin; the LLC row keeps the leaf"),
    ("d50caedb", "first choice property vacation rentals",
     "parent First Choice row already renders on vacation-rentals"),
)

# --- enrichment (fill empty fields only): (provider_id prefix, guard, fields) --
_ENRICH: tuple[tuple[str, str, dict], ...] = (
    ("5c5ebd84", "shooters outpost", {
        "address": "2183 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        "website": "http://www.samsguns.com/",
        "description": "Sam's Shooters Emporium — gun store and the longest "
                       "indoor shooting range in western Arizona.",
    }),
    ("1f7515d5", "integrity arizona vacation", {"phone": "(928) 846-4080"}),
    ("a56c9386", "pmi lake havasu", {"phone": "(928) 412-6925"}),
)

# --- secondary cross-links (never primary): (entity_id, guard, leaf) -----------
_CROSSLINK: tuple[tuple[str, str, str], ...] = (
    ("2fe04819-5241-4866-804d-b5c74f5741ef", "prima medical", "med-spas-and-aesthetics"),
    ("5cee611a-83b5-4153-993f-5d2d5864077b", "express health", "med-spas-and-aesthetics"),
)

# --- inserts (verified-current; every one cross-checked absent) ---------------
# (name, leaf_slug, legacy_category, subcategory, address, phone, website, description)
_INSERTS: tuple[tuple[str, str, str, str, str | None, str | None, str | None, str | None], ...] = (
    ("Southwest Firearms", "firearms-and-shooting-sports", "retail", "specialty",
     "2148 McCulloch Blvd N Ste 101, Lake Havasu City, AZ 86403", "(928) 680-0000", None, None),
    ("Goliath Industries", "firearms-and-shooting-sports", "retail", "specialty",
     "5691 Hwy 95 N, Lake Havasu City, AZ 86404", "(928) 764-4646", None, None),
    ("Zeeman's Gunworks", "firearms-and-shooting-sports", "retail", "specialty",
     "4063 Little Finger Rd, Lake Havasu City, AZ 86406", "(928) 855-4213", None, None),
    ("Dzuro's Guns & Accessories", "firearms-and-shooting-sports", "retail", "specialty",
     "2100 College Dr #124, Lake Havasu City, AZ 86403", "(928) 889-1329", None, None),
    ("Hav-A-Handyman", "handyman", "home_services", "handyman",
     None, "(928) 351-8939", None, None),
    ("Handy Andy's", "handyman", "home_services", "handyman",
     None, "(928) 412-6806", None, None),
    ("Havasu Remodeling & Handyman", "handyman", "home_services", "handyman",
     None, "(928) 706-9745", None, None),
    ("TCS Handyman", "handyman", "home_services", "handyman",
     None, "(928) 733-0586", None, None),
    ("Just Garage Doors & More", "garage-doors", "home_services", "garage-doors",
     None, "(928) 855-6331", None, None),
    ("Superior Garage Doors LHC", "garage-doors", "home_services", "garage-doors",
     None, "(928) 208-0429", None, None),
    ("Sonora Quest Laboratories", "medical-specialists-and-imaging", "health_medical",
     "health-medical", "1964 Mesquite Ave, Lake Havasu City, AZ 86403",
     "(928) 854-6943", None, "Medical lab: blood work and diagnostic testing."),
    ("Labcorp", "medical-specialists-and-imaging", "health_medical", "health-medical",
     "2082 Mesquite Ave Ste 114, Lake Havasu City, AZ 86403", "(928) 855-4077",
     None, "Medical lab: blood work and diagnostic testing."),
    ("Havasu Regional Medical Center Outpatient Lab", "medical-specialists-and-imaging",
     "health_medical", "health-medical", None, "(928) 453-1003", None,
     "Hospital outpatient lab draws."),
    ("Havasu Rental Homes", "vacation-rentals", "lodging", "vacation-rentals",
     None, "(928) 854-7210", None, "Vacation-rental and property management."),
    ("Sculpted MD", "med-spas-and-aesthetics", "beauty_personal_care", "med-spas",
     None, "(928) 302-9853", None, "Medical weight loss and wellness."),
    ("Steelhead Aquatics", "kids-classes-and-camps", "childcare_education", "kids-classes",
     None, None, "https://www.facebook.com/SteelheadAquatics/",
     "Private in-home swim lessons for all ages (Candis' Swim Lessons)."),
    ("Leslie's Pool Supplies", "pools-and-spas", "retail", "specialty",
     "1850 McCulloch Blvd N Ste C6, Lake Havasu City, AZ 86403", "(928) 453-9200",
     "https://lesliespool.com/", "Pool supplies, chemicals, and equipment."),
    ("Good Vibez Havasu", "jet-ski-and-watersports", "lake_recreation", "watersports",
     None, None, "https://goodvibezhavasu.com/",
     "Captained wake surf charters on a 2022 MasterCraft NXT20."),
)


def _leaf(db, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug, Category.level == 1).first()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase-5 search-gap backfills (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"PHASE-5 SEARCH-GAP BACKFILLS — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    snap: dict = {"generated_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  "db": redacted, "rehomes": [], "dedups": [], "enrich": [],
                  "crosslinks": [], "inserts": []}

    with SessionLocal() as db:
        for dep in ("firearms-and-shooting-sports", "medical-specialists-and-imaging"):
            if _leaf(db, dep) is None:
                print(f"NOTE: leaf {dep!r} absent — run "
                      "apply_search_data_ops_2026_07_01.py first; its items SKIP below.\n")

        print("--- 1 re-homes / primary links (old membership kept as secondary) ---")
        rehome_plans: list[dict] = []

        def _plan_rehome(eid: str, guard: str, target_slug: str) -> None:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP  {eid[:8]}: missing or name mismatch ({guard!r})")
                return
            target = _leaf(db, target_slug)
            if target is None:
                print(f"  SKIP  {ent.name!r}: target leaf {target_slug!r} absent")
                return
            prim = db.query(EntityCategory).filter_by(
                entity_id=eid, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            if cur is not None and cur.slug == target_slug:
                print(f"  OK  {ent.name!r}: already on {target_slug}")
                return
            print(f"  MOVE  {ent.name[:46]:46s} | {(cur.slug if cur else '(none)'):22s} -> {target_slug}")
            rehome_plans.append({"entity_id": eid, "name": ent.name,
                                 "prim_ec_id": prim.id if prim else None,
                                 "from_slug": cur.slug if cur else None,
                                 "to_id": target.id, "to_slug": target_slug})

        for eid, guard, target_slug in _REHOME:
            _plan_rehome(eid, guard, target_slug)
        for name, target_slug in _REHOME_BY_NAME:
            provs = db.query(Provider).filter(
                Provider.provider_name.ilike(f"%{name}%"),
                Provider.is_active.is_(True)).all()
            if not provs:
                print(f"  SKIP  {name!r}: no active rows")
            for p in provs:
                if p.entity_id:
                    _plan_rehome(p.entity_id, name.lower().split()[0], target_slug)
        snap["rehomes"] = rehome_plans

        print("\n--- 2 dup twins to retire ---")
        dedup_rows = []
        for prefix, guard, reason in _DEACTIVATE_DUPS:
            row = db.query(Provider).filter(
                Provider.id.like(f"{prefix}%"), Provider.is_active.is_(True)).first()
            if row is None or guard not in (row.provider_name or "").lower():
                print(f"  SKIP  {prefix}: not found / name mismatch / already inactive")
                continue
            print(f"  DEACTIVATE  {row.provider_name[:46]:46s} | {reason}")
            dedup_rows.append(row)
        snap["dedups"] = [r.id for r in dedup_rows]

        print("\n--- 3 enrichment (fill empty fields only) ---")
        enrich_rows = []
        for prefix, guard, fields in _ENRICH:
            row = db.query(Provider).filter(Provider.id.like(f"{prefix}%")).first()
            if row is None or guard not in (row.provider_name or "").lower():
                print(f"  SKIP  {prefix}: not found / name mismatch")
                continue
            todo = {k: v for k, v in fields.items() if not (getattr(row, k) or "").strip()}
            if not todo:
                print(f"  OK  {row.provider_name!r}: nothing empty to fill")
                continue
            print(f"  FILL  {row.provider_name[:40]:40s} | {', '.join(todo)}")
            enrich_rows.append((row, todo))
        snap["enrich"] = [{"id": r.id, "fields": list(t)} for r, t in enrich_rows]

        print("\n--- 4 secondary cross-links ---")
        crosslinks = []
        for eid, guard, target_slug in _CROSSLINK:
            ent = db.get(Entity, eid)
            target = _leaf(db, target_slug)
            if ent is None or guard not in (ent.name or "").lower() or target is None:
                print(f"  SKIP  {eid[:8]}: missing / mismatch / leaf absent")
                continue
            existing = db.query(EntityCategory).filter_by(
                entity_id=eid, category_id=target.id).one_or_none()
            if existing is not None:
                print(f"  OK  {ent.name!r}: already linked to {target_slug}")
                continue
            print(f"  LINK  {ent.name[:40]:40s} +-> {target_slug} (secondary)")
            crosslinks.append({"entity_id": eid, "to_id": target.id})
        snap["crosslinks"] = crosslinks

        print("\n--- 5 inserts (verified-current; all cross-checked absent) ---")
        insert_rows = []
        with db.no_autoflush:
            for name, leaf_slug, legacy, subcat, address, phone, website, desc in _INSERTS:
                slug = slugify(name)
                leaf = _leaf(db, leaf_slug)
                if leaf is None:
                    print(f"  SKIP  {name}: leaf {leaf_slug!r} absent (dependency)")
                    continue
                if db.scalar(select(Provider).where(Provider.slug == slug)) is not None:
                    print(f"  SKIP  {name}: already exists (slug {slug})")
                    continue
                print(f"  INSERT  {name[:38]:38s} -> {leaf_slug:32s} | {phone or website or '(contact tbd)'}")
                insert_rows.append((name, leaf.id, legacy, subcat, address, phone, website, desc, slug))
        snap["inserts"] = [r[0] for r in insert_rows]

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        tag = "apply" if writing else "dryrun"
        snap_path = _SNAP_DIR / f"search_gaps_2026_07_01_snapshot_{tag}_{snap['generated_utc']}.json"
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {snap_path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        # ---- write ----
        for plan in rehome_plans:
            prim = db.get(EntityCategory, plan["prim_ec_id"]) if plan["prim_ec_id"] else None
            if prim is not None:
                prim.is_primary = False
            existing = db.query(EntityCategory).filter_by(
                entity_id=plan["entity_id"], category_id=plan["to_id"]).one_or_none()
            if existing is not None:
                existing.is_primary = True
            else:
                db.add(EntityCategory(entity_id=plan["entity_id"],
                                      category_id=plan["to_id"], is_primary=True))

        for row in dedup_rows:
            row.is_active = False
            ent = db.get(Entity, row.entity_id) if row.entity_id else None
            if ent is not None:
                ent.is_active = False

        for row, todo in enrich_rows:
            for k, v in todo.items():
                setattr(row, k, v)

        for link in crosslinks:
            db.add(EntityCategory(entity_id=link["entity_id"],
                                  category_id=link["to_id"], is_primary=False))

        with db.no_autoflush:
            for name, leaf_id, legacy, subcat, address, phone, website, desc, slug in insert_rows:
                db.add(Provider(
                    provider_name=name, category=legacy, subcategory=subcat,
                    category_id=leaf_id, address=address, phone=phone,
                    website=website, description=desc, slug=slug,
                    source=BACKFILL_SOURCE, draft=False, is_active=True,
                ))

        db.commit()
        print("\nAPPLIED. Reversible from the snapshot; inserted rows carry "
              f"source={BACKFILL_SOURCE!r}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
