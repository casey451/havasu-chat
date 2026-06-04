"""READ-ONLY export of providers with ``primary_category IS NULL`` (backlog #2).

Prints a markdown table (id, name, Google primary type, Google types, legacy
category, subcategory) for every active, non-draft provider whose canonical
``primary_category`` is NULL, and optionally writes the same rows to CSV with
``--csv PATH``. Used to decide which rows map unambiguously to one of the 13
canonical primaries (mapping additions go to ``app/categories/subcategories.py``
as a code PR) and which stay NULL for Casey's manual call.

Makes NO database writes of any kind.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\export_uncategorized_providers.py
    .venv\\Scripts\\python.exe scripts\\export_uncategorized_providers.py --csv outputs\\uncategorized.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

FIELDS = (
    "id",
    "provider_name",
    "google_primary_category",
    "google_categories",
    "category",
    "subcategory",
)


def _google_types(value: object) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return value
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def fetch_rows(include_all: bool = False) -> list[dict[str, str]]:
    with SessionLocal() as db:
        q = db.query(Provider).filter(Provider.primary_category.is_(None))
        if not include_all:
            q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        q = q.order_by(Provider.category, Provider.provider_name)
        return [
            {
                "id": p.id,
                "provider_name": p.provider_name,
                "google_primary_category": p.google_primary_category or "",
                "google_categories": _google_types(p.google_categories),
                "category": p.category or "",
                "subcategory": p.subcategory or "",
            }
            for p in q.yield_per(500)
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="also write rows to this CSV path")
    parser.add_argument("--all", action="store_true", help="include drafts and inactive rows")
    args = parser.parse_args()

    rows = fetch_rows(include_all=args.all)
    print(f"{len(rows)} providers with primary_category IS NULL\n")
    print("| id | name | google primary | google types | legacy category | subcategory |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['id']} | {r['provider_name']} | {r['google_primary_category']} "
            f"| {r['google_categories']} | {r['category']} | {r['subcategory']} |"
        )

    if args.csv:
        path = Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nWrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
