# Schedule Hunt — find class/activity schedules for every relevant business

Casey's directive (2026-06-03): shelve the bars sweep (OpenClaw cron `lhc-fb-sweep`
disabled; 2/5 captures done and sitting in the inbox). New priority: businesses
with CLASS/ACTIVITY SCHEDULES (gyms, martial arts, yoga, pilates, dance,
gymnastics, swim, scuba, trampoline parks, tennis, climbing, etc.). These
schedules are almost never on the Google listing — they live on the business's
website (sometimes buried several clicks deep) or only on Facebook.

## Pipeline (3 phases)

### Phase 1 — Identify candidates (one-time, then maintain)
Source: `data/events.db` (local copy of entities DB; 2,990 active entities).
Sweep ALL active businesses — not just obvious categories — and flag any that
plausibly run scheduled classes/sessions/events. Heuristics: category
(Classes/Sports/Rec, Health & Wellness, On the Water), name/description keywords
(gym, yoga, pilates, dance, martial, karate, jiu jitsu, gymnastics, swim, dive,
scuba, climb, fitness, training, studio, ranch/riding, art class, pottery,
music lessons, tutoring, league, club...), plus judgment (e.g. breweries with
trivia nights count later — bars avenue; skip here).
IMPORTANT: the DB contains test fixtures ("Verified URL Gym", "Backfill
Plumbing...", hash-suffixed names) — exclude them. Dedupe repeated rows.
Output: `docs/scraper/schedule_hunt_candidates.csv` with columns:
name,type,website,facebook_url,address,schedule_found(blank|website|facebook|none),schedule_url,notes
Seed it from `havasu_fitness_seed.csv` (23 venues, 20 with verified FB pages —
already resolved 2026-06-03).

### Phase 1b — Discovery audit (NEW 2026-06-03 — the Bridge City Combat lesson)
The DB alone is NOT a sufficient candidate source: real businesses are missing
entirely, and some real businesses are shadowed by tier2-test fixtures
(hash-suffixed names, source='tier2-test') so the dedupe rule silently drops
them. Periodically (and whenever a spot check finds a miss):
1. Web-discovery sweep per category (WebSearch: "<category> Lake Havasu City",
   plus site:mohavelocal.com / site:golakehavasu.com queries) and compare
   against the candidates CSV — add misses.
2. Audit DB for `source LIKE '%test%'` and hash-suffixed names; check whether a
   REAL business of the same name exists before discarding.

### Phase 2b — Directory fallback (NEW 2026-06-03)
For any candidate whose website yields no/partial schedule: pull hours, class
times, and prices from directory sources BEFORE relying on the FB sweep:
- **golakehavasu.com** — best local directory (full hours + pricing, maintained)
- mohavelocal.com — decent coverage, hours often STALE; cross-check
- Google Business data via search snippets; Yelp (check "updated" date)
- Niche/booking platforms: Matmade, dojos.info (often LEGACY — verify against
  the business's own site), Gymdesk/GymMaster/WellnessLiving/Mindbody/Vagaro/
  iClassPro/DanceStudio-Pro/SportsEngine/gomotionapp portals — these are often
  fetchable and machine-readable even when the marketing site is a JS shell.
STALE-DATA TRAPS (hard-won): dojos.info grids can contradict a pivoted
business; mohavelocal hours lag; unclaimed WellnessLiving stubs are useless;
sports-team schedules carry explicit end dates — check them.

### Phase 2 — Website deep-crawl (Cowork's job, scheduled task)
Per candidate with a website: fetch the homepage, follow likely nav links
(schedule, classes, calendar, timetable, book, programs, lessons — up to ~4
internal pages; e.g. the gymnastics gym's schedule is a few clicks deep).
Extract the actual schedule (days/times/class names/prices) per the data
contract (`havasu_scraper_data_contract.md`): ongoing weekly classes →
Offering + Schedule on the entity; dated sessions/camps → Events.
Record findings + schedule_url in the CSV; mark `schedule_found=website`.
If the site fails or has no schedule: mark candidate for Phase 3.
Work in chunks (~10–15 businesses per run) so each run stays small. Compile
findings into `docs/scraper/reports/schedule_hunt_<date>.md` for Casey.
NOTHING auto-publishes — reports + CSV only, Casey reviews.

### Phase 3 — Facebook via OpenClaw (only for website misses)
For candidates with `schedule_found` blank/none and a facebook_url:
reuse the proven OpenClaw capture pipeline (see PROJECT_HANDOFF.md):
- exec headless chromium full-page PNG (NOT the gateway browser tool — broken):
  `timeout 120 chromium --headless=new --no-sandbox --disable-gpu
  --disable-dev-shm-usage --hide-scrollbars --window-size=1366,4000
  --screenshot=/tmp/lhc/<slug>.png '<fb_url>'`
- upload via curl to POST /api/ingest/capture with
  `-H "Authorization: Bearer $(cat /data/.openclaw/workspace/lhc/.token)"`
- then Cowork vision-reads captures per `COWORK_REVIEW_RUNBOOK.md`.
Create a NEW cron (e.g. `lhc-schedule-sweep`) with its own master list — do not
reuse/re-enable `lhc-fb-sweep` (that's the bars list, shelved).
Venues with FB page but no website go straight to Phase 3.

## Operational notes (hard-won today — do not relearn)
- OpenClaw chat: DeepSeek hallucinates and stalls. Give exact exec commands,
  demand raw outputs, verify stored cron state, no GET re-verify loops.
- Isolated cron sessions do NOT inherit chat context and did not get
  $INGEST_API_TOKEN env — hence the .token file approach.
- repo `.env` may still hold an OLD ingest token; Railway value is current.
- One Claude Code session per repo checkout; this checkout's git HEAD is broken
  — repo code changes go through Casey's Claude Code session.

## Status log
- 2026-06-03: plan created; fitness seed (23) resolved; scheduled task created
  to run the pipeline daily; bars sweep shelved with 2/5 captures in inbox
  (Barley Brothers, College Street — still need review + Casey sign-off).
- 2026-06-03 (late): Phase 2 deep-crawl COMPLETE — all 30 sites re-crawled,
  CSV updated, report at reports/schedule_hunt_deepcrawl_2026-06-03.md
  (Amalaya full grid via rendered Momence; Aquatic Center + Beyond Dance PDFs
  extracted; Sportsman's match calendar found; WACKO is NOT dead). Phase 3
  STARTED: cron `lhc-schedule-sweep` live on OpenClaw (45 min, 2 venues/run,
  self-disabling; queue now 14 — Amalaya removed). First batch (Anytime
  Fitness, Iron Age Gym) uploaded with 201s — note: the cron's isolated
  DeepSeek run stalled after screenshots; uploads were completed supervised.
  Watch the next runs for the same stall. Capture review done:
  reports/capture_review_2026-06-03.md — 4 reviewed, 2 left `new` for Casey
  (mislabeled: actually Flying X Saloon + The Office). repo .env token fixed.
