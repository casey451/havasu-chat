# Schedule Hunt — deep-crawl verification report (2026-06-03, second pass)

All 30 candidate websites re-crawled with 4 parallel agents + rendered (in-browser)
fetches for the JS-only holdouts. CSV fully updated. Headlines below; full detail
per venue is in `schedule_hunt_candidates.csv` notes.

## NEW complete schedules captured this pass

- **Amalaya Yoga — FULL weekly grid** (rendered the Momence JS widget — the gap
  from pass 1 is closed; Amalaya removed from the FB queue, now 14 venues):
  - Mon: Inferno Hot Pilates 6–7a · Hot Fusion 8:30–9:30a · Amalaya Hot Yoga 4–5p ·
    Inferno 5:30–6:30p · Non-Heated Mat Pilates 7–8p ($20)
  - Tue: Amalaya Hot Yoga 6–7a · Sculpt 8:30–9:30a · Gentle Stretch 10–11a ($25) ·
    Inferno 4–5p · Amalaya Hot Yoga 5:30–6:30p · Inferno 7–8p
  - Wed: Inferno 6–7a · Hot Fusion 8:30–9:30a · Sculpt 4–5p · Inferno 5:30–6:30p ·
    Hot Fusion 7–8p
  - Thu: Sculpt 6–7a · Inferno 8:30–9:30a · Gentle Stretch 10–11a ($25) · Inferno
    4–5p · Beginner's Hot Yoga 5:30–6:30p ($5) · Inferno 7–8p
  - Fri: Amalaya Hot Yoga 6–7a · Hot Fusion 8:30–9:30a · Hot Mat Pilates 4–5p & 6–7p
  - Sat: Amalaya Hot Yoga 8:30–9:30a · Inferno 10–11a — Sun: Sunday Reset 11a–12p ($25)
  - Drop-in $30 unless noted. Ready to model as Offerings + Schedules.
- **LHC Aquatic Center — both June 2026 PDFs extracted** — complete exercise-class
  grid with instructors (M/W/F + T/Th mornings), lap & open swim times, swim league,
  Jr Lifeguard. Pricing correction: punch pass is **$80**/20 (PDF rev 5/29/26
  supersedes the web page's $78).
- **Beyond Dance — both schedule PDFs extracted**: kids/teens 2025–26 season
  (M–Th, 3:30–8p time blocks, $45 enroll + $35–60/mo) and adult ballroom (Foxtrot
  12p, Single-Time Swing 4p, Mon & Fri, $15/class or $80×8 — PDF dated March, may
  be stale). Caveat: text extraction loses the exact class↔day grid mapping; the
  FB sweep or a visual PDF render can settle it.
- **Sportsman's Club — match calendar IS published** (pass 1 missed
  /pistol_range.html + /rifle_range.html): SASS 2nd & 4th Sat 7a–2p; Steel
  Challenge 2nd Sun; USPSA 3rd Sat + following Sun 5a–4p; smallbore benchrest
  1st & 3rd Sat 9–11a; high-power 1st/2nd/4th Sun 9–11a. Public range Wed/Sat/Sun
  (summer 7–11a), trap/skeet $6/$9 per round.
- **Library (Trumba calendar, rendered)**: Preschool Playtime Storytime Wed+Thu
  9:30–11:30a; SR Preschool Storytime Wed 10:30–11:30a; teen Summer Reading events;
  Summer Reading 2026 through 7/11. All free.
- **Iron Age Gym (Gymdesk portal)**: no group classes, but Day Care M–Sa 7–9a &
  9–11a + full membership pricing ($75/mo).

## Corrections to pass-1 data

- **WACKO Kayak is NOT closed** — the homepage is a Wix JS shell (hence the "dead"
  verdict) but inner pages render: full tour list with prices (Topock $70, Castle
  Rock $50, Full Moon $50, rentals $45–100), phone-only booking. Casey flag resolved.
- **Lake Havasu Bike & Fitness is NOT js-only** — site renders; simply has no
  rides/events (rentals only). Stays in FB queue for group rides.
- **Tap Room Jiu Jitsu grid updated**: Littles now 4:30p (no Peewee class), Fri MMA
  6:15–7:15p, NEW Mon Women's-Only NoGi 9–10a; $109/mo + $39.99 signup.
- **Iron Wolf verified current** through June 2026 + dated concert: Headgames &
  Illusion, Sat Jun 6, 6–11p.

## Confirmed unchanged (no schedule exists)

Anytime Fitness (no times; FB queue), Chris Padgett, Heart & Sole, Athletic
Advantage, Soul Lifting (classes still not launched), Pilates of LH ($70 private),
FOS Gym (pricing now visible via GymMaster; no classes), Cycle Therapy, Scuba
Training (on-demand), Grand Piano, Hava Math, MJ's Dog Training (still suspended),
Bridgewater Links, LH Golf Club (lessons $75; calendar dead since 2022), Tennis
Assoc (genuinely no clock times on site — FB queue), studio 2959 (still 2024-dated),
Senior Center (several activities still without published times), Yacht Club
(+ NEW Mon 12p line dance lessons).

## Still JS-locked (→ Facebook sweep, queue now 14 venues)

Planet Fitness, Altitude, Stingrays (gomotion), PetSmart (booking app), MCC
(Ellucian Journey portal — static catalog is Spring/Summer 2025, stale).

## One-off dated events found

- Stronger Together senior-safety seminar — Tue **6/9/26** 12–2p, Senior Center, free
- Headgames & Illusion concert — Sat **6/6/26** 6–11p, Iron Wolf Pavilion
- Free Family Swim — Sun **6/28/26** 12–4p, Aquatic Center (first 400)

## Flags for Casey (carried/updated)

- ~~WACKO dead~~ → resolved, business is active (phone bookings only).
- Align and Define Pilates: still no website/FB found at all.
- "Kids Activities Studio", "River Rat Yacht Club", "RockerBens": still need
  research or removal from DB.
- studio 2959: schedule currency unverifiable from site — someone should text
  928-733-8110.
- Iron Age Gym wk of 6/1 marked closed (equipment delivery) — temporary.
