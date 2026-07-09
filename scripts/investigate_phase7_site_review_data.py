"""READ-ONLY investigation for the two site-review data corrections (Phase 7).

Surfaces the current state of:
  §4d — "Cosmic Bowling" Saturday time (review: shows 6 PM, should be 9 PM-midnight;
        the 6-9 PM session is the *Friday* family one).
  §6  — "Glow in the Park" cost field (review: header reads "See link for pricing"
        though the $20 price is in the description).

SELECT-only: no INSERT/UPDATE/DELETE, no commit. Safe to run against prod — this
is the dry-run/show-counts step before any operator-approved write. Run:

    .venv\\Scripts\\python.exe scripts/investigate_phase7_site_review_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event


def _fmt(t) -> str:
    return t.strftime("%H:%M") if t else "—"


def main() -> None:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"[investigate] DB target: …@{redacted}")
    print("[investigate] READ-ONLY — no writes.\n")

    with SessionLocal() as db:
        for needle in ("cosmic", "glow"):
            rows = (
                db.query(Event)
                .filter(Event.title.ilike(f"%{needle}%"))
                .order_by(Event.date)
                .all()
            )
            print(f"=== Events matching '{needle}' ({len(rows)}) ===")
            for e in rows:
                print(
                    f"  id={e.id}\n"
                    f"    title={e.title!r}  status={e.status}  recurring={e.is_recurring}\n"
                    f"    date={e.date}  start={_fmt(e.start_time)}  end={_fmt(e.end_time)}\n"
                    f"    rrule={e.rrule!r}\n"
                    f"    cost={e.cost!r}  cost_description={e.cost_description!r}\n"
                    f"    location={e.location_name!r}\n"
                    f"    description={(e.description or '')[:160]!r}\n"
                )
            print()


if __name__ == "__main__":
    main()
