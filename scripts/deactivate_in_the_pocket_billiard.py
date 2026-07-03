"""Remove "In the Pocket Billiard" from the site (directory + calendar).

Calendar/directory audit (2026-06-26): "In the Pocket Billiard" (2871 Indian
Pipe Dr) is a billiard SUPPLY shop / pool-table repair service (Olhausen dealer;
re-felting, moving, repair), not a playable pool hall. Casey chose to remove it
entirely (2026-06-26).

Code side (already applied on the branch): the venue was deleted from
``app/home/family_venues.py`` (calendar → Billiards card) and from
``app/contrib/lhc_funzone.py`` IN_TOWN_VENUES (directory re-ingest), so it will
not be republished.

This script cleans the existing PROD rows:
  * deactivate the directory Provider (is_active=False), and
  * soft-delete any leftover live funzone Event rows (status='duplicate').

Both are reversible. Per CLAUDE.md: dry-run, show counts, approve, --apply.

    python scripts/deactivate_in_the_pocket_billiard.py            # dry-run
    python scripts/deactivate_in_the_pocket_billiard.py --apply    # commit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event, Provider  # noqa: E402

NAME = "In the Pocket Billiard"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        provs = (
            db.query(Provider)
            .filter(Provider.provider_name == NAME, Provider.is_active.is_(True))
            .all()
        )
        events = (
            db.query(Event)
            .filter(Event.location_name == NAME, Event.status == "live")
            .all()
        )

        snap = {
            "providers": [
                {"id": p.id, "entity_id": p.entity_id, "name": p.provider_name,
                 "source": p.source, "is_active_before": p.is_active}
                for p in provs
            ],
            "events": [
                {"id": e.id, "title": e.title, "date": str(e.date),
                 "status_before": e.status} for e in events
            ],
        }
        print("=" * 64)
        print("REMOVE 'In the Pocket Billiard'",
              "(APPLY)" if args.apply else "(DRY RUN — no writes)")
        print("=" * 64)
        print(f"providers to deactivate (is_active=False): {len(provs)}")
        for p in provs:
            print(f"    - provider {p.id} (entity {p.entity_id}) source={p.source}")
        print(f"live events to soft-delete (status='duplicate'): {len(events)}")
        for e in events:
            print(f"    - event {e.id} {e.date} {e.title}")
        print("SNAPSHOT:", json.dumps(snap))

        if not provs and not events:
            print("\nNothing to do / already removed.")
            return
        if not args.apply:
            print("\nDRY-RUN: nothing written. Re-run with --apply.")
            return

        for p in provs:
            p.is_active = False
        for e in events:
            e.status = "duplicate"
        db.commit()
        print(f"\nAPPLIED: {len(provs)} provider(s) is_active=False, "
              f"{len(events)} event(s) status='duplicate'. Reversible.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
