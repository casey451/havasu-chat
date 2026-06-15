"""Recategorize non-food providers mis-filed in the Eat & Drink bucket (B6).

Finds active eat-bucket members (subcategory in EAT_SUBCATS or category in
EAT_LEGACY_CATEGORIES) that the non-food heuristic flags as not a place to eat
(app.categories.eat_pollution.looks_non_food — e.g. a wedding planner mis-tagged
``food_drink``), and proposes a corrected ``primary_category`` derived from each
row's GOOGLE signals (ignoring the bad category/subcategory). Setting the
canonical primary_category routes the row off Eat & Drink (route_provider_filter
keys on primary first), without touching the legacy fields.

DEFAULT IS DRY-RUN: prints the flagged rows + current/proposed primary and the
before/after counts, and writes NOTHING. ``--apply --confirm`` writes the new
primary_category for rows with a confident proposal and saves an undo snapshot
first; rows with no confident Google target are listed as ``<review>`` and left
untouched.

Usage (Windows):

    .venv\\Scripts\\python.exe scripts\\recat_eat_drink_mislabels.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\recat_eat_drink_mislabels.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import or_  # noqa: E402

from app.categories.eat_pollution import looks_non_food  # noqa: E402
from app.categories.subcategories import derive_primary_category  # noqa: E402
from app.chat.intents.dicts import EAT_LEGACY_CATEGORIES, EAT_SUBCATS  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def _proposed_primary(p: Provider) -> str | None:
    """The corrected primary derived from GOOGLE signals only — category and
    subcategory are forced to None so the mis-tag doesn't poison the proposal."""
    return derive_primary_category(
        category=None,
        subcategory=None,
        name=p.provider_name,
        google_primary_category=p.google_primary_category,
        google_categories=p.google_categories,
        attributes=p.attributes,
    )


def _sanitized_target() -> str:
    try:
        from app.db.database import engine

        url = engine.url
        return f"{url.host}:{url.port or ''}/{url.database}"
    except Exception:
        return "(unknown)"


def _eat_bucket(db) -> list[Provider]:
    """Active non-draft providers that land in the Eat & Drink bucket."""
    return (
        db.query(Provider)
        .filter(
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            or_(
                Provider.subcategory.in_(EAT_SUBCATS),
                Provider.category.in_(EAT_LEGACY_CATEGORIES),
            ),
        )
        .all()
    )


def _flagged(members: list[Provider]) -> list[Provider]:
    return [
        p
        for p in members
        if looks_non_food(p.category, p.google_primary_category, p.google_categories)
    ]


def run(*, apply: bool = False) -> Counter:
    db = SessionLocal()
    counts: Counter = Counter()
    snapshot: list[dict[str, object]] = []
    mode = "APPLY" if apply else "DRY-RUN (no writes)"
    print(f"[{mode}] target={_sanitized_target()}")
    try:
        members = _eat_bucket(db)
        flagged = _flagged(members)
        print(
            f"eat-bucket members: {len(members)}; "
            f"flagged non-food: {len(flagged)}\n"
        )
        for p in flagged:
            proposed = _proposed_primary(p)
            target = proposed or "<review>"
            counts[target] += 1
            print(
                f"  {(p.provider_name or '')[:42]:<42} "
                f"category={p.category!r} sub={p.subcategory!r} "
                f"google={p.google_primary_category!r} -> {target}"
            )
            if proposed and proposed != p.primary_category:
                snapshot.append(
                    {"id": p.id, "name": p.provider_name,
                     "old_primary": p.primary_category, "new_primary": proposed}
                )
                if apply:
                    p.primary_category = proposed
        if apply and snapshot:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = _ROOT / f"recat_eat_drink_snapshot_{stamp}.json"
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            print(f"\n[APPLY] undo snapshot written: {path.name} ({len(snapshot)} rows)")
        if apply:
            db.commit()
    finally:
        db.close()
    verb = "recategorized" if apply else "would recategorize"
    review = counts.get("<review>", 0)
    print(f"\n[{mode}] {verb} {len(snapshot)} rows; {review} need manual review")
    for target, n in counts.most_common():
        print(f"  -> {target}: {n}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--confirm", action="store_true", help="required alongside --apply")
    args = parser.parse_args()
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. Re-run with --apply --confirm.")
        sys.exit(2)
    run(apply=args.apply)


if __name__ == "__main__":
    main()
