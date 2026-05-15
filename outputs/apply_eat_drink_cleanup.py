"""Deactivate 31 non-eateries + 1 duplicate row in the eat-drink load — Phase 5.1.

Staged by Cowork primary (Phase 5 lane, 2026-05-15) from the data-quality audit
(`outputs/phase5_1_eat_drink_data_quality_audit.md`). Sets `is_active = 0` on both
the `entities` and `providers` rows for 32 entities. Reversible (flip back to 1).
Leaves the 15 "borderline" judgment-call rows untouched.

Run Windows-side from the repo root:
    python outputs/apply_eat_drink_cleanup.py --dry-run   # preview, no writes
    python outputs/apply_eat_drink_cleanup.py             # apply

Idempotent. Sets updated_at explicitly (raw sqlite3 does not fire ORM onupdate).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "events.db"

# 31 clear non-eateries + 1 redundant "Lady Lee's" duplicate row (keeping b4d80817...).
DEACTIVATE_IDS: list[str] = [
    "968b4a6e-124d-4b6f-b125-cb3b58fa3145",  # A Toe Truck (towing company)
    "4d420b76-3451-4d89-a504-edd8d1cb45ba",  # Hava Event Planner & Coordinator
    "afa108ea-ddf1-48a1-a9d0-9b6d300e8bb5",  # Lovedwell Creative (creative agency)
    "0da5a4ac-111b-4734-9a07-e47666840bca",  # Posh Planning & Event Co.
    "bae5cda8-8db2-4f4a-b541-736806b0b402",  # River Rat Motorsports
    "61197d69-fb83-4b88-bfd8-731d261388cb",  # Lake Havasu Cigars
    "eb5d36e9-4575-4336-b30a-3722675a1a37",  # Farm Fresh Marijuana Dispensary
    "c020ba06-3f36-4eac-93f4-86831292e4ee",  # Close to Downtown Nightlife... (vacation rental, dup)
    "cdae678d-4ef1-4eea-8794-d15642f51390",  # Close to Downtown Nightlife... (vacation rental, dup)
    "240c4f19-23c6-4f19-b8e4-5be5b8eaf7b5",  # London Bridge Resort (hotel)
    "2b38d5af-5bce-46aa-bd4a-2bc12574e334",  # The Nautical Beachfront Resort
    "3c499705-09b0-40d6-915c-8d25b20f88c4",  # Iron Wolf Golf & Country Club
    "1b58b28e-7ea8-4d09-8c3b-a409c77d7a7c",  # Site Six Launch Ramp (boat ramp)
    "b0acdc8a-3c14-41bc-9e89-ab67ab95531f",  # Hava Style Recreation (gear supplier)
    "a68f7dd8-c196-4a45-92cc-372263087cb5",  # Lake Havasu Rodeo Grounds
    "1b82d3fe-85e0-4b14-b6e9-4b4b2c50766e",  # McCulloch Center Plaza (shopping plaza)
    "c0c513fb-20ab-4245-a080-24dfaa1d49d1",  # Havasu 95 Speedway
    "1920fe0f-aff9-4178-825b-ffd02a2cb7f5",  # Grace Arts Live (theater)
    "f0497e6e-d433-4df9-9a0f-278dd1fe0f1d",  # London Bridge Beach (park)
    "b3b1c0f7-e999-48fa-ba5f-05d8c2793f9e",  # Movies Havasu (movie theater)
    "bf3fe419-de3a-43b4-a4a4-e5452a391251",  # London Bridge Swap Meet
    "5020a3b8-b3dd-40e5-b4cb-d6d82c23e1a3",  # DELI LAUNDROMAT (laundromat)
    "6737ecc9-4a4f-4e93-a7fa-b27e2fe7a005",  # Sunshine Indoor Play (kids playground)
    "b7731508-0993-4538-b58e-770ba3dac2fc",  # The Back Nine Golf (indoor golf)
    "dc9b2e08-7e6e-4733-947c-f0f9669488d7",  # Lake Havasu Golf Club
    "791cf1e6-df8b-401e-9840-e4250f426d07",  # W.A.V.E. Culinary and Hospitality (school)
    "e3272eaa-28e7-4583-bf24-3e023a5a6f0d",  # Western States Restaurant Consulting (firm)
    "afa6dc88-9a55-465e-af4d-776fc22e9144",  # Detail Specialties & Ceramic Coating (auto detail)
    "b8dfe489-6b11-42d4-8966-69200427e9d3",  # Martin Swanty's Paradise Auto (car dealer)
    "b996edfe-0c54-4941-91d3-26fb84e4895b",  # Our Shabby Shack & Book Exchange (bookstore)
    "368c5360-c3bd-465d-9337-83e9cc201d24",  # The Speakeasy Beauty Lounge (beauty salon)
    "71ad6c09-f6c7-4d4f-a137-d653d697cbc1",  # Lady Lee's (duplicate row; keeping b4d80817...)
]


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH} — run from the repo root.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    placeholders = ",".join("?" * len(DEACTIVATE_IDS))

    # before
    cur.execute("SELECT COUNT(*) FROM providers WHERE is_active = 1")
    before = cur.fetchone()[0]
    # missing check
    cur.execute(
        f"SELECT COUNT(*) FROM entities WHERE id IN ({placeholders})", DEACTIVATE_IDS
    )
    found = cur.fetchone()[0]

    if not dry_run:
        cur.execute(
            f"UPDATE entities SET is_active = 0, updated_at = ? "
            f"WHERE id IN ({placeholders})",
            [now, *DEACTIVATE_IDS],
        )
        cur.execute(
            f"UPDATE providers SET is_active = 0, updated_at = ? "
            f"WHERE entity_id IN ({placeholders})",
            [now, *DEACTIVATE_IDS],
        )
        conn.commit()

    # after
    cur.execute("SELECT is_active, COUNT(*) FROM providers GROUP BY is_active")
    prov_dist = dict(cur.fetchall())
    cur.execute("SELECT is_active, COUNT(*) FROM entities GROUP BY is_active")
    ent_dist = dict(cur.fetchall())
    conn.close()

    print()
    print(f"--- eat-drink cleanup ({'dry-run' if dry_run else 'committed'}) ---")
    print(f"ids in script:        {len(DEACTIVATE_IDS)}")
    print(f"matched in entities:  {found}")
    if found != len(DEACTIVATE_IDS):
        print(f"  WARNING: {len(DEACTIVATE_IDS) - found} id(s) not found in DB")
    print(f"providers active before: {before}")
    print(f"providers is_active dist now: {prov_dist}   (expect 0->32, 1->255)")
    print(f"entities  is_active dist now: {ent_dist}   (expect 0->32, 1->255)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
