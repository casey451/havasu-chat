"""Backfill the cost field on "Glow in the Park" events that state $20 in their
description (site review §6: header showed "See link for pricing" though $20 is
right there in the copy).

Targeted + conservative: only "Glow in the Park" events whose ``cost`` is empty
AND whose description contains "$20" get ``cost = "$20"``. The weekday "Jump
under the blacklights" occurrences (no price stated) are left untouched, and the
unrelated "Glow-in-the-Dark Pickleball" rows (different title, already priced)
never match.

Dry-run by default (prints the rows it WOULD change, no write). Pass ``--apply``
to commit — only after operator approval of the dry-run counts.

    .venv\\Scripts\\python.exe scripts/fix_glow_cost_2026_06_27.py            # dry-run
    .venv\\Scripts\\python.exe scripts/fix_glow_cost_2026_06_27.py --apply    # write
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

NEW_COST = "$20"


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"[glow-cost] DB target: …@{redacted}")
    print(f"[glow-cost] mode: {'APPLY (writing)' if apply else 'DRY-RUN (no writes)'}\n")

    with SessionLocal() as db:
        rows = (
            db.query(Event)
            .filter(
                Event.title.ilike("%glow in the park%"),
                Event.cost.is_(None),
                Event.description.ilike("%$20%"),
            )
            .order_by(Event.date)
            .all()
        )
        print(f"[glow-cost] {len(rows)} event(s) match (cost empty + '$20' in description):")
        for e in rows:
            print(f"  {e.date}  {e.start_time}–{e.end_time}  id={e.id}  cost {e.cost!r} -> {NEW_COST!r}")

        if not apply:
            print("\n[glow-cost] DRY-RUN complete — no rows changed. Re-run with --apply to write.")
            return

        for e in rows:
            e.cost = NEW_COST
        db.commit()
        print(f"\n[glow-cost] APPLIED — set cost={NEW_COST!r} on {len(rows)} event(s).")


if __name__ == "__main__":
    main()
