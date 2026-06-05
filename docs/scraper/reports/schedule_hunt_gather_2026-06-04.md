# Schedule Hunt — recurring gather run (2026-06-04, scheduled/unattended)

Scheduled Cowork run against `schedule_hunt_entity_ids.csv`. Auto-publish OFF —
all findings queued, as expected. **42 contributions posted (IDs 568–609), 0
duplicates, 0 errors.** Request bodies + results.json in the session outputs
folder (`ingest_2026-06-04/`).

## Environment notes (read first)

- **Chrome extension was NOT connected** (unattended run, no browser). Fell back
  to static fetches + the city PDF. Only schedules readable cleanly without JS
  were ingested; JS-widget venues were skipped, not guessed.
- `web_fetch` is provenance-gated in this session, so each venue URL was surfaced
  via web search first, then fetched. Worked fine.
- Git: `git pull origin main` ran while the checkout was on
  `fix/admin-contribution-proposed-record` (leftover from the prior session), so
  that local branch fast-forwarded to the main tip (`bb0e720`, the merge of its
  own PR — no commits lost, branch now shows "ahead 1" of its remote). Also stale
  `.git/HEAD.lock`/`index.lock` files exist that the sandbox cannot unlink —
  clear from Windows. No commits/pushes/branch changes were made.

## Posted (5 venues, 42 classes — all `queued`)

| IDs | Venue → entity | What | Conf | Source |
|---|---|---|---|---|
| 568–576 | LHC Parks & Rec | 9 Aquatic Center exercise classes from the **June 2026 PDF (rev 5/29/26)**: Motion & Mobility M/W/F 8–9a; Tai Chi M/W 8–9a; Aqua Aerobics M/W/F 9:30–10:30; Arthritis M/W/F 9:15–10:15; Deep Water Fit M/W/F 10:45–11:45; Fit & Flex (land, Rm 155) T/Th 9–10; Aqua Challenge T/Th 9:30–10:30; Warm Water Yoga T/Th 10:15–11:15; Water Wellness T/Th 10:45–11:45. $5/class, $80/20 punch pass | 0.85 | lhcaz.gov DocumentCenter/View/7325 |
| 577 | LHC Parks & Rec | Open Swim (summer) daily noon–4 exc T/Th, Jun–Jul, $6/$3 | 0.80 | lhcaz.gov/329/Aquatic-Center |
| 578 | LHC Parks & Rec | Summer Swim League ages 6–12, four team slots M/W or T/Th 5–6p / 6–7p. **City page season dates are garbled** ("starts July 2, ends June 11") — flagged in description | 0.65 | lhcaz.gov/329/Aquatic-Center |
| 579–580 | LHC Parks & Rec | Junior Lifeguard: 12–15 M/W 4–6p (from Jun 1), 9–11 T/Th 4–6p (from Jun 2); ends Jul 10 | 0.75 | lhcaz.gov/329/Aquatic-Center |
| 581–582 | Havasu Stitchers | General Member Meeting 2nd Thu 6–8p, Mohave College Rm 600 ($5 guests; **Jul 2026 moves to Wed 7/8**); Community Outreach Sewing 3rd Wed 10a–2p, Aquatic Center Rm 153/154. Monthly (not weekly) recurrence noted in descriptions | 0.80 | havasustitchers.com/events |
| 583 | Havasu Art Guild | Maturing Masters Art Workshop, every Thu 8:30–11:00a, Mohave County Senior Center, $1, members. Site says "8:30 am – 11:00 **pm**" — assumed am typo | 0.65 | sites.google.com/site/havasuartguild |
| 584–588 | Desert Bloom Learning Center | Morning Homeschool Support T/W/Th 8–11a + 4 afternoon enrichment workshops (Movement Lab Mon @ Altitude, Life Skills Tue, Creative Arts Wed, History Explorers Thu) 12:30–2:30p, ages 5–12. **Address flag: site footer now says 1100 London Bridge Rd Ste 202, DB/CSV has 2170 Havasupai Blvd** | 0.70 | desertbloomlearningcenter.com/learn-more |
| 589–609 | GraceArts LIVE Youth Theatricals | Full ACPA dance grid, 21 classes M–F (ballet/tap/jazz/hip hop/contemporary/pointe/musical theatre), $60/40/35 monthly tiers. **2025-26 season — showcase was May 15–17, 2026, so summer status unverified → 0.55 so nothing auto-publishes**. Dance studio is at 3476 McCulloch (ACPA), affiliated with GraceArts — Casey should confirm the entity attach is right | 0.55 | graceartslive.com/dance-studio |

## Skipped (with reasons)

- **Aqua Beginnings** — appointment-only lessons; only fixed window is free assessments Tue/Wed/Fri 8a–2p. Excluded per the "appointment-only" precedent; flag if you want the assessment window listed.
- **Driftwood Acres** — Wix booking calendar (Loading days…), appointment lessons $40/$50. Note: moved to 1807 Aztec Rd (matches CSV). Yelp marks the old Kingman location CLOSED.
- **Havasu Horseback Rides** — Pony/Leadline Mondays 10–5 is marked "ENDS IN APRIL FOR SUMMER" (paused now); other lessons appointment-based. Summer camp Jun 1–4 / 8–11 7–9a nearly over. Re-check in fall.
- **HavaLife CPR** — "call to register," no published schedule. Address note: site header says 2150 McCulloch Blvd N Unit B (CSV: 1940 Mesquite per Yelp — site is authoritative).
- **Bella Faccia** — unclaimed WellnessLiving stub ("online booking not available yet") — the known-useless case from the watch-outs.
- **Havasu Lions FC** — fall rec league only (practices from wk of Sep 22, Sat games Oct–Dec); off-season now. Revisit at fall registration.
- **Marlene Arden** — appointment lessons (Zoom/in person), no schedule.
- **No-website venues left for OpenClaw FB sweep:** Angie's Line Dance, Kids Activities Studio, Marsh Dance, Next Generation MMA, Sew What, Steelhead Aquatics.
- **Previously posted (validation run 6/04):** Eight Lotus, Ballet Havasu, Stingrays. **Previously dead/known-no-schedule:** Trinity MMA, Flips For Fun, Windy Hills, LHC Pickleball, Havasu Pilates, Soul Lifting, Kaizen, Shaolin Kempo, WACKO (tours, phone-only), MCC (stale portal).

## Venue progress tracker (entity-id map, 33 rows)

Posted: Eight Lotus, Ballet Havasu, Stingrays (prior run) + Parks & Rec, Stitchers,
Art Guild, Desert Bloom, GraceArts/ACPA (this run) = **8 venues done**.
Appointment-only/no-schedule: Aqua Beginnings, Bella Faccia, Driftwood, HavaLife,
Havasu Horseback, Marlene Arden, Soul Lifting, WACKO, MCC, Little League*, Chiefs*,
Lions FC (seasonal — revisit fall). FB-only → OpenClaw: Angie's, Kids Activities,
Marsh, NextGen MMA, Sew What, Steelhead, Kaizen, Shaolin Kempo. Dead sites:
Trinity MMA, Flips For Fun. Unreadable embeds: Pickleball, Windy Hills, Havasu
Pilates ("up soon" — worth a re-check next run).
(*Little League/Chiefs not crawled this run — seasonal sports with end dates;
queue for a browser-enabled run.)

## Addendum — browser sweep (same day, Chrome reconnected)

Casey reconnected Chrome; re-checked the JS-locked venues:

- **Driftwood Acres — 2 findings extracted** from the live Wix booking calendar:
  Group Riding Lessons weekdays 7:00 & 8:30a (90 min, $40, conf 0.65) and Roping
  Group Tue/Thu 3:30–5:00p ($40, conf 0.70). NOT yet posted: the ingest token
  was rotated mid-session and the sandbox's cached `.env` still has the old
  value → 401. Casey runs `scripts/resend_driftwood.ps1` locally to post both
  (payloads also in session outputs f43/f44.json).
- **Havasu Pilates / Crazy Ed's** — June sessions started Jun 1–3, signup page
  now shows "new services coming soon" + waitlist; still no postable times.
- **LHC Pickleball** — beginner lessons + novice clinics paused until
  **December 2026** (ARK Center gym, 2700 Jamaica Blvd S; first lesson free,
  then $5/session); round robins also resume December. Revisit then.
- **Windy Hills Pottery** — site errors out in a real browser; dead → liveness flag.
- **Bella Faccia** — bellafacciaskincare.com is now skincare-only (no
  pilates/movement content); WellnessLiving stub unclaimed. Entity may need
  re-categorizing or removal of the movement-studio angle.

Token note: prod + Railway + Windows `.env` all agree on the new 43-char token
(sha8 edc1cd52); the sandbox mount serves a stale pre-rotation copy (sha8
efc1efaa). Future scheduled runs are fine (fresh mount); this session just
can't re-read the file.

## Addendum 2 — approve + publish + two chat fixes (same evening)

- All 42 contributions (568–609) approved via the admin attach flow; #567
  (stale Stingrays) rejected `unverifiable` with re-scrape note. Queue clear.
- **PR #139** (merged, deployed): chat entity rows now carry a `programs`
  list pairing Offerings with Schedules; publish path writes the class title
  into `Schedule.notes`; admin approve form prefills from `proposed_record`
  (it previously submitted venue-name + Mon 9–5 defaults — near-miss).
- **PR #141** (merged, deployed): catalog provider-gate carve-out — commercial
  entities with NO Provider row but published Offerings are now chat-visible
  (schedule-hunt imports create bare entities the gate hid unconditionally).
- **Verified live:** "where can I take a yoga class?" → Warm Water Yoga
  10:15–11:15a at the Aquatic Center. Scrape → ingest → approve → chat, closed
  loop.

### Known gaps for next session
1. Entity-name queries ("what does Grace Arts offer") use the legacy tier2
   path which never reads Offerings — same serialization needed there.
2. `_NOUN_TO_CATEGORY_SLUGS` lacks class nouns (dance/yoga/fitness/quilting);
   needle fallback fetches an unordered 80-entity cap, so venues can miss.
3. Stitchers entity has NO EntityCategory ("quilt guild" matches no import
   keyword) → still invisible; needs category backfill + keyword fix.
4. Likely duplicate entities: provider-backed GraceArts/Stitchers twins vs
   schedule-hunt entities (chat found a Stitchers at 2131 Rainbow Ave N).
5. Cosmetic: expanded event titles concatenate instructor ("Warm Water Yoga
   Stephanie"); responses repeat each occurrence verbatim.
6. Driftwood resend (f43/f44) still pending — needs Casey's machine.

## For Casey's review pass

1. The 21 ACPA entries (589–609) are the bulk of the queue — if the entity
   attach (GraceArts Youth Theatricals) or seasonal staleness bothers you,
   bulk-reject is fine; data is preserved in the session outputs.
2. Address changes spotted: Desert Bloom (1100 London Bridge Rd Ste 202),
   HavaLife CPR (2150 McCulloch Blvd N Unit B), Driftwood (1807 Aztec Rd ✓ already).
3. Aquatic Center punch pass is $80 (PDF) — the web page still says $78.
4. Swim League season dates on the city page are self-contradictory; someone
   should call 928-453-8686 before publishing 578.
