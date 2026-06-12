"""Youth/family venues as place providers — cabana dedupe + categorize, BMX
insert, and NULL-only hours/phone gap fills (Casey-approved 2026-06-12).

Reconciles the six youth/family venues from the calendar handoff into the
provider catalog so Ask Hava can answer "what are their hours". Mirrors the
golakehavasu_partners_load discipline: it never creates a new duplicate, never
overwrites a non-empty field, and prints a full plan under dry-run.

Three operations, each idempotent / re-runnable:

1. Cabana Boat Rentals (Casey: "categorize + dedupe + verified info") — folds
   the duplicate row into one via provider_merge.merge_providers, categorizes the
   keeper on-the-water / boat_rental (mirroring a live boat-rental row:
   category='boat_rental', primary_category='on-the-water', category_id=6,
   subcategory='on-the-water'), and sets the verified direct booking address +
   phone. It was hidden from boat-rental queries because it sat 'uncategorized'.

2. Lake Havasu City BMX (Casey: "insert if missing") — genuinely absent; inserted
   as a place provider with hours + phone via entity_dual_write.create_provider_
   and_entity. Categorized classes-sports-recreation per the handoff (a level-0
   legacy slug that currently renders on no department page — flagged for the B3
   taxonomy reconcile; it does not block name/hours lookup).

3. The other five venues (Casey: "fill NULL hours/phone gaps only") — for each,
   pick the single best Google-backed row and fill ONLY a genuinely NULL hours /
   phone gap. Existing (Google) hours are never overwritten; duplicate rows are
   left untouched.

SAFETY: defaults to DRY-RUN. Pass --apply to write. Prod write ⇒ dry-run, show
counts, Casey approves, apply (CLAUDE.md). Casey pre-approved 2026-06-12.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Provider  # noqa: E402

# --- verified hours (24h HH:MM), from the handoff table (verified 2026-06-12) --
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def hours(**by_day: list[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    """{'monday': [('12:00','21:00')], ...} -> hours_structured shape."""
    out: dict[str, list[dict[str, str]]] = {}
    for day, spans in by_day.items():
        out[day] = [{"open": o, "close": c} for o, c in spans]
    return out


HAVASU_LANES_HOURS = hours(
    monday=[("12:00", "21:00")], tuesday=[("12:00", "21:00")],
    wednesday=[("12:00", "21:00")], thursday=[("12:00", "21:00")],
    friday=[("12:00", "23:00")], saturday=[("12:00", "23:00")],
    sunday=[("12:00", "19:00")],
)
ALTITUDE_HOURS = hours(
    sunday=[("11:00", "19:00")], monday=[("10:00", "19:00")], tuesday=[("10:00", "19:00")],
    wednesday=[("10:00", "19:00")], thursday=[("10:00", "19:00")],
    friday=[("10:00", "20:00")], saturday=[("10:00", "21:00")],
)
THE_SPOT_HOURS = hours(
    wednesday=[("15:00", "21:00")], thursday=[("15:00", "21:00")],
    friday=[("15:00", "22:00")], saturday=[("12:00", "22:00")], sunday=[("12:00", "21:00")],
)
IRON_WOLF_TOPTRACER_HOURS = hours(
    monday=[("17:00", "21:00")], wednesday=[("17:00", "21:00")], thursday=[("17:00", "21:00")],
    friday=[("14:00", "22:00")], saturday=[("14:00", "22:00")], sunday=[("11:00", "19:00")],
)
BMX_HOURS = hours(tuesday=[("19:00", "21:00")], thursday=[("19:00", "21:00")])

# Existing venues: precise name match (+ excludes for co-located different
# businesses), verified phone, and verified hours used ONLY to fill a NULL gap.
EXISTING_VENUES = [
    {
        "label": "Havasu Lanes",
        "like": ["Havasu Lanes%"],
        "exclude": ["Kegler's Pub at Havasu Lanes"],
        "phone": "(928) 855-2695",
        "hours": HAVASU_LANES_HOURS,
    },
    {
        "label": "Altitude Trampoline Park",
        "like": ["Altitude Trampoline%"],
        "exclude": [],
        "phone": "(928) 436-8316",
        "hours": ALTITUDE_HOURS,
    },
    {
        "label": "The Spot",
        "like": ["The Spot%"],
        "exclude": [],
        "phone": "(928) 505-7768",
        "hours": THE_SPOT_HOURS,
    },
    {
        "label": "Iron Wolf G&CC (Toptracer Range)",
        "like": ["Iron Wolf Golf%"],
        "exclude": ["Reflections Steakhouse%"],
        "phone": "(928) 764-1404",
        "hours": IRON_WOLF_TOPTRACER_HOURS,
    },
    {
        "label": "Desert Hawks RC Club",
        "like": ["Desert Hawks RC%"],
        "exclude": [],
        "phone": None,  # handoff gives only an email; no phone to fill
        "hours": None,  # "no set hours / weather permitting" — only fill if NULL
    },
]


def _has_hours(p: Provider) -> bool:
    return bool(p.hours_structured or p.hours or p.google_hours)


def _pick_best(rows: list[Provider]) -> Provider | None:
    """The single best Google-backed row: prefer google_place_id, then existing
    hours, then richer Google signal, then active."""
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda p: (
            bool(p.google_place_id),
            _has_hours(p),
            (p.google_review_count or 0),
            bool(p.is_active),
        ),
        reverse=True,
    )[0]


def _fmt(p: Provider) -> str:
    return (
        f"id={p.id} name={p.provider_name!r} active={p.is_active} "
        f"cat={p.category!r} primary={p.primary_category!r} cat_id={p.category_id} "
        f"phone={p.phone!r} hours={'Y' if _has_hours(p) else '-'} gpid={'Y' if p.google_place_id else '-'}"
    )


def do_cabana(db, plan: list[str]) -> None:
    rows = db.scalars(
        select(Provider).where(
            Provider.provider_name.ilike("Cabana Boat Rentals%"),
            Provider.website.ilike("%cabanaboathavasu%"),
        )
    ).all()
    plan.append(f"\n[CABANA] {len(rows)} 'Cabana Boat Rentals' row(s):")
    for r in rows:
        plan.append(f"    {_fmt(r)} source={r.source!r}")
    if not rows:
        plan.append("    -> none found; nothing to do (would have inserted, but expected to exist)")
        return

    # Keep an operator-sourced row if present (merge_providers refuses to retire
    # one); otherwise keep the richest row. Everything else folds in.
    operator = [r for r in rows if (r.source or "").strip() == "operator"]
    keeper = operator[0] if operator else _pick_best(rows)
    dups = [r for r in rows if r.id != keeper.id]

    for dup in dups:
        if not dup.is_active:
            plan.append(f"    skip dup {dup.id}: already retired (idempotent re-run)")
            continue
        res = merge_providers(db, keep_id=keeper.id, dup_id=dup.id, dry_run=DRY)
        plan.append(
            f"    MERGE dup {dup.id} -> keep {keeper.id} "
            f"(gap_filled={getattr(res, 'gap_filled', '?')}, repointed={getattr(res, 'repointed', '?')})"
        )

    # categorize + verified contact on the keeper (mirror a live boat-rental row)
    changes = []
    # The cabana rows are deactivated; the keeper must be active to be queryable
    # (no other active Cabana Boat Rentals row exists).
    if not keeper.is_active:
        changes.append("is_active False->True")
        if not DRY:
            keeper.is_active = True
    if keeper.category in (None, "", "uncategorized"):
        changes.append(f"category {keeper.category!r}->'boat_rental'")
        if not DRY:
            keeper.category = "boat_rental"
    if keeper.primary_category != "on-the-water":
        changes.append(f"primary {keeper.primary_category!r}->'on-the-water'")
        if not DRY:
            keeper.primary_category = "on-the-water"
    if keeper.category_id != 6:
        changes.append(f"category_id {keeper.category_id}->6")
        if not DRY:
            keeper.category_id = 6
    if keeper.subcategory != "on-the-water":
        changes.append(f"subcategory {keeper.subcategory!r}->'on-the-water'")
        if not DRY:
            keeper.subcategory = "on-the-water"
    # verified direct booking info (Casey: update to verified)
    if keeper.address != "515 Shoreline Trl, Lake Havasu City, AZ 86403":
        changes.append(f"address {keeper.address!r}->verified")
        if not DRY:
            keeper.address = "515 Shoreline Trl, Lake Havasu City, AZ 86403"
    if keeper.phone != "(928) 486-6951":
        changes.append(f"phone {keeper.phone!r}->'(928) 486-6951'")
        if not DRY:
            keeper.phone = "(928) 486-6951"
    if changes and not DRY:
        sync_provider_entity_from_legacy(db, keeper)
    plan.append(f"    KEEPER {keeper.id} changes: {changes or 'none'}")


def do_bmx(db, plan: list[str]) -> None:
    existing = db.scalars(
        select(Provider).where(Provider.provider_name.ilike("%BMX%"))
    ).all()
    plan.append(f"\n[BMX] existing %BMX% rows: {len(existing)}")
    for r in existing:
        plan.append(f"    {_fmt(r)}")
    if existing:
        plan.append("    -> already present; not inserting (idempotent)")
        return
    plan.append("    INSERT 'Lake Havasu City BMX' as place provider (hours+phone+category)")
    if DRY:
        return
    p = Provider(
        provider_name="Lake Havasu City BMX",
        category="sports_recreation",
        primary_category="classes-sports-recreation",
        subcategory="classes-sports-recreation",
        category_id=13,
        address="7269 Sara Park Ln, Lake Havasu City, AZ 86406",
        phone="(928) 208-5388",
        hours_structured=BMX_HOURS,
        hours="Tue & Thu race nights — practice 7 PM, racing 8 PM (full schedule on the "
        "Lake Havasu City BMX Facebook page).",
        description="USA BMX-sanctioned track at SARA Park — Tuesday & Thursday "
        "practice/race nights. New riders get a free one-day pass. It's for the kids!",
        source="operator",
        is_active=True,
        verified=True,
    )
    db.add(p)  # caller must add the Provider; create_provider_and_entity only adds the Entity
    create_provider_and_entity(db, p)
    db.flush()
    plan.append(f"    INSERTED id={p.id} entity={p.entity_id}")


def do_existing(db, plan: list[str]) -> None:
    plan.append("\n[EXISTING VENUES] fill NULL hours/phone gaps on best Google-backed row only:")
    for spec in EXISTING_VENUES:
        clauses = [Provider.provider_name.ilike(p) for p in spec["like"]]
        rows = list(db.scalars(select(Provider).where(or_(*clauses))).all())
        for ex in spec["exclude"]:
            rows = [r for r in rows if not r.provider_name.lower().startswith(ex.lower().rstrip("%"))]
        best = _pick_best(rows)
        plan.append(f"\n  {spec['label']}: {len(rows)} candidate(s); best -> "
                    + (_fmt(best) if best else "NONE"))
        if best is None:
            continue
        changes = []
        if spec["hours"] and not _has_hours(best):
            changes.append("hours (was NULL) -> verified")
            if not DRY:
                best.hours_structured = spec["hours"]
        if spec["phone"] and not (best.phone or "").strip():
            changes.append(f"phone (was NULL) -> {spec['phone']}")
            if not DRY:
                best.phone = spec["phone"]
        if changes and not DRY:
            sync_provider_entity_from_legacy(db, best)
        plan.append(f"    gap-fill: {changes or 'none (no NULL gap)'}")


DRY = True


def main() -> int:
    global DRY
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write to the DB (default: dry-run)")
    args = ap.parse_args()
    DRY = not args.apply

    plan: list[str] = []
    with SessionLocal() as db:
        do_cabana(db, plan)
        do_bmx(db, plan)
        do_existing(db, plan)
        if DRY:
            db.rollback()
            plan.append("\n=== DRY-RUN: no writes (pass --apply to commit) ===")
        else:
            db.commit()
            plan.append("\n=== APPLIED: committed ===")
    print("\n".join(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
