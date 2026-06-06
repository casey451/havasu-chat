# "Make it work" — full changelog + Cowork verification checklist (2026-06-06)

Everything done by Claude Code this session lives in **one PR: #186**
(`feat/make-it-work-2026-06-05`). It bundles the five earlier PRs (#181–#185, now
closed) plus the gym/class-schedule system. **9678 pytest green, ruff + `mypy app`
clean.** Nothing is merged — merging #186 deploys to prod and turns on the crons.

This doc is for **Cowork** to (a) run the gated prod steps and (b) verify on the
live site that everything actually shows up.

---

## 0. To make it live (in order)

1. **Merge PR #186** (Casey's gate — deploys + activates crons).
2. **Civic/provider events** auto-fill via the new crons (or trigger manually:
   GitHub → Actions → `civic-events`, `aggregator-events`, `provider-scrapes` →
   *Run workflow*).
3. **Gym/class schedules** (two gated prod-data ops — dry-run → counts → apply):
   - `python scripts/import_schedule_hunt_entities.py --apply`
     (creates the real venue **Entities**, incl. Bridge City Combat; quarantines
     the test fixtures). Run the dry-run first and eyeball the counts.
   - `python scripts/import_captured_schedules.py --apply`
     (creates one **program Contribution** per class from the dataset below).
   - Publish them: either set **`SCHEDULE_HUNT_AUTOPUBLISH=true`** on Railway
     (+ `SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD`, default 0.85 — the captured rows
     carry confidence 0.6, so lower the threshold to ~0.5 **or** approve them in
     `/admin/contributions`), **or** `POST /api/ingest/publish` (has a dry-run).
4. **Optional secrets** (light up dormant sources): `BANDSINTOWN_APP_ID`,
   `EVENTBRITE_API_TOKEN` on Railway; `GAS_SCRAPE_PROXY_URL` for gas freshness.

---

## 1. Scrapers wired (events + providers)

New reusable core `app/contrib/event_ingest.py` (`ingest_event_records`): record →
reconcile → contribution → trust-tiered approve.

| source | tier | result | cron |
|---|---|---|---|
| **legistar** (council/board meetings) | civic | **auto-live** events | `civic-events.yml` Tue/Fri |
| **lhusd** (school calendar) | official | **auto-live** events | `civic-events.yml` |
| **allevents** | aggregator | **pending** (review queue) | `aggregator-events.yml` Mon/Thu |
| **bandsintown / eventbrite** | aggregator | **pending** | `aggregator-events.yml` (no-op until keys set) |
| **pdga / usapickleball** | provider funnel | live providers (classes-sports-recreation) | `provider-scrapes.yml` Sat |

**Verify on site after a run:** `/events-ui` shows upcoming council/board meetings
(legistar) + LHUSD school-calendar dates; the admin review queue
(`/admin/contributions`) holds allevents listings. `/categories/classes-sports-recreation`
gains disc-golf + pickleball providers.

**Event categorisation:** events are tag-driven (the Event model has no category
column). Ingest now normalises tags (drops the "Select Category" junk, folds
Events/events case) and keyword-tags class events → `classes-sports-recreation`.

---

## 2. Live bugs fixed — verify on prod after merge

- [ ] **24/7 hours** — a 24-hour business shows open every day, not "Sunday only".
  Check `/provider/a-toe-truck` (and any 24-hour towing/gym).
- [ ] **Distance** — `/categories/professional-services` no longer shows
  "~2405 min away · Parker area" on a mis-geocoded row (hint hidden past ~150 km).
- [ ] **UV tile** — `/home` conditions strip shows a real UV value (EPA fallback),
  not "UV 0 · Stale".
- [ ] **Wind tile** — `/home` utility strip shows NWS wind (replaces lake level).
- [ ] **Recurring classes tile** — `/home` week strip + month calendar show a
  weekly class on **every** occurrence (parks-rec aquatic etc.), not just once.

---

## 3. Gym / class schedules — THE BIG ONE

### How it works
A captured class → a `program` Contribution → published → a recurring **Schedule +
Offering** on the venue's Entity → rendered in the new **"Classes & schedule"**
section on the venue's `/provider/<slug>` page (`app/providers/view_models.py` +
`provider_profile.html`).

### The dataset — `docs/scraper/captured_class_schedules.json` (14 venues, 110 classes)
**Cowork: after the import + publish, open each `/provider/` page and confirm the
"Classes & schedule" section matches the source. Times/days were transcribed from
the schedule-hunt captures (and, for Bridge City, read from the schedule image).**

| # | Venue | Type | Classes | Source to check against | Caveat to verify |
|---|---|---|---|---|---|
| 1 | **Bridge City Combat** | BJJ/MMA | 9 | bridgecityjiujitsu.com (Schedule page = image) | new site; address 2143 McCulloch Blvd N |
| 2 | **Elite Martial Arts** | karate/kickbox | 5 | elitemartialartslakehavasucity.com/class-schedule.html | Karate end time estimated |
| 3 | **The Tap Room Jiu Jitsu** | BJJ/MMA | 13 | thetaproomjiujitsu.com/schedule | — |
| 4 | **The Study Yoga** | yoga | 8 | thestudylhcaz.com/class-schedule | — |
| 5 | **Amalaya Yoga** | yoga/pilates | 15 | amalayayoga.com/schedule (Momence widget) | only Mon–Thu captured; verify Fri–Sun |
| 6 | **Eight Lotus** | yoga/wellness | 10 | 8lotuswellness.com (Mindbody) | Tue lineup newly added |
| 7 | **Ballet Havasu** | dance | 12 | ballethavasu.org (image) | may pause summer; fall starts Aug 4 |
| 8 | **Arizona Coast Performing Arts** | dance | 7 | graceartslive.com/dance-studio | Mon full; Tue–Fri partial — verify |
| 9 | **Universal Sonics Gymnastics** | gymnastics/cheer | 14 | universalgymnasticslakehavasu.com | "off season" note — verify active |
| 10 | **LHC Aquatic Center** | aquatics/fitness | 12 | lhcaz.gov/.../aquatic-center (June PDF) | — |
| 11 | **Senior Center** | senior fitness/arts | 2 | lakehavasuseniorcenter.com | only timed classes; many others have no fixed time |
| 12 | **Iron Wolf G&CC** | line dancing | 1 | ironwolfgcc.com/events-calendar | — |
| 13 | **Lake Havasu Yacht Club** | line dance | 1 | lakehavasuyachtclub.net | Burgee Girls lessons |
| 14 | **Arizona Krav Maga** | self-defense | 1 | arizonakravmaga.com | traveling model; 1 fixed LHC class |

**Repeated classes** (e.g. a yoga "Inferno" at several times) are stored as **one
row per time slot**, titled with the slot — that's intentional (the Program model
is one-time-per-row and the ingest dedup keys on title).

### To add MORE venues later
Append a venue block to `captured_class_schedules.json` and re-run
`import_captured_schedules.py`. For **image-based schedules** (Wix/Squarespace),
download the schedule image and read it (vision) — that's how Bridge City was done.

---

## 4. Known gaps / skipped (with reasons) — for Cowork to chase manually

**Skipped from the dataset (not auto-importable):**
- **Fiore's Endorphin Factory** — week of 6/1 showed all days CLOSED (summer pause?). Verify via FB.
- **Titan Gym** — schedule is a stale image (Feb 2025). Needs a fresh capture/OCR or a call.
- **Ben Hicks Yoga** — daily classes but no published grid; needs a deeper crawl.
- **Beyond Dance / Footlite** — class-to-day mapping unclear from the PDFs; needs a visual render.
- **Tennis Assoc / Sportsman's Club** — no weekly clock-times / monthly match calendar (doesn't fit the weekly Program model).
- **High-frequency gyms (Havasu CrossFit, Fit Lab 928, Feelin Good)** — 7–8 identical daily slots; need a "one class, many session times" representation decision before loading (would otherwise be very repetitive).

**Manual list (can't auto-scrape — see `docs/scraper/SCHEDULE_STATUS_REPORT_2026-06-06.md`):**
- Facebook-only: Havasu Shaolin Kempo, Next Generation MMA, Kaizen, Angie's Line Dance.
- Dead sites: Trinity MMA, Flips For Fun, Windy Hills Pottery.
- No website / image-only: The Dance Center, Steelhead Aquatics, Align & Define Pilates, Marsh Dance.

**Other still-open:** the lhusd/news sources are on hold (no news surface);
`movies` endpoint is unreachable; `senior_center` *event* scraper can't ingest
(records have no fixed date — its classes are covered via the dataset instead);
OSM provider fallback deferred (Overpass returns coordless way-elements).

---

## 5. Full change inventory (PR #186)

**New files:** `app/contrib/event_ingest.py`, `scripts/import_captured_schedules.py`,
`docs/scraper/captured_class_schedules.json`, `docs/scraper/SCHEDULE_STATUS_REPORT_2026-06-06.md`,
3 workflow ymls (`civic-events`, `aggregator-events`, `provider-scrapes`),
and tests (`test_provider_classes`, `test_import_captured_schedules`,
`test_event_ingest_tags`, `test_week_strip`, `test_conditions_wind_tile`, +
additions to `test_hours_helper`, `test_wp5_browse`, `test_event_sources`,
`test_legistar`, `test_lhusd`, `test_openuv`, `test_uv_fallback`).

**Edited:** `app/providers/view_models.py` + `provider_profile.html` (classes
section), `app/contrib/{legistar,lhusd,approval_service,hours_helper}.py`,
`app/categories/queries.py` (distance), `app/conditions/{openuv,view_model}.py`
(UV + wind), `app/home/{sandstone,router}.py` + `home_sandstone.html` +
`sandstone.css` (week strip + recurrence), `app/schemas/contribution.py`
(sources), `scripts/{events_pull,legistar_pull,lhusd_pull}.py`.

36 files, ~2,700 insertions. Every ingestion path proven against an
alembic-upgraded **copy** of `data/events.db` (never the file itself).
