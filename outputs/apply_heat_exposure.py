"""Apply heat_exposure tags to the eat-drink load — Phase 5.1 field entry.

Staged by Cowork primary (Phase 5 lane, 2026-05-15) from the LOCKED decision tree
`outputs/heat_exposure_priority_30_list.md`. Applies the 7 LOCKED off-default tags,
then sweeps every remaining NULL to the 'indoor' default (rubric §4 rule 1).

The 2 PROVISIONAL rows + the Cornerside Bakery judgment call are NOT applied here —
they need an on-site confirm. See PROVISIONAL block at the bottom; uncomment and
re-run after you've confirmed them.

Run Windows-side from the repo root:
    python outputs/apply_heat_exposure.py --dry-run   # preview, no writes
    python outputs/apply_heat_exposure.py             # apply

Idempotent. Sets updated_at explicitly. heat_exposure CHECK constraint allows only
'indoor' / 'shaded' / 'outdoor' / 'water_adjacent'.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "events.db"

# 7 LOCKED off-default tags (heat_exposure_priority_30_list.md §1/§2/§3).
LOCKED_TAGS: dict[str, str] = {
    "dc5168c6-f5ec-4e0f-ab5a-a4cbf8ed7506": "shaded",          # Locos Bar and Cocina - Northside (§2 #13)
    "c1c8829c-b200-49ac-8cab-f69bf7ff23bd": "water_adjacent",  # Shugrue's Restaurant and Brewery Group (§3 #20)
    "d7e8fb73-9c1f-4491-9881-821026e16220": "water_adjacent",  # Makai Cafe (§3 #20)
    "400e7926-68cf-4eb8-a94e-639b02e4c817": "water_adjacent",  # Barley Brothers Brewery (§3 #20)
    "ba787210-66ac-45f2-b7eb-54b3a8cbff1f": "water_adjacent",  # Javelina Cantina (§3 #20)
    "f491e591-256f-4dc7-8280-42ea83d584f8": "water_adjacent",  # HEAT Bar (§3 #20)
    "2b4b33dc-5e97-4b00-8479-0e87b35253e3": "outdoor",         # Lake Havasu Farmers Market (§1 #9)
}

# --- PROVISIONAL — confirm on-site, then move into LOCKED_TAGS above and re-run ---
# "82d0eaea-06b7-451f-b3de-b67870ce4e09": "shaded",          # El Paraiso Mexican — confirm patio mid-day shade
# "f36fb5b3-f2e6-4236-8668-3c7e99994084": "shaded",          # College Street Brewhouse & Pub — confirm tag (shaded vs water_adjacent)
# "3723c4ba-3115-401b-a31c-78c7724d5c27": "water_adjacent",  # Shugrue's Cornerside Bakery — judgment call: part of English Village cluster?


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH} — run from the repo root.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    missing: list[str] = []
    for entity_id in LOCKED_TAGS:
        cur.execute("SELECT name FROM entities WHERE id = ?", (entity_id,))
        if cur.fetchone() is None:
            missing.append(entity_id)

    if not dry_run:
        # 1. the 7 LOCKED off-default tags
        for entity_id, tag in LOCKED_TAGS.items():
            cur.execute(
                "UPDATE entities SET heat_exposure = ?, updated_at = ? WHERE id = ?",
                (tag, now, entity_id),
            )
        # 2. indoor default sweep — everything still NULL
        cur.execute(
            "UPDATE entities SET heat_exposure = 'indoor', updated_at = ? "
            "WHERE heat_exposure IS NULL",
            (now,),
        )
        conn.commit()

    cur.execute(
        "SELECT heat_exposure, COUNT(*) FROM entities GROUP BY heat_exposure"
    )
    dist = dict(cur.fetchall())
    conn.close()

    print()
    print(f"--- heat_exposure apply ({'dry-run' if dry_run else 'committed'}) ---")
    print(f"LOCKED tags in script: {len(LOCKED_TAGS)}")
    if missing:
        print(f"  WARNING: {len(missing)} id(s) not found in DB: {missing}")
    else:
        print("all 7 LOCKED entity_ids matched")
    print(f"heat_exposure distribution now: {dist}")
    print("  expect (LOCKED + sweep only): water_adjacent->5, shaded->1, outdoor->1, indoor->280, NULL->0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
