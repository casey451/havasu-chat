"""Two small GATED recategorization ops (dry-run default; --apply gated).

Follow-ups to Session 5, keyed on the **EntityCategory primary leaf**
(``is_primary=True``), mirroring ``scripts/deactivate_places_to_stay_2026_07_05.py``.

  Op 1 (heat-bar): HEAT Bar is misfiled in the ``hotels-and-motels`` leaf but is a
    bar — repoint its PRIMARY EntityCategory to ``bars-and-breweries`` (Eat & Drink).
  Op 2 (pm-firms, ONLY with --include-pm): reactivate the 3 property-management
    firms Session 5 deactivated (First Choice Property of Mohave County, Integrity
    Arizona Vacation Rentals, PMI Lake Havasu) and repoint their primary leaf from
    ``vacation-rentals`` to ``property-management`` (Home & Property Services).
    Runs ONLY when Casey says keep them — gated behind --include-pm.

Repoint = swap ``is_primary`` onto an existing target link if one exists, else
repoint the primary row's ``category_id``. Reactivation = ``Entity.is_active=True``
+ cascade ``Provider.is_active=True``. Reversible via ``--reactivate-from <undo.csv>
--apply``.

PROD GATE (CLAUDE.md): dry-run -> counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe -m scripts.recategorize_lodging_misfiles_2026_07_05
    .venv\\Scripts\\python.exe -m scripts.recategorize_lodging_misfiles_2026_07_05 --apply --undo-csv undo_recat.csv
    .venv\\Scripts\\python.exe -m scripts.recategorize_lodging_misfiles_2026_07_05 --apply --include-pm --undo-csv undo_recat.csv
    .venv\\Scripts\\python.exe -m scripts.recategorize_lodging_misfiles_2026_07_05 --reactivate-from undo_recat.csv --apply
"""

from __future__ import annotations

import argparse
import csv
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

_HOTELS_SLUG = "hotels-and-motels"
_VR_SLUG = "vacation-rentals"
_BARS_SLUG = "bars-and-breweries"
_PM_SLUG = "property-management"

# The 3 PM firms Session 5 deactivated (VR leaf). Resolved by name + VR primary +
# inactive, so the real-estate / government / orphan "First Choice"/"Integrity"
# rows are never touched.
_PM_NAME_LIKES = (
    "First Choice Property of Mohave County",
    "Integrity Arizona Vacation Rentals",
    "PMI Lake Havasu",
)


def _cat(db, slug: str) -> Category:
    return db.query(Category).filter(Category.slug == slug).one()


def _primary_ec(db, entity_id: str) -> EntityCategory | None:
    return (
        db.query(EntityCategory)
        .filter(EntityCategory.entity_id == entity_id, EntityCategory.is_primary.is_(True))
        .first()
    )


def _slug_of(db, cat_id) -> str:
    c = db.get(Category, cat_id)
    return c.slug if c else str(cat_id)


def _plan_repoint(db, entity_id: str, target: Category) -> dict | None:
    """Compute (no mutation) the repoint plan for one entity's primary leaf."""
    prim = _primary_ec(db, entity_id)
    if prim is None:
        return None
    if prim.category_id == target.id:
        return None  # already there
    existing = (
        db.query(EntityCategory)
        .filter(
            EntityCategory.entity_id == entity_id,
            EntityCategory.category_id == target.id,
        )
        .one_or_none()
    )
    mode = "swap" if (existing is not None and existing.id != prim.id) else "repoint"
    return {
        "prim_ec_id": prim.id,
        "old_category_id": prim.category_id,
        "old_slug": _slug_of(db, prim.category_id),
        "target_ec_id": existing.id if mode == "swap" else "",
        "new_category_id": target.id,
        "new_slug": target.slug,
        "mode": mode,
    }


def _heat_bar_targets(db) -> list[Entity]:
    bars = _cat(db, _BARS_SLUG)
    hotels = _cat(db, _HOTELS_SLUG)
    out = []
    for e in db.query(Entity).filter(Entity.name == "HEAT Bar").all():
        prim = _primary_ec(db, e.id)
        if prim is not None and prim.category_id == hotels.id:
            out.append(e)
    _ = bars
    return out


def _pm_targets(db) -> list[Entity]:
    vr = _cat(db, _VR_SLUG)
    out: list[Entity] = []
    for like in _PM_NAME_LIKES:
        for e in db.query(Entity).filter(
            Entity.name.ilike(like), Entity.is_active.is_(False)
        ).all():
            prim = _primary_ec(db, e.id)
            if prim is not None and prim.category_id == vr.id:
                out.append(e)
    return out


def run(apply: bool, include_pm: bool, undo_csv: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        bars = _cat(db, _BARS_SLUG)
        pm = _cat(db, _PM_SLUG)
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        heat = _heat_bar_targets(db)
        pm_firms = _pm_targets(db)

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 84)
        print(f"RECATEGORIZE LODGING MISFILES — {mode}")
        print("=" * 84)
        print(f"DB target: …@{redacted}\n")

        undo_rows: list[list[object]] = []

        # ---- Op 1: HEAT Bar -> bars-and-breweries ----
        print(f"OP 1 — HEAT Bar → {bars.slug} ({len(heat)} entity)")
        for e in heat:
            plan = _plan_repoint(db, e.id, bars)
            if plan is None:
                print(f"    (no-op) {e.name}")
                continue
            print(f"    {e.name[:36]:36s} {plan['old_slug']} -> {plan['new_slug']}  [{plan['mode']}]")
            if apply:
                undo_rows.append([
                    "repoint", e.id, e.name or "", plan["prim_ec_id"], plan["old_category_id"],
                    plan["target_ec_id"], plan["new_category_id"], plan["mode"], "", "0",
                ])

        # ---- Op 2: PM firms (reactivate + repoint) — ONLY with --include-pm ----
        gate = "WILL APPLY" if (apply and include_pm) else (
            "dry-run preview (contingent on Casey: keep the PM firms?)"
            if not apply else "SKIPPED (no --include-pm)"
        )
        print(f"\nOP 2 — reactivate 3 PM firms + repoint → {pm.slug}  [{gate}] ({len(pm_firms)} entities)")
        for e in pm_firms:
            plan = _plan_repoint(db, e.id, pm)
            pids = [p.id for p in provs_by_entity.get(e.id, [])]
            old = plan["old_slug"] if plan else "?"
            print(f"    {e.name[:36]:36s} active {e.is_active}→True | {old} → {pm.slug} | providers={len(pids)}")
            if apply and include_pm:
                if plan is not None:
                    undo_rows.append([
                        "reactivate_repoint", e.id, e.name or "", plan["prim_ec_id"],
                        plan["old_category_id"], plan["target_ec_id"], plan["new_category_id"],
                        plan["mode"], ";".join(pids), "1",
                    ])
                else:
                    undo_rows.append([
                        "reactivate_repoint", e.id, e.name or "", "", "", "", "", "", ";".join(pids), "1",
                    ])

        if not apply:
            print("\nDRY RUN — nothing written. After approval:")
            print("  --apply                → Op 1 only (HEAT Bar)")
            print("  --apply --include-pm   → Op 1 + Op 2 (only if Casey keeps the PM firms)")
            return 0

        # ---- writes ----
        for e in heat:
            plan = _plan_repoint(db, e.id, bars)
            if plan is None:
                continue
            _apply_repoint(db, plan)
        if include_pm:
            for e in pm_firms:
                e.is_active = True
                for p in provs_by_entity.get(e.id, []):
                    if not p.is_active:
                        p.is_active = True
                plan = _plan_repoint(db, e.id, pm)
                if plan is not None:
                    _apply_repoint(db, plan)

        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "op", "entity_id", "name", "prim_ec_id", "old_category_id",
                    "target_ec_id", "new_category_id", "mode", "provider_ids", "reactivated",
                ])
                w.writerows(undo_rows)
        db.commit()
        n_pm = len(pm_firms) if include_pm else 0
        print(f"\nAPPLIED: repointed {len(heat)} HEAT Bar; "
              f"reactivated+repointed {n_pm} PM firms. Undo: {undo_csv}")
        return 0


def _apply_repoint(db, plan: dict) -> None:
    prim = db.get(EntityCategory, plan["prim_ec_id"])
    if prim is None:
        return
    if plan["mode"] == "swap" and plan["target_ec_id"]:
        target_ec = db.get(EntityCategory, plan["target_ec_id"])
        prim.is_primary = False
        if target_ec is not None:
            target_ec.is_primary = True
    else:
        prim.category_id = plan["new_category_id"]


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = 0
        with open(undo_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                # reverse the repoint (int PKs come back from CSV as strings)
                prim = db.get(EntityCategory, int(r["prim_ec_id"])) if r.get("prim_ec_id") else None
                if prim is not None:
                    if r.get("mode") == "swap" and r.get("target_ec_id"):
                        target_ec = db.get(EntityCategory, int(r["target_ec_id"]))
                        if apply:
                            prim.is_primary = True
                            if target_ec is not None:
                                target_ec.is_primary = False
                    elif r.get("old_category_id") and apply:
                        prim.category_id = int(r["old_category_id"])
                    n += 1
                # reverse the reactivation (re-deactivate)
                if r.get("reactivated") == "1":
                    ent = db.get(Entity, r["entity_id"])
                    if ent is not None and apply:
                        ent.is_active = False
                    for pid in (r.get("provider_ids") or "").split(";"):
                        pid = pid.strip()
                        if pid and apply:
                            p = db.get(Provider, pid)
                            if p is not None:
                                p.is_active = False
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: {n} entity recategorizations (+ any reactivations undone).")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recategorize lodging misfiles (dry-run default).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-pm", action="store_true",
                    help="also run Op 2 (reactivate PM firms) — ONLY if Casey keeps them")
    ap.add_argument("--undo-csv", default="undo_recategorize_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.apply, args.include_pm, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
