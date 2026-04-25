# Phase 8.8.5 — HALT 2.5 Catalog Survey Report (Expanded Lexicon)

Date: 2026-04-25  
Scope: Re-run production catalog survey with lexicon Classes 5–7 added; thresholds unchanged.

---

## Updated lexicon additions (Classes 5–7)

### Class 5 — Business duration / longevity

- `\b\d+\s*(?:years|yrs)\b`
- `\bsince\s+\d{4}\b`
- `\bestablished\s+\d{4}\b`
- `\bfounded\s+\d{4}\b`

### Class 6 — Organization type

- `\bnonprofit\b`
- `\b501\(c\)\(?3\)?\b`
- `\b501c3\b`
- `\bfemale[- ]owned\b`
- `\bfamily[- ]owned\b`
- `\bveteran[- ]owned\b`
- `\bcooperative\b`

### Class 7 — Audience / enrollment

- `\ball\s+(?:levels|ages|skill levels|abilities)\b`
- `\bages?\s+\d+(?:\s*[-–]\s*\d+)?\b`
- `\bopen\s+enrollment\b`
- `\b(?:esa|empowerment scholarship)\s+accepted\b`
- `\bmembership\s+(?:required|optional|fees?)\b`
- `\bno\s+(?:fees|membership)\b`
- `\bfirst\s+(?:class|session|lesson)\s+free\b`
- `\bloaner\s+(?:bikes?|equipment|gear)\b`

### Dedup map additions / behavior

- No new synonym-folding conflicts introduced in Classes 5–7.
- Existing canonical dedup behavior remains:
  - match pattern -> canonical concept key -> count distinct canonical keys only.

---

## Verbatim survey output

```text
=== DESCRIPTION RICHNESS CATALOG SURVEY (EXPANDED LEXICON) ===

Providers:
- total: 24
- sparse: 19 (79.17%)
- rich: 5 (20.83%)

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
3. Bless This Nest LHC
   description: 'owner: Amber Kramer Lohrman'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=4, fact_token_count=0)
4. Bridge City Combat
   description: 'In-person booking only. Founder: Christian Beyers.

instagram: instagram.com/bridgecitycombat'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=10, fact_token_count=0)
5. Flips for Fun Gymnastics
   description: 'Classes 6 months to adult. Recreational and competitive.

organization: Non-profit'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=10, fact_token_count=0)

Provider rich spot-check (up to 5):
1. Aqua Beginnings
   description: 'Max 3 swimmers per group. Free initial assessment.

coach: Coach Rick (Swim America® certified)'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=14, fact_token_count=6)
2. Arizona Coast Performing Arts (ACPA)
   description: '31 years. Female-owned. Max 16 students/class. Full Tue–Thu schedule on website.

season: August–May'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=16, fact_token_count=4)
3. Ballet Havasu
   description: 'First class FREE. Open enrollment. ESA accepted.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=7, fact_token_count=4)
4. Lake Havasu City Aquatic Center
   description: 'Indoor facility. Olympic pool, wave pool, water slide, hot tubs, splash pad.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=12, fact_token_count=8)
5. Lake Havasu Mountain Bike Club
   description: 'NO membership fees. Loaner bikes for first few practices. Race season Jan–May.

organization: 501(c)3 nonprofit'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=18, fact_token_count=5)

Program sparse spot-check (up to 5):
1. Adult Gi Jiu-Jitsu
   description: 'Adult gi Brazilian Jiu-Jitsu. All levels.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=6, fact_token_count=1)
2. Adult NoGi Jiu-Jitsu
   description: 'Schedule: Also Fri 5:15–6:15pm (Leg Locks focus).

Adult no-gi Jiu-Jitsu. All levels.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=15, fact_token_count=1)
3. BMX Practice — Tuesday
   description: 'Schedule: Striders ride free on practice nights.

Open practice night. All skill levels welcome.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=14, fact_token_count=2)
4. BMX Training — Wednesday
   description: 'Coached training session focused on skills development.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=7, fact_token_count=0)
5. Littles Gi Jiu-Jitsu (Ages 3–6)
   description: 'Gi Jiu-Jitsu for the youngest students ages 3–6.'
   classification: sparse
   sanity: check if this feels appropriately sparse (word_count=9, fact_token_count=1)

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
   sanity: check if this feels appropriately rich (word_count=46, fact_token_count=6)
3. Junior Golf Clinic — Session 1
   description: 'Schedule: 2-week session starting June 30, 2026

Small-group junior golf clinic for ages 7–17. Focused instruction, small class sizes. Includes clubs and swag bag. Limited availability. Register via golf shop phone or email.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=34, fact_token_count=2)
4. Junior Golf Clinic — Session 2
   description: 'Schedule: 2-week session starting July 14, 2026

Small-group junior golf clinic for ages 7–17. Focused instruction, small class sizes. Includes clubs and swag bag. Limited availability. Register via golf shop phone or email.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=34, fact_token_count=2)
5. Lap Swim
   description: 'Schedule: See lhcaz.gov/parks-recreation/open-swim-schedule for monthly schedule.

6-lane 25-meter heated indoor pool. Kickboards and fins available first-come, first-served.'
   classification: rich
   sanity: check if this feels appropriately rich (word_count=21, fact_token_count=4)
```

---

## Calibration status

- Provider sparse improved from 87.5% -> 79.17%, but remains outside guardrail (`>70%`).
- Program distribution remains within acceptable range.

