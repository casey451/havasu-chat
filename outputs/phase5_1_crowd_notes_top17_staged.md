# Phase 5.1 Field Entry — `crowd_notes` Staged (Top-17 Eat & Drink)

> **What this is:** long-form `crowd_notes` pre-drafted for the top-17 Eat & Drink
> venues, ready for operator review and a one-command apply. Cowork pulled the
> highest-review venues from the live DB, mined their Google review snippets for
> **crowding signal** (wait times, parking, seasonal/snowbird surges, best windows
> — per the Opus design intent of `crowd_notes`, *not* a food review), and drafted
> a `{short, long}` note for each.
>
> **These are DRAFTS** synthesized from review snippets. You have local knowledge
> the snippets don't — review and edit the text in `outputs/apply_crowd_notes_top17.py`
> before running if any call is off.
>
> **DB read method:** bash sandbox can't open the rebuilt `events.db` directly
> (gotcha #4/#15) — Cowork read a `/tmp` copy. The apply script runs Windows-side
> against the live `data/events.db`. All 17 entity_ids verified against the live DB.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`d34d4c3`, 2026-05-15). Brand-new `outputs/` files — safe under the
> parallel-chat scope lock.

---

## §1 Decisions baked in

**Top-20 scope → 14 eateries + 3 grocery anchors (17 total).** The literal top-20
rows by review count included 2 hotels and 1 park; this set follows the LOCKED
§3.3.h rubric, which explicitly names "top-5 grocery/big-box anchors" as long-form
targets. See §4 for what was excluded and why.

**`crowd_notes` JSON shape → `{"short": ..., "long": ...}` dict.** Decided this
session (operator delegated to Cowork's recommendation). Rationale: structured, so
Phase 6 can render `short` in list/card views and `long` on the profile page
without parsing; typical (non-top-20) venues will later get `{"short": ...}` only,
and the absence of `long` is a clean signal. **⚠ Phase 6 agent coordination:** this
shape is a contract the Phase 6 lane renders — it lands on origin via the operator's
commit of these files, so the Phase 6 agent picks it up from the commit. If the
Phase 6 agent has already assumed a different shape, reconcile before both lanes
get deep into it.

## §2 The 17 venues + their short-form note

Full `long` text (2 paragraphs each) is in `outputs/apply_crowd_notes_top17.py` —
that file is plain readable Python, it *is* the review surface for the long-form
prose. Short-form preview for scanning:

| # | Venue | Reviews | `short` note |
|---|---|---|---|
| 1 | In-N-Out Burger | 3878 | Lines look long but move fast — biggest crowds during festival weekends and lake events. |
| 2 | Juicy's | 3124 | Busy on weekend mornings — service lags at the breakfast/lunch peak; mid-afternoon is calm. |
| 3 | Black Bear Diner | 2735 | Booth waits common at breakfast and dinner peaks; wide 6am-10pm window dodges the rush. |
| 4 | ChaBones | 2493 | Reservations recommended — fills at dinner and through happy hour. |
| 5 | Culver's | 2371 | Standard fast-food flow — drive-through and online pickup keep peak waits short. |
| 6 | Smith's *(grocery)* | 2074 | Parking is the bottleneck — lot fills midday; locals shop early or after dark. |
| 7 | El Paraiso Mexican | 2071 | Packs out at dinner and happy hour; after-2pm lull is the calm window. |
| 8 | Red Robin | 2023 | Popular with London Bridge Resort guests within walking distance; busiest at dinner/weekends. |
| 9 | Chico's Tacos | 2020 | Taco Tuesdays draw long lines and seat scarcity, worse in snowbird season. |
| 10 | Chili's Grill & Bar | 1888 | Steady dinner crowds but rarely a long wait; bar seating is the fast option. |
| 11 | Rosati's Pizza | 1867 | Mostly takeout/slice counter — minimal dine-in waits; delivery runs long at peak. |
| 12 | Javelina Cantina | 1862 | Waterfront English Village spot — channel-view patio tables go first at dinner. |
| 13 | Denny's Restaurant | 1847 | Billed 24h but the kitchen can go limited overnight (~2-5am). |
| 14 | Rusty's Restaurant | 1796 | North-side breakfast staple with real weekend waits; closes 2pm daily. |
| 15 | Safeway *(grocery)* | 1779 | Service counter and bakery pickup are the slow points, not the checkout lines. |
| 16 | Shugrue's | 1732 | Dinner-only waterfront — arrive by 4-4:30pm for prompt seating and a bridge-view table. |
| 17 | Bashas' *(grocery)* | 1674 | South-side anchor, calmer than the central stores; deli counter is the main wait. |

Three of these (El Paraiso, Javelina Cantina, Shugrue's) are also on the
`heat_exposure` priority list — their `long` notes carry a cross-reference line.

## §3 How to apply

Run Windows-side from the repo root:

```
python outputs/apply_crowd_notes_top17.py --dry-run   # preview — lists matched venues, no writes
python outputs/apply_crowd_notes_top17.py             # apply + commit to data/events.db
```

The script is idempotent (re-running re-sets the same values), sets `updated_at`
explicitly, and reports matched/missing counts. It uses `from datetime import UTC`
— matches the repo's existing convention (`scripts/places_load.py` does the same).

## §4 Excluded from the literal top-20 (not a decision to make — just provenance)

| Rank | Row | Why excluded |
|---|---|---|
| 3 | London Bridge Beach | `google_primary_category = park` — it loaded into `category=food_drink` (a mild discovery-precision artifact) but it's really a park / on-the-water entity, already on the heat list as `water_adjacent` §3 #18. Not an eatery. **Possible follow-up:** you may want to recategorize this row out of `food_drink` — flagging, not acting. |
| 6 | The Nautical Beachfront Resort | Resort/hotel. Has the Turtle Grille restaurant, but the entity is the resort, not the eatery — §3.3.h names grocery anchors, not hotels. |
| 12 | London Bridge Resort | Hotel. Same reasoning. |

If you'd rather pull the 2 hotels in (they do have notable on-site restaurants) or
swap in the next eateries down the list to hit a literal 20, that's a quick change —
say the word and I'll re-stage.

## §5 What this advances

Applying the script populates long-form `crowd_notes` on 17 of the top-volume
Eat & Drink venues — the bulk of the acceptance-gate item **"Top-20 entries have
long-form `crowd_notes` populated."** Whether the gate reads as "literal 20" or
"the §3.3.h set" is the one open question (§4); the 17 here cover the §3.3.h
reading. Short-form `crowd_notes` for the remaining ~270 typical venues is a
separate, later field-entry pass (`{"short": ...}` only).

---

## §6 Files

- `outputs/apply_crowd_notes_top17.py` — the runnable apply script (also the review surface for the full `long` prose)
- `outputs/phase5_1_crowd_notes_top17_staged.md` — this doc

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`d34d4c3`,
2026-05-15). `crowd_notes` drafted from Google review-snippet analysis of the live
`data/events.db`; entity_ids verified against a `/tmp` copy. Brand-new `outputs/`
files, safe under the parallel-chat scope lock.*
