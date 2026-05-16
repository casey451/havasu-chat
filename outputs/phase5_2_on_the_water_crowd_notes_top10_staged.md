# Phase 5.2 — On the Water — `crowd_notes` top-10 staged

> Mirrors `outputs/phase5_1_crowd_notes_top17_staged.md` shape. Closes
> Phase 5.2 acceptance gate item 4 ("Top-10 marinas + ramps have
> `crowd_notes`"). Notes use the locked Phase 5.1 JSON shape:
> ``{"short": str, "long"?: str}``. Phase 6 consumes the absence-of-long
> signal (list-blurb vs profile-section).
>
> Top-10 picks: the runbook §6 says "marinas + ramps" but LHC strictly
> only has 5 marinas + 1 ferry + 1 fishing pier in our DB (7 total).
> Expanded to "top-10 highest-traffic on-the-water venues" by adding
> the 4 top-reviewed rentals — these are the highest-impact entries
> for boat-mode UI users.
>
> Drafted from `google_review_snippets` cached during enrichment (real
> reviewer language summarized into operator-curated notes).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.2 session
> (2026-05-15) post-`e68e424`.

---

## §1 The 10 entries

| # | entity_id | name | reviews | rating | type |
|---|---|---|---|---|---|
| 1 | `99028be4` | Nautical Watersports | 541 | 4.8 | rental |
| 2 | `7b2cc749` | Above Water Rentals | 464 | 5.0 | rental |
| 3 | `3eeb1137` | Havasu Landing Ferry Boat Terminal | 312 | 4.6 | ferry/ramp |
| 4 | `9118ee9d` | Wet Monkey Powersport Rentals | 302 | 3.7 | rental |
| 5 | `8ce77957` | Lake Havasu Marina | 293 | 4.6 | marina |
| 6 | `1016c727` | Paradise Wild Wave Boat Rentals | 247 | 4.2 | rental |
| 7 | `b5b50d10` | Lake Havasu Jet Ski Rentals | 247 | 5.0 | rental |
| 8 | `308417e2` | Beach Shack Rentals | 221 | 3.8 | rental |
| 9 | `1f64b259` | Arizona WaterSports Rentals | 195 | 3.5 | rental |
| 10 | `a63febcb` | Havasu Riviera Marina | 171 | 4.6 | marina |

---

## §2 Drafts (operator edits in `outputs/apply_on_the_water_crowd_notes_top10.py`)

### 1. Nautical Watersports — `99028be4`

**short:**
"Top-rated rental fleet on the lake — pontoons, jet skis, Seadoos with knowledgeable staff."

**long:**
"Lake Havasu's highest-volume rental operation (540+ reviews, 4.8★). Pontoons, jet skis, and Seadoos run clean and well-maintained. Crew (Nate, Nathan, Noah) get singled out repeatedly for patience with first-time renters. Dog-friendly. Located on McCulloch Blvd at the marina end."

### 2. Above Water Rentals — `7b2cc749`

**short:**
"Five-star boat and jet ski rentals — quick text-back booking, premium boats, easy pickup at the bridge."

**long:**
"464 reviews and still a perfect 5.0★ — rare on the lake. Quick text-back booking (often <5min), 'nicest boat we've ever rented' is a recurring line. Staff (James, Matt, Parker) make first-time renters comfortable; pickup at the end of the bridge. Pontoons, jet skis, tubes. Located on N Lake Havasu Ave."

### 3. Havasu Landing Ferry Boat Terminal — `3eeb1137`

**short:**
"The AZ↔CA ferry across to Havasu Landing — air-conditioned terminal, bring cash."

**long:**
"The only ferry service across Lake Havasu, running AZ↔CA to Havasu Landing Resort/Casino. Short clean ride, air-conditioned waiting area. **Bring cash** — the ticket machine has been flaky with cards. Copper Canyon boat tours depart from the same terminal and sell out fast on holiday weekends (Labor Day, July 4th). Located on Shoreline Trail at the McCulloch Blvd end."

### 4. Wet Monkey Powersport Rentals — `9118ee9d`

**short:**
"ATVs, Can-Ams, and boats — owner Chris delivers to your Airbnb and stages the trip."

**long:**
"Versatile rental fleet (ATVs, Can-Ams, boats) with hands-on owner Chris who'll deliver to your Airbnb and arrange staging. Guided ATV trips with Jason head out on trails with photo stops and local history along the way. Located on London Bridge Rd near the channel."

### 5. Lake Havasu Marina — `8ce77957`

**short:**
"Flagship marina — 6-lane ramp, slip rentals, fuel pumps. Reserve slips online for event weekends."

**long:**
"Lake Havasu's main public marina: 6-lane concrete ramp at a gentle slope, generous parking, slip rentals (bookable online), and fuel pumps. Day-use fee is **$21** (card at the gatehouse). Long walk back from the parking area to the dock. For holiday/event weekends, book slips ahead and arrive early to beat the ramp lineup. Located at McCulloch Blvd N near London Bridge."

### 6. Paradise Wild Wave Boat Rentals — `1016c727`

**short:**
"Pontoon rentals — friendly office staff (Cheryl, Mary, Toni) and easy ramp launches."

**long:**
"Family-friendly pontoon rental shop. Office on Industrial Blvd; Toni launches from the ramp so you don't deal with the trailer. Cheryl and Theresa handle bookings — patient with first-time renters. Get busy on Saturday mornings; book ahead. 4.2★ rating with consistent praise for staff communication."

### 7. Lake Havasu Jet Ski Rentals — `b5b50d10`

**short:**
"Perfect 5-star jet ski rental — owner Rob calls personally to confirm weather and conditions."

**long:**
"247 reviews, all 5★ — owner Rob runs it personally and pre-calls every customer with weather/wind advisories ('today might be choppy, you may want to reschedule'). Tight safety briefings, takes photos/videos of riders as a bonus. Smaller operation than the big shops, but consistently the highest-rated jet ski rental in town. Located on Acoma Ln."

### 8. Beach Shack Rentals — `308417e2`

**short:**
"Jet skis and kayaks right on the beach — owner Frenchie is laid-back and accommodating."

**long:**
"Right on the beach off McCulloch Blvd — kayaks and jet skis without the trailer hassle. Owner Frenchie is consistently described as personable and flexible (waived late-return fees show up in multiple reviews). Off-season is the time for one-on-one attention."

### 9. Arizona WaterSports Rentals — `1f64b259`

**short:**
"Tripletoons and UTVs — launch at Pirates Cove for the trip down through Topock Gorge."

**long:**
"Tripletoon pontoon rentals and 2/4-seat UTVs, with owners Blaine and Holly. Operating from an office on Kiowa Ave; launch typically happens at Pirates Cove (Park Moabi) or you trailer yourself. The Tripletoon Topock Gorge trip gets highlighted as memorable by reviewers. Owners spend time up front with tips about the lake before you head out."

### 10. Havasu Riviera Marina — `a63febcb`

**short:**
"Newer northern marina — 6-lane ramp, fuel, slips, on-site store, well kept and uncrowded."

**long:**
"The newer marina at the north end (Havasu Riviera Pkwy, 86406). Six-lane concrete ramp, multiple gas pumps, well-laid-out slips, and an on-site store. Reviewers consistently note 'new and gorgeous' and the staff is responsive. Less of a holiday-weekend bottleneck than Lake Havasu Marina, but the trade-off is the longer drive from downtown."

---

## §3 Apply

`outputs/apply_on_the_water_crowd_notes_top10.py` — id-keyed dict
matching the 5.1 pattern. ``--dry-run`` first, idempotent (overwrites
existing crowd_notes JSON on the entity), self-verifies via a count of
on-the-water entities with non-NULL crowd_notes.

---

## §4 Coverage status (post-apply)

| Slug-level coverage | Pre-apply | Post-apply |
|---|---|---|
| on-the-water entities with `crowd_notes` populated | 0 | 10 |
| of which long-form (`{short, long}`) | 0 | 10 |
| of which short-only (`{short}` only) | 0 | 0 |

**Phase 5.2 §6 acceptance gate item 4 ("Top-10 marinas + ramps have
`crowd_notes`") CLEARED post-apply.**

Follow-on (optional, not gate-blocking): short-form `{short}`-only
notes for ranks 11-30 (mirroring the 5.1 batch 2 pattern). The 4 marinas
not in top-10 by reviews (Lake Havasu Yacht Club, Riverside Boat Dock
Sales, Havasu Cove) should arguably get at least short-form notes for
completeness. Operator can extend the apply-script's dict to cover
these in a follow-on or leave for the next refresh.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15) post-`e68e424`. Apply script + commit pending operator
review.*
