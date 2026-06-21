"""Create the missing level-1 service leaves for the 2026-06-20 search-coverage
work (Casey: "make every plausible service search land on a page").

Four of these slugs are already referenced by the chat router
(``_QUERY_TO_LEAF`` / ``PENDING_LEAF_SLUGS``) but were never seeded as a
``categories`` row, so the search term routes nowhere. Two (``painting``,
``locksmiths``) are brand-new leaves. This script inserts exactly the missing
Category rows under their existing level-0 departments and no-ops on any that
already exist. It deliberately does NOT run the full ``seed_taxonomy.py``
(which would upsert the whole tree and could revert recent prod relabels).

Once a leaf exists AND has >=1 active entity whose PRIMARY ``entity_categories``
link is that leaf, the page renders and the search term works. Seed the
businesses with ``scripts/seed_service_businesses_2026_06_20.py`` and approve
them in /admin (approval is what assigns the primary category + dual-writes the
entity graph).

DEFAULT IS DRY-RUN: prints the plan, writes NOTHING. ``--apply`` requires
``--confirm``. An insert run writes a JSON rollback snapshot first.

    .venv\\Scripts\\python.exe scripts\\create_missing_service_leaves_2026_06_20.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\create_missing_service_leaves_2026_06_20.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the plan, get approval, THEN a
human runs --apply --confirm against prod. The agent never runs --apply on prod.
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
from app.db.models import Category  # noqa: E402

# (leaf_slug, leaf_name, parent department slug). Department slugs are the
# live level-0 taxonomy keys (see docs/proposals/taxonomy-seed.json top level).
LEAVES_TO_CREATE: tuple[tuple[str, str, str], ...] = (
    ("junk-removal-and-hauling", "Junk Removal & Hauling", "home-and-property-services"),
    ("property-management", "Property Management", "professional-and-financial"),
    ("laundry-and-dry-cleaning", "Laundry & Dry Cleaning", "professional-and-financial"),
    ("auto-glass", "Auto Glass", "auto-rv-and-marine"),
    ("painting", "Painting", "home-and-property-services"),
    ("locksmiths", "Locksmiths", "home-and-property-services"),
    # 2026-06-20 batch 2
    ("golf-carts", "Golf Carts", "auto-rv-and-marine"),
    ("window-tint-and-wraps", "Window Tint & Wraps", "auto-rv-and-marine"),
    ("pressure-washing-and-exterior-cleaning",
     "Pressure Washing & Exterior Cleaning", "home-and-property-services"),
    ("funeral-cremation-and-cemeteries",
     "Funeral, Cremation & Cemeteries", "community-and-civic"),
    ("hearing-and-audiology", "Hearing & Audiology", "health-and-medical"),
    ("flooring", "Flooring", "home-and-property-services"),
    ("fencing", "Fencing", "home-and-property-services"),
    ("garage-doors", "Garage Doors", "home-and-property-services"),
    ("concrete-and-masonry", "Concrete & Masonry", "home-and-property-services"),
    # 2026-06-20 batch 3
    ("trailer-sales-and-repair", "Trailer Sales & Repair", "auto-rv-and-marine"),
    ("mobile-home-services", "Mobile Home Services", "home-and-property-services"),
    ("shade-screens-and-patio-covers",
     "Shade Screens & Patio Covers", "home-and-property-services"),
    ("pet-waste-removal", "Pet Waste Removal", "pets"),
    ("firearms-and-shooting-sports", "Firearms & Shooting Sports", "shopping-and-retail"),
    ("medical-specialists-and-imaging",
     "Medical Specialists & Imaging", "health-and-medical"),
    ("drywall", "Drywall", "home-and-property-services"),
    ("carpentry-and-cabinets", "Carpentry & Cabinets", "home-and-property-services"),
    ("welding-and-fabrication", "Welding & Fabrication", "home-and-property-services"),
    ("gutters", "Gutters", "home-and-property-services"),
    ("windows-and-doors", "Windows & Doors", "home-and-property-services"),
    ("appliance-repair", "Appliance Repair", "home-and-property-services"),
    ("liquor-stores", "Liquor Stores", "shopping-and-retail"),
    ("pawn-shops", "Pawn Shops", "shopping-and-retail"),
    ("nurseries-and-garden-centers", "Nurseries & Garden Centers", "shopping-and-retail"),
)


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def plan_leaf_action(
    leaf_slug: str, leaf_name: str, dept_slug: str, existing_by_slug: dict[str, dict]
) -> tuple[str, str]:
    """Decide the action for one leaf. Pure (no DB) for unit-testing.

    Returns ``(action, message)`` where action is ``insert`` / ``noop`` / ``abort``.
    """
    dept = existing_by_slug.get(dept_slug)
    if dept is None or dept["level"] != 0:
        return ("abort", f"department {dept_slug!r} not found at level 0 — cannot parent {leaf_slug!r}")
    leaf = existing_by_slug.get(leaf_slug)
    if leaf is not None:
        if leaf["level"] == 1 and leaf["parent_id"] == dept["id"]:
            return ("noop", f"{leaf_slug!r} already a level-1 leaf under {dept_slug}")
        return (
            "abort",
            f"{leaf_slug!r} already exists as level={leaf['level']} "
            f"parent_id={leaf['parent_id']} — refusing to mutate it",
        )
    return ("insert", f"insert level-1 {leaf_slug!r} ({leaf_name!r}) under {dept_slug} id={dept['id']}")


def run(*, apply: bool = False, confirm: bool = False, snapshot_dir: Path | None = None,
        session=None) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    created: list[dict] = []
    try:
        print(f"DB target: {_sanitized_target()}\n")
        cats = session.query(Category).all()
        existing_by_slug = {
            c.slug: {"id": c.id, "level": c.level, "parent_id": c.parent_id} for c in cats
        }
        # next sort_order per department, advanced as we plan inserts
        sort_cursor: dict[int, int] = {}
        for slug, name, dept_slug in LEAVES_TO_CREATE:
            action, message = plan_leaf_action(slug, name, dept_slug, existing_by_slug)
            counts[action] += 1
            print(f"plan: {action.upper():6} — {message}")
            if action != "insert" or not (apply and confirm):
                continue
            dept_id = existing_by_slug[dept_slug]["id"]
            if dept_id not in sort_cursor:
                sort_cursor[dept_id] = sum(
                    1 for c in cats if c.level == 1 and c.parent_id == dept_id
                )
            leaf = Category(slug=slug, name=name, level=1, sort_order=sort_cursor[dept_id])
            leaf.parent_id = dept_id
            sort_cursor[dept_id] += 1
            session.add(leaf)
            session.flush()  # assign id
            created.append(
                {"id": leaf.id, "slug": leaf.slug, "name": leaf.name,
                 "level": leaf.level, "parent_id": leaf.parent_id}
            )
            # so a later duplicate slug in the list would no-op
            existing_by_slug[slug] = {"id": leaf.id, "level": 1, "parent_id": dept_id}

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts
        if not created:
            print("\nNothing to insert (all leaves already exist).")
            return counts

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"create_missing_service_leaves_snapshot_{stamp}.json"
        ids = ", ".join(str(c["id"]) for c in created)
        snap_path.write_text(
            json.dumps(
                {"created": created, "rollback": f"DELETE FROM categories WHERE id IN ({ids});"},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nrollback snapshot: {snap_path}")
        session.commit()
        counts["committed"] += 1
        print(f"\nAPPLIED — created {len(created)} leaf/leaves: {[c['slug'] for c in created]}")
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
