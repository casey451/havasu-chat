"""Taxonomy anchor checker — the §6.1 phase gate (Track B3 prep).

Standalone and LLM-free: reads the regression sidecar CSV
(``scripts/eval_anchors/taxonomy_regression_10.csv``), looks up each anchor
entity by name, resolves its PRIMARY leaf (EntityCategory ``is_primary`` →
level-1 Category + parent department), and compares against the expected
department/leaf. Exits non-zero on any mismatch (or missing anchor, unless
``--allow-missing``) so it can gate a migration phase or run in CI.

Spec: HAVA_AUDIT_AND_TAXONOMY_REBUILD.md §6.1 — "Standalone script
recommended: it keeps the confabulation harness single-purpose and runs
without LLM calls. Exit non-zero on any mismatch → CI-able and a phase-gate
requirement." Phase usage (§7 step 2): run with ``--department`` limited to
the migrating department's anchors.

READ-ONLY — writes nothing.

Usage:
    python scripts/check_taxonomy_anchors.py
    python scripts/check_taxonomy_anchors.py --department "Health & Medical"
    python scripts/check_taxonomy_anchors.py --allow-missing   # provisional names
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

DEFAULT_ANCHORS = _ROOT / "scripts" / "eval_anchors" / "taxonomy_regression_10.csv"


@dataclass(frozen=True)
class AnchorResult:
    case_id: str
    row_name: str
    expected_department: str
    expected_leaf: str
    actual_department: str | None
    actual_leaf: str | None
    status: str  # ok | mismatch | missing | no_primary


def _load_anchors(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def check_anchors(
    session,
    anchors: list[dict[str, str]],
    *,
    department: str | None = None,
) -> list[AnchorResult]:
    """Resolve each anchor's live primary leaf and compare to expectations."""
    from sqlalchemy import func, select

    from app.db.models import Category, Entity, EntityCategory

    results: list[AnchorResult] = []
    for row in anchors:
        # NUL-strip: stale filesystem caches have served this CSV with
        # trailing NUL padding; a phantom row must never count as an anchor.
        name = (row.get("row_name") or "").replace("\x00", "").strip()
        exp_dept = (row.get("expected_department") or "").strip()
        exp_leaf = (row.get("expected_leaf") or "").strip()
        case_id = (row.get("case_id") or "?").strip()
        if not name:
            continue
        if department and exp_dept.lower() != department.strip().lower():
            continue

        entity = session.scalar(
            select(Entity).where(
                func.lower(Entity.name) == name.lower(),
                Entity.is_active.is_(True),
            )
        )
        if entity is None:
            results.append(
                AnchorResult(case_id, name, exp_dept, exp_leaf, None, None, "missing")
            )
            continue

        primary = session.scalar(
            select(Category)
            .join(EntityCategory, EntityCategory.category_id == Category.id)
            .where(
                EntityCategory.entity_id == entity.id,
                EntityCategory.is_primary.is_(True),
                Category.level == 1,
            )
        )
        if primary is None:
            results.append(
                AnchorResult(case_id, name, exp_dept, exp_leaf, None, None, "no_primary")
            )
            continue

        parent = session.get(Category, primary.parent_id) if primary.parent_id else None
        actual_dept = parent.name if parent else None
        actual_leaf = primary.name
        ok = (
            actual_leaf.strip().lower() == exp_leaf.lower()
            and (actual_dept or "").strip().lower() == exp_dept.lower()
        )
        results.append(
            AnchorResult(
                case_id,
                name,
                exp_dept,
                exp_leaf,
                actual_dept,
                actual_leaf,
                "ok" if ok else "mismatch",
            )
        )
    return results


def _print_report(results: list[AnchorResult]) -> None:
    width = max((len(r.row_name) for r in results), default=10)
    for r in results:
        mark = {"ok": "PASS", "mismatch": "FAIL", "missing": "MISS", "no_primary": "NOPRIM"}[
            r.status
        ]
        actual = (
            f"{r.actual_department} > {r.actual_leaf}"
            if r.actual_leaf
            else "(not found)" if r.status == "missing" else "(no primary leaf)"
        )
        print(
            f"  [{mark:6}] #{r.case_id:>2} {r.row_name:<{width}}  "
            f"expected {r.expected_department} > {r.expected_leaf}  ·  got {actual}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchors", type=Path, default=DEFAULT_ANCHORS, help="Anchor sidecar CSV path."
    )
    parser.add_argument(
        "--department",
        default=None,
        help="Only check anchors whose expected_department matches (phase gate).",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Missing/no-primary anchors warn instead of fail (provisional names "
        "pre-WS-3 reconcile; mismatches still fail).",
    )
    args = parser.parse_args(argv)

    from app.db.database import SessionLocal

    anchors = _load_anchors(args.anchors)
    with SessionLocal() as session:
        results = check_anchors(session, anchors, department=args.department)

    print(f"taxonomy anchors: {len(results)} checked"
          f"{f' (department={args.department})' if args.department else ''}")
    _print_report(results)

    mismatches = [r for r in results if r.status == "mismatch"]
    absent = [r for r in results if r.status in ("missing", "no_primary")]
    failures = len(mismatches) + (0 if args.allow_missing else len(absent))
    print(
        f"\n{sum(r.status == 'ok' for r in results)} ok · "
        f"{len(mismatches)} mismatch · {len(absent)} missing/no-primary"
        f"{' (allowed)' if args.allow_missing and absent else ''}"
    )
    if failures:
        print("GATE: FAIL")
        return 1
    print("GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
