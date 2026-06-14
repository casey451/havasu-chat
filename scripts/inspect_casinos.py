"""Read-only: print every provider row whose name relates to casinos / the
specific names in §6.7, so we can make PRECISE fixes instead of broad name
matches (which catch local businesses like 'Bluewater Accounting'). No writes."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import or_, select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

NEEDLES = ("havasu landing", "casino", "game spot", "gamespot", "blue water", "bluewater")


def main() -> int:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Provider).where(
            or_(*[Provider.provider_name.ilike(f"%{n}%") for n in NEEDLES]))))
        rows.sort(key=lambda p: (p.provider_name or "").lower())
        print(f"{len(rows)} casino-related name matches:\n")
        for p in rows:
            print(f"- {p.provider_name!r}")
            print(f"    id={p.id}")
            print(f"    is_active={p.is_active}  category={p.category!r}  "
                  f"primary_category={p.primary_category!r}  subcategory={p.subcategory!r}")
            print(f"    website={p.website!r}")
            print(f"    address={p.address!r}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
