"""Session 5 — Places to Stay cleanup: reversibly deactivate VR + out-of-area lodging.

Removes (soft, reversible) three buckets of lodging so "Places to Stay" keeps only
verified hotels/motels + RV parks/campgrounds. Keyed on the **EntityCategory
primary leaf** (``is_primary=True``), NOT the legacy ``Provider.subcategory`` string.

  Bucket A — the whole ``vacation-rentals`` leaf (straight deactivate).
  Bucket B — VR / property-mgmt MISFILED under ``hotels-and-motels`` (the batch-10
             classifier: not-a-real-hotel AND (OTA domain OR VR name-tell OR no
             street number); the real-hotel KEEP guard protects true hotels).
  Bucket C — OUT-OF-AREA lodging in ``hotels-and-motels`` or
             ``rv-parks-and-campgrounds`` (is_local IS FALSE, or region parker/
             laughlin-bullhead, or a name/address OOA match incl. Black Meadow /
             Havasu Springs).

Mirrors the gold-standard reversible deactivator ``scripts/apply_bogus_deactivation.py``:
DRY-RUN BY DEFAULT; ``--apply`` writes inside ONE transaction; ``--undo-csv`` emits
the manifest; ``--reactivate-from <undo.csv> --apply`` reverses. Skip-guards protect
anything verified / claimed / sponsored, and anything already inactive.

Deactivation convention (all prior ops): ``Entity.is_active=False`` + cascade each
``Provider.is_active=False``. Undo CSV schema: ``entity_id,name,provider_ids``.

No code/deploy needed: the emptied VR leaf auto-hides via the leaf-page gate and
"Places to Stay N" recomputes on the next deploy/restart (or ~1h cache TTL).

    .venv\\Scripts\\python.exe -m scripts.deactivate_places_to_stay_2026_07_05
    .venv\\Scripts\\python.exe -m scripts.deactivate_places_to_stay_2026_07_05 --apply --undo-csv undo_places_to_stay.csv
    .venv\\Scripts\\python.exe -m scripts.deactivate_places_to_stay_2026_07_05 --reactivate-from undo_places_to_stay.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Claim, Entity, EntityCategory, Provider  # noqa: E402

_VR_SLUG = "vacation-rentals"
_HOTELS_SLUG = "hotels-and-motels"
_RV_SLUG = "rv-parks-and-campgrounds"

# --- classifier (reused/extended from rehome_vacation_rentals_batch10_2026_06_27) ---
_STREET_NUM_RE = re.compile(r"\b\d{2,6}\s+[A-Za-z]")
# Explicit OTA/booking hosts (NO bare hotels.com/choicehotels — those are real chains).
_OTA_RE = re.compile(
    r"(vrbo|airbnb|expedia|bluepillow|despegar|booking\.com|rentalsunited|"
    r"vacasa|evolve|furnishedfinder|agoda|express-getaway|avrhavasu|"
    r"havasuvacationrentals)", re.IGNORECASE)
_VR_NAME_RE = re.compile(
    r"(retreat|oasis|villa|getaway|hideaway|casita|\bmi to\b|w/\s|home w/|"
    r"poolside|private pool|hot tub|swim spa|sleeps|game room|fire ?pit|"
    r"putting green|pet-friendly|vacation rental|xanadu|hacienda|home in la|"
    r"home with|home:|house with|luxury home|mtn view|water views|!)",
    re.IGNORECASE)
# KEEP guard: a real hotel/motel keyword (NO bare "london bridge").
_HOTEL_NAME_RE = re.compile(
    r"(hotel|motel|\binn\b|resort|suites|lodge|hampton|holiday inn|hilton|"
    r"marriott|days inn|super 8|travelodge|quality|comfort|rodeway|knights|"
    r"nautical|studio 6|microtel|best western|island suites|olina|sway|home2|"
    r"queens bay|hidden palms|lake place|beachcomber|islander|lakeside|"
    r"twin palms|havasu suites|havasu dunes|havasu inn)", re.IGNORECASE)
# OOA name/address backstop — batch-10 set + the Session-5 named targets.
_OOA_RE = re.compile(
    r"\b(parker|kingman|needles|topock|black meadow|havasu springs)\b", re.IGNORECASE)
_OOA_REGIONS = {"parker", "laughlin-bullhead"}


def _is_sponsored(p: Provider, now: datetime) -> bool:
    tier = (p.tier or "").strip()
    if tier not in ("", "free"):
        return True
    su = p.sponsored_until
    if su is not None:
        if su.tzinfo is None:
            su = su.replace(tzinfo=UTC)
        if su > now:
            return True
    return False


def _primary_provider(provs: list[Provider]) -> Provider | None:
    """The most-reviewed provider — the one whose address/website/region anchors
    the classifier (mirrors batch-10)."""
    if not provs:
        return None
    return sorted(provs, key=lambda p: -(p.google_review_count or 0))[0]


def _protected(
    ent: Entity, provs: list[Provider], claimed: set[str], now: datetime
) -> str | None:
    """Reason this entity must NOT be deactivated (verified/claimed/sponsored), or
    None. Never touch a paying/claimed listing."""
    if ent.id in claimed:
        return "claimed"
    for p in provs:
        if p.verified:
            return "verified"
        if _is_sponsored(p, now):
            return "sponsored"
    return None


def _classify(
    ent: Entity, provs: list[Provider], leaf_slug: str
) -> str | None:
    """Return the removal bucket 'A'|'B'|'C' for this entity, or None to keep."""
    name = ent.name or ""
    pr = _primary_provider(provs)
    addr = (pr.address if pr else "") or ""
    site = (pr.website if pr else "") or ""
    local = pr.is_local if pr else None
    region = (pr.region if pr else None) or ""

    is_ooa = (
        local is False
        or region.lower() in _OOA_REGIONS
        or bool(_OOA_RE.search(addr))
        or bool(_OOA_RE.search(name))
    )

    if leaf_slug == _VR_SLUG:
        return "A"  # whole VR leaf
    if leaf_slug == _RV_SLUG:
        return "C" if is_ooa else None  # RV: OOA only
    # hotels-and-motels: OOA first (bucket C), else VR-misfiled classifier (bucket B)
    if is_ooa:
        return "C"
    has_num = bool(_STREET_NUM_RE.search(addr))
    is_real_hotel = has_num and bool(_HOTEL_NAME_RE.search(name))
    is_vr = (not is_real_hotel) and (
        bool(_OTA_RE.search(site)) or bool(_OTA_RE.search(addr))
        or bool(_VR_NAME_RE.search(name)) or not has_num
    )
    return "B" if is_vr else None


def _leaf_primary_entities(
    db, slug: str
) -> dict[str, str]:
    """{entity_id: slug} for ACTIVE entities whose PRIMARY leaf is ``slug``."""
    cat = db.query(Category).filter(Category.slug == slug).one_or_none()
    if cat is None:
        return {}
    rows = (
        db.query(EntityCategory.entity_id)
        .join(Entity, Entity.id == EntityCategory.entity_id)
        .filter(
            EntityCategory.category_id == cat.id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
        )
        .all()
    )
    return {r[0]: slug for r in rows}


def deactivate(apply: bool, undo_csv: str | None) -> int:
    now = datetime.now(UTC)
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        # primary-leaf membership for the three lodging leaves
        leaf_of: dict[str, str] = {}
        for slug in (_VR_SLUG, _HOTELS_SLUG, _RV_SLUG):
            leaf_of.update(_leaf_primary_entities(db, slug))

        ents = {e.id: e for e in db.query(Entity).filter(Entity.id.in_(leaf_of.keys())).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).filter(Provider.entity_id.in_(leaf_of.keys())).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        claimed = {
            r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()
        }

        buckets: dict[str, list[Entity]] = {"A": [], "B": [], "C": []}
        skipped: list[tuple[str, str]] = []  # (name, reason)
        for eid, slug in leaf_of.items():
            ent = ents.get(eid)
            if ent is None:
                continue
            provs = provs_by_entity.get(eid, [])
            bucket = _classify(ent, provs, slug)
            if bucket is None:
                continue
            reason = _protected(ent, provs, claimed, now)
            if reason is not None:
                skipped.append((ent.name or eid, reason))
                continue
            buckets[bucket].append(ent)

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 84)
        print(f"SESSION 5 — PLACES TO STAY CLEANUP — {mode}")
        print("=" * 84)
        print(f"DB target: …@{redacted}")
        print(
            f"live lodging listings scanned: VR={sum(1 for s in leaf_of.values() if s == _VR_SLUG)} "
            f"hotels={sum(1 for s in leaf_of.values() if s == _HOTELS_SLUG)} "
            f"rv={sum(1 for s in leaf_of.values() if s == _RV_SLUG)} "
            f"(total {len(leaf_of)})\n"
        )
        total = sum(len(v) for v in buckets.values())
        print(
            f"WOULD DEACTIVATE: {total}   "
            f"[A vacation-rentals leaf={len(buckets['A'])}  "
            f"B misfiled-under-hotels={len(buckets['B'])}  "
            f"C out-of-area={len(buckets['C'])}]"
        )
        print(f"SKIPPED (protected/already-hidden): {len(skipped)}")
        for reason, n in Counter(r for _n, r in skipped).most_common():
            print(f"    {n:4d}  {reason}")
        if skipped:
            for nm, r in skipped[:15]:
                print(f"        [{r}] {nm[:56]}")

        def _dump(bucket: str, label: str, cap: int) -> None:
            rows = sorted(buckets[bucket], key=lambda e: (e.name or "").lower())
            print(f"\n--- Bucket {bucket}: {label} ({len(rows)}) ---")
            for e in rows[:cap]:
                pr = _primary_provider(provs_by_entity.get(e.id, []))
                addr = (pr.address if pr else "") or ""
                site = (pr.website if pr else "") or ""
                print(f"    {(e.name or '')[:46]:46s}  | {addr[:34]:34s} | {site[:28]}")
            if len(rows) > cap:
                print(f"    ... and {len(rows) - cap} more")

        _dump("A", "whole vacation-rentals leaf", 15)
        # Bucket B is the eyeball-critical one: show the FULL list so a wrongly
        # keep-guarded real hotel is easy to spot.
        _dump("B", "VR/property-mgmt misfiled under hotels-and-motels", 999)
        _dump("C", "out-of-area lodging (hotels + RV leaves)", 999)

        if not apply:
            print(
                "\nDRY RUN — nothing written. After approval, re-run with "
                "--apply --undo-csv <path> to deactivate."
            )
            return 0

        to_deactivate = buckets["A"] + buckets["B"] + buckets["C"]
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["entity_id", "name", "provider_ids"])
                for e in to_deactivate:
                    pids = [p.id for p in provs_by_entity.get(e.id, [])]
                    w.writerow([e.id, e.name or "", ";".join(pids)])

        for e in to_deactivate:
            e.is_active = False
            for p in provs_by_entity.get(e.id, []):
                if p.is_active:
                    p.is_active = False
        db.commit()
        print(f"\nAPPLIED: deactivated {len(to_deactivate)} lodging entities (+ their providers).")
        if undo_csv:
            print(f"Undo manifest: {undo_csv} "
                  f"(reverse with --reactivate-from {undo_csv} --apply).")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        changed = 0
        with open(undo_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                eid = r.get("entity_id")
                if not eid:
                    continue
                ent = db.get(Entity, eid)
                if ent is not None and not ent.is_active:
                    if apply:
                        ent.is_active = True
                    changed += 1
                for pid in (r.get("provider_ids") or "").split(";"):
                    pid = pid.strip()
                    if not pid:
                        continue
                    p = db.get(Provider, pid)
                    if p is not None and not p.is_active and apply:
                        p.is_active = True
        if apply:
            db.commit()
        verb = "REACTIVATED" if apply else "would reactivate"
        print(f"{verb}: {changed} entities (is_active=True, providers cascaded).")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Session 5 lodging cleanup (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_places_to_stay_2026-07-05.csv",
                    help="where to write the undo manifest on --apply")
    ap.add_argument("--reactivate-from", dest="undo_in",
                    help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return deactivate(args.apply, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
