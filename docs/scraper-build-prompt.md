# Claude Code Build Prompt — Ask Hava Source Expansion Scrapers

**Status: BUILD ONLY — DO NOT INTEGRATE.** Casey will green-light each source
individually after reviewing dry-run output. Companion research (every endpoint
verified live 2026-06-04): `docs/source-expansion-research.md`.

---

## MASTER PROMPT (paste this to the Claude Code session)

You are building data-source scrapers for Ask Hava in the `havasu-chat` repo.
Read `CLAUDE.md` and `docs/scraper-build-prompt.md` (this file) fully before
writing code. The research backing every endpoint is in
`docs/source-expansion-research.md` — consult it for verified URLs, caveats,
and paywall/ToS notes.

### Ground rules (non-negotiable)

1. **Work in a separate git worktree.** Other Claude sessions are active in the
   main checkout. Create `git worktree add ../havasu-chat-scrapers -b
   feat/source-expansion-scrapers main` and do ALL work there. Never touch the
   main checkout's HEAD.
2. **Never push or merge to `main`.** When done, push the feature branch and
   open a PR. Stop there.
3. **BUILD ONLY — no integration.** Specifically:
   - Do NOT register any new source in `scripts/run_scrapes.py`,
     `scripts/scrape_events.py`, the conditions fetcher cron list, or any
     orchestrator/scheduler.
   - Do NOT run any loader against the database for real. Every loader must
     default to `--dry-run` and require an explicit `--apply` flag that prints
     a warning. You never run `--apply`.
   - No alembic migrations unless a source truly needs a new column — and if
     so, write the migration but do not apply it anywhere; flag it in the PR.
4. **Per-scraper quality bar:** follow the existing patterns —
   client/parser module in `app/contrib/` (or `app/events/scrapers/` for event
   sources, `app/conditions/` for conditions sources), CLI driver in
   `scripts/`, unit tests with recorded/fixture HTML-JSON (no live HTTP in
   tests). Before every commit: `python -m pytest -q` green and
   `ruff check .` clean. One scoped commit per scraper.
5. **No secrets.** Where an API key is needed, read from an env var, document
   it in the module docstring and PR description, and make the module degrade
   gracefully (skip with a log line) when the key is absent — same pattern as
   `app/conditions/openuv.py`. Never type or fetch actual key values.
6. **Paywall ethics:** for Today's News-Herald, ingest ONLY headline, date,
   keywords, and the freely-served lede (first ~2 paragraphs). Do NOT decode
   the ROT47-obfuscated body — that is paywall circumvention.
7. **Politeness:** every scraper gets a descriptive User-Agent, conservative
   rate limiting (reuse `SourceLimiter`), and caching where the existing
   `external_conditions_cache` pattern fits.
8. **Dry-run output contract:** each CLI driver's `--dry-run` prints: item
   count fetched, would-insert / would-update / would-skip counts, and 3
   sample records. This is what Casey reviews to approve each source.
9. If a target turns out to be unreachable from the build environment
   (Cloudflare etc.), build the module against fixture data, mark it
   `NEEDS_PROD_VERIFY` in the PR description, and move on. The repo's proxy
   pattern (`GAS_SCRAPE_PROXY_URL`-style env var) is the fallback for
   Cloudflare-protected targets.

### Task 0 — Conditions display swap (the ONE approved site change)

This task IS approved for implementation (still via PR, never merged by you):

- **Lake hero mini-strip** (`app/home/sandstone.py::lake_mini_conditions`):
  remove the "Lake level" tile; ensure "Wind" (already present from
  `wind_speed_mph`) renders in its place/position.
- **Conditions panel** (`app/conditions/view_model.py`): remove/demote the
  `sky_condition` ("Sunny") tile and surface the UV tile in its place. The UV
  tile already exists but is gated on `OPENUV_API_KEY`. Make UV robust:
  if no OpenUV key is configured, fall back to a keyless UV source — check
  whether the existing NWS gridpoint payload or the EPA AirNow/UV index API
  (`https://data.epa.gov/efservice/...` or
  `https://enviro.epa.gov/envirofacts` UV endpoints) can supply it; implement
  the cheapest reliable fallback and document the choice.
- Update `tests/test_sky_condition.py`, `tests/test_today_payload.py`, and any
  template assertions accordingly.
- Note in the PR: prod needs `OPENUV_API_KEY` set (free tier, 50 req/day) for
  the primary path — Casey action.

### Scrapers to build

Build each as an independent, inert module. Order roughly as listed; P2C last.

**Group A — City & civic feeds (reuse feedparser/iCal patterns)**

1. `lhc_newsflash` — CivicPlus RSS
   `https://www.lhcaz.gov/RSSFeed.aspx?ModID=1&CID=All-newsflash.xml`
   (road closures, PD/city press releases). New content type: consider a
   simple `news_items` store or reuse contribution flow — propose in PR.
2. `lhc_alerts` — Alert Center RSS
   `https://www.lhcaz.gov/RSSFeed.aspx?ModID=63&CID=All-0` (usually 0 items;
   that's expected — design for poll-until-nonempty).
3. `legistar` — Legistar Web API (JSON, no auth):
   `https://webapi.legistar.com/v1/lakehavasucity/events?$top=20&$orderby=EventDate+desc`
   Council/P&Z/board meetings + agenda/minutes PDF links
   (`View.ashx?M=A|M&ID=..&GUID=..`). Model as events with body name, date,
   location, agenda URL.
4. `lhusd` — Apptegy Thrillshare JSON:
   live feed `https://thrillshare-cmsv2.services.thrillshare.com/api/v2/s/322922/live_feeds?page=1`,
   events `.../api/v2/s/322924/events?start_date=..&end_date=..`,
   district iCal `.../api/v4/o/19160/cms/events/generate_ical` (reuse
   `ical_parse.py`). Filter all-day academic-span noise (e.g. month-long
   "Summer School") from event ingestion.
5. `mcso_press` — Mohave County Sheriff press releases (HTML scrape):
   `https://www.mohave.gov/departments/sheriff/press-release/` (~2-3/wk).

**Group B — News**

6. `news_herald` — TownNews/BLOX news sitemap:
   `https://www.havasunews.com/tncms/sitemap/news.xml` (Google News sitemap;
   title, pub date, keywords). Fetch each article page for the free lede only
   (rule 6). Also ingest the weekly fishing column via the working BLOX search
   RSS: `https://www.havasunews.com/search/?q=fishing+report&t=article&f=rss&s=start_time&sd=desc&l=5`.
   Note: the generic `?f=rss` section feeds are dead on this site — sitemap is
   the path.
7. `river_scene_news` — WordPress REST (full text, free, no auth):
   `https://riverscenemagazine.com/wp-json/wp/v2/posts` (supports
   `?after=`, `?categories=`, pagination). Extend the existing
   `app/contrib/river_scene*` family; do not disturb the events scraper.
8. `abc15_havasu` — Scripps section RSS (free full text, sporadic):
   `https://www.abc15.com/news/region-northern-az/lake-havasu.rss`.

**Group C — Events & entertainment**

9. `allevents` — `https://allevents.in/lake-havasu-city` (+ `/this-weekend`).
   Serves clean markdown to bot UAs; detail pages carry schema.org JSON-LD.
   ~130 rolling events incl. bar/nightlife nothing else has. MUST route
   through `decide_ingest` with dedupe keyed on normalized
   (title, start date, venue) — high overlap with golakehavasu/RiverScene.
10. `bandsintown` — public Events API (free `app_id`, env var
    `BANDSINTOWN_APP_ID`), query location "lake havasu city, az" + radius to
    catch BlueWater (Parker) and Laughlin casino shows. Tag events
    `regional`/nearby.
11. `movies` — showtimes for both theaters. Movies Havasu
    (`movieshavasu.com`) is JS-rendered on the Webedia/BoxOffice CMS (theater
    id `X0QCN`, circuit 101364) — sniff the underlying webediamovies.pro JSON
    XHR first; if unworkable, scrape a showtimes aggregator
    (showtimes.com / cinemaclock.com) for BOTH Movies Havasu and Star Cinemas
    (`starcinemashavasu.com`). **Also:** check both theater websites for the
    kids' free summer movie schedule (it's confirmed on the Movies Havasu
    Facebook page; the website may mirror it). If it's website-visible,
    parse it into family-tagged events. If it's Facebook-only, do NOT scrape
    Facebook — add a note in the PR that it should go through the OpenClaw
    facebook_scrape pipeline instead.
12. `eventbrite_orgs` — Eventbrite organizer-events endpoint
    (`GET /v3/organizations/{id}/events/`; public search API is dead).
    Seed organizer list: Havasu Community Health Foundation
    (org 40584556073) + any other LHC organizers discovered on
    allevents/eventbrite pages during build. Exclude recurring
    worship-service listings. **Relevance gate:** in the PR, include the
    dry-run sample so Casey can judge whether content is Havasu-relevant
    enough to keep; build it to be trivially removable.
13. `senior_center` — `https://lakehavasuseniorcenter.com/current-events`
    (small HTML scrape, classes/activities). Same relevance gate as #12:
    surface samples in PR; easy to drop if not useful.

    *(Deliberately NOT building: Havasu 95 Speedway, Desert Storm, Balloon
    Fest, Boat Show organizer scrapers — these should arrive via the existing
    RiverScene/golakehavasu scrapers. Instead, add a small verification
    script `scripts/verify_marquee_event_coverage.py` that checks the events
    table for upcoming entries matching those marquee names and prints
    gaps, so Casey can confirm the assumption.)*

**Group D — Conditions & outdoors**

14. `nws_extras` — parse-only change to the existing NWS integration: surface
    `windGust`, `heatRisk`, `wetBulbGlobeTemperature`, `twentyFootWind` from
    the already-fetched gridpoint `https://api.weather.gov/gridpoints/VEF/141,19`,
    and confirm Lake Wind Advisory zone AZZ036 is covered by the alerts
    filter (currently AZZ002 default). New cache fields only; no new fetcher.
15. `rise_water_temp` — Bureau of Reclamation RISE:
    `https://data.usbr.gov/rise/api/result?itemId=6127&dateTime[after]=...`
    (item 6127 = Parker Dam daily water temp °F; 6126/6130 = releases;
    send `Accept: application/json`). This replaces/augments the dead Bill
    Williams sensor (USGS 09426630 returning −100000 sentinel). Build as an
    alternate water-temp source behind a feature flag, mirroring
    `usgs_water_temp.py`. `NEEDS_PROD_VERIFY` if blocked from sandbox.
16. `wildfire` — NIFC WFIGS ArcGIS:
    `https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query?where=POOState='US-AZ'&outFields=IncidentName,IncidentSize,PercentContained,FireDiscoveryDateTime&f=json`
    (URL-encode the where clause properly). Filter to ~100 mi of Havasu via
    geometry params. Cache ~5 min TTL pattern.
17. `az511` — official REST API (`https://az511.gov/api/v2/get/event?key=..`,
    docs `https://az511.gov/developers/doc`), env var `AZ511_API_KEY`
    (Casey registers; free; **10 calls/60s throttle**). Filter SR-95 / I-40 /
    Mohave & La Paz counties. Also wire the keyless WZDx feed
    `https://az511.com/api/wzdx` as a secondary.
18. `azgfd_fishing` — monthly GovDelivery bulletins: discover from archive
    `https://www.azgfd.com/fishing-2/where-to-fish/fishing-report-archive/`
    (Cloudflare — use the proxy env-var pattern), bulletins themselves at
    `content.govdelivery.com` are plain HTML; extract the Lake Havasu
    section. Secondary: FishAZ WP REST
    `https://fishaz.azgfd.com/wp-json/wp/v2/posts?search=havasu`
    (`NEEDS_PROD_VERIFY`).

**Group E — Business & community**

19. `food_inspections` — Mohave County monthly PDFs:
    index `https://www.mohave.gov/departments/public-health/environmental-health/reports/`,
    files like `/media/ldcfiinh/food-safety-inspections_2026-04-apr.pdf`.
    pdfplumber tabular parse; keep only the Lake Havasu region section;
    match establishments to existing Providers by name+address (reuse the
    reconciler's matching).
20. `chamber_directory` — GrowthZone member directory enumeration via
    `https://business.havasuchamber.com/active-member-directory` →
    `FindStartsWith?term=A..Z` (plain HTML) + member detail pages. Use as a
    verification/enrichment signal (`chamber_member=true`) on existing
    providers via the reconciler, not as a primary creator of new ones.
    Gentle rate limit; attribute.
21. `reddit_havasu` — public JSON polling:
    `https://www.reddit.com/r/LakeHavasu/new.json` + weekly
    `search.json?q=<business name>&restrict_sr=1` sweeps. Descriptive UA,
    ≤10 req/min. Store permalink + snippet only (attribution required at
    display time); pipe business mentions toward the existing
    `mention_scanner` flow. (reddit.com may be blocked from sandbox —
    fixtures + `NEEDS_PROD_VERIFY`.)
22. `downtown_lhc` — `https://downtownlakehavasu.com` WordPress: member pages
    (`/member/<slug>/`) for the Main Street directory (enrichment signal like
    #20) — but SKIP its events (they syndicate from golakehavasu; dedupe
    hazard).
23. `zillow_research` — monthly CSV pulls from
    `https://www.zillow.com/research/data/` (ZHVI/ZORI), filter to Lake
    Havasu City / ZIPs 86403-04-06. Store as a small market-context cache
    payload. Do NOT scrape zillow.com listing pages.
24. `p2c_bulletin` (LAST, OPTIONAL) — LHCPD daily bulletin
    `https://p2c.lhcaz.gov/dailybulletin.aspx` (CentralSquare P2C). Probe the
    known JSON backend `POST /jqHandler.ashx?op=s` first; if it's not there,
    document findings and stop — do not sink more than a couple hours into
    reverse-engineering. Arrests/incidents/accidents by date.

### Deliverable

- One PR from `feat/source-expansion-scrapers` with per-scraper commits.
- PR description: table of scraper → status (built / NEEDS_PROD_VERIFY /
  stopped+why) → dry-run sample output → env vars or Casey-actions needed
  (AZ511_API_KEY, BANDSINTOWN_APP_ID, OPENUV_API_KEY in prod, proxy for
  AZGFD).
- A short `docs/source-rollout-checklist.md` listing, for each scraper, the
  exact command Casey runs to dry-run it and what "good" output looks like —
  this is the go/no-go artifact for turning each source on later.

### Explicitly out of scope (do not build)

Facebook scraping of any kind (OpenClaw's beat) · decoding News-Herald
paywalled text · Nextdoor/Indeed/Burbio/AllTrails scraping · Yelp/TripAdvisor
(deferred, cost/ToS) · UniSource outage API (ToS-prohibited) · sun/moon tiles
(not wanted) · Speedway/festival organizer scrapers (see #13 note) ·
recreation.gov availability · MLS · any orchestrator registration · any
production data operation.
