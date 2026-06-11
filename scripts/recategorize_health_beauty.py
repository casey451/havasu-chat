"""Re-shelve the health/beauty skin-cluster leaves (DRY-RUN by default; gated).

Fixes the inverted Med Spas / Dermatology / Day Spas leaves found in the
2026-06-11 audit, per Casey's routing decisions. For every active provider it
computes the correct leaf via ``app.categories.health_beauty_leaf_rules.
classify_skin_spa_leaf`` (pure name + Google-type signal rules) and, where that
differs from the provider's CURRENT primary ``entity_categories`` leaf, stages a
reassignment. Rows the classifier returns ``None`` for (hair, nail, GPs, every
non-skin/spa business) are never touched — minimal blast radius.

This mirrors ``scripts/apply_taxonomy_remap.py`` exactly: it changes only the
PRIMARY entity_categories link (clear old primary, set new), wraps writes in one
transaction, and saves a JSON rollback snapshot first.

DEFAULT IS DRY-RUN: prints transition counts + writes a per-change CSV, writes
NOTHING to the DB. ``--apply`` requires ``--confirm``. Every run prints the
sanitized DB target — the repo .env can point DATABASE_URL at prod.

    .venv\\Scripts\\python.exe scripts\\recategorize_health_beauty.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_health_beauty.py --apply --confirm  # writes

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

from app.categories.health_beauty_leaf_rules import (  # noqa: E402
    classify_skin_spa_leaf,
)
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402


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

        # Leaf slug <-> id (level-1 categories are the leaves).
        slug_to_id = {
            slug: cid
            for slug, cid in session.query(Category.slug, Category.id).filter(
                Category.level == 1
            )
        }
        id_to_slug = {cid: slug for slug, cid in slug_to_id.items()}

        # Current PRIMARY leaf per entity.
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True)
            )
        }

        # Scope to Google-sourced directory businesses (where the migration
        # mis-shelving lives); never event/program providers that might happen
        # to carry "massage"/"spa" in a class name.
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
            desired_slug = classify_skin_spa_leaf(
                p.provider_name, p.google_primary_category, p.google_categories
            )
            if desired_slug is None:
                continue
            counts["in_scope"] += 1
            new_leaf_id = slug_to_id.get(desired_slug)
            if new_leaf_id is None:
                counts["unresolved_leaf"] += 1
                continue
            cur_leaf_id = current_primary.get(p.entity_id)
            if cur_leaf_id == new_leaf_id:
                counts["already_correct"] += 1
                continue
            old_slug = id_to_slug.get(cur_leaf_id, "∅") if cur_leaf_id else "∅"
            counts["would_change"] += 1
            transitions[(old_slug, desired_slug)] += 1
            staged.append((p.entity_id, new_leaf_id))
            change_rows.append(
                {
                    "entity_id": p.entity_id,
                    "provider_id": p.id,
                    "name": p.provider_name,
                    "google_primary_category": p.google_primary_category or "",
                    "old_leaf": old_slug,
                    "new_leaf": desired_slug,
                }
            )

        # --- report ---------------------------------------------------------
        out_path = out_path or (
            _ROOT / f"recategorize_health_beauty_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        )
        _write_changes_csv(out_path, change_rows)

        print(f"Active providers     : {counts['active_providers']}")
        print(f"In scope (classified): {counts.get('in_scope', 0)}")
        print(f"Already correct      : {counts.get('already_correct', 0)}")
        print(f"Would change         : {counts.get('would_change', 0)}")
        print(f"Unresolved leaf      : {counts.get('unresolved_leaf', 0)}")
        print(f"Change CSV           : {out_path}\n")
        print("Transitions (old leaf -> new leaf):")
        for (old, new), n in transitions.most_common():
            print(f"  {n:>4}  {old:>26}  ->  {new}")
        print("\nSample changes:")
        for r in change_rows[:40]:
            print(
                f"  - {r['name'][:38]:38}  {r['google_primary_category'][:18]:18}  "
                f"{r['old_leaf']:>26} -> {r['new_leaf']}"
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

        # --- rollback snapshot of every entity_categories row we may touch ---
        touched_ids = list({eid for eid, _ in staged})
        snapshot = [
            {
                "id": ec.id,
                "entity_id": ec.entity_id,
                "category_id": ec.category_id,
                "is_primary": ec.is_primary,
            }
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id.in_(touched_ids)
            )
        ] if touched_ids else []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"recategorize_health_beauty_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        # --- one transaction: reassign primaries ---------------------------
        for entity_id, leaf_id in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.is_primary.is_(True),
            ):
                ec.is_primary = False
            existing = session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.category_id == leaf_id,
            ).one_or_none()
            if existing is None:
                session.add(
                    EntityCategory(
                        entity_id=entity_id, category_id=leaf_id, is_primary=True
                    )
                )
            else:
                existing.is_primary = True
        session.commit()
        counts["primaries_changed"] = len(staged)
        print(
            f"\nAPPLIED — {len(staged)} primary leaf reassignments in one transaction."
        )
        return counts
    finally:
        if own_session:
            session.close()


def _write_changes_csv(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "entity_id", "provider_id", "name", "google_primary_category",
        "old_leaf", "new_leaf",
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
