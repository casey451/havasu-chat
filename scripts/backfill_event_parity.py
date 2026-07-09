"""Backfill event-parity fields on existing rows (DRY-RUN by default).

Two idempotent passes over the ``events`` table:

  1. **category** — stamp ``Event.category`` from the row's ``tags`` via the
     canonical crosswalk (``derive_event_category``) where it's currently NULL.
  2. **recurrence flag** — clear ``is_recurring`` on rows that carry the flag but
     have NO ``rrule`` and NO ``rdate`` (the ~266-row anomaly). The render path
     already tolerates these; this makes the data honest too.

Writes NOTHING unless ``--apply`` AND ``--confirm`` are both passed. Every run
prints the counts a real apply would make, per the repo's dry-run→counts→approve
→apply rule. The agent never runs --apply against prod; a human does after
reviewing the counts.

Usage:
    .venv\\Scripts\\python.exe scripts\\backfill_event_parity.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_event_parity.py --apply --confirm
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.source_category_map import derive_event_category  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.recurrence import normalize_recurrence_flag  # noqa: E402


def _sanitized_target() -> str:
    import os

    url = os.environ.get("DATABASE_URL", "")
    if "@" in url:
        return "…@" + url.split("@", 1)[1]
    return url or "(sqlite default)"


def run(*, apply: bool = False, confirm: bool = False, session=None) -> Counter:
    own = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        events = session.query(Event).all()
        counts["scanned"] = len(events)
        for ev in events:
            # 1. category stamp (only when NULL)
            if not ev.category:
                cat = derive_event_category(list(ev.tags or []))
                if cat:
                    counts[f"category:{cat}"] += 1
                    counts["category_stamped"] += 1
                    if apply and confirm:
                        ev.category = cat
            # 2. clear stray recurrence flag
            normalized = normalize_recurrence_flag(
                is_recurring=ev.is_recurring, rrule=ev.rrule, rdate=ev.rdate
            )
            if normalized != ev.is_recurring:
                counts["recurrence_flag_cleared"] += 1
                if apply and confirm:
                    ev.is_recurring = normalized

        print(f"scanned events:            {counts['scanned']}")
        print(f"category would-stamp:      {counts['category_stamped']}")
        print(f"recurrence flag would-clear:{counts['recurrence_flag_cleared']}")
        top = [(k, v) for k, v in counts.items() if k.startswith("category:")]
        for k, v in sorted(top, key=lambda kv: -kv[1]):
            print(f"    {k[len('category:'):]:<24} {v}")

        if not (apply and confirm):
            print("\nDRY RUN: nothing written. Re-run with --apply --confirm to write.")
            if apply and not confirm:
                print("REFUSING TO WRITE — --apply requires --confirm.")
        else:
            session.commit()
            print("\nAPPLIED.")
        return counts
    finally:
        if own:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = parser.parse_args()
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
