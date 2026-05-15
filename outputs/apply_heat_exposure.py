"""Apply heat_exposure tags to the eat-drink load — Phase 5.1 field entry.

Staged by Cowork primary (Phase 5 lane, 2026-05-15) from the LOCKED decision tree
`outputs/heat_exposure_priority_30_list.md`. Applies the 8 LOCKED off-default tags,
then sweeps every remaining NULL to the 'indoor' default (rubric §4 rule 1).

The 2 PROVISIONAL rows were resolved 2026-05-15 by web research: El Paraiso ->
`shaded` (now in LOCKED_TAGS), College Street Brewhouse -> confirmed `indoor` (no
entry needed). The Shugrue's Cornerside Bakery judgment call remains open — see the
comment block below LOCKED_TAGS.

Idempotent — safe to re-run; if you already ran the 7-tag version, re-running now
just adds El Paraiso and re-sweeps.

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

# 8 LOCKED off-default tags (heat_exposure_priority_30_list.md §1/§2/§3 + the
# El Paraiso PROVISIONAL row, resolved 2026-05-15 by web research).
LOCKED_TAGS: dict[str, str] = {
    "dc5168c6-f5ec-4e0f-ab5a-a4cbf8ed7506": "shaded",          # Locos Bar and Cocina - Northside (§2 #13)
    "c1c8829c-b200-49ac-8cab-f69bf7ff23bd": "water_adjacent",  # Shugrue's Restaurant and Brewery Group (§3 #20)
    "d7e8fb73-9c1f-4491-9881-821026e16220": "water_adjacent",  # Makai Cafe (§3 #20)
    "400e7926-68cf-4eb8-a94e-639b02e4c817": "water_adjacent",  # Barley Brothers Brewery (§3 #20)
    "ba787210-66ac-45f2-b7eb-54b3a8cbff1f": "water_adjacent",  # Javelina Cantina (§3 #20)
    "f491e591-256f-4dc7-8280-42ea83d584f8": "water_adjacent",  # HEAT Bar (§3 #20)
    "2b4b33dc-5e97-4b00-8479-0e87b35253e3": "outdoor",         # Lake Havasu Farmers Market (§1 #9)
    "82d0eaea-06b7-451f-b3de-b67870ce4e09": "shaded",          # El Paraiso Family Mexican — was PROVISIONAL (§2 #14); resolved 2026-05-15: web research confirms misters + sun shades + a new enclosed patio
}

# --- PROVISIONAL rows — resolved 2026-05-15 by web research (see phase5_1_field_entry_close_out.md §7) ---
# El Paraiso Family Mexican -> RESOLVED `shaded`, now in LOCKED_TAGS above.
# College Street Brewhouse & Pub (f36fb5b3-f2e6-4236-8668-3c7e99994084) -> CONFIRMED `indoor`:
#   ~900ft inland (distant view only, not water_adjacent) + full-sun patio (misters, no shade
#   structures). The indoor default is correct — no entry needed, intentionally left out.
# Shugrue's Cornerside Bakery (3723c4ba-3115-401b-a31c-78c7724d5c27) -> still a judgment call:
#   no water-access evidence found; left at the indoor default pending an operator call.


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
    n_locked = len(LOCKED_TAGS)

    if not dry_run:
        # 1. the LOCKED off-default tags
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
    print(f"LOCKED tags in script: {n_locked}")
    if missing:
        print(f"  WARNING: {len(missing)} id(s) not found in DB: {missing}")
    else:
        print(f"all {n_locked} LOCKED entity_ids matched")
    print(f"heat_exposure distribution now: {dist}")
    print("  expect (LOCKED + sweep): water_adjacent->5, shaded->2, outdoor->1, indoor->279, NULL->0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
