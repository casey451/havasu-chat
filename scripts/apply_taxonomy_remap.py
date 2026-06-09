"""Apply the A.3 taxonomy remap to entities (DRY-RUN by default; gated).

Reads ``docs/proposals/A-migration-PROD-final.csv`` (every entity -> proposed
department + leaf) and, for each row, stages the entity's single PRIMARY
category as the resolved leaf. Folds in Workstream C: rows the migration flagged
``Vacation Rental — PARK [C]`` and the EXCLUDE/TEST-SEED rows are deactivated
(``is_active = false``, reversible), never reassigned.

Per-row action:
* deactivate  -> proposed_department is ``(EXCLUDE …)`` / ``(TEST/SEED …)``, OR
                 the leaf carries a ``[C]`` Workstream-C flag  -> is_active=False
* skip        -> signal ``unresolved`` or a ``(needs review)`` dept/leaf (the
                 13 the migration could not resolve) -> left untouched
* assign      -> resolve (department, leaf) to a seeded leaf category and set it
                 as the entity's primary (clearing any old primary)

The leaf name is normalised before lookup (a trailing ``[NEW]`` annotation is
stripped) so the 3 new leaves resolve to their seeded rows.

DEFAULT IS DRY-RUN: prints the action counts + leaf-resolution coverage and
writes nothing. ``--apply`` requires ``--confirm``, wraps every write in ONE
transaction, and first saves a rollback snapshot of the affected
``entity_categories`` rows to a JSON file. Every run prints the sanitized DB
target — the repo's .env can point DATABASE_URL at prod.

    .venv\\Scripts\\python.exe scripts\\apply_taxonomy_remap.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\apply_taxonomy_remap.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the counts, get approval,
THEN a human runs --apply --confirm against prod (after the migration + seed
have shipped there). The agent never runs --apply against prod.
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

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

DEFAULT_CSV = _ROOT / "docs" / "proposals" / "A-migration-PROD-final.csv"
DEFAULT_SEED = _ROOT / "docs" / "proposals" / "taxonomy-seed.json"

ACTION_ASSIGN = "assign"
ACTION_SKIP = "skip_review"
ACTION_DEACTIVATE = "deactivate"

_ANNOTATION_RE = re.compile(r"\s*\[[^\]]*\]\s*$")


def normalize_leaf(leaf: str) -> str:
    """Strip a trailing bracket annotation (e.g. ' [NEW]') from a leaf name."""
    return _ANNOTATION_RE.sub("", leaf).strip()


def classify(department: str, leaf: str, signal: str) -> str:
    """Decide the per-row action from the CSV's department/leaf/signal."""
    if (
        department.startswith("(EXCLUDE")
        or department.startswith("(TEST/SEED")
        or "[C]" in leaf
    ):
        return ACTION_DEACTIVATE
    if signal == "unresolved" or department == "(needs review)" or leaf == "(needs review)":
        return ACTION_SKIP
    return ACTION_ASSIGN


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _leaf_slug_map(seed_path: Path) -> dict[tuple[str, str], str]:
    """(department name, leaf name) -> leaf slug, from the taxonomy seed JSON."""
    with seed_path.open(encoding="utf-8") as f:
        seed = json.load(f)
    out: dict[tuple[str, str], str] = {}
    for dept in seed.values():
        for leaf_slug, leaf in (dept.get("leaves") or {}).items():
            out[(dept["name"], leaf["name"])] = leaf_slug
    return out


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    csv_path: Path | None = None,
    seed_path: Path | None = None,
    snapshot_dir: Path | None = None,
    session=None,
) -> Counter:
    """Stage (and optionally commit) the taxonomy remap. Dry-run by default."""
    csv_path = csv_path or DEFAULT_CSV
    seed_path = seed_path or DEFAULT_SEED
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}")
        print(f"csv:  {csv_path}\nseed: {seed_path}\n")

        name_to_slug = _leaf_slug_map(seed_path)
        slug_to_id = {
            slug: cid
            for slug, cid in session.query(Category.slug, Category.id).filter(
                Category.level == 1
            )
        }

        with csv_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        counts["csv_rows"] = len(rows)

        # entity_id -> desired leaf category_id (assign), and the deactivate set.
        assign_plan: list[tuple[str, int]] = []
        deactivate_ids: list[str] = []
        for r in rows:
            dep, leaf, sig = (
                r["proposed_department"],
                r["proposed_leaf"],
                r["signal"],
            )
            action = classify(dep, leaf, sig)
            counts[action] += 1
            if action == ACTION_DEACTIVATE:
                deactivate_ids.append(r["entity_id"])
            elif action == ACTION_ASSIGN:
                slug = name_to_slug.get((dep, normalize_leaf(leaf)))
                leaf_id = slug_to_id.get(slug) if slug else None
                if leaf_id is None:
                    counts["unresolved_leaf"] += 1
                    continue
                assign_plan.append((r["entity_id"], leaf_id))

        # Compare desired primary to current, against whatever DB we're pointed
        # at. On a local dry-run the prod entities are absent -> "entity_absent"
        # (each would be a would-change on the real target).
        present_ids = {
            eid
            for (eid,) in session.query(Entity.id).filter(
                Entity.id.in_([e for e, _ in assign_plan])
            )
        } if assign_plan else set()
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True),
                EntityCategory.entity_id.in_(list(present_ids)),
            )
        } if present_ids else {}

        would_change = unchanged = entity_absent = 0
        staged: list[tuple[str, int]] = []
        for entity_id, leaf_id in assign_plan:
            if entity_id not in present_ids:
                entity_absent += 1
                continue
            if current_primary.get(entity_id) == leaf_id:
                unchanged += 1
            else:
                would_change += 1
                staged.append((entity_id, leaf_id))

        present_deactivate = {
            eid
            for (eid,) in session.query(Entity.id).filter(
                Entity.id.in_(deactivate_ids), Entity.is_active.is_(True)
            )
        } if deactivate_ids else set()

        # --- report ------------------------------------------------------
        print("action plan (from CSV):")
        for k in (ACTION_ASSIGN, ACTION_SKIP, ACTION_DEACTIVATE):
            print(f"  {counts.get(k, 0):>5}  {k}")
        print(f"  {counts.get('unresolved_leaf', 0):>5}  unresolved_leaf (assign rows w/o a seeded leaf)")
        print(f"  {len(rows):>5}  total CSV rows\n")
        print("assign rows vs the current DB:")
        print(f"  {would_change:>5}  would-change (primary differs)")
        print(f"  {unchanged:>5}  unchanged (primary already correct)")
        print(f"  {entity_absent:>5}  entity_absent (not in this DB; would-change on prod)")
        print(f"\ndeactivate (Workstream C): {len(deactivate_ids)} flagged, "
              f"{len(present_deactivate)} currently active in this DB")

        if not apply:
            print(
                "\nDRY RUN — no rows written. Re-run with --apply --confirm "
                "against the seeded target to write."
            )
            return counts
        if not confirm:
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        # --- rollback snapshot of every entity_categories row we may touch ---
        touched_ids = list({eid for eid, _ in staged} | present_deactivate)
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
        snap_path = snapshot_dir / f"taxonomy_remap_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        # --- one transaction: reassign primaries + deactivate ---------------
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
        deactivated = 0
        for entity in session.query(Entity).filter(
            Entity.id.in_(list(present_deactivate))
        ):
            entity.is_active = False
            deactivated += 1
        session.commit()
        counts["primaries_changed"] = len(staged)
        counts["deactivated"] = deactivated
        print(
            f"\nAPPLIED — {len(staged)} primary reassignments, "
            f"{deactivated} deactivations, in one transaction."
        )
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    parser.add_argument("--csv", type=Path, default=None, help="Override the remap CSV.")
    parser.add_argument("--seed", type=Path, default=None, help="Override the seed JSON.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, csv_path=args.csv, seed_path=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
