# Phase 5.1 — Short-form `crowd_notes`, Batch 2 (Staged)

> **What this is:** short-form (1-sentence) `crowd_notes` for the next 31 active
> eateries by review volume — ranks 18–48, the ~525–1070-review band. The top-17
> already have long-form notes; per runbook §4, typical venues get the 1-sentence
> `{short}`-only treatment (no `long` key — that's how Phase 6 tells list-blurb
> from profile-section).
>
> **DRAFTS** mined from Google review snippets, crowd-pattern focused (busy times,
> waits, parking, hours, seasonal). Review/edit the text in
> `outputs/apply_crowd_notes_batch2.py` before running if any call is off.
>
> **Tiering:** 238 active eateries still need `crowd_notes`. 130 have ≥100 reviews
> (real signal); the rest thin out fast. This is **batch 2 of that tier** — ~99
> more ≥100-review venues remain for follow-on batches. Sub-50-review venues are
> better left for the operator's own pass — a crowd note from 3 reviews is guessing.
>
> **DB read method:** `/tmp` copy (gotcha #4/#15). All 31 entity_ids verified
> against the live DB on 2026-05-15 — all exist, all active, none already had
> `crowd_notes`, no overlap with the top-17.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`250fa6b`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

## §1 The 31 venues + short notes

| Rank | Venue | Short note |
|---|---|---|
| 18 | Burgers by the Bridge | Walk-up counter in the English Village — tourist traffic, but the line moves quick and outdoor seating handles big groups. |
| 19 | Legendz Sports Bar & Grill | Game days are the peak — the big-screen sports crowd's spot; lots of space keeps it absorbable otherwise. |
| 20 | Bad Miguel's Mexican | Rarely crowded; the 3–5pm happy hour is the quiet, cheap window. |
| 21 | Wendy's | Open 24 hours but service runs slow — order ahead on the app if you're rushed. |
| 22 | Panda Express | Lines back up waiting on fresh-cooked batches — peak meals mean a wait. |
| 23 | BJ's Cabana Bar & Karaoke | Live-music nights (Sundays especially) draw the crowd; arrive early for a shaded patio seat. |
| 24 | Arby's | Standard fast-food flow — quick turnaround, no notable wait. |
| 25 | Locos – Northside | Dinner-only and closed some weekdays — the live-music patio is the draw, good for groups. |
| 26 | Wienerschnitzel | Drive-through, open late to midnight — quick, no real peak to dodge. |
| 27 | Food City | Neighborhood grocery with a seating area where south-side locals gather for a morning snack. |
| 28 | Carl's Jr. (Love's truck stop) | Inside a Love's truck stop; open 5am–midnight — drive-through can stall when short-staffed. |
| 29 | Montana's | Dinner steakhouse, closed Mondays — service runs slow at the dinner hour. |
| 30 | College Street Brewhouse & Pub | Locals' pub with a strong regular crowd — steady not spiky; the lake-view patio is the seat to want. |
| 31 | Dairy Queen Grill & Chill | Service can drag (20-min waits reported) — dog-friendly patio when it's not too hot. |
| 32 | Mario's Italian | Dinner-only (opens 4pm), cozy and no-rush — flag your server early. |
| 33 | Flying X Saloon | Live-music nights are the event — fills after the 6pm band; downtown's most happening late spot. |
| 34 | Martini Bay | Waterfront resort restaurant — happy hour + dinner peaks; book ahead, bridge-view patio fills first. |
| 35 | Lin's Little China | Closed Mondays; early dinner (~4:30) walks right in. |
| 36 | Boat House Grill | On the island near Islanda Resort — closed Tuesdays; resort + sunny-day waterfront crowd. |
| 37 | Locos – Swanson | Dinner-only (opens 4pm) — bar runs games + Friday live music; happy-hour margaritas pull a crowd. |
| 38 | Jersey's American Grill | Limited days — closed Mon–Tue, closes early; a regulars' lunch spot, check hours first. |
| 39 | Peggy's Sunrise Cafe | Breakfast-and-lunch only (6am–2pm) — small and often packed, but turns over fast. |
| 40 | Niko's Grill & Pub | Off-the-main-drag neighborhood gathering spot — steady locals, not a tourist rush. |
| 41 | Sonora Tacos Y Mariscos | Steady neighborhood Mexican-seafood spot — happy hour margaritas are the busy draw. |
| 42 | Habit Burger & Grill | Typical fast-casual; event days (Havasu Half) bring a post-race rush — drive-through + kiosks move it. |
| 43 | McKee's Pub & Grill | Busy downtown locals' pub with darts + poker nights — fills but booths turn; snowbird-friendly. |
| 44 | The Spot | Closed Mon–Tue; loud arcade-and-pizza family spot, often packed — expect a real food wait. |
| 45 | Carl's Jr. (N Lake Havasu Ave) | Open 6am–midnight; drive-through can be slow — orders often pulled forward to wait. |
| 46 | El Mariachi Mexican | Quaint spot near the channel, easy parking — gets busy but seating turns quickly. |
| 47 | Filiberto's | Open 24 hours — reliable late-night + early-morning stop; stays busy for breakfast burritos. |
| 48 | Starbucks (52 Lake Havasu Ave) | Roomy with lots of seating, but the parking lot is the bottleneck — tight and awkward to enter. |

## §2 How to apply

Run Windows-side from the repo root:

```
python outputs\apply_crowd_notes_batch2.py --dry-run   # preview, no writes
python outputs\apply_crowd_notes_batch2.py             # apply
```

The script reports matched count and flags any id that's missing or already had
`crowd_notes` (none do, per verification).

## §3 After this

`crowd_notes` populated count goes 17 → 48. Remaining: ~99 more ≥100-review active
eateries for follow-on batches, then the sub-100 long tail (better as the
operator's own pass). Not a gate item — the gate's `crowd_notes` requirement
(top-20 long-form) is already met — this is field-entry completeness.

---

## §4 Files

- `outputs/apply_crowd_notes_batch2.py` — the runnable apply script (also the review surface for exact text)
- `outputs/phase5_1_crowd_notes_top17_staged.md` — the long-form top-17 (already applied)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`250fa6b`,
2026-05-15). Lives at `outputs/phase5_1_crowd_notes_batch2_staged.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Entity_ids verified against
a `/tmp` copy of the live `data/events.db`.*
