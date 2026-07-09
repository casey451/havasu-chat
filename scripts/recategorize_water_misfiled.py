"""Re-shelve rows mis-filed under boat-and-watercraft-rentals to their true leaf.

QA diagnostic 2026-06-12 (Phase 4): the ``boat-and-watercraft-rentals`` leaf was
stamped on businesses that don't rent watercraft, so "where can I rent a kayak?"
surfaced detailing shops. This moves them to the correct PRIMARY leaf via
``classify_water_misfiled_leaf``: detailing shops -> auto-marine-detailing, the
saloon -> eat-drink, plus the Casey-approved (2026-06-12) marine rule (supplier/
store/dealer types -> boat-sales, explicit marine-service names ->
boat-repair-and-service). Genuine rentals/tours/guides are left untouched.

This mirrors ``scripts/recategorize_health_beauty.py`` exactly: changes only the
PRIMARY entity_categories link, scoped to rows whose CURRENT primary leaf is
``boat-and-watercraft-rentals``, wraps writes in one transaction, and saves a
JSON rollback snapshot first.

DEFAULT IS DRY-RUN: prints transition counts + writes a per-change CSV, writes
NOTHING to the DB. ``--apply`` requires ``--confirm``. Every run prints the
sanitized DB target — the repo .env can point DATABASE_URL at prod.

    .venv\\Scripts\\python.exe scripts\\recategorize_water_misfiled.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_water_misfiled.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the counts + the change CSV,
get approval, THEN a human runs --apply --confirm against prod. The agent never
runs --apply against prod.
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

from app.categories.water_misfiled_rules import classify_water_misfiled_leaf  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402

_SOURCE_LEAF = "boat-and-watercraft-rentals"


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
    out_path: Path | None = None,
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

        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True)
            )
        }

        providers = (
            session.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.google_place_id.isnot(None),
            )
            .all()
        )
        counts["active_providers"] = len(providers)

        transitions: Counter = Counter()
        staged: list[tuple[str, int]] = []  # (entity_id, new_leaf_id)
        change_rows: list[dict] = []

        for p in providers:
            cur_leaf_id = current_primary.get(p.entity_id)
            cur_slug = id_to_slug.get(cur_leaf_id) if cur_leaf_id else None
            # Scope: only rows currently shelved under boat-and-watercraft-rentals.
            if cur_slug != _SOURCE_LEAF:
                continue
            counts["in_source_leaf"] += 1
            desired_slug = classify_water_misfiled_leaf(
                p.provider_name, p.google_primary_category, p.google_categories
            )
            if desired_slug is None:
                continue  # genuine rental, or repair/sales judgment -> leave alone
            counts["classified"] += 1
            new_leaf_id = slug_to_id.get(desired_slug)
            if new_leaf_id is None:
                counts["unresolved_leaf"] += 1
                continue
            if cur_leaf_id == new_leaf_id:
                counts["already_correct"] += 1
                continue
            counts["would_change"] += 1
            transitions[(_SOURCE_LEAF, desired_slug)] += 1
            staged.append((p.entity_id, new_leaf_id))
            change_rows.append(
                {
                    "entity_id": p.entity_id,
                    "provider_id": p.id,
                    "name": p.provider_name,
                    "google_primary_category": p.google_primary_category or "",
                    "old_leaf": _SOURCE_LEAF,
                    "new_leaf": desired_slug,
                }
            )

        out_path = out_path or (
            _ROOT / f"recategorize_water_misfiled_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        )
        _write_changes_csv(out_path, change_rows)

        print(f"Active providers       : {counts['active_providers']}")
        print(f"In source leaf         : {counts.get('in_source_leaf', 0)}")
        print(f"Classified (correctable): {counts.get('classified', 0)}")
        print(f"Already correct        : {counts.get('already_correct', 0)}")
        print(f"Would change           : {counts.get('would_change', 0)}")
        print(f"Unresolved leaf        : {counts.get('unresolved_leaf', 0)}")
        print(f"Change CSV             : {out_path}\n")
        print("Transitions (old leaf -> new leaf):")
        for (old, new), n in transitions.most_common():
            print(f"  {n:>4}  {old:>30}  ->  {new}")
        print("\nChanges:")
        for r in change_rows:
            print(
                f"  - {r['name'][:38]:38}  {r['google_primary_category'][:18]:18}  "
                f"{r['old_leaf']} -> {r['new_leaf']}"
            )

        if not apply:
            print(
                "\nDRY RUN — no rows written. Review the CSV, then re-run with "
                "--apply --confirm against the intended target to write."
            )
            return counts
        if not confirm:
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        touched_ids = list({eid for eid, _ in staged})
        snapshot = (
            [
                {
                    "id": ec.id,
                    "entity_id": ec.entity_id,
                    "category_id": ec.category_id,
                    "is_primary": ec.is_primary,
                }
                for ec in session.query(EntityCategory).filter(
                    EntityCategory.entity_id.in_(touched_ids)
                )
            ]
            if touched_ids
            else []
        )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"recategorize_water_misfiled_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        for entity_id, leaf_id in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.is_primary.is_(True),
            ):
                ec.is_primary = False
            existing = (
                session.query(EntityCategory)
                .filter(
                    EntityCategory.entity_id == entity_id,
                    EntityCategory.category_id == leaf_id,
                )
                .one_or_none()
            )
            if existing is None:
                session.add(
                    EntityCategory(entity_id=entity_id, category_id=leaf_id, is_primary=True)
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


def _write_changes_csv(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "entity_id", "provider_id", "name", "google_primary_category", "old_leaf", "new_leaf",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    parser.add_argument("--out", type=Path, default=None, help="Change-CSV path.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
