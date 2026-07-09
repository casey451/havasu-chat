"""Read-only: counts + rows for the food-drink and stay subcategories, so the
Quick Bites merge (§6.1), Hotels audit (§6.3), and Vacation Rentals removal
(§6.4) can be built precisely. No writes."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        # Active-row counts per subcategory of interest.
        subs = ("restaurants", "quick-bites", "bars-breweries", "cafes-coffee",
                "hotels", "vacation-rentals", "rv-parks")
        print("Active provider counts by subcategory:")
        for s in subs:
            n = db.scalar(select(func.count()).select_from(Provider).where(
                Provider.subcategory == s, Provider.is_active.is_(True)))
            print(f"  {s:18} {n}")
        print()

        def dump(sub: str, show_site: bool = True) -> None:
            rows = list(db.scalars(select(Provider).where(
                Provider.subcategory == sub, Provider.is_active.is_(True))
                .order_by(Provider.provider_name)))
            print(f"--- {sub}: {len(rows)} active ---")
            no_site = 0
            for p in rows:
                site = (p.website or "").strip()
                if not site:
                    no_site += 1
                tag = "" if site else "   <-- NO WEBSITE"
                if show_site:
                    print(f"  {p.provider_name}{tag}")
            print(f"  ({no_site} of {len(rows)} have NO website)\n")

        dump("quick-bites")
        dump("hotels")
        dump("vacation-rentals")
        print("DONE_MARKER")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
