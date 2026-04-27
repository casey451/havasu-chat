# Confabulation Eval Summary

## Inclusion policy
- Included in gating-confabulation-rate summary: 650
- Excluded from gating confabulation-rate summary: 286
- **Gating rate denominator:** Tier `2` always; Tier `3` when Layer 2 has at least one hit (partial inclusion; spec §3.5.2 / §3.6). Headline **confabulation rate** uses **Layer 2 + Layer 3** in Tier 2, and **Layer 2** in Tier 3; **Layer 1** is **advisory** (see spec §3.5.1 / §3.6). Tier `1` and Tier `3` runs with no Layer 2 hits are excluded from the headline denominator.
- Tier 1 invocations excluded: 138
- Tier 3 invocations excluded (no Layer 2 gating signal): 148
- Tier 3 invocations **included** due to Layer 2 hits: 42

## Per-flag gating confabulation rate (Layer 2 + Layer 3 only)
- `off`: 59/391 (15.1%) with ≥1 gating hit
- `on`: 70/259 (27.0%) with ≥1 gating hit

## Top offending rows (by gating hits, Tier-2-included only)
- `Arizona Coast Performing Arts (ACPA)` (`69ac46d9-e557-4357-9c8d-4744e4906a44`): 13/18 included runs with ≥1 gating hit
- `Littles NoGi Jiu-Jitsu (Ages 3–6)` (`d2d5b702-84a8-4768-a1df-cf98015df019`): 10/18 included runs with ≥1 gating hit
- `Aqua Aerobics / Water Fitness` (`9f57dc7e-48f6-4949-86dc-24ac55960c2d`): 10/15 included runs with ≥1 gating hit
- `MMA` (`0eef6522-3acf-436a-9603-bbb4d6977a82`): 10/12 included runs with ≥1 gating hit
- `Footlite School of Dance` (`b4efd7fd-b6a8-4471-9a4c-00356c2c882d`): 9/11 included runs with ≥1 gating hit
- `Flips for Fun Gymnastics` (`dcfa87ab-18ce-4782-8f05-e112e867c234`): 9/9 included runs with ≥1 gating hit
- `Littles Gi Jiu-Jitsu (Ages 3–6)` (`05caa2e3-24bf-4337-bede-4ff60baba0d7`): 8/18 included runs with ≥1 gating hit
- `Arevalo Academy` (`b0900e1e-8441-474f-aa6a-7b83ed143fe8`): 7/10 included runs with ≥1 gating hit
- `Rock & Bowl (Cosmic Bowling)` (`24f8c545-005d-4a98-9762-04ed9e5a3673`): 6/18 included runs with ≥1 gating hit
- `Open Swim` (`a5756cb3-a9c0-42c5-8b33-2afd1021ef08`): 5/17 included runs with ≥1 gating hit
- `Altitude Trampoline Park — Lake Havasu City` (`7ab2fd82-e1ed-41a9-b69f-4f18b5c2def1`): 5/7 included runs with ≥1 gating hit
- `Ballet Havasu` (`cfe36f3f-9ba7-4a4a-8a06-4137d5125044`): 4/9 included runs with ≥1 gating hit
- `The Tap Room Jiu Jitsu` (`3caa56ff-2035-4036-b75f-a30f7c761a0a`): 4/9 included runs with ≥1 gating hit
- `Youth Gi Jiu-Jitsu (All Levels)` (`649a3caf-8ea1-4840-a745-941c6a0f1c22`): 3/15 included runs with ≥1 gating hit
- `Mountain Bike Practice — Rotary Park (Wednesday)` (`2c61f512-a7ce-477c-958e-0f17a84fb02c`): 3/12 included runs with ≥1 gating hit
- `Lake Havasu City Aquatic Center` (`47b5dd11-6d6b-49c4-88ce-82dc4e5ad86b`): 3/8 included runs with ≥1 gating hit
- `Strider/Balance Bike Track (Patrick Tinnell Balance Bike Track)` (`30a4ec1f-0b68-4f97-b536-a00ada5ff3a4`): 2/18 included runs with ≥1 gating hit
- `Lap Swim` (`66d7f0bc-bc71-4179-9f39-2b734967c22f`): 2/17 included runs with ≥1 gating hit
- `Open Bowling` (`0255ab36-383b-4fe4-898f-5ba5a471bdb8`): 2/15 included runs with ≥1 gating hit
- `Monthly Membership — Standard` (`3cf5cf2e-782c-4dc8-917a-f110882f1ba2`): 2/14 included runs with ≥1 gating hit

## Top gating confabulation tokens (Layer 2 + Layer 3, Tier-2-included only)
- `studio`: 32
- `enrollment`: 26
- `18+`: 20
- `t:16:45`: 13
- `call ahead`: 9
- `pool`: 9
- `drop-in`: 7
- `all ages`: 4
- `qt:some`: 4
- `qt:most`: 3
- `private`: 3
- `heated`: 3
- `indoor`: 2
- `outdoor`: 2
- `casual`: 2
- `beginner-friendly`: 2
- `bar`: 2
- `perfect for`: 2
- `c:free`: 1
- `sign up`: 1

## Layer 1 candidate tokens (advisory — do not gate the headline rate)
These are **advisory** lemma-diff surface tokens for human review (spec §3.5.1). They are **not** used for the gating confabulation rate or for offender row ranking above.
- `cost`: 211
- `program`: 136
- `p.m`: 113
- `class`: 101
- `age`: 95
- `kid`: 92
- `meet`: 88
- `open`: 82
- `thursday`: 82
- `a.m`: 77
- `session`: 66
- `martial`: 61
- `art`: 61
- `day`: 57
- `gym`: 54
- `week`: 52
- `daily`: 50
- `time`: 45
- `row`: 44
- `focus`: 42

## Tier breakdown
- tier `1`: 138
- tier `2`: 590
- tier `3`: 190
- tier `chat`: 18

## Regression-anchor sanity check (gating: Layer 2 + Layer 3 only)
- `Aqua Beginnings`: 0/12 included runs with ≥1 gating hit
- `Grace Arts Live`: 0/18 included runs with ≥1 gating hit
