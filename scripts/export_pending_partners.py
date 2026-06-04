"""READ-ONLY export of the provider approval queue (backlog #3).

Prints the same set the admin UI shows at ``/admin/providers/pending``
(draft + pending_review + active), as a markdown table of id, name, category,
and submitted date, oldest first. Optionally writes CSV with ``--csv PATH``.

Approval itself stays in the admin UI — this script makes NO writes and
never approves anything (that's Casey's judgment call).

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\export_pending_partners.py
    .venv\\Scripts\\python.exe scripts\\export_pending_partners.py --csv outputs\\pending_partners.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

FIELDS = ("id", "provider_name", "category", "submitted", "source")


def fetch_rows() -> list[dict[str, str]]:
    """Mirror app/admin/provider_approval.py::_pending_providers exactly."""
    with SessionLocal() as db:
        providers = db.scalars(
            select(Provider)
            .where(
                Provider.draft.is_(True),
                Provider.pending_review.is_(True),
                Provider.is_active.is_(True),
            )
            .order_by(Provider.created_at.asc())
        ).all()
        return [
            {
                "id": p.id,
                "provider_name": p.provider_name,
                "category": p.category or "",
                "submitted": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
                "source": p.source or "",
            }
            for p in providers
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="also write rows to this CSV path")
    args = parser.parse_args()

    rows = fetch_rows()
    print(f"{len(rows)} providers pending review (approve in /admin/providers/pending)\n")
    print("| id | name | category | submitted | source |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['id']} | {r['provider_name']} | {r['category']} "
            f"| {r['submitted']} | {r['source']} |"
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
