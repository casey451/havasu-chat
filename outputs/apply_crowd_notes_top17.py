"""Apply long-form crowd_notes to the top-17 eat-drink venues — Phase 5.1 field entry.

Staged by Cowork primary (Phase 5 lane, 2026-05-15) from Google review-snippet
analysis. DRAFTS — review `outputs/phase5_1_crowd_notes_top17_staged.md` and edit
the text below before running if you disagree with any call.

crowd_notes JSON shape (decided this session — noted for the Phase 6 agent):
    {"short": "<1-sentence crowd pattern>", "long": "<multi-paragraph, \\n\\n between>"}
Typical (non-top-20) venues will later get {"short": ...} only.

Run Windows-side from the repo root:
    python outputs/apply_crowd_notes_top17.py            # apply
    python outputs/apply_crowd_notes_top17.py --dry-run  # preview, no writes

Idempotent — re-running re-sets the same values. Sets updated_at explicitly
(raw sqlite3 does not fire the ORM onupdate).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "events.db"

# entity_id -> {"short": ..., "long": ...}
CROWD_NOTES: dict[str, dict[str, str]] = {
    # 1. In-N-Out Burger — 3878 reviews, 4.6
    "dd03459c-142e-4aa6-9fdd-4435a4f4f992": {
        "short": "Lines look long but move fast — expect the biggest crowds during Havasu festival weekends and lake events.",
        "long": (
            "In-N-Out runs one of the highest review volumes of any eatery in town, and the dining room "
            "frequently looks packed — reviewers describe walking in to a full waiting area. The line moves "
            "much faster than it appears, though: counter service and the kitchen turn orders in a minute or "
            "two even at the lunch peak. The drive-through is the steadier bet when the lot is full.\n\n"
            "The real surge is event-driven. Festival weekends and lake events on the London Bridge Road "
            "corridor push the wait areas well beyond normal. Open 10:30am to 1:00am, so late night is a "
            "genuine low-traffic window if the daytime crowds aren't worth fighting."
        ),
    },
    # 2. Juicy's — 3124 reviews, 4.5
    "f889b808-53e6-40a3-8a31-59664a561fee": {
        "short": "Busy on weekend mornings — service can lag at the breakfast-and-lunch peak; mid-afternoon is the calm window.",
        "long": (
            "Juicy's pulls heavy breakfast and lunch traffic downtown on Smoketree, and reviewers note that on "
            "busy mornings it can take a while just to get acknowledged and seated. The kitchen and servers keep "
            "up well outside the rush, but weekend mid-mornings are the pinch point.\n\n"
            "Open 7am to 8pm. The stretch after the lunch rush and before dinner is the easiest time to walk in "
            "without a wait."
        ),
    },
    # 3. Black Bear Diner — 2735 reviews, 4.4
    "b767eea4-07e0-40d0-b2a6-0a9ba23d7682": {
        "short": "Booth waits are common at breakfast and dinner peaks; the wide 6am-10pm window makes it easy to dodge the rush.",
        "long": (
            "Black Bear Diner is a high-volume family diner on McCulloch, and the booths in particular fill up "
            "— reviewers describe waiting specifically for a booth even when tables are open. Staff are attentive "
            "about working the waiting area, but expect a queue at weekend breakfast and at the dinner hour.\n\n"
            "The long service window helps: open 6am to 10pm daily, so an early breakfast or a late dinner "
            "sidesteps the busiest stretches entirely."
        ),
    },
    # 4. ChaBones — 2493 reviews, 4.6
    "9fabfe79-d567-4cea-a079-0c1582baf42a": {
        "short": "Reservations recommended — one of Havasu's busiest upscale tables; fills at dinner and through happy hour.",
        "long": (
            "ChaBones is consistently called one of Havasu's top dining rooms, and that reputation shows in the "
            "crowds — reviewers explicitly recommend booking ahead because walk-ins risk a wait. Happy hour is a "
            "second daily peak on top of the dinner rush, drawing its own crowd for the discounted plates and "
            "drinks.\n\n"
            "Open 11am to 9pm. Staff will try to fit walk-ins in, but a reservation is the difference between "
            "being seated promptly and waiting at one of the busiest tables in town, especially in peak season."
        ),
    },
    # 5. Culver's — 2371 reviews, 4.5
    "798c2902-feaa-4dab-be55-0e280e73c609": {
        "short": "Standard fast-food flow — drive-through and online pickup keep peak waits short.",
        "long": (
            "Culver's runs a typical quick-service pattern: counter and drive-through orders move steadily, and "
            "online ordering for pickup is a well-used option that keeps the lobby from backing up. Reviewers "
            "don't report meaningful waits even at busy times.\n\n"
            "Open 10am to 10pm. No strong daily peak worth steering around — the drive-through absorbs the rush."
        ),
    },
    # 6. Smith's — 2074 reviews, 4.5 — GROCERY ANCHOR
    "8d088a4d-2e89-4412-9520-3bd73272f406": {
        "short": "Parking is the real bottleneck — the lot fills midday; locals shop early morning or after dark.",
        "long": (
            "Smith's is one of Havasu's main grocery anchors, and the recurring crowd complaint isn't the "
            "checkout lines — it's the parking lot. Multiple reviewers describe it as a hassle to park midday "
            "and specifically recommend going very early or after dark to get a spot easily.\n\n"
            "The store's draw as a one-stop shop compounds the traffic: an in-store Starbucks, a beer-and-wine "
            "bar, a full butcher counter, hot food, and a fuel station on site all pull people in. Open 6am to "
            "midnight, so the early-morning and late-evening windows are both genuinely quieter."
        ),
    },
    # 7. El Paraiso Mexican — 2071 reviews, 4.4 — also PROVISIONAL on heat list
    "82d0eaea-06b7-451f-b3de-b67870ce4e09": {
        "short": "Packs out at dinner and happy hour; the after-2pm lull is the calm window and still catches the lunch special.",
        "long": (
            "El Paraiso runs full at dinner and through its well-known $6 happy hour — reviewers describe the "
            "place as packed while still praising how the service holds up under it. It's a high-volume "
            "favorite, so the dinner rush is real.\n\n"
            "The sweet spot is mid-afternoon: one reviewer noted that arriving after 2pm meant a calm room and "
            "still being in time for the daily lunch special. Open 11am to 9pm. (Note: this venue is also a "
            "PROVISIONAL row on the heat_exposure priority list — patio-shade confirm still pending.)"
        ),
    },
    # 8. Red Robin — 2023 reviews, 4.3
    "949c5c01-c6f6-4ed7-843a-72b7eb1b5dae": {
        "short": "Popular with London Bridge Resort guests within walking distance — busiest at dinner and on weekends.",
        "long": (
            "Red Robin sits within walking distance of the London Bridge Resort, and a notable share of its "
            "traffic is resort and vacation guests — reviewers repeatedly mention walking over during a Havasu "
            "trip. That tourist foot traffic makes it a steady, popular spot rather than a locals' weeknight "
            "default.\n\n"
            "Open 11am to 9pm. Dinner and weekends are the peaks; weekday lunches and early afternoons are the "
            "easier walk-in windows."
        ),
    },
    # 9. Chico's Tacos — 2020 reviews, 4.5
    "facd8ac2-34a0-4a36-9e24-0fc05345c0b2": {
        "short": "Taco Tuesdays draw long lines and seat scarcity — especially in snowbird season; pick another day for a calmer visit.",
        "long": (
            "Chico's has a sharp weekly peak: reviewers single out Taco Tuesday as extremely busy, with long "
            "lines and a real struggle to find a seat. The crowding is seasonal on top of that — it's noticeably "
            "worse when the snowbirds are in town, and reviewers say the atmosphere depends on the season.\n\n"
            "The layout gives you options: you can order quick-service at the counter or go full-service in the "
            "bar, and the bar side is the better bet when the counter line is deep. Open 9am to 9pm — any day "
            "but Tuesday is the lower-stress visit."
        ),
    },
    # 10. Chili's Grill & Bar — 1888 reviews, 4.2
    "676775cb-6506-4027-a8bc-0b362cd9e21c": {
        "short": "Steady dinner crowds but rarely a long wait — weeknights move quickly, bar seating is the fast option.",
        "long": (
            "Chili's stays busy at dinner but reviewers consistently report walking right in without a wait, "
            "even on nights they expected a crowd. It's a reliable, well-run flow rather than a wait-list "
            "restaurant.\n\n"
            "The bar is the fast lane when the dining room looks full. Open 11am to 10pm; weeknights are quicker "
            "than weekends, but neither is a long wait."
        ),
    },
    # 11. Rosati's Pizza — 1867 reviews, 4.3
    "04134e0a-1b48-493e-8dd7-0faee8743586": {
        "short": "Mostly a takeout and slice counter — minimal dine-in waits; delivery can run long at the dinner peak.",
        "long": (
            "Rosati's runs primarily as a takeout, slice, and delivery operation rather than a sit-down "
            "destination, so dine-in waits are minimal. The crowd pressure shows up instead on the delivery side "
            "— one reviewer noted an order taking over an hour at peak.\n\n"
            "Open 10:30am to 10pm. For dine-in or slices there's rarely a reason to time your visit; for "
            "delivery, build in extra time on weekend evenings."
        ),
    },
    # 12. Javelina Cantina — 1862 reviews, 4.3 — water_adjacent on heat list
    "ba787210-66ac-45f2-b7eb-54b3a8cbff1f": {
        "short": "Waterfront English Village location draws steady tourist traffic — channel-view patio tables go first at dinner.",
        "long": (
            "Javelina Cantina is in the English Village waterfront cluster, with patio seating overlooking the "
            "London Bridge and the Bridgewater Channel. That location makes it a steady tourist destination, and "
            "the dog-friendly patio tables with the channel view are the ones that fill first — reviewers prize "
            "that seating specifically.\n\n"
            "Open 11am to 9pm. Dinner is the peak; the patio competition is heaviest on warm evenings and "
            "weekends. (Note: this venue is tagged water_adjacent on the heat_exposure priority list.)"
        ),
    },
    # 13. Denny's Restaurant — 1847 reviews, 4.1
    "ac1dc9d9-3c80-410c-aab1-5b58ed074123": {
        "short": "Billed 24 hours, but the kitchen can go limited overnight — late-night orders (roughly 2-5am) aren't always available.",
        "long": (
            "Denny's is listed as open 24 hours, and reviewers confirm the 24-hour availability is the main "
            "reason people choose it. But the overnight reality is softer than the listing: at least one "
            "reviewer was told around 2:30am that no orders could be made until 5am. Treat the deep-overnight "
            "window as unreliable for a hot meal.\n\n"
            "Daytime and evening run as normal diner flow with no notable wait. The value is the off-hours "
            "coverage when little else is open — just don't count on a full kitchen in the 2-5am stretch."
        ),
    },
    # 14. Rusty's Restaurant — 1796 reviews, 4.6
    "94db3b94-57d5-43f0-8f06-de6ccb44488f": {
        "short": "North-side breakfast staple with real weekend waits — Saturday mornings are the peak; closes at 2pm daily.",
        "long": (
            "Rusty's is a well-loved north-side breakfast-and-lunch spot, and reviewers are explicit about the "
            "trade-off: the food earns a 4.6, but busy Saturdays bring long wait times. Weekend mornings are the "
            "clear peak.\n\n"
            "It's breakfast and lunch only — open 7am to 2pm daily, no dinner service. Weekday mornings are "
            "considerably calmer than the weekend rush; if you're going on a Saturday, go early."
        ),
    },
    # 15. Safeway — 1779 reviews, 4.4 — GROCERY ANCHOR
    "2b6b097f-e88c-44ae-b9e3-871738bbd80b": {
        "short": "Steady grocery flow — the service counter (money orders, Western Union) and bakery pickup are the slow points, not the checkout lines.",
        "long": (
            "Safeway is a central grocery anchor with a steady, manageable flow — reviewers don't flag checkout "
            "lines or parking as the problem. The friction points are the specialty counters: the "
            "customer-service counter for money orders and Western Union draws complaints about slow, "
            "inconsistent service, and bakery-order pickup has its own hiccups.\n\n"
            "The bakery and deli are genuine destination counters that pull traffic beyond normal grocery runs. "
            "Open 6am to 10pm; the grocery-pickup service is popular and well-reviewed for dodging the in-store "
            "trip entirely."
        ),
    },
    # 16. Shugrue's Restaurant and Brewery Group — 1732 reviews, 4.4 — water_adjacent on heat list
    "c1c8829c-b200-49ac-8cab-f69bf7ff23bd": {
        "short": "Dinner-only waterfront spot — arrive by 4-4:30pm for prompt seating and a bridge-view table; later dinner fills up.",
        "long": (
            "Shugrue's is a dinner-only upscale restaurant in the English Village waterfront cluster, and its "
            "bridge-and-channel views make the window tables the prized seating. Reviewers who arrive around 4pm "
            "report being seated promptly; the later dinner hour is when it fills.\n\n"
            "Open 3pm to 9pm. There's a clear early-arrival advantage here — both for getting a view table and "
            "for avoiding the dinner-rush wait. English Village tourist density makes weekends and peak season "
            "the busiest. (Note: this venue is tagged water_adjacent on the heat_exposure priority list.)"
        ),
    },
    # 17. Bashas' — 1674 reviews, 4.3 — GROCERY ANCHOR
    "b4e3d473-f1ba-4679-8771-46e3d9493b35": {
        "short": "South-side grocery anchor with a calmer pace than the central stores — the deli counter is the main wait, lightest early morning.",
        "long": (
            "Bashas' on Maricopa Avenue serves the south side of Havasu and runs at a noticeably calmer pace "
            "than the central Smith's and Safeway — parking and checkout aren't the recurring complaints here. "
            "The deli counter is the main slow point, with reviewers describing variable service depending on "
            "who's working it.\n\n"
            "One regular's tell: shopping in the morning with the older staff for better counter service. Open "
            "6am to 10pm; early mornings are the quietest and the best bet for the deli."
        ),
    },
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
    for entity_id, notes in CROWD_NOTES.items():
        cur.execute("SELECT name FROM entities WHERE id = ?", (entity_id,))
        row = cur.fetchone()
        if row is None:
            missing.append(entity_id)
            continue
        payload = json.dumps({"short": notes["short"], "long": notes["long"]})
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
    print(f"--- crowd_notes apply ({'dry-run' if dry_run else 'committed'}) ---")
    print(f"venues in script:   {len(CROWD_NOTES)}")
    print(f"matched + applied:  {applied}")
    if missing:
        print(f"NOT FOUND ({len(missing)}): {', '.join(missing)}")
    else:
        print("all 17 entity_ids matched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
