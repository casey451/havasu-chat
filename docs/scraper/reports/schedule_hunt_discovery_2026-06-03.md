# Schedule Hunt — discovery audit + directory fallback (2026-06-03, evening)

Trigger: Casey's spot check on **Bridge City Combat** — a real MMA gym that the
pipeline missed because its only DB rows are tier2-test fixtures. Root cause:
Phase 1 seeded candidates from the DB alone, and Phase 2 crawled only official
websites. Fix shipped: new **Phase 1b (web discovery audit)** and **Phase 2b
(directory fallback)** in SCHEDULE_HUNT_PLAN.md, plus this first full run of both.

## Headline numbers
- Candidate list grew **44 → 83 venues** (~39 real, verified-current additions).
- **8 venues arrived with complete, ingest-ready weekly schedules** found on
  their own sites that the DB-seeded pass never saw: Havasu CrossFit, Fit Lab
  928, Feelin Good Fitness, Elite Martial Arts, The Study Yoga, Arizona Coast
  Performing Arts (full 2025-26 dance grid), Fabrics Unlimited, Havasu Lanes
  Junior Bowlers. Plus full price sheets for both horseback-riding schools.
- FB capture queue grew 15 → **26**; OpenClaw master list updated live
  (verified: 26 venues). Sweep is running and self-sufficient (run 2 completed
  unsupervised: Planet Fitness + FOS Gym captured; 4 done, 0 flagged).
- Whole categories the DB missed entirely: CrossFit/HIIT studios, gymnastics
  (2 gyms), youth sports leagues (5+), horseback riding (2), swim schools (2),
  yoga (3 more studios), kids art/craft (3), quilting (2), youth theater,
  pickleball, CPR schools.

## Key corrections to existing candidates (directory fallback)
- **Havasu Martial Arts Academy** — current site says appointment-only privates
  + DVDs; the dojos.info group grid is legacy. Do NOT ingest old times.
- **Havasu Stingrays** — full school-year practice grid recovered from
  gomotionapp (it IS fetchable), but it ended 6/2/26; summer = 7–9a at Aquatic
  Center. Dues $60–120/mo.
- **Swivel & Sway** — Intro to Salsa Tue 5:30p, $10/class (Yelp Feb-26 + FB).
- **Altitude** — full hours + price card from golakehavasu.com (their own site
  is JS-locked).
- **Cycle Therapy** — confirmed NO group rides exist; deprioritized.
- **Planet Fitness** — hours captured; PE@PF times remain JS-only (FB sweep).
- **studio 2959** — still unverified for 2026; site frozen at Oct-2024 bootcamp.

## Stale-data traps (now codified in the plan)
dojos.info legacy grids; mohavelocal hours lag; unclaimed WellnessLiving stubs;
dated team schedules (check end dates); 2022 event listings at old venues.
Best local directory by far: **golakehavasu.com**.

## Machine-readable schedule portals worth crawling next pass
iClassPro (Universal Sonics), DanceStudio-Pro (Ballet Havasu), Mindbody (Eight
Lotus), Vagaro (The Study), Wild Apricot (Havasu Stitchers), Gymdesk (Fiore's,
Iron Age), GymMaster (FOS), gomotionapp (Stingrays), RxGym (Havasu CrossFit),
SportsEngine (Chiefs), Driftwood Acres booking. These often render statically
even when the marketing site doesn't.

## Needs verification (flagged in CSV)
Fiore's Endorphin Factory (June week shows all-closed — pause or closing?),
Next Generation MMA (directory ghosts only), Arevalo Academy grid (page from
2018), Titan Gym schedule image (Feb 2025), Sew What, Havasu Pilates Studio
(no address), Trinity MMA (JS site, no address), Footlite address conflict,
LH Black Belt Academy address conflict, Kids Activities Studio (possible test
row), studio 2959.

## Confirmed non-existent / closed / out of scope
No climbing gym (one approved for 3485 Maricopa — recheck late 2026); Magnum
Sport Center never opened; Four Dragons Martial Arts closed; no Kumon/Sylvan/
Mathnasium; no AYSO (Lions FC covers soccer); no standalone cooking school
(Parks & Rec only); no barre studio; uCreate Ceramics is Fort Mohave.

## For Casey / Jobs-page build
1. DB hygiene: add real entities for the ~39 discoveries; audit
   `source LIKE '%test%'` + hash-suffixed names for shadowing (Bridge City
   Combat had 2 such rows); remove or quarantine fixtures.
2. The discovery audit should become a recurring job type (quarterly-ish), not
   a one-off — new studios open constantly (Snap opened Oct 2024, The Dance
   Center Jan 2025, Iron Wolf academy pending).
3. Capture review of the growing FB inbox will need its own daily cadence once
   the 26-venue sweep finishes (~8 more hours at current pacing).
