"""Phase-4 rental categories: leaves, re-homes, publishes, verified adds (gated).

Consolidated plan Phase 4 + Casey's 2026-07-01 [ASK] answers (#5 bikes dept =
Outdoors/Things-to-Do; #5 RV = fold into rv-sales-and-service; #7 Wake Surf
Adventures = reinstate; #8 out-of-area = tag + exclude via ``is_local``).
Grounded in a live prod recon (2026-07-01 PM) — several planned "adds" turned
out to already exist and became re-homes/publishes instead:

  1-leaves    Create ``bikes-and-e-bikes`` + ``utv-and-offroad-rentals`` under
              Things to Do & Attractions (off-road-and-ohv's department).
  2-rehome    Primary link repoint (old membership kept as secondary):
                * Desert Experience UTV Offroad Rentals  powersports -> utv leaf
                * Wet Monkey Powersport Rentals          powersports -> utv leaf
                * Bee's Rentals (zero links today)       (none)      -> utv leaf
                * Cycle Therapy Bike & E-bike Shop       sporting-goods -> bikes
  3-dedup     Deactivate the phoneless, leafless orphan twin
              "Desert Experience Offroad Rentals" (the attributed row stays).
  4-publish   Lake Havasu Bike & Fitness is an unfinished admin DRAFT with real
              address+phone — publish it (draft off, active on) onto the bikes
              leaf.
  5-insert    Verified-current operators absent from the catalog:
              Havasu E-Bikes (bikes), Lake Havasu Houseboats / Lake Havasu
              Party Boat / VIP Cabana Boats (boat-and-watercraft-rentals),
              Lake Havasu RV & Boat Rentals (rv-sales-and-service).
  6-wsa       Reinstate Wake Surf Adventures ([ASK #7]): reactivate the
              REAL-phone row (928-361-0540), attribute website + description,
              add a boat-tours-and-charters secondary link. The CVB-phone twin
              stays dead. (The ingest unblocklist ships in this PR's code, so
              apply promptly after merge — the daily re-scrape matches by name.)
  7-ooa       [ASK #8]: set ``is_local = False`` on ACTIVE rows whose address
              carries an out-of-area locality and is_local is still NULL —
              leaf/search/home/chat surfaces all honor the flag.
  8-premier   Ensure Premier Golf Cars' description notes rentals are
              resort-guest-only (plan 4.1).

HELD (not here): Adrenaline RZR — the plan's phone (928) 680-1030 belongs to
ADRENALINE TRAILERS in the catalog; needs re-confirmation before any row is
made. Sunn Slide Beach Rentals — no contact data verified; adding it would
mint a render-level ghost. Southwest Outfitters — stays a sporting-goods
primary (leaf surfaces read primary links only; its rental claim unconfirmed).

Usage:
    .venv\\Scripts\\python.exe scripts/backfill_rentals_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/backfill_rentals_2026_07_01.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import re
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

BACKFILL_SOURCE = "rentals_backfill_2026_07_01"
_SNAP_DIR = _ROOT / "scripts" / "_snapshots"
_DEPT_SLUG = "things-to-do-and-attractions"

_NEW_LEAVES: tuple[tuple[str, str], ...] = (
    ("bikes-and-e-bikes", "Bikes & E-Bikes"),
    ("utv-and-offroad-rentals", "UTV & Off-Road Rentals"),
)

# (entity_id, name guard, target leaf slug)
_REHOME: tuple[tuple[str, str, str], ...] = (
    ("b6f24d09-4e98-4868-b38d-f2a49830dcd2", "desert experience", "utv-and-offroad-rentals"),
    ("3b6df1d7-695f-4867-a69f-10ebf0491465", "wet monkey", "utv-and-offroad-rentals"),
    ("73ebdc15-98f6-44c5-911d-950b6a3f74bd", "bee's rentals", "utv-and-offroad-rentals"),
    ("6d096f0f-20fb-408c-8959-d3f871708974", "cycle therapy", "bikes-and-e-bikes"),
)

# Orphan twin to retire: (provider_id, name guard).
_DEDUP = ("fd8bb3cc", "desert experience offroad rentals")

# Draft to publish: (provider_id prefix, name guard, target leaf).
_PUBLISH = ("18fd72c9", "bike & fitness", "bikes-and-e-bikes")

# (name, leaf_slug, legacy_category, subcategory, address, phone, website, description)
_INSERTS: tuple[tuple[str, str, str, str, str | None, str | None, str | None, str | None], ...] = (
    ("Havasu E-Bikes", "bikes-and-e-bikes", "retail", "sporting-goods",
     None, "(928) 733-7820", None,
     "Delivery-based e-bike rentals around Lake Havasu City."),
    ("Lake Havasu Houseboats", "boat-and-watercraft-rentals", "boat_rental", "on-the-water",
     None, "(800) 843-9218", None,
     "Houseboat rentals on Lake Havasu."),
    ("Lake Havasu Party Boat", "boat-and-watercraft-rentals", "boat_rental", "on-the-water",
     None, "(928) 408-6878", None,
     "Captained party-boat charters on Lake Havasu."),
    ("VIP Cabana Boats", "boat-and-watercraft-rentals", "boat_rental", "on-the-water",
     None, "(928) 486-6951", None,
     "Cabana boat rentals on Lake Havasu."),
    ("Lake Havasu RV & Boat Rentals", "rv-sales-and-service", "auto", "rv-sales",
     None, "(928) 487-5600", None,
     "RV and boat rentals in Lake Havasu City."),
)

# Wake Surf Adventures reinstate ([ASK #7]).
_WSA_PROVIDER_PREFIX = "23c38057"
_WSA_GUARD = "wake surf adventures"
_WSA_WEBSITE = "https://wakesurfadventures.com"
_WSA_DESC = "Captained wake surf charters, boat rentals and boat tours on Lake Havasu."

_OUT_OF_AREA_RE = re.compile(
    r"\b(kingman|bullhead|parker|needles|laughlin|oatman|topock|golden shores|"
    r"fort mohave|mohave valley|yucca|peach springs|havasu landing)\b",
    re.IGNORECASE,
)

_PREMIER_GUARD = "premier golf cars"
_PREMIER_NOTE = "Golf car sales and service; rentals are available to resort guests only."


def _leaf(db, slug: str, created: dict[str, int]) -> int | None:
    if slug in created:
        return created[slug]
    row = db.query(Category).filter(Category.slug == slug, Category.level == 1).first()
    return row.id if row else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase-4 rentals backfill (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"PHASE-4 RENTALS BACKFILL — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    snap: dict = {"generated_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  "db": redacted}
    created: dict[str, int] = {}

    with SessionLocal() as db:
        dept = db.query(Category).filter(
            Category.slug == _DEPT_SLUG, Category.level == 0).first()
        if dept is None:
            print(f"ABORT: department {_DEPT_SLUG!r} not found")
            return 1

        print("--- 1 leaves ---")
        to_create = []
        for slug, name in _NEW_LEAVES:
            if db.query(Category).filter(Category.slug == slug).first() is not None:
                print(f"  OK  {slug}: already exists")
            else:
                print(f"  CREATE  {slug} under {_DEPT_SLUG}")
                to_create.append((slug, name))
        snap["leaves"] = [s for s, _ in to_create]

        if writing:
            for slug, name in to_create:
                sibs = db.query(Category).filter(Category.parent_id == dept.id).all()
                next_sort = max((c.sort_order or 0 for c in sibs), default=0) + 1
                leaf = Category(slug=slug, name=name, level=1,
                                parent_id=dept.id, sort_order=next_sort)
                db.add(leaf)
                db.flush()
                created[slug] = leaf.id

        print("\n--- 2 re-homes (primary repoint; old membership kept) ---")
        rehome_plans = []
        for eid, guard, target in _REHOME:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP  {eid[:8]}: missing or name mismatch ({guard!r})")
                continue
            prim = db.query(EntityCategory).filter_by(
                entity_id=eid, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            if cur is not None and cur.slug == target:
                print(f"  OK  {ent.name!r}: already on {target}")
                continue
            print(f"  MOVE  {ent.name[:44]:44s} | {(cur.slug if cur else '(none)'):22s} -> {target}")
            rehome_plans.append({"entity_id": eid, "name": ent.name,
                                 "prim_ec_id": prim.id if prim else None,
                                 "from_slug": cur.slug if cur else None, "to_slug": target})
        snap["rehomes"] = rehome_plans

        print("\n--- 3 dedup orphan twin ---")
        dd_prefix, dd_guard = _DEDUP
        twin = (db.query(Provider)
                .filter(Provider.id.like(f"{dd_prefix}%"), Provider.is_active.is_(True))
                .first())
        if twin is None or dd_guard not in (twin.provider_name or "").lower():
            print("  SKIP: orphan twin not found / name mismatch")
            twin = None
        else:
            print(f"  DEACTIVATE  {twin.provider_name!r} (phoneless, zero leaves)")
        snap["dedup_twin"] = twin.id if twin else None

        print("\n--- 4 publish draft ---")
        pub_prefix, pub_guard, pub_leaf = _PUBLISH
        draft = db.query(Provider).filter(Provider.id.like(f"{pub_prefix}%")).first()
        if draft is None or pub_guard not in (draft.provider_name or "").lower():
            print("  SKIP: draft row not found / name mismatch")
            draft = None
        else:
            print(f"  PUBLISH  {draft.provider_name!r} (draft->live) -> {pub_leaf}")
        snap["publish"] = draft.id if draft else None

        print("\n--- 5 inserts (verified operators) ---")
        insert_rows = []
        for name, leaf_slug, legacy, subcat, address, phone, website, desc in _INSERTS:
            slug = slugify(name)
            if db.scalar(select(Provider).where(Provider.slug == slug)) is not None:
                print(f"  SKIP  {name}: already exists (slug {slug})")
                continue
            print(f"  INSERT  {name[:36]:36s} -> {leaf_slug:28s} | {phone or '(no phone)'}")
            insert_rows.append((name, leaf_slug, legacy, subcat, address, phone, website, desc, slug))
        snap["inserts"] = [r[0] for r in insert_rows]

        print("\n--- 6 Wake Surf Adventures reinstate ([ASK #7]) ---")
        wsa = db.query(Provider).filter(Provider.id.like(f"{_WSA_PROVIDER_PREFIX}%")).first()
        if wsa is None or _WSA_GUARD not in (wsa.provider_name or "").lower():
            print("  SKIP: WSA row not found / name mismatch")
            wsa = None
        else:
            print(f"  REACTIVATE  {wsa.provider_name!r} (phone {wsa.phone}) + website + "
                  "description + boat-tours secondary link")
        snap["wsa"] = wsa.id if wsa else None

        print("\n--- 7 out-of-area is_local tagging ([ASK #8]) ---")
        ooa_rows = [p for p in db.query(Provider).filter(
                        Provider.is_active.is_(True), Provider.draft.is_(False)).all()
                    if _OUT_OF_AREA_RE.search(p.address or "") and p.is_local is None]
        for p in ooa_rows:
            m = _OUT_OF_AREA_RE.search(p.address or "")
            print(f"  TAG is_local=False  {(p.provider_name or '')[:44]:44s} [{m.group(0).title()}]")
        if not ooa_rows:
            print("  (none — every address-signal row already carries is_local=False)")
        snap["ooa_tagged"] = [p.id for p in ooa_rows]

        print("\n--- 8 Premier Golf Cars resort-only note ---")
        premier = db.query(Provider).filter(
            Provider.provider_name.ilike("%Premier Golf Car%"),
            Provider.is_active.is_(True)).first()
        premier_needs_note = bool(
            premier is not None
            and _PREMIER_GUARD in (premier.provider_name or "").lower()
            and "resort" not in (premier.description or "").lower()
        )
        if premier is None:
            print("  SKIP: Premier Golf Cars not found")
        elif premier_needs_note:
            print(f"  NOTE  {premier.provider_name!r}: add resort-guest-only rental note")
        else:
            print(f"  OK  {premier.provider_name!r}: description already notes it")
        snap["premier"] = premier.id if premier and premier_needs_note else None

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        tag = "apply" if writing else "dryrun"
        snap_path = _SNAP_DIR / f"rentals_backfill_2026_07_01_snapshot_{tag}_{snap['generated_utc']}.json"
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {snap_path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        # ---- write ----
        for plan in rehome_plans:
            target_id = _leaf(db, plan["to_slug"], created)
            if target_id is None:
                print(f"  SKIP write rehome {plan['name']!r}: target leaf missing")
                continue
            prim = db.get(EntityCategory, plan["prim_ec_id"]) if plan["prim_ec_id"] else None
            if prim is not None:
                prim.is_primary = False
            existing = db.query(EntityCategory).filter_by(
                entity_id=plan["entity_id"], category_id=target_id).one_or_none()
            if existing is not None:
                existing.is_primary = True
            else:
                db.add(EntityCategory(entity_id=plan["entity_id"],
                                      category_id=target_id, is_primary=True))

        if twin is not None:
            twin.is_active = False
            tw_ent = db.get(Entity, twin.entity_id) if twin.entity_id else None
            if tw_ent is not None:
                tw_ent.is_active = False

        if draft is not None:
            draft.draft = False
            draft.is_active = True
            d_ent = db.get(Entity, draft.entity_id) if draft.entity_id else None
            if d_ent is not None:
                d_ent.is_active = True
            target_id = _leaf(db, pub_leaf, created)
            if target_id is not None and d_ent is not None:
                prim = db.query(EntityCategory).filter_by(
                    entity_id=d_ent.id, is_primary=True).one_or_none()
                if prim is None:
                    db.add(EntityCategory(entity_id=d_ent.id,
                                          category_id=target_id, is_primary=True))
                else:
                    prim.category_id = target_id

        with db.no_autoflush:
            for name, leaf_slug, legacy, subcat, address, phone, website, desc, slug in insert_rows:
                target_id = _leaf(db, leaf_slug, created)
                if target_id is None:
                    print(f"  SKIP write insert {name}: leaf {leaf_slug!r} missing")
                    continue
                db.add(Provider(
                    provider_name=name, category=legacy, subcategory=subcat,
                    category_id=target_id, address=address, phone=phone,
                    website=website, description=desc, slug=slug,
                    source=BACKFILL_SOURCE, draft=False, is_active=True,
                ))

        if wsa is not None:
            wsa.is_active = True
            wsa.website = wsa.website or _WSA_WEBSITE
            if not (wsa.description or "").strip():
                wsa.description = _WSA_DESC
            w_ent = db.get(Entity, wsa.entity_id) if wsa.entity_id else None
            if w_ent is not None:
                w_ent.is_active = True
                tours = _leaf(db, "boat-tours-and-charters", created)
                if tours is not None:
                    link = db.query(EntityCategory).filter_by(
                        entity_id=w_ent.id, category_id=tours).one_or_none()
                    if link is None:
                        db.add(EntityCategory(entity_id=w_ent.id,
                                              category_id=tours, is_primary=False))

        for p in ooa_rows:
            p.is_local = False

        if premier is not None and premier_needs_note:
            base = (premier.description or "").strip()
            premier.description = f"{base} {_PREMIER_NOTE}".strip()

        db.commit()
        print("\nAPPLIED. Reversible from the snapshot above; inserted rows carry "
              f"source={BACKFILL_SOURCE!r}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
