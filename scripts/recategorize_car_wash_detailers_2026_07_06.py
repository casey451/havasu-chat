"""Re-shelve detailing shops mis-filed under ``car-wash`` to ``auto-detailing``.

Audit 2026-07-06 (T3.2): the ``car-wash`` leaf holds auto-detailing / ceramic-
coating shops. This moves them to the correct PRIMARY leaf via
``classify_car_wash_misfiled_leaf``. Mirrors ``scripts/recategorize_water_misfiled``:
changes only the PRIMARY entity_categories link, scoped to rows whose CURRENT
primary leaf is ``car-wash``, one transaction, JSON rollback snapshot first.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``. Every run prints the
sanitized DB target — the repo .env can point DATABASE_URL at prod.

    .venv\\Scripts\\python.exe scripts\\recategorize_car_wash_detailers_2026_07_06.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_car_wash_detailers_2026_07_06.py --apply --confirm  # writes
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

from app.categories.car_wash_misfiled_rules import classify_car_wash_misfiled_leaf  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402

_SOURCE_LEAF = "car-wash"


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

        providers = session.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        ).all()
        counts["active_providers"] = len(providers)

        staged: list[tuple[str, int]] = []
        change_rows: list[dict] = []
        for p in providers:
            cur_leaf_id = current_primary.get(p.entity_id)
            cur_slug = id_to_slug.get(cur_leaf_id) if cur_leaf_id else None
            if cur_slug != _SOURCE_LEAF:
                continue
            counts["in_source_leaf"] += 1
            desired = classify_car_wash_misfiled_leaf(p.provider_name)
            if desired is None:
                continue
            new_leaf_id = slug_to_id.get(desired)
            if new_leaf_id is None:
                counts["unresolved_leaf"] += 1
                continue
            if cur_leaf_id == new_leaf_id:
                counts["already_correct"] += 1
                continue
            counts["would_change"] += 1
            staged.append((p.entity_id, new_leaf_id))
            change_rows.append({"entity_id": p.entity_id, "provider_id": p.id,
                                "name": p.provider_name, "old_leaf": _SOURCE_LEAF, "new_leaf": desired})

        out_path = _ROOT / f"recategorize_car_wash_detailers_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["entity_id", "provider_id", "name", "old_leaf", "new_leaf"])
            w.writeheader()
            w.writerows(change_rows)

        print(f"Active providers : {counts['active_providers']}")
        print(f"In source leaf   : {counts.get('in_source_leaf', 0)}")
        print(f"Would change     : {counts.get('would_change', 0)}")
        print(f"Change CSV       : {out_path}\n")
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
        snap_path = _ROOT / f"recategorize_car_wash_detailers_snapshot_{stamp}.json"
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
