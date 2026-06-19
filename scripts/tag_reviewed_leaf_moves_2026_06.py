"""Apply a HUMAN-REVIEWED set of provider→leaf primary moves (DRY-RUN; gated).

Companion to ``find_empty_leaf_candidates.py``. That diagnostic casts a wide net;
this script applies ONLY an explicit, hand-checked allowlist of entity_id→leaf
moves (``APPROVED`` below) — so a fuzzy candidate never moves without a person
having vetted it. Same safe write shape as the other backfills: clear the old
primary ``entity_categories`` link, set the new leaf primary, in one transaction,
after a rollback snapshot.

The seed list is the 2026-06-19 marine-supply review: the two genuine
marine-supply *retailers* pulled out of the 51 "marine" candidates (the rest were
boat repair/sales/service already filed correctly). Add more rows from a reviewed
``candidates.csv`` as you vet them.

    .venv\\Scripts\\python.exe scripts\\tag_reviewed_leaf_moves_2026_06.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\tag_reviewed_leaf_moves_2026_06.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): dry-run, confirm the plan, THEN a human runs --apply
--confirm. The agent never runs --apply against prod.
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

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# (entity_id, leaf_slug, note) — each row HAND-VERIFIED against candidates.csv.
APPROVED: tuple[tuple[str, str, str], ...] = (
    (
        "d6b2dca0-14c1-4ac2-ab30-db00dbc98ae5",
        "marine-supply",
        "West Marine — national marine-supply retailer (was clothing-and-apparel)",
    ),
    (
        "7be7251c-e9e0-40f0-a69b-010ee0dbd383",
        "marine-supply",
        "Connolly Marine Performance — marine parts retailer (was auto-parts)",
    ),
    # 2026-06-19 Golf hub: pull real golf venues onto the combined Golf page.
    # (Both indoor sims are covered — "The Back Nine Golf" is already on
    # golf-courses as indoor_golf_course; "Golf N' Brews" is the other.)
    (
        "5af265bb-2da7-4a4f-a060-c095e67ca2fa",
        "golf-courses",
        "Golf N' Brews — indoor golf simulator + bar (was bars-and-breweries)",
    ),
    (
        "e1b5064b-2f37-4198-8ede-69f449dc174a",
        "golf-courses",
        "Iron Wolf Golf & Country Club — golf course (misfiled under nonprofits)",
    ),
    (
        "5772280e-dd53-4efd-b0e9-e9a34228e9e6",
        "golf-courses",
        "Havasu Island Golf Course — golf course (had no primary leaf)",
    ),
    # 2026-06-19 bonus tags (strengthen thin leaves with clean name matches).
    (
        "68f869fe-bb57-4e10-8c63-d7ca83c539a6",
        "trailer-sales-and-repair",
        "ADRENALINE TRAILERS — trailer business (was auto-repair)",
    ),
    (
        "bdb77299-17d2-49a1-8acb-26fd489cc8c6",
        "trailer-sales-and-repair",
        "Competitive Trailers — trailer business (was auto-repair)",
    ),
    (
        "60836750-4f0b-4053-b68c-c58ff9aacc97",
        "off-road-shops-and-accessories",
        "Speed UTV Havasu — UTV/off-road shop (was sporting-goods)",
    ),
)


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
    own = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        leaf_id_by_slug = {
            c.slug: c.id for c in session.query(Category).filter(Category.level == 1).all()
        }
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(EntityCategory.is_primary.is_(True))
        }

        staged: list[tuple[str, int]] = []
        print("planned moves:")
        for eid, slug, note in APPROVED:
            leaf_id = leaf_id_by_slug.get(slug)
            entity = session.get(Entity, eid)
            if leaf_id is None:
                counts["leaf_absent"] += 1
                print(f"  SKIP  {note}\n        -> leaf {slug!r} not in DB")
                continue
            if entity is None:
                counts["entity_absent"] += 1
                print(f"  SKIP  {note}\n        -> entity {eid} not found")
                continue
            if current_primary.get(eid) == leaf_id:
                counts["already"] += 1
                print(f"  NOOP  {note}\n        -> already primary on {slug}")
                continue
            counts["would_move"] += 1
            staged.append((eid, leaf_id))
            print(f"  MOVE  {note}\n        -> {slug} (cat_id={leaf_id})")

        print(
            f"\n  would_move={counts.get('would_move', 0)} already={counts.get('already', 0)} "
            f"leaf_absent={counts.get('leaf_absent', 0)} entity_absent={counts.get('entity_absent', 0)}"
        )

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts
        if not staged:
            print("\nnothing to write.")
            return counts

        touched = list({eid for eid, _ in staged})
        snapshot = [
            {"id": ec.id, "entity_id": ec.entity_id, "category_id": ec.category_id, "is_primary": ec.is_primary}
            for ec in session.query(EntityCategory).filter(EntityCategory.entity_id.in_(touched))
        ]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"tag_reviewed_leaf_moves_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        for eid, leaf_id in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True)
            ):
                ec.is_primary = False
            existing = (
                session.query(EntityCategory)
                .filter(EntityCategory.entity_id == eid, EntityCategory.category_id == leaf_id)
                .one_or_none()
            )
            if existing is None:
                session.add(EntityCategory(entity_id=eid, category_id=leaf_id, is_primary=True))
            else:
                existing.is_primary = True
        session.commit()
        counts["primaries_changed"] = len(staged)
        print(f"\nAPPLIED — {len(staged)} reviewed primary moves in one transaction.")
        return counts
    finally:
        if own:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply a reviewed allowlist of provider→leaf moves.")
    ap.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    ap.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = ap.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
