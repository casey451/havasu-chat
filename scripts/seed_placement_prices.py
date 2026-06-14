"""Seed the global default price book into ``placement_prices`` (idempotent, gated).

Phase F monetization (brief §7): pricing is DATA, not code. This seeds the
*global default* prices (``category_slug IS NULL``) for each paid surface so the
serving/portal layers have a price to read the moment a placement is sold. The
admin panel (Phase G) edits these and adds per-category overrides without a
deploy — this script only establishes the baseline, it never deletes overrides.

Upsert is by the unique key ``(placement_type, category_slug, rank_tier)``:
an existing row is updated in place (price + active), a missing row is inserted.
Per-category override rows (non-NULL ``category_slug``) are never touched.

DEFAULT IS DRY-RUN: prints what it would insert/update and writes nothing.
``--apply`` requires ``--confirm`` to write (the repo's .env can point
DATABASE_URL at prod — every run prints the sanitized target). Before any write
it dumps the current ``placement_prices`` rows to a timestamped snapshot JSON in
the repo root so the change is reversible.

    .venv\\Scripts\\python.exe scripts\\seed_placement_prices.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\seed_placement_prices.py --apply --confirm  # writes
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

from sqlalchemy import select  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.monetization_models import PlacementPrice, PlacementType  # noqa: E402

# Placeholder monthly defaults in CENTS. These are intentionally round starter
# numbers — the whole point of the price book is that the admin retunes them.
# category_slug is NULL on every row (global defaults); rank_tier is set only for
# the category_rank sticky tiers, with a NULL-tier fallback for any tier without
# an explicit price. Tier 1 (locked #1 spot) is the most valuable.
DEFAULT_PRICES: list[dict] = [
    {"placement_type": PlacementType.homepage_rotating.value, "rank_tier": None,
     "price_cents": 19900},
    {"placement_type": PlacementType.page_ad.value, "rank_tier": None,
     "price_cents": 9900},
    {"placement_type": PlacementType.category_rank.value, "rank_tier": None,
     "price_cents": 9900},   # fallback for any tier not explicitly priced below
    {"placement_type": PlacementType.category_rank.value, "rank_tier": 1, "price_cents": 14900},
    {"placement_type": PlacementType.category_rank.value, "rank_tier": 2, "price_cents": 11900},
    {"placement_type": PlacementType.category_rank.value, "rank_tier": 3, "price_cents": 9900},
    {"placement_type": PlacementType.category_rank.value, "rank_tier": 4, "price_cents": 7900},
    {"placement_type": PlacementType.category_rank.value, "rank_tier": 5, "price_cents": 5900},
]


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _snapshot(session) -> Path:
    """Dump current placement_prices to a timestamped JSON in the repo root."""
    rows = session.scalars(select(PlacementPrice)).all()
    payload = [
        {
            "id": r.id,
            "placement_type": r.placement_type,
            "category_slug": r.category_slug,
            "rank_tier": r.rank_tier,
            "price_cents": r.price_cents,
            "active": r.active,
        }
        for r in rows
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = _ROOT / f"placement_prices_snapshot_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def run(*, apply: bool = False, confirm: bool = False, session=None) -> Counter:
    """Upsert the global default price book. Dry-run (default) writes nothing."""
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")

        for spec in DEFAULT_PRICES:
            existing = session.scalars(
                select(PlacementPrice).where(
                    PlacementPrice.placement_type == spec["placement_type"],
                    PlacementPrice.category_slug.is_(None),
                    (
                        PlacementPrice.rank_tier.is_(None)
                        if spec["rank_tier"] is None
                        else PlacementPrice.rank_tier == spec["rank_tier"]
                    ),
                )
            ).first()
            tier_suffix = "" if spec["rank_tier"] is None else f" tier {spec['rank_tier']}"
            label = f"{spec['placement_type']}{tier_suffix}"
            if existing is None:
                session.add(
                    PlacementPrice(
                        placement_type=spec["placement_type"],
                        category_slug=None,
                        rank_tier=spec["rank_tier"],
                        price_cents=spec["price_cents"],
                        active=True,
                    )
                )
                counts["insert"] += 1
                print(f"  insert  {label:<32} ${spec['price_cents'] / 100:,.2f}/mo")
            elif existing.price_cents != spec["price_cents"] or not existing.active:
                old = existing.price_cents
                existing.price_cents = spec["price_cents"]
                existing.active = True
                counts["update"] += 1
                print(
                    f"  update  {label:<32} "
                    f"${old / 100:,.2f} -> ${spec['price_cents'] / 100:,.2f}/mo"
                )
            else:
                counts["noop"] += 1
                print(f"  noop    {label:<32} ${existing.price_cents / 100:,.2f}/mo")

        print(
            f"\nplanned: {counts['insert']} insert, "
            f"{counts['update']} update, {counts['noop']} unchanged"
        )

        if not apply:
            session.rollback()
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to seed.")
            return counts
        if not confirm:
            session.rollback()
            print("\nREFUSING TO WRITE — --apply requires --confirm.")
            return counts

        snap = _snapshot(session)
        print(f"\nsnapshot written: {snap.name}")
        session.commit()
        print("APPLIED — global default price book seeded.")
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
