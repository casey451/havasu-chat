"""Apply short-form crowd_notes — batch 2, eat-drink ranks 18-48 by review count.

Staged by Cowork primary (Phase 5 lane, 2026-05-15) from Google review-snippet
analysis. The top-17 highest-volume venues got long-form {short, long} notes
(apply_crowd_notes_top17.py); this batch gives the next 31 active eateries the
1-sentence {short}-only treatment per the runbook §4 ("short-form for typical
venues"). The absence of a "long" key is the signal Phase 6 uses to render these
as list/card blurbs rather than profile sections.

DRAFTS from review snippets — review/edit the text below before running if any
call is off. Run Windows-side from the repo root:
    python outputs/apply_crowd_notes_batch2.py --dry-run
    python outputs/apply_crowd_notes_batch2.py

Idempotent. Sets updated_at explicitly.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "events.db"

# entity_id -> short-form crowd note (1 sentence, crowd-pattern focused)
CROWD_NOTES_SHORT: dict[str, str] = {
    "948cc644-d754-416f-85d1-f74e1f25afc4":  # Burgers by the Bridge
        "Walk-up counter in the English Village by the London Bridge — tourist foot traffic, but the line moves quick and the outdoor seating handles big groups.",
    "cae4cf8d-3c62-480f-9950-88107e7eb2f1":  # Legendz Sports Bar & Grill
        "Game days are the peak — it's the big-screen sports crowd's spot; plenty of bar and table space keeps it absorbable otherwise.",
    "c35ec8d6-6a75-4404-89c5-2541aeabb290":  # Bad Miguel's Mexican Restaurant
        "Rarely crowded; the 3-5pm happy hour is the quiet, cheap window — full bar, $2 beer.",
    "e3cc0737-8363-455d-93e7-639c6dd1de94":  # Wendy's
        "Open 24 hours but service runs slow — order ahead on the app if you're in a hurry.",
    "a736cf63-2c13-43d6-b126-6a9cfffc5249":  # Panda Express
        "Gets busy enough that lines back up waiting on fresh-cooked batches — peak meals mean a wait.",
    "6a5f74e6-36c4-43b8-87f3-3d03ad40653d":  # BJ's | Cabana Bar & Karaoke
        "Live-music nights (Sundays especially) draw the crowd; arrive early for a shaded patio seat.",
    "d3f5e4db-3666-43d4-8c5a-705b2b5d60da":  # Arby's
        "Standard fast-food flow — quick turnaround, no notable wait.",
    "dc5168c6-f5ec-4e0f-ab5a-a4cbf8ed7506":  # Locos Bar and Cocina - Northside
        "Dinner-only and closed some weekdays — check the day; the patio with live music is the draw, good for groups.",
    "b46c7433-a9d3-42bb-bb6c-c389894128d0":  # Wienerschnitzel
        "Drive-through fast food, open late (to midnight) — quick, no real peak to dodge.",
    "62983ad7-1474-4bd5-a48c-5e99f9dcfeac":  # Food City
        "A neighborhood grocery with a seating area where south-side locals gather for a morning snack — steady, not a crush.",
    "f7610100-04c9-482f-8b44-144d683da2e7":  # Carl's Jr. (Love's truck stop, AZ-95)
        "Inside a Love's truck stop on the highway — open 5am-midnight; drive-through can stall when it's short-staffed.",
    "9748c306-cf26-4940-8bd4-c23e7823769d":  # Montana's
        "Dinner steakhouse, closed Mondays — service can run slow at the dinner hour, so plan for an unhurried meal.",
    "f36fb5b3-f2e6-4236-8668-3c7e99994084":  # College Street Brewhouse & Pub
        "A locals' pub with a strong regular crowd — steady rather than spiky; the lake-view patio is the seat to want.",
    "3ad0f2fd-b697-4a53-accf-3f8267c86af3":  # Dairy Queen Grill & Chill
        "Service can drag (20-minute waits reported) — the dog-friendly patio is nice when it's not too hot out.",
    "adadb90c-490d-4bc6-b5e1-6ed179a4af17":  # Mario's Italian Restaurant
        "Dinner-only (opens 4pm), cozy and deliberately no-rush — flag your server early, then settle in.",
    "f3026987-143b-4f99-9073-3582c99de616":  # Flying X Saloon
        "Live-music nights are the event — it fills up after the 6pm band starts; downtown's most happening late spot.",
    "e50c0500-24eb-4a29-b2f9-4a590a92d604":  # Martini Bay
        "Waterfront resort restaurant — happy hour and dinner are the peaks; book ahead but confirm, and the London Bridge-view patio tables go first.",
    "18dc2529-67c4-4bcd-9dab-b63785376e43":  # Lin's Little China
        "Closed Mondays; early dinner (around 4:30) walks right in with no notable wait.",
    "4b157e3c-87bc-4c93-a551-0ceb1fbb60b0":  # Boat House Grill
        "On the island near Islanda Resort — closed Tuesdays; draws resort guests and a sunny-day waterfront crowd.",
    "0e865f8a-b0a4-4c87-a6f4-aa1a332d2a55":  # Locos Bar and Cocina - Swanson
        "Dinner-only (opens 4pm) — the bar side runs games and Friday live music; happy-hour margaritas pull a crowd.",
    "ca4fbae4-1c77-41f9-97af-9a1a960ae6cc":  # Jersey's American Grill
        "Limited days — closed Mon-Tue and closes early; a regulars' lunch spot, check the hours before you go.",
    "715e5936-67c4-4abe-99ab-8de4576d5c15":  # Peggy's Sunrise Cafe
        "Breakfast-and-lunch only (6am-2pm) — small and often packed, but the crowd turns over fast.",
    "effec819-c072-47ba-ac77-a72adfb32f4f":  # Niko's Grill & Pub
        "An off-the-main-drag neighborhood gathering spot — steady locals' crowd rather than a tourist rush.",
    "27a4be4a-9163-4211-8d87-1b8f85111d21":  # Sonora Tacos Y Mariscos
        "Steady neighborhood Mexican-seafood spot — happy hour margaritas are the busy draw, otherwise an easy walk-in.",
    "97c8ad65-147a-4904-81dc-e75fb85ae113":  # Habit Burger & Grill
        "Typical fast-casual flow; event days (like the Havasu Half) bring a post-race rush — drive-through and kiosks keep it moving.",
    "e4c4fe17-103b-4baa-bcf8-255ed18a54f3":  # McKee's Pub & Grill
        "Busy downtown locals' pub with dart tournaments and poker nights — gets full but booths turn over; snowbird-friendly.",
    "b0e43ac4-2c0a-4fa9-843d-02956cccd31d":  # The Spot
        "Closed Mondays-Tuesdays; a loud arcade-and-pizza family spot that's often packed — expect a real wait on the food.",
    "e285fe82-cf8c-4096-a97a-07b9964e54e7":  # Carl's Jr. (N Lake Havasu Ave)
        "Open 6am-midnight; drive-through can be slow — orders often get pulled forward to wait.",
    "74663daa-6975-4ef4-83ca-fc8e6e7cd844":  # El Mariachi Mexican Restaurant
        "Quaint spot near the channel with easy parking — gets busy but seating turns quickly.",
    "a77909c4-a683-4ac5-bd6b-66d2b48ccad5":  # Filiberto's
        "Open 24 hours — a reliable late-night and early-morning stop; stays busy, especially for breakfast burritos.",
    "f1eeb6d3-782c-4f22-bfc6-c7d824792ead":  # Starbucks Coffee Company (52 Lake Havasu Ave)
        "Roomy with plenty of seating, but the parking lot is tight and awkward to enter — the bottleneck here is the lot, not the line.",
}


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH} — run from the repo root.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    applied = 0
    missing: list[str] = []
    already: list[str] = []
    for entity_id, short in CROWD_NOTES_SHORT.items():
        cur.execute(
            "SELECT name, crowd_notes FROM entities WHERE id = ?", (entity_id,)
        )
        row = cur.fetchone()
        if row is None:
            missing.append(entity_id)
            continue
        if row[1] is not None:
            already.append(f"{row[0]} ({entity_id})")
        payload = json.dumps({"short": short})
        if dry_run:
            print(f"  [dry-run] {row[0]}")
        else:
            cur.execute(
                "UPDATE entities SET crowd_notes = ?, updated_at = ? WHERE id = ?",
                (payload, now, entity_id),
            )
        applied += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print()
    print(f"--- crowd_notes batch 2 ({'dry-run' if dry_run else 'committed'}) ---")
    print(f"venues in script:   {len(CROWD_NOTES_SHORT)}")
    print(f"matched + applied:  {applied}")
    if missing:
        print(f"NOT FOUND ({len(missing)}): {', '.join(missing)}")
    else:
        print("all 31 entity_ids matched")
    if already:
        print(f"NOTE: {len(already)} already had crowd_notes (overwritten): {already}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
