# Phase 6.1.2 — Dry-run transcript & Tier 1 matrix justification

**Date:** 2026-04-21  
**Related:** `scripts/run_voice_audit.py`, `docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt` (machine-captured UTF-8), `docs/phase-6-1-2-audit-runner-report.md`

---

## Tier 1 count — what changed and why

**Earlier (17 auditable, 0 skips):** LOCATION and WEBSITE only tried **one** successful provider each, TIME-hours used the first hours-bearing row (not necessarily Altitude), there was only **one** DATE/NEXT provider pair, **one** OPEN_NOW row, and **two** AGE rows. That was **too collapsed** versus the proposal matrix, which names **multiple entities** for several rows and expects **seed-dependent** `branch_present_not_auditable` when a named cell cannot render (e.g. Bridge City Combat with no `website`).

**Current runner:** The runner matches the matrix more literally:

| Area | Behavior |
|------|-----------|
| **HOURS** | 3 providers (Footlite / Altitude / Iron Wolf when present). |
| **TIME hours** | Prefers **Altitude** when that row has hours (proposal). |
| **TIME program** | Provider **without** hours + program `schedule_start_time` (often not Altitude, because Altitude always hits the hours branch — `matrix_note` explains). |
| **PHONE** | 3 named providers. |
| **LOCATION** | **Two** matrix targets: Iron Wolf + Altitude. |
| **WEBSITE** | **Two** matrix targets: Bridge City Combat, then Altitude. Bridge with empty `website` → **`branch_present_not_auditable`**; Altitude renders. |
| **COST** | 2 rows (Altitude Open Jump + Iron Wolf Junior Golf). |
| **AGE** | Up to **3** providers; prefers Flips then Universal…Sonics when **`try_tier1`-eligible** (active program with ages). In the stock seed, **Flips has no age-bearing programs** and **Universal’s programs are all `is_active=False`**, so the runner correctly walks to other providers (same as production `try_tier1`). |
| **DATE / NEXT** | Up to **two** providers with future live `Event.provider_id` → **four** lines when two exist (`t1-DATE`/`t1-NEXT` + `t1-DATE-p2`/`t1-NEXT-p2`). |
| **OPEN_NOW** | Up to **four** providers with parseable hours, **Altitude first**. |

**Proposal `~25–40`:** Clarified in `docs/phase-6-1-2-audit-runner-proposal.md` as an **upper bound** over rich seeds (extra OPEN_NOW rows, second DATE provider, etc.). On the migrated local seed used for this capture: **24 auditable + 1 not-auditable = 25** Tier 1 matrix outcomes, aligned with the matrix + explicit WEBSITE skip.

**Tier 3 in dry-run:** Still **no `route()`** (would burn LLM tokens). Enumeration is **full `user_query` + tags**; `assistant_text` only after `--execute`.

---

## Full `--dry-run` transcript (runner output)

```
=== Voice audit runner — dry run ===
git_sha: 7aa49a08734616e9ea12046f7887139ce2c6d11d

--- Tier 1 matrix (auditable) — full enumeration ---
--- t1-HOURS-01 ---
  intent_or_mode: HOURS_LOOKUP
  user_query: What are Footlite School of Dance hours on Monday?
  matrix_note: provider=Footlite School of Dance
  assistant_text: Footlite School of Dance is open Mon–Thu 3–7pm during dance year.

--- t1-HOURS-02 ---
  intent_or_mode: HOURS_LOOKUP
  user_query: What are Altitude Trampoline Park — Lake Havasu City hours on Monday?
  matrix_note: provider=Altitude Trampoline Park — Lake Havasu City
  assistant_text: Altitude Trampoline Park's open 11am–7pm on Monday.

--- t1-HOURS-03 ---
  intent_or_mode: HOURS_LOOKUP
  user_query: What are Iron Wolf Golf & Country Club hours on Monday?
  matrix_note: provider=Iron Wolf Golf & Country Club
  assistant_text: Iron Wolf Golf & Country Club's open 9am–9pm on Monday.

--- t1-TIME-hours ---
  intent_or_mode: TIME_LOOKUP
  user_query: What time does Altitude Trampoline Park — Lake Havasu City open on Tuesday?
  matrix_note: render path: HOURS_LOOKUP via TIME_LOOKUP; matrix prefers Altitude, actual provider='Altitude Trampoline Park — Lake Havasu City'
  assistant_text: Altitude Trampoline Park's open 10am–7pm on Tuesday.

--- t1-TIME-program ---
  intent_or_mode: TIME_LOOKUP
  user_query: What time is Mountain Bike Practice — Sara Park (Sunday) at Lake Havasu Mountain Bike Club — schedule window
  matrix_note: render path: TIME_LOOKUP program window (provider without hours + schedule_start_time — may differ from proposal's Altitude example when Altitude has hours and always hits the hours branch)
  assistant_text: Mountain Bike Practice — Sara Park (Sunday) starts at 09:00–10:30.

--- t1-PHONE-01 ---
  intent_or_mode: PHONE_LOOKUP
  user_query: What is the phone number for Footlite School of Dance?
  matrix_note: provider=Footlite School of Dance
  assistant_text: Footlite School of Dance: (928) 854-4328.

--- t1-PHONE-02 ---
  intent_or_mode: PHONE_LOOKUP
  user_query: What is the phone number for Bridge City Combat?
  matrix_note: provider=Bridge City Combat
  assistant_text: Bridge City Combat: (928) 716-3009.

--- t1-PHONE-03 ---
  intent_or_mode: PHONE_LOOKUP
  user_query: What is the phone number for Flips for Fun Gymnastics?
  matrix_note: provider=Flips for Fun Gymnastics
  assistant_text: Flips for Fun Gymnastics: (928) 566-8862.

--- t1-LOCATION-iron-wolf ---
  intent_or_mode: LOCATION_LOOKUP
  user_query: Where is Iron Wolf Golf & Country Club located?
  matrix_note: matrix entity=Iron Wolf Golf & Country Club
  assistant_text: Iron Wolf Golf & Country Club is at 3275 N. Latrobe Dr, Lake Havasu City, AZ 86404.

--- t1-LOCATION-altitude ---
  intent_or_mode: LOCATION_LOOKUP
  user_query: Where is Altitude Trampoline Park — Lake Havasu City located?
  matrix_note: matrix entity=Altitude Trampoline Park — Lake Havasu City
  assistant_text: Altitude Trampoline Park — Lake Havasu City is at 5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404.

--- t1-WEBSITE-altitude ---
  intent_or_mode: WEBSITE_LOOKUP
  user_query: What is the website for Altitude Trampoline Park — Lake Havasu City?
  matrix_note: matrix entity=Altitude Trampoline Park — Lake Havasu City
  assistant_text: Altitude Trampoline Park — Lake Havasu City: altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/

--- t1-COST-01 ---
  intent_or_mode: COST_LOOKUP
  user_query: How much is Open Jump at Altitude?
  assistant_text: Open Jump — 90 Minutes is $19.00.

--- t1-COST-02 ---
  intent_or_mode: COST_LOOKUP
  user_query: How much is the Junior Golf Clinic at Iron Wolf?
  assistant_text: Junior Golf Clinic — Session 1 is $250.00.

--- t1-AGE-iron-wolf-golf-country-club ---
  intent_or_mode: AGE_LOOKUP
  user_query: What ages is Junior Golf Clinic — Session 1 at Iron Wolf Golf & Country Club?
  matrix_note: provider=Iron Wolf Golf & Country Club
  assistant_text: Junior Golf Clinic — Session 1 is for ages 7–17.

--- t1-AGE-lake-havasu-city-aquatic-center ---
  intent_or_mode: AGE_LOOKUP
  user_query: What ages is Aqua Aerobics / Water Fitness at Lake Havasu City Aquatic Center?
  matrix_note: provider=Lake Havasu City Aquatic Center
  assistant_text: Aqua Aerobics / Water Fitness is for ages 18+.

--- t1-AGE-lake-havasu-city-bmx ---
  intent_or_mode: AGE_LOOKUP
  user_query: What ages is BMX Racing — Race Night at Lake Havasu City BMX?
  matrix_note: provider=Lake Havasu City BMX
  assistant_text: BMX Racing — Race Night is for ages 5+.

--- t1-DATE ---
  intent_or_mode: DATE_LOOKUP
  user_query: When is the next event for Lake Havasu City BMX?
  matrix_note: provider=Lake Havasu City BMX slug=lake-havasu-city-bmx
  assistant_text: The next Local BMX Race is Tuesday, April 21, 2026.

--- t1-NEXT ---
  intent_or_mode: NEXT_OCCURRENCE
  user_query: When is the next event for Lake Havasu City BMX?
  matrix_note: provider=Lake Havasu City BMX slug=lake-havasu-city-bmx
  assistant_text: The next Local BMX Race is Tuesday, April 21, 2026.

--- t1-DATE-p2 ---
  intent_or_mode: DATE_LOOKUP
  user_query: When is the next event for Universal Gymnastics and All Star Cheer — Sonics?
  matrix_note: provider=Universal Gymnastics and All Star Cheer — Sonics slug=universal-gymnastics-and-all-star-cheer-sonics
  assistant_text: The next Sonics All Star Cheer 2026–2027 Season — Team Placements is Sunday, May 17, 2026.

--- t1-NEXT-p2 ---
  intent_or_mode: NEXT_OCCURRENCE
  user_query: When is the next event for Universal Gymnastics and All Star Cheer — Sonics?
  matrix_note: provider=Universal Gymnastics and All Star Cheer — Sonics slug=universal-gymnastics-and-all-star-cheer-sonics
  assistant_text: The next Sonics All Star Cheer 2026–2027 Season — Team Placements is Sunday, May 17, 2026.

--- t1-OPEN_NOW-altitude-trampoline-park-lake-havasu-city ---
  intent_or_mode: OPEN_NOW
  user_query: Is Altitude Trampoline Park — Lake Havasu City open right now?
  matrix_note: provider=Altitude Trampoline Park — Lake Havasu City
  assistant_text: They're open right now — hours say they're in window for today.

--- t1-OPEN_NOW-havasu-lanes ---
  intent_or_mode: OPEN_NOW
  user_query: Is Havasu Lanes open right now?
  matrix_note: provider=Havasu Lanes
  assistant_text: They're open right now — hours say they're in window for today.

--- t1-OPEN_NOW-havasu-shao-lin-kempo ---
  intent_or_mode: OPEN_NOW
  user_query: Is Havasu Shao-Lin Kempo open right now?
  matrix_note: provider=Havasu Shao-Lin Kempo
  assistant_text: They're open right now — hours say they're in window for today.

--- t1-OPEN_NOW-iron-wolf-golf-country-club ---
  intent_or_mode: OPEN_NOW
  user_query: Is Iron Wolf Golf & Country Club open right now?
  matrix_note: provider=Iron Wolf Golf & Country Club
  assistant_text: They're open right now — hours say they're in window for today.

Tier 1 auditable count: 24

--- Tier 1 matrix (branch_present_not_auditable) ---
  t1-WEBSITE-bridge-city-combat [WEBSITE_LOOKUP]
    branch_present_not_auditable — branch present, not auditable with current seed — possible dead code or data gap.
    detail: matrix target 'Bridge City Combat': empty website (seed-dependent)
Tier 1 not-auditable rows: 1

--- Tier 3 generated (unified_router.route) — queries only in dry-run ---
  Note: dry-run does not call route() (would invoke Tier 2/3 LLMs). assistant_text is omitted here; use --execute to materialize Tier 3 responses.
--- t3-01 ---
  tags: [happy_path]
  user_query: What's happening this weekend?

--- t3-02 ---
  tags: [happy_path]
  user_query: What time does the BMX track open Saturday?

--- t3-03 ---
  tags: [happy_path]
  user_query: When is the farmers market on Thursday?

--- t3-04 ---
  tags: [happy_path]
  user_query: Is Altitude open late on Friday?

--- t3-05 ---
  tags: [happy_path]
  user_query: Kids gymnastics programs near me

--- t3-06 ---
  tags: [happy_path]
  user_query: Tell me about Bridge City Combat

--- t3-07 ---
  tags: [happy_path]
  user_query: Events at Sara Park

--- t3-08 ---
  tags: [happy_path]
  user_query: BMX race times

--- t3-09 ---
  tags: [happy_path]
  user_query: Swimming lessons for beginners

--- t3-10 ---
  tags: [happy_path]
  user_query: Dance classes for a 7-year-old

--- t3-11 ---
  tags: [gap]
  user_query: My son wants to ride mountain bikes. Any classes available?

--- t3-12 ---
  tags: [gap]
  user_query: Is there a curling club in Havasu?

--- t3-13 ---
  tags: [gap]
  user_query: When is the hot air balloon festival?

--- t3-14 ---
  tags: [gap]
  user_query: Who teaches violin to adults?

--- t3-15 ---
  tags: [gap]
  user_query: Underground techno tonight?

--- t3-16 ---
  tags: [multi_entity,disambiguation]
  user_query: Sonics or Flips for fun for a shy 5-year-old?

--- t3-17 ---
  tags: [multi_entity,disambiguation]
  user_query: Bridge City Combat vs Footlite School of Dance for Saturday morning kids classes?

--- t3-18 ---
  tags: [multi_entity,disambiguation]
  user_query: Which martial arts gym has Saturday morning kids classes?

--- t3-19 ---
  tags: [multi_entity,explicit_rec_query]
  user_query: Best place for toddler tumbling

--- t3-20 ---
  tags: [multi_entity,disambiguation]
  user_query: Compare Footlite and Ballet Havasu for preschool dance

--- t3-21 ---
  tags: [out_of_scope]
  user_query: What's the best sushi in town?

--- t3-22 ---
  tags: [out_of_scope]
  user_query: Are home prices going down in Havasu?

--- t3-23 ---
  tags: [out_of_scope]
  user_query: Weather this weekend?

--- t3-24 ---
  tags: [explicit_rec_query]
  user_query: What should I do Saturday?

--- t3-25 ---
  tags: [explicit_rec_query]
  user_query: Pick one thing to do with kids this weekend

Tier 3 count: 25

--- Reference (frozen §8 goldens) — full enumeration ---
--- ref-8.5-low ---
  intent_or_mode: §8.5 low-stakes contested-state
  user_query: (contested hours — no live user query)
  assistant_text: Opens at 7 — someone recently reported it moved from 6. Let me know if that's wrong.
  tags: ['contested_state']

--- ref-8.5-high ---
  intent_or_mode: §8.5 high-stakes contested-state
  user_query: (contested phone — no live user query)
  assistant_text: My info says the phone is (928) 555-0100. Someone recently reported a different number — I'll get it confirmed before updating.
  tags: ['contested_state']

--- ref-8.8-intake ---
  intent_or_mode: §8.8 intake
  user_query: there's a car show at the channel saturday
  assistant_text: nice — got a time, and who's running it?
  tags: ['intake']

--- ref-8.8-commit ---
  intent_or_mode: §8.8 commit
  user_query: Casey I just submitted a car show event
  assistant_text: got it, added to the pile. Casey reviews new events before they go live — usually within a day or two.
  tags: ['intake']

--- ref-8.9-correction-low ---
  intent_or_mode: §8.9 correction low-stakes
  user_query: (user corrected a small catalog fact)
  assistant_text: got it, noted — I'll flag it and watch for more confirmations.
  tags: ['correction']

--- ref-8.9-high ---
  intent_or_mode: §8.9 correction high-stakes
  user_query: Altitude's phone isn't (928) 555-0100 anymore — it's a different number now
  assistant_text: got it — that one needs to go through review before I update it. Thanks for the heads up.
  tags: ['correction']

Reference count: 6

--- Cost estimate (Haiku 4.5 @ $1/M input, $5/M output; order-of-magnitude) ---
Assumes: 55 voice-audit calls (~900+280 tok/call) + 25 Tier 3 generations at worst-case (~7500+220 tok each).
Estimated total USD (upper bound): $0.3415
Estimated total tokens (in+out): 257900
Hard ceiling configured: $2.00 (runner aborts --execute if estimate exceeds)

=== End dry run ===
```

---

## Counts (this seed)

| Bucket | Count |
|--------|------:|
| Tier 1 auditable | 24 |
| Tier 1 not auditable | 1 |
| Tier 3 (queries only in dry-run) | 25 |
| Reference | 6 |
| **Voice-audit payloads on `--execute`** | **55** |

---

## Regenerate

```powershell
.\.venv\Scripts\python.exe -c "import subprocess, pathlib; r=subprocess.run(['.venv/Scripts/python.exe','scripts/run_voice_audit.py','--dry-run'], capture_output=True, text=True, encoding='utf-8'); pathlib.Path('docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt').write_text(r.stdout, encoding='utf-8')"
```

Or: `.\.venv\Scripts\python.exe scripts/run_voice_audit.py --dry-run` (use `PYTHONIOENCODING=utf-8` on Windows if the console mangles punctuation).
