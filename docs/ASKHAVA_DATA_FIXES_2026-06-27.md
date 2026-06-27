# Ask Hava — data-quality findings & Claude Code fix prompt (2026-06-27)

Live audit of askhava.com (prod). Each issue below was confirmed on the live
site; correct values were pulled from the businesses' own sources. **Part B** is
a ready-to-paste prompt for a Claude Code session to do the fixes, written to the
repo's `CLAUDE.md` rules (feature branch, DB ops dry-run → counts → Casey
approves → apply, never push to `main`).

---

## Part A — Findings

### 1. Lady Lee's Billiards Hall — missing hours, address, and phone
- **Page:** `/provider/lady-lee-s-billiards-hall` (breadcrumb *Things to Do & Attractions*).
- **What's wrong:** shows "Hours not available — call to confirm," "Address not listed," and no phone number. The About text is placeholder ("call or see the venue's page for current hours").
- **The data exists elsewhere:** the venue's own event rows already carry the address `2180 McCulloch Blvd N`, so the provider entity is missing data the events have.
- **Correct values** (official site `ladyleesbilliards.com` / `ladylees.com`, fetched 2026-06-27):
  - Address: **2180 McCulloch Blvd N, Lake Havasu City, AZ 86403**
  - Phone: **(928) 732-0426**
  - Hours: ⚠️ the site contradicts itself — the "Find Us" block says **"Everyday 11am–1am (kitchen closes 10pm)"** while the footer says **Mon–Thu 11a–10p, Fri–Sat 11a–12a, Sun 11a–9p**. **Verify against the Google Business Profile before publishing** (judgment call — don't guess).

### 2. Havasu Lanes — duplicate business listing (root cause of the "bowling events look like another place" report)
- **Two provider entities for the same bowling alley**, same phone `(928) 855-2695`, identical About text:
  - `/provider/havasu-lanes` — **"Havasu Lanes"**: no hours, no address, no reviews. *This bare duplicate is where the Cosmic Bowling event and the daily bowling activity point their venue label.*
  - `/provider/havasu-lanes-keglers-pub` — **"Havasu Lanes & Keglers Pub"**: full hours (Mon–Sun), address `2134 McCulloch Blvd N`, 463 Google reviews (4.2). The complete record.
- **Inconsistent categorization:** search lists "Havasu Lanes" under *Attractions* and "Havasu Lanes & Keglers Pub" under *Restaurants*, but both provider breadcrumbs say *Family Fun & Arcades*.
- **Address note:** the alley's own site (`havasulanesaz.com`) and the "Havasu Lanes" search snippet show `2128 McCulloch Blvd N`; the Keglers record shows `2134 McCulloch Blvd N` (same complex — bowling at 2128, pub suite at 2134). Reconcile to one canonical address.
- **Why the reviewer saw it as "another place":** the bowling events are split across the two names. When you view one listing, the events reference the *other* name, so they read as a different venue.
- **Fix:** merge into one canonical entity — keep the complete record's hours/address/reviews, and re-point **all** bowling events (Cosmic Bowling + the daily "Bowling — …" activity rows) to it. Canonical display name is a **judgment call for Casey** ("Havasu Lanes" vs "Havasu Lanes & Keglers Pub").

### 3. "Glow in the Park" appears twice on Jun 27 (duplicate event)
- On **2026-06-27 at Altitude Trampoline Park**, two near-duplicate rows: **"Glow in the Park" (6 PM)** and **"Glow in the Park — All Ages" (7 PM)**.
- "Glow in the Park — All Ages" is the **recurring series** (Jun 13 → Aug 5, many dates). The plain "Glow in the Park" appears **only on Jun 27** — classic double-ingest from two loaders. (Same shape as the bowling/cosmic dedup already done in `scripts/dedup_bowling_cosmic_2026_06_26.py` on 2026-06-26.)
- Note: "Glow in the Park" is an **Altitude Trampoline Park** event, *not* a bowling event — so if it surfaced near the bowling content it would also read as "another place."
- **Fix:** keep the recurring "— All Ages" series; remove/merge the one-off Jun 27 "Glow in the Park" collision. **First verify** whether 6 PM and 7 PM are genuinely two separate sessions on Altitude's real schedule — if so, keep both but harmonize the naming instead of deleting.

### 4. Fitness & Sports is missing all strength / CrossFit / HIIT / gym group classes
- The Fitness & Sports classes feed (`/events-ui?view=classes`) surfaces Yoga, Pilates, Mind & Body, Aquatic fitness, Dance, Gymnastics, Golf, Martial arts, Pickleball — but the **"Strength & Cardio"** subgroup (which **already exists** in `app/events/activity_taxonomy.py`) is **empty on every day**. No CrossFit, functional-fitness, HIIT, bootcamp, or spin classes appear.
- The directory *does* list 18 gyms (incl. Havasu CrossFit, Fit Lab 928, Bridge Body Fitness, Feelin' Good Fitness, Family Office Society Gym, Iron Age, Titan, Fiore's), so the businesses exist — only their **class schedules** are absent from the events feed.
- **The schedules are already captured** in `docs/scraper/schedule_hunt_candidates.csv` but were never imported (studio yoga/pilates/dance/martial-arts *were* imported). Confirmed-current rows to ingest:
  - **Havasu CrossFit** — WODs M–F 5:00a / 6:10a / 7:20a / 8:30a / 3:20p / 4:30p / 5:40p (+ Open Gym), Sat 7:30a + 8:30a.
  - **Fit Lab 928** — M–F Function/Sweat blocks (5:00a, 5:30a, 6:15a, 8:30a, 3:05p, 4:15p, 5:15p, 5:30p), Sat Function 8a.
  - **Feelin' Good Fitness** — M–F 5:00a/6:15a/8:00a/9:45a/11a/4:00p/5:15p/6:30p (HIIT/Strength), Sat 7:00a/8:15a/9:45a, Sun closed.
  - Lower-confidence, **verify before importing:** Titan Gym (schedule is a stale Feb-2025 image — OCR or call), Fiore's Endorphin Factory (week of 6/1 showed all-closed — confirm it's running).
- **Fix:** import the confirmed gym schedules through the established `scripts/import_captured_schedules.py` path; they should auto-classify into "Strength & Cardio." Then verify they show under Fitness & Sports across the week.

### 5. Design note (judgment call, not auto-fix) — activity-as-daily-event "filler" rows
- Daily auto-generated entries like "Billiards — Lady Lee's Billiards Hall," "Bowling — Havasu Lanes," "Trampoline Park — Altitude" represent "this venue is open and offers this activity," not a scheduled event. They sit alongside real events and inherit "Hours vary" when the venue's hours are missing (that's why Lady Lee's reads "Hours vary").
- Likely intentional (drop-in rec surfacing). **Flagging for Casey** — fixing #1 and #2 (hours + the merge) removes most of the visible confusion without touching this behavior.

---

## Part B — Prompt for Claude Code

> Paste everything below into a fresh Claude Code session in the `havasu-chat` repo.

---

You're fixing four confirmed data-quality issues in Ask Hava, found in a live prod audit on 2026-06-27. Full findings: `docs/ASKHAVA_DATA_FIXES_2026-06-27.md`.

**Follow `CLAUDE.md` exactly.** In particular:
- Work on a **feature branch off `main`**. Do **not** push or merge to `main` — open a PR and stop.
- Every prod-DB write (entity merge, event rename/delete, hours/address backfill, schedule import) is **dry-run first → print counts → wait for Casey's approval in chat → then `--apply`**. Never apply without the go-ahead.
- `python -m pytest -q` green and `ruff check .` clean before any commit. Update tests in the same commit as behavior changes.
- On genuine judgment calls, **STOP and ask Casey** — don't guess.

Start by reading: `app/db/models.py` (Event + provider/entity models), `app/events/activity_taxonomy.py`, `scripts/dedup_entities.py`, `scripts/dedup_bowling_cosmic_2026_06_26.py` (use as a template), `scripts/import_captured_schedules.py`, and `docs/scraper/schedule_hunt_candidates.csv`.

### Task 1 — Backfill Lady Lee's Billiards Hall (hours, address, phone)
Provider `lady-lee-s-billiards-hall` is missing hours, address, and phone. Apply:
- Address: `2180 McCulloch Blvd N, Lake Havasu City, AZ 86403`
- Phone: `(928) 732-0426`
- Hours: the official site conflicts — "Everyday 11am–1am (kitchen closes 10pm)" vs footer "Mon–Thu 11a–10p / Fri–Sat 11a–12a / Sun 11a–9p." **Confirm against the Google Business Profile first, then ask Casey which to use.** Don't guess hours.
Write a dry-run script (or use the existing backfill path), show the before/after, get approval, apply.

### Task 2 — Merge the duplicate Havasu Lanes listing
Two entities for one bowling alley: `havasu-lanes` (bare: no hours/address/reviews) and `havasu-lanes-keglers-pub` (complete: hours, `2134 McCulloch Blvd N`, 463 reviews). Same phone `(928) 855-2695`.
- Merge into one canonical entity, preserving the complete record's hours/address/reviews.
- Re-point **all** bowling events (the "Cosmic Bowling" series and the daily "Bowling — …" activity rows) to the canonical entity so no event references the retired name.
- Reconcile the address (`2128` alley vs `2134` pub suite) and the category (search shows Attractions vs Restaurants; breadcrumb says Family Fun & Arcades).
- **Ask Casey** which display name is canonical ("Havasu Lanes" vs "Havasu Lanes & Keglers Pub") before applying.
Use the `dedup_entities.py` pattern; dry-run → counts → approve → apply.

### Task 3 — Dedup "Glow in the Park" on Jun 27
At Altitude Trampoline Park on 2026-06-27 there are two rows: "Glow in the Park" (6 PM) and "Glow in the Park — All Ages" (7 PM, the recurring Jun 13–Aug 5 series). The plain 6 PM row is a one-off collision.
- **First verify** whether Altitude actually runs two distinct sessions (6 PM and 7 PM) that night. If yes, keep both and harmonize naming. If it's a duplicate, keep the recurring "— All Ages" series and delete the one-off, mirroring `dedup_bowling_cosmic_2026_06_26.py`.
- Dry-run → counts → approve → apply.

### Task 4 — Import strength/CrossFit/HIIT gym classes into Fitness & Sports
The "Strength & Cardio" subgroup in `activity_taxonomy.py` exists but is empty — no gym/CrossFit/HIIT classes appear in the classes feed, though their schedules are already captured in `docs/scraper/schedule_hunt_candidates.csv`.
- Import the confirmed-current schedules for **Havasu CrossFit**, **Fit Lab 928**, and **Feelin' Good Fitness** (grids are in the findings doc / CSV) via `scripts/import_captured_schedules.py`.
- **Re-verify before importing** the stale/uncertain ones: Titan Gym (schedule is a Feb-2025 image) and Fiore's Endorphin Factory (recently showed all-closed). Skip or flag if you can't confirm they're currently running.
- After import, confirm the classes land under Fitness & Sports → "Strength & Cardio" across a full week (check a weekday and a weekend day).
- Dry-run → counts → approve → apply.

### Wrap up
- Add/extend tests for each behavior change (entity merge, glow dedup, strength import classification).
- `pytest -q` + `ruff check .` clean, commit on the feature branch, open a PR, and stop. Summarize what's pending Casey's approval (anything DB-writing) in the PR body.

### Out of scope / flag only
The daily "activity-as-event" filler rows (Billiards/Bowling/Trampoline "open today" entries) are likely intentional — don't change that behavior; just note it for Casey.
