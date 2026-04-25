# Phase 8.8.5 — HALT 2 Catalog Survey Report

Date: 2026-04-25  
Scope: Production catalog distribution check for description richness classifier

Command context:

- Survey executed via Railway production context using `railway run ... python -c "runpy.run_path(...)"`.
- Temporary survey script was deleted after run.

---

## Verbatim survey output

```text
=== DESCRIPTION RICHNESS CATALOG SURVEY ===

Providers:
- total: 24
- sparse: 21 (87.5%)
- rich: 3 (12.5%)

Programs:
- total: 28
- sparse: 11 (39.29%)
- rich: 17 (60.71%)

CALIBRATION FLAG (Providers): sparse percentage outside [20, 70].

Provider sparse spot-check (up to 5):
1. Altitude Trampoline Park — Lake Havasu City
   description: 'Children 12 & under must have adult present.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=7, fact_token_count=0)
2. Arevalo Academy
   description: '⚠️ Schedule data from 2018 — VERIFY before going live.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=8, fact_token_count=0)
3. Arizona Coast Performing Arts (ACPA)
   description: '31 years. Female-owned. Max 16 students/class. Full Tue–Thu schedule on website.

season: August–May'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=16, fact_token_count=2)
4. Ballet Havasu
   description: 'First class FREE. Open enrollment. ESA accepted.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=7, fact_token_count=1)
5. Bless This Nest LHC
   description: 'owner: Amber Kramer Lohrman'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=4, fact_token_count=0)

Provider rich spot-check (up to 5):
1. Aqua Beginnings
   description: 'Max 3 swimmers per group. Free initial assessment.

coach: Coach Rick (Swim America® certified)'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=14, fact_token_count=6)
2. Lake Havasu City Aquatic Center
   description: 'Indoor facility. Olympic pool, wave pool, water slide, hot tubs, splash pad.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=12, fact_token_count=8)
3. Lake Havasu Mountain Bike Club
   description: 'NO membership fees. Loaner bikes for first few practices. Race season Jan–May.

organization: 501(c)3 nonprofit'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=18, fact_token_count=0)

Program sparse spot-check (up to 5):
1. Adult Gi Jiu-Jitsu
   description: 'Adult gi Brazilian Jiu-Jitsu. All levels.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=6, fact_token_count=0)
2. Adult NoGi Jiu-Jitsu
   description: 'Schedule: Also Fri 5:15–6:15pm (Leg Locks focus).

Adult no-gi Jiu-Jitsu. All levels.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=15, fact_token_count=0)
3. BMX Practice — Tuesday
   description: 'Schedule: Striders ride free on practice nights.

Open practice night. All skill levels welcome.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=14, fact_token_count=1)
4. BMX Training — Wednesday
   description: 'Coached training session focused on skills development.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=7, fact_token_count=0)
5. Littles Gi Jiu-Jitsu (Ages 3–6)
   description: 'Gi Jiu-Jitsu for the youngest students ages 3–6.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=9, fact_token_count=0)

Program rich spot-check (up to 5):
1. Aqua Aerobics / Water Fitness
   description: 'Schedule: Multiple class types. See monthly schedule at lhcaz.gov.

Year-round adult water fitness. Classes include Aqua Aerobics, Ai-Chi, Arthritis Exercise, Cardio Challenge, and Aqua Motion.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=26, fact_token_count=7)
2. BMX Racing — Race Night
   description: 'Schedule: Registration 6–7pm. Racing starts 7pm. Oct–Jun schedule.

USA BMX-sanctioned race night. All ages and skill levels. Quarter-mile dirt track with paved start hill. Spectators free. Loaner bikes and helmets available for first-timers. USA BMX membership required ($80/yr). 30-day trial memberships also available.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=46, fact_token_count=3)
3. Junior Golf Clinic — Session 1
   description: 'Schedule: 2-week session starting June 30, 2026

Small-group junior golf clinic for ages 7–17. Focused instruction, small class sizes. Includes clubs and swag bag. Limited availability. Register via golf shop phone or email.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=34, fact_token_count=1)
4. Junior Golf Clinic — Session 2
   description: 'Schedule: 2-week session starting July 14, 2026

Small-group junior golf clinic for ages 7–17. Focused instruction, small class sizes. Includes clubs and swag bag. Limited availability. Register via golf shop phone or email.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=34, fact_token_count=1)
5. Lap Swim
   description: 'Schedule: See lhcaz.gov/parks-recreation/open-swim-schedule for monthly schedule.

6-lane 25-meter heated indoor pool. Kickboards and fins available first-come, first-served.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=21, fact_token_count=4)
```

---

## Calibration interpretation

- Provider sparse = **87.5%** -> outside guardrail (`>70%`) -> likely miscalibrated.
- Program distribution is within guardrail.

## Candidate adjustment directions (not yet applied)

1. Lower word threshold to `>=16` (keep fact threshold `>=4`).
2. Keep `18/4` and broaden fact concepts to include stronger provider metadata markers.
3. Hybrid tuning: `>=16 OR >=4` plus current lexicon.
