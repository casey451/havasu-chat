"""Apply the 2026-07-01 consolidated Phase-3 data ops (dry-run default; gated).

Scope = the CLEAR-CUT, reversible subset of PROMPT_CC_SEARCH_CONSOLIDATED
Amendment 1, Phase 3 (master audit = ASKHAVA_FULL_SITE_AUDIT_2026-07-01_MASTER):

  1-seed      Create the three leaves the Phase-2 routing targets:
              firearms-and-shooting-sports (Shopping & Retail),
              medical-specialists-and-imaging + pediatrics (Health & Medical).
  2-rehome    Repoint PRIMARY entity_categories links (old membership kept as a
              secondary link, so nothing loses history):
                * primary-care specialists -> medical-specialists-and-imaging /
                  pediatrics (computed by the same signal regexes as the audit
                  script; ~15 rows incl. Lakeside Heart & Vascular, Advanced
                  Women's Care, Az Coast Radiology, Havasu Pediatrics).
                * Shooters Outpost (browse-orphan) -> firearms leaf.
                * Custom T'z Recovery Store -> gifts-and-boutiques (was Mental
                  Health).
                * Hava Math Tutor -> tutoring-and-test-prep (surfaces it there;
                  kids-classes link kept).
  3-remove    Deactivate two non-businesses the 06-30 pass could not hold down
              (the re-scrape reactivated the Marine Program row within a day):
              Marine Association Designated Operator Program + Outdoor
              Enthusiasts. The durable ingest blocklist entries ship in the
              same PR (app/contrib/ingest_suppression.py), so this sticks.
  4-address   Null the "Go Lake Havasu Visitor Center" placeholder address on
              every ACTIVE Provider row + every Location row still carrying it
              (display-only; businesses stay active).
  5-events    Deduplicate live events sharing (normalized title, date,
              start_time, venue): keep the richest row, flip the twins'
              status live -> deleted (the permitted retire value).
  6-dedup     The 5 phone/address-VERIFIED provider duplicate pairs from the
              master audit (NextCare, Studio 6, Holiday Inn Express, Integrity
              Arizona, First Choice Property): keep the richest row, deactivate
              the twin. A twin is only touched when it shares a phone or street
              address with the keeper, or has neither to its name.

DELIBERATELY NOT here (blocked on [ASK]s / their own pass):
  * Out-of-area class B (~25 rows) — [ASK #8] tag-vs-purge.
  * Dead practitioner twins class C (~35) — [ASK #9] 410 policy.
  * The ~20 same-name clusters beyond the 5 verified pairs — each needs a check.
  * Ghost-listing enrichment (needs external ground-truthing).
  * Wake Surf Adventures reinstatement — [ASK #7].
  * HavaLife CPR + Stingrays/Steelhead — rows do not exist in prod (verified).

Every change is snapshotted to scripts/_snapshots/ for a manual undo; entity
targets carry name guards so a mismatched DB SKIPS rather than mutating.

Usage:
    .venv\\Scripts\\python.exe scripts/apply_search_data_ops_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/apply_search_data_ops_2026_07_01.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.ingest_suppression import is_placeholder_address  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    Entity,
    EntityCategory,
    Event,
    Location,
    Provider,
)

_SNAP_DIR = _ROOT / "scripts" / "_snapshots"

# --- 1-seed ------------------------------------------------------------------
_SEED_LEAVES: tuple[tuple[str, str, str], ...] = (
    ("firearms-and-shooting-sports", "Firearms & Shooting Sports", "shopping-and-retail"),
    ("medical-specialists-and-imaging", "Medical Specialists & Imaging", "health-and-medical"),
    ("pediatrics", "Pediatrics", "health-and-medical"),
)

# --- 2-rehome (same signal regexes as the audit script) ----------------------
_SPECIALIST_RE = re.compile(
    r"heart|vascular|cardio|obgyn|obstetric|gynecol|women'?s|podiat|\bdpm\b|"
    r"foot\s*(?:&|and)\s*ankle|urolog|oncolog|orthoped|imaging|radiolog|"
    r"neurolog|\bent\b|ear,?\s*nose",
    re.IGNORECASE,
)
_PEDIATRIC_RE = re.compile(r"pediatric|paediatric", re.IGNORECASE)

# Explicit re-homes: (name ilike pattern, name guard substring, target slug).
_EXPLICIT_REHOME: tuple[tuple[str, str, str], ...] = (
    ("Shooters Outpost%", "shooters outpost", "firearms-and-shooting-sports"),
    ("%Custom T%Recovery%", "custom t", "gifts-and-boutiques"),
    ("Hava Math Tutor%", "hava math", "tutoring-and-test-prep"),
)

# --- 3-remove — (entity_id, name-guard substring) -----------------------------
_DEACTIVATE: tuple[tuple[str, str], ...] = (
    ("6372a690-ee2e-4d6d-96cb-abea8a4609d3", "designated operator program"),
    ("bca905d9-d4ff-4cc0-946c-95f495bb48a2", "outdoor enthusiasts"),
)

# --- 6-dedup — verified pairs, matched by name fragment -----------------------
_DEDUP_FRAGMENTS: tuple[str, ...] = (
    "NextCare Urgent Care",
    "Studio 6",
    "Holiday Inn Express",
    "Integrity Arizona",
    "First Choice Property",
)

_PHONE_DIGITS = re.compile(r"\d")
_WS = re.compile(r"\s+")


def _norm_phone(phone: str | None) -> str:
    digits = "".join(_PHONE_DIGITS.findall(phone or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _norm_text(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


_STREET_CORE = re.compile(
    r"^(\d+\s+[a-z0-9\s]*?\b(?:ave|avenue|blvd|boulevard|st|street|dr|drive|rd|"
    r"road|ln|lane|way|pkwy|parkway|hwy|highway|cir|circle|ct|court|pl|plaza))\b"
)


def _street(address: str | None) -> str:
    """Number + street-name core, suite/unit markers dropped, so
    '1810 Mesquite Ave Ste B' and '1810 Mesquite Ave # B, Lake Havasu…'
    compare equal."""
    line = _norm_text((address or "").split(",", 1)[0])
    m = _STREET_CORE.match(line)
    return m.group(1).strip() if m else line


def _leaf(db, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug, Category.level == 1).first()


def _richness(p: Provider) -> tuple:
    """Keeper score for a duplicate cluster: most data wins, stable tiebreak."""
    return (
        p.google_rating is not None,
        p.google_review_count or 0,
        bool((p.address or "").strip()),
        bool((p.phone or "").strip()),
        len(p.description or ""),
        p.id,
    )


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------


def _plan_seed(db) -> list[dict]:
    plans = []
    for slug, name, dept_slug in _SEED_LEAVES:
        if db.query(Category).filter(Category.slug == slug).first() is not None:
            print(f"  OK seed {slug}: already exists")
            continue
        dept = db.query(Category).filter(
            Category.slug == dept_slug, Category.level == 0).first()
        if dept is None:
            print(f"  SKIP seed {slug}: department {dept_slug!r} not found")
            continue
        plans.append({"slug": slug, "name": name, "dept_slug": dept_slug,
                      "dept_id": dept.id})
    return plans


def _plan_specialists(db) -> list[dict]:
    pc = db.query(Category).filter(Category.slug == "primary-care").first()
    if pc is None:
        print("  SKIP specialists: primary-care leaf not found")
        return []
    plans = []
    for ec in db.query(EntityCategory).filter(
            EntityCategory.category_id == pc.id, EntityCategory.is_primary.is_(True)).all():
        ent = db.get(Entity, ec.entity_id)
        if ent is None or not ent.is_active:
            continue
        name = ent.name or ""
        if _SPECIALIST_RE.search(name):
            target = "medical-specialists-and-imaging"
        elif _PEDIATRIC_RE.search(name):
            target = "pediatrics"
        else:
            continue
        plans.append({"entity_id": ent.id, "name": name, "prim_ec_id": ec.id,
                      "from_slug": "primary-care", "to_slug": target})
    return plans


def _plan_explicit_rehomes(db) -> list[dict]:
    plans = []
    for pattern, guard, target in _EXPLICIT_REHOME:
        provs = db.query(Provider).filter(
            Provider.provider_name.ilike(pattern), Provider.is_active.is_(True)).all()
        ents = {p.entity_id for p in provs if p.entity_id}
        if not ents:
            print(f"  SKIP rehome {pattern!r}: no active rows")
            continue
        for eid in sorted(ents):
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP rehome {pattern!r}: entity {eid} name mismatch")
                continue
            prim = db.query(EntityCategory).filter_by(
                entity_id=eid, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            if cur is not None and cur.slug == target:
                print(f"  OK rehome {ent.name!r}: already on {target}")
                continue
            plans.append({"entity_id": eid, "name": ent.name,
                          "prim_ec_id": prim.id if prim else None,
                          "from_slug": cur.slug if cur else "(none)",
                          "to_slug": target})
    return plans


def _plan_deactivate(db) -> list[dict]:
    plans = []
    for eid, guard in _DEACTIVATE:
        ent = db.get(Entity, eid)
        if ent is None or guard not in (ent.name or "").lower():
            print(f"  SKIP deactivate {eid}: missing or name mismatch")
            continue
        if not ent.is_active:
            print(f"  OK deactivate {ent.name!r}: already inactive")
            continue
        provs = db.query(Provider).filter(Provider.entity_id == eid).all()
        plans.append({"entity_id": eid, "name": ent.name,
                      "provider_ids": [p.id for p in provs],
                      "provider_was_active": {p.id: p.is_active for p in provs}})
    return plans


def _plan_addresses(db) -> dict:
    # The CVB's own row legitimately lives at the visitor center — exempt it.
    prov_hits = [p for p in db.query(Provider).filter(Provider.is_active.is_(True)).all()
                 if is_placeholder_address(p.address)
                 and "go lake havasu" not in _norm_text(p.provider_name)
                 and "visitor center" not in _norm_text(p.provider_name)]
    loc_hits = [loc for loc in db.query(Location).all()
                if is_placeholder_address(loc.address)
                or is_placeholder_address(loc.address_normalized)]
    return {
        "providers": [{"id": p.id, "name": p.provider_name, "old_address": p.address}
                      for p in prov_hits],
        "locations": [{"id": loc.id, "entity_id": loc.entity_id, "old_address": loc.address,
                       "old_address_normalized": loc.address_normalized}
                      for loc in loc_hits],
    }


def _plan_event_dedup(db) -> list[dict]:
    by_key: dict[tuple, list[Event]] = defaultdict(list)
    for ev in db.query(Event).filter(Event.status == "live").all():
        key = (_norm_text(ev.title), ev.date, ev.start_time, _norm_text(ev.location_name))
        by_key[key].append(ev)
    plans = []
    for key, evs in by_key.items():
        if len(evs) < 2:
            continue
        evs.sort(key=lambda e: (len(e.description or ""), str(e.created_at or ""), e.id),
                 reverse=True)
        keeper, twins = evs[0], evs[1:]
        plans.append({"title": keeper.title, "date": str(key[1]), "keep_id": keeper.id,
                      "delete_ids": [e.id for e in twins]})
    return plans


def _plan_provider_dedup(db) -> list[dict]:
    plans = []
    for frag in _DEDUP_FRAGMENTS:
        rows = db.query(Provider).filter(
            Provider.provider_name.ilike(f"%{frag}%"),
            Provider.is_active.is_(True), Provider.draft.is_(False)).all()
        if len(rows) < 2:
            print(f"  OK dedup {frag!r}: {len(rows)} active row(s) — nothing to do")
            continue
        rows.sort(key=_richness, reverse=True)
        keeper, rest = rows[0], rows[1:]
        k_phone, k_street = _norm_phone(keeper.phone), _street(keeper.address)
        twins = []
        for t in rest:
            shares_phone = _norm_phone(t.phone) and _norm_phone(t.phone) == k_phone
            shares_street = _street(t.address) and _street(t.address) == k_street
            contactless = not (t.phone or "").strip() and not (t.address or "").strip()
            if "vacation rental" in _norm_text(t.provider_name):
                # Cross-flagged rows: the master audit lists the VR-named twins
                # BOTH as dupes (§3.1) and as class-A recategorization
                # candidates for the thin vacation-rentals leaf (§4.1). Hold
                # them for Casey instead of auto-retiring a potential listing.
                print(f"  HOLD dedup {t.provider_name!r}: VR-named twin — "
                      "cross-flagged as a vacation-rentals recat candidate ([ASK])")
                continue
            if shares_phone or shares_street or contactless:
                twins.append({"id": t.id, "entity_id": t.entity_id,
                              "name": t.provider_name,
                              "evidence": ("phone" if shares_phone
                                           else "address" if shares_street
                                           else "contactless twin")})
            else:
                print(f"  HOLD dedup {t.provider_name!r}: no shared phone/address "
                      f"with keeper {keeper.provider_name!r} — left alone")
        if twins:
            plans.append({"fragment": frag, "keep_id": keeper.id,
                          "keep_name": keeper.provider_name,
                          "keep_phone": keeper.phone, "twins": twins})
    return plans


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply consolidated Phase-3 data ops (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE the changes (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required alongside --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"CONSOLIDATED PHASE-3 DATA OPS — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        print("--- 1 seed leaves ---")
        seeds = _plan_seed(db)
        for s in seeds:
            print(f"  CREATE  {s['slug']:36s} under {s['dept_slug']}")

        print("\n--- 2 re-homes (primary link repoint; old membership kept) ---")
        specialists = _plan_specialists(db)
        for p in specialists:
            print(f"  MOVE  {p['name'][:44]:44s} | primary-care -> {p['to_slug']}")
        explicit = _plan_explicit_rehomes(db)
        for p in explicit:
            print(f"  MOVE  {p['name'][:44]:44s} | {p['from_slug']} -> {p['to_slug']}")

        print("\n--- 3 deactivate non-businesses (blocklist ships in this PR) ---")
        deacts = _plan_deactivate(db)
        for d in deacts:
            print(f"  DEACTIVATE  {d['name'][:56]} (+{len(d['provider_ids'])} provider rows)")

        print("\n--- 4 null placeholder addresses ---")
        addrs = _plan_addresses(db)
        print(f"  provider rows: {len(addrs['providers'])}   location rows: {len(addrs['locations'])}")

        print("\n--- 5 event dedup (title, date, time, venue) ---")
        ev_plans = _plan_event_dedup(db)
        redundant = sum(len(p["delete_ids"]) for p in ev_plans)
        for p in ev_plans[:20]:
            print(f"  x{1 + len(p['delete_ids'])}  {p['date']}  {(p['title'] or '')[:52]}")
        if len(ev_plans) > 20:
            print(f"  … +{len(ev_plans) - 20} more clusters")
        print(f"  clusters: {len(ev_plans)} — rows to retire: {redundant}")

        print("\n--- 6 verified provider dedup pairs ---")
        dedups = _plan_provider_dedup(db)
        for p in dedups:
            for t in p["twins"]:
                print(f"  DEACTIVATE  {t['name'][:44]:44s} | keep {p['keep_name'][:34]:34s} "
                      f"| evidence: {t['evidence']}")

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tag = "apply" if writing else "dryrun"
        snap_path = _SNAP_DIR / f"search_data_ops_2026_07_01_snapshot_{tag}_{stamp}.json"
        snap = {"generated_utc": stamp, "db": redacted, "seed": seeds,
                "specialists": specialists, "explicit_rehomes": explicit,
                "deactivate": deacts, "addresses": addrs,
                "event_dedup": ev_plans, "provider_dedup": dedups}
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {snap_path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written to the DB. "
                  "Re-run with --apply --confirm (after approval).")
            return 0

        # ---- write ----
        leaf_ids: dict[str, int] = {}
        for s in seeds:
            sibs = db.query(Category).filter(Category.parent_id == s["dept_id"]).all()
            next_sort = max((c.sort_order or 0 for c in sibs), default=0) + 1
            leaf = Category(slug=s["slug"], name=s["name"], level=1,
                            parent_id=s["dept_id"], sort_order=next_sort)
            db.add(leaf)
            db.flush()
            leaf_ids[s["slug"]] = leaf.id

        def _repoint(entity_id: str, prim_ec_id: int | None, to_slug: str) -> None:
            target = _leaf(db, to_slug)
            target_id = leaf_ids.get(to_slug) or (target.id if target else None)
            if target_id is None:
                print(f"  SKIP write rehome {entity_id}: target {to_slug!r} missing")
                return
            existing = db.query(EntityCategory).filter_by(
                entity_id=entity_id, category_id=target_id).one_or_none()
            prim = db.get(EntityCategory, prim_ec_id) if prim_ec_id else None
            if prim is not None:
                prim.is_primary = False  # old membership kept as secondary
            if existing is not None:
                existing.is_primary = True
            else:
                db.add(EntityCategory(entity_id=entity_id, category_id=target_id,
                                      is_primary=True))

        for p in specialists:
            _repoint(p["entity_id"], p["prim_ec_id"], p["to_slug"])
        for p in explicit:
            _repoint(p["entity_id"], p["prim_ec_id"], p["to_slug"])

        for d in deacts:
            ent = db.get(Entity, d["entity_id"])
            if ent is not None:
                ent.is_active = False
            for pid in d["provider_ids"]:
                pr = db.get(Provider, pid)
                if pr is not None:
                    pr.is_active = False

        for row in addrs["providers"]:
            pr = db.get(Provider, row["id"])
            if pr is not None:
                pr.address = None
        for row in addrs["locations"]:
            loc = db.get(Location, row["id"])
            if loc is not None:
                loc.address = None
                loc.address_normalized = None

        for p in ev_plans:
            for eid in p["delete_ids"]:
                ev = db.get(Event, eid)
                if ev is not None:
                    ev.status = "deleted"

        for p in dedups:
            for t in p["twins"]:
                pr = db.get(Provider, t["id"])
                if pr is not None:
                    pr.is_active = False
                if t["entity_id"]:
                    ent = db.get(Entity, t["entity_id"])
                    if ent is not None:
                        ent.is_active = False

        db.commit()
        print("\nAPPLIED. Reversible from the snapshot above.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
