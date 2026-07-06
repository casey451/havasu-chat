"""T3.4 — merge the ``auto-detailing`` leaf into ``auto-marine-detailing``.

Two overlapping detailing leaves ("Auto Detailing" + "Auto/Marine Detailing")
confused browsing. Consolidate onto the broader ``auto-marine-detailing``: move
every active provider whose PRIMARY leaf is ``auto-detailing`` onto it. The old
slug 301s via ``LEAF_SLUG_ALIASES`` (router.py) and the leaf_query terms now point
at the survivor, so the retired ``auto-detailing`` row is left empty (never linked).

Mirrors ``scripts/recategorize_car_wash_detailers``: repoints only the PRIMARY
entity_categories link, one transaction, JSON rollback snapshot first.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``.

    .venv\\Scripts\\python.exe scripts\\merge_detailing_leaves_2026_07_06.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\merge_detailing_leaves_2026_07_06.py --apply --confirm  # writes
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

_SOURCE_LEAF = "auto-detailing"
_TARGET_LEAF = "auto-marine-detailing"


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
        src_id = slug_to_id.get(_SOURCE_LEAF)
        tgt_id = slug_to_id.get(_TARGET_LEAF)
        if src_id is None or tgt_id is None:
            print(f"ABORT — source ({src_id}) or target ({tgt_id}) leaf missing.")
            return counts
        current_primary = {ec.entity_id: ec.category_id for ec in
                           session.query(EntityCategory).filter(EntityCategory.is_primary.is_(True))}
        providers = session.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)).all()

        staged: list[str] = []
        change_rows: list[dict] = []
        for p in providers:
            if id_to_slug.get(current_primary.get(p.entity_id)) != _SOURCE_LEAF:
                continue
            counts["in_source_leaf"] += 1
            staged.append(p.entity_id)
            change_rows.append({"entity_id": p.entity_id, "provider_id": p.id,
                                "name": p.provider_name, "old_leaf": _SOURCE_LEAF, "new_leaf": _TARGET_LEAF})

        out_path = _ROOT / f"merge_detailing_leaves_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["entity_id", "provider_id", "name", "old_leaf", "new_leaf"])
            w.writeheader()
            w.writerows(change_rows)

        print(f"In source leaf ({_SOURCE_LEAF}): {counts.get('in_source_leaf', 0)}")
        print(f"Would move -> {_TARGET_LEAF}\nChange CSV: {out_path}\n")
        for r in change_rows:
            print(f"  - {r['name'][:44]:44}  {_SOURCE_LEAF} -> {_TARGET_LEAF}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        snapshot = [{"id": ec.id, "entity_id": ec.entity_id, "category_id": ec.category_id,
                     "is_primary": ec.is_primary}
                    for ec in session.query(EntityCategory).filter(EntityCategory.entity_id.in_(staged))] if staged else []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = _ROOT / f"merge_detailing_leaves_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        for entity_id in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id, EntityCategory.is_primary.is_(True)):
                ec.is_primary = False
            existing = session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id, EntityCategory.category_id == tgt_id).one_or_none()
            if existing is None:
                session.add(EntityCategory(entity_id=entity_id, category_id=tgt_id, is_primary=True))
            else:
                existing.is_primary = True
        session.commit()
        counts["primaries_changed"] = len(staged)
        print(f"\nAPPLIED — moved {len(staged)} providers {_SOURCE_LEAF} -> {_TARGET_LEAF}.")
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
