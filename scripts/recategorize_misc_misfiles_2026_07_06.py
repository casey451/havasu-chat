"""Reclassify the remaining audit misfiles (NEEDS_DECISION rows resolved).

The 2026-07-06 misfile audit flagged a handful of rows whose correct leaf needed a
call. Resolved here (curated, exact-source-leaf scoped):
  * "REDHAWK Pool Service & Repair"  auto-repair                 -> pools-and-spas
  * "Winners Circle Storage"         auto-repair                 -> self-storage
  * "Rodney Koenig, PAC"             pharmacies                  -> primary-care
  * "Hypnotherapist On Line"         primary-care                -> mental-and-behavioral-health

Deliberately LEFT: the two dental labs (Foster's / New West) — a dental lab is
dental-adjacent (some do consumer denture repair) and there is no dentures/lab
leaf to move them to; deactivating real businesses without a target isn't warranted.

Mirrors ``scripts/recategorize_car_wash_detailers``: repoints only the PRIMARY
entity_categories link, scoped so it only touches a row whose current leaf matches,
one transaction, JSON rollback snapshot first.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``.

    .venv\\Scripts\\python.exe scripts\\recategorize_misc_misfiles_2026_07_06.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_misc_misfiles_2026_07_06.py --apply --confirm  # writes
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402

# (name substring lower, current leaf slug, target leaf slug)
MOVES: list[tuple[str, str, str]] = [
    ("redhawk pool", "auto-repair", "pools-and-spas"),
    ("winners circle storage", "auto-repair", "self-storage"),
    ("rodney koenig", "pharmacies", "primary-care"),
    ("hypnotherapist on line", "primary-care", "mental-and-behavioral-health"),
]


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(*, apply: bool = False, confirm: bool = False, session=None) -> Counter:
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        slug_to_id = {slug: cid for slug, cid in
                      session.query(Category.slug, Category.id).filter(Category.level == 1)}
        id_to_slug = {cid: slug for slug, cid in slug_to_id.items()}
        current_primary = {ec.entity_id: ec.category_id for ec in
                           session.query(EntityCategory).filter(EntityCategory.is_primary.is_(True))}

        staged: list[tuple[str, int]] = []
        change_rows: list[dict] = []
        for needle, src_slug, tgt_slug in MOVES:
            tgt_id = slug_to_id.get(tgt_slug)
            if tgt_id is None:
                print(f"  SKIP — target leaf {tgt_slug!r} missing")
                continue
            provs = session.query(Provider).filter(
                Provider.is_active.is_(True), Provider.draft.is_(False),
                Provider.provider_name.ilike(f"%{needle}%"),
            ).all()
            for p in provs:
                cur_slug = id_to_slug.get(current_primary.get(p.entity_id))
                if cur_slug != src_slug:
                    print(f"  SKIP {p.provider_name!r}: current leaf {cur_slug!r} != {src_slug!r}")
                    continue
                staged.append((p.entity_id, tgt_id))
                change_rows.append({"entity_id": p.entity_id, "provider_id": p.id,
                                    "name": p.provider_name, "old_leaf": src_slug, "new_leaf": tgt_slug})

        out_path = _ROOT / f"recategorize_misc_misfiles_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["entity_id", "provider_id", "name", "old_leaf", "new_leaf"])
            w.writeheader()
            w.writerows(change_rows)

        print(f"Would move: {len(change_rows)}\nChange CSV: {out_path}\n")
        for r in change_rows:
            print(f"  - {r['name'][:40]:40}  {r['old_leaf']} -> {r['new_leaf']}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        touched = list({eid for eid, _ in staged})
        snapshot = [{"id": ec.id, "entity_id": ec.entity_id, "category_id": ec.category_id,
                     "is_primary": ec.is_primary}
                    for ec in session.query(EntityCategory).filter(EntityCategory.entity_id.in_(touched))] if touched else []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = _ROOT / f"recategorize_misc_misfiles_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        for entity_id, leaf_id in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id, EntityCategory.is_primary.is_(True)):
                ec.is_primary = False
            existing = session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id, EntityCategory.category_id == leaf_id).one_or_none()
            if existing is None:
                session.add(EntityCategory(entity_id=entity_id, category_id=leaf_id, is_primary=True))
            else:
                existing.is_primary = True
        session.commit()
        counts["primaries_changed"] = len(staged)
        print(f"\nAPPLIED — {len(staged)} primary leaf reassignments in one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
