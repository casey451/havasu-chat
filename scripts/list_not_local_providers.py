"""List providers classified NOT local to Lake Havasu (READ-ONLY).

After ``backfill_is_local.py`` set ``Provider.is_local``, this prints every
active provider flagged ``is_local = False`` — the rows the directory/search
locality filter now hides — with name, address, and current primary leaf, so a
human can eyeball that nothing genuinely local got misclassified. Writes nothing.

    .venv\\Scripts\\python.exe scripts\\list_not_local_providers.py
    .venv\\Scripts\\python.exe scripts\\list_not_local_providers.py --csv not_local.csv
    .venv\\Scripts\\python.exe scripts\\list_not_local_providers.py --unknown   # also show is_local NULL
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(*, csv_path: Path | None = None, include_unknown: bool = False, session=None) -> int:
    own = session is None
    session = session or SessionLocal()
    try:
        print(f"DB target: {_sanitized_target()} (READ-ONLY)\n")
        cat_by_id = {c.id: c for c in session.query(Category).all()}
        primary_leaf = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(EntityCategory.is_primary.is_(True))
        }

        states = [False] + ([None] if include_unknown else [])
        rows: list[dict] = []
        for state in states:
            cond = Provider.is_local.is_(None) if state is None else Provider.is_local.is_(False)
            q = (
                session.query(Provider)
                .join(Entity, Provider.entity_id == Entity.id)
                .filter(Entity.is_active.is_(True), Provider.is_active.is_(True), cond)
                .order_by(Provider.provider_name.asc())
            )
            label = "unknown" if state is None else "not_local"
            providers = q.all()
            print(f"== {label}: {len(providers)} ==")
            for p in providers:
                cur = cat_by_id.get(primary_leaf.get(p.entity_id))
                addr = (p.address or "").strip()
                print(f"  {(p.provider_name or '')[:40]:40s} | {cur.slug if cur else '(none)':28s} | {addr[:45]}")
                rows.append(
                    {
                        "is_local": label,
                        "provider_name": (p.provider_name or "").strip(),
                        "current_leaf_slug": cur.slug if cur else "",
                        "address": addr,
                        "entity_id": p.entity_id,
                    }
                )
            print()

        if csv_path and rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {len(rows)} rows to {csv_path}")
        return 0
    finally:
        if own:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="List not-local (and optionally unknown) providers.")
    ap.add_argument("--csv", type=Path, default=None, help="Write rows to this CSV.")
    ap.add_argument("--unknown", action="store_true", help="Also list is_local NULL (unknown) rows.")
    args = ap.parse_args(argv)
    return run(csv_path=args.csv, include_unknown=args.unknown)


if __name__ == "__main__":
    raise SystemExit(main())
