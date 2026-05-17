"""Discover the top-10 events (cat-2) entities by review_count and dump
their Provider.google_review_snippets to JSON for the
``apply_phase5_8_events_crowd_notes.py`` drafting step.

Read-only against ``data/events.db``. Produces
``outputs/phase5_8_top10_data.json`` for the Cowork agent to Read
and hand-curate short+long crowd_notes from.

Mirrors ``outputs/phase5_7_top10_discovery.py`` exactly with slug
swap (outdoors-parks-trails → events).

Usage:
    python outputs/phase5_8_top10_discovery.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402


def main() -> int:
    out_path = (
        Path(__file__).resolve().parent / "phase5_8_top10_data.json"
    )
    with SessionLocal() as session:
        cat = session.scalar(
            select(Category).where(Category.slug == "events")
        )
        if cat is None:
            print("ERROR: Category.slug='events' not found.")
            return 2

        q = (
            select(Entity, Provider)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .join(Provider, Provider.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat.id,
                Entity.is_active.is_(True),
            )
            .order_by(Provider.google_review_count.desc().nullslast())
            .limit(10)
        )

        rows = []
        for e, p in session.execute(q).all():
            snips = p.google_review_snippets
            if isinstance(snips, str):
                try:
                    snips = json.loads(snips)
                except Exception:
                    pass
            rows.append(
                {
                    "entity_id_prefix": e.id[:8],
                    "entity_id": e.id,
                    "name": e.name,
                    "review_count": p.google_review_count,
                    "rating": p.google_rating,
                    "primary_type": p.google_primary_category,
                    "snippets": snips,
                }
            )

        out_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"wrote {len(rows)} entries to {out_path}")
        print()
        for row in rows:
            snips = row["snippets"]
            if isinstance(snips, list):
                nsnips = len(snips)
            elif snips:
                nsnips = "?"
            else:
                nsnips = 0
            star = "*"
            print(
                f"  {row['entity_id_prefix']}  "
                f"reviews={row['review_count']!s:>5}  "
                f"{row['rating']}{star}  "
                f"snippets={nsnips!s:>3}  "
                f"primary={row['primary_type']!r:30s}  "
                f"{row['name']!r}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
