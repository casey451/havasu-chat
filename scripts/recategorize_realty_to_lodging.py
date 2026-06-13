"""Re-shelve 3 vacation-rental property managers from professional-services to lodging.

QA diagnostic 2026-06-12 (Phase 4, realty judgment rows): three firms stored with
a PRIMARY ``professional-services``/realty leaf actually run vacation-rental booking
operations (verified on their sites), so a "where can I stay" ask should surface
them. Casey approved moving all three to ``lodging-vacation-rentals`` on 2026-06-12.

These rows are NOT in the ``boat-and-watercraft-rentals`` leaf, so
``recategorize_water_misfiled.py`` (which is scoped to that leaf) cannot touch
them — hence this tiny by-ID companion. It mirrors that script exactly: changes
only the PRIMARY entity_categories link, wraps writes in one transaction, and
saves a JSON rollback snapshot first.

DEFAULT IS DRY-RUN: prints what would change, writes NOTHING. ``--apply`` requires
``--confirm``. Every run prints the sanitized DB target.

    .venv\\Scripts\\python.exe scripts\\recategorize_realty_to_lodging.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_realty_to_lodging.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the counts, get approval, THEN a
human runs --apply --confirm against prod. The agent never runs --apply against prod.
"""

from __future__ import annotations

import argparse
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
from app.db.models import Category, EntityCategory  # noqa: E402

_TARGET_LEAF = "lodging-vacation-rentals"

# Casey-approved 2026-06-12 (ASK_HAVA_PHASE4_JUDGMENT_DECISIONS_2026-06-12.md).
_TARGET_ENTITY_IDS = {
    "e1f99729-d1fe-418c-9d34-ccaf65c3411b": "Copper Canyon Realty",
    "4543064b-4703-43af-9128-3641727acca7": "Destination Havasu",
    "e2c7f9a6-b67d-40ce-8f6a-c71358ae2a94": "First Choice Property of Mohave County",
}


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    snapshot_dir: Path | None = None,
    session=None,
) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")

        slug_to_id = {
            slug: cid
            for slug, cid in session.query(Category.slug, Category.id).filter(
                Category.level == 1
            )
        }
        id_to_slug = {cid: slug for slug, cid in slug_to_id.items()}
        target_id = slug_to_id.get(_TARGET_LEAF)
        if target_id is None:
            print(f"ABORT — target leaf {_TARGET_LEAF!r} is not a level-1 Category slug.")
            return counts

        entity_ids = list(_TARGET_ENTITY_IDS)
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id.in_(entity_ids),
                EntityCategory.is_primary.is_(True),
            )
        }

        staged: list[str] = []
        for eid in entity_ids:
            name = _TARGET_ENTITY_IDS[eid]
            cur_id = current_primary.get(eid)
            cur_slug = id_to_slug.get(cur_id) if cur_id else None
            if cur_id is None:
                counts["no_primary_found"] += 1
                print(f"  ! {name[:42]:42}  (no primary entity_categories row — skipped)")
                continue
            if cur_id == target_id:
                counts["already_correct"] += 1
                print(f"  = {name[:42]:42}  already {_TARGET_LEAF}")
                continue
            counts["would_change"] += 1
            staged.append(eid)
            print(f"  - {name[:42]:42}  {cur_slug} -> {_TARGET_LEAF}")

        print(f"\nWould change: {counts.get('would_change', 0)}  ·  "
              f"already correct: {counts.get('already_correct', 0)}  ·  "
              f"no primary: {counts.get('no_primary_found', 0)}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                  f"{_sanitized_target()}.")
            return counts
        if not staged:
            print("\nNothing to write.")
            return counts

        snapshot = [
            {
                "id": ec.id,
                "entity_id": ec.entity_id,
                "category_id": ec.category_id,
                "is_primary": ec.is_primary,
            }
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id.in_(staged)
            )
        ]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"recategorize_realty_to_lodging_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        for eid in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == eid,
                EntityCategory.is_primary.is_(True),
            ):
                ec.is_primary = False
            existing = (
                session.query(EntityCategory)
                .filter(
                    EntityCategory.entity_id == eid,
                    EntityCategory.category_id == target_id,
                )
                .one_or_none()
            )
            if existing is None:
                session.add(
                    EntityCategory(entity_id=eid, category_id=target_id, is_primary=True)
                )
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
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
