"""Re-shelve genuinely-marine shops mis-filed under auto/Car-Repair to boat-repair.

QA diagnostic 2026-06-17 (#2 boat↔auto): "fix my boat" surfaced auto/RV "Car
Repair" yards above the real marine shop. The chat de-rank (PR #390) fixes the
*ranking* query-side; this script fixes the underlying *data*: providers whose
google_primary_category is an automotive/repair bucket but whose name clearly
signals MARINE (marine / boat / watercraft / outboard / pontoon / jet-ski) are
re-shelved to the PRIMARY leaf ``boat-repair-and-service``.

Mirrors ``scripts/recategorize_water_misfiled.py`` exactly: changes only the
PRIMARY entity_categories link, wraps writes in one transaction, saves a JSON
rollback snapshot first, writes a per-change CSV.

Conservative scope (read the CSV before trusting it):
  * google_primary_category in an automotive/repair set, AND
  * provider_name matches a marine signal on a word boundary
    (so "Britton's Auto" is NOT touched, "J&J ... Marine Service" IS).

DEFAULT IS DRY-RUN: prints transition counts + writes a CSV, writes NOTHING to
the DB. ``--apply`` requires ``--confirm``. Every run prints the sanitized DB
target — the repo .env can point DATABASE_URL at prod.

    .venv\\Scripts\\python.exe scripts\\recategorize_marine_carrepair.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recategorize_marine_carrepair.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the counts + change CSV, get
approval, THEN a human runs --apply --confirm against prod. The agent never runs
--apply against prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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

_TARGET_LEAF = "boat-repair-and-service"

# Marine name signal — word-boundary so an auto shop with "board"/"arctic" etc.
# doesn't collide; covers jet-ski spellings (space / hyphen / joined).
_MARINE_RE = re.compile(
    r"\b(marine|boat|watercraft|outboard|pontoon|jet[\s-]?ski)\b", re.IGNORECASE
)
# Automotive/repair primary categories that a real marine shop is mis-filed under.
_AUTO_CATEGORIES = {
    "car_repair",
    "auto_repair_shop",
    "rv_repair_shop",
    "rv_supply_store",
    "auto_parts_store",
    "truck_repair_shop",
}


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _is_marine_name(name: str | None) -> bool:
    return bool(_MARINE_RE.search(name or ""))


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
        target_leaf_id = slug_to_id.get(_TARGET_LEAF)
        if target_leaf_id is None:
            print(f"ABORT — target leaf '{_TARGET_LEAF}' not found in categories.")
            return counts

        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True)
            )
        }

        providers = (
            session.query(Provider)
            .filter(Provider.is_active.is_(True))
            .all()
        )
        counts["active_providers"] = len(providers)

        staged: list[tuple[str, int]] = []
        change_rows: list[dict] = []
        for p in providers:
            gcat = (p.google_primary_category or "").strip().lower()
            if gcat not in _AUTO_CATEGORIES:
                continue
            if not _is_marine_name(p.provider_name):
                continue
            counts["marine_named_auto"] += 1
            cur_leaf_id = current_primary.get(p.entity_id)
            if cur_leaf_id == target_leaf_id:
                counts["already_correct"] += 1
                continue
            counts["would_change"] += 1
            staged.append((p.entity_id, target_leaf_id))
            change_rows.append(
                {
                    "entity_id": p.entity_id,
                    "provider_id": p.id,
                    "name": p.provider_name,
                    "google_primary_category": p.google_primary_category or "",
                    "old_leaf": id_to_slug.get(cur_leaf_id, "(none)"),
                    "new_leaf": _TARGET_LEAF,
                }
            )

        out_path = out_path or (
            _ROOT / f"recategorize_marine_carrepair_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        )
        _write_changes_csv(out_path, change_rows)

        print(f"Active providers        : {counts['active_providers']}")
        print(f"Marine-named auto rows  : {counts.get('marine_named_auto', 0)}")
        print(f"Already correct         : {counts.get('already_correct', 0)}")
        print(f"Would change            : {counts.get('would_change', 0)}")
        print(f"Change CSV              : {out_path}\n")
        print("Changes (name -> new leaf):")
        for r in change_rows:
            print(
                f"  - {r['name'][:40]:40}  {r['google_primary_category'][:18]:18}  "
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
        snap_path = snapshot_dir / f"recategorize_marine_carrepair_snapshot_{stamp}.json"
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
