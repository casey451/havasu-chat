# Source Expansion — Rollout Checklist (go/no-go per source)

This is the operator artifact for turning each new source ON. Every scraper here
is **inert**: it fetches + parses and prints a dry-run report, but performs no
DB writes and is registered in no orchestrator. `--apply` is intentionally
guarded (it prints a warning and exits non-zero) — wiring the persistence path +
orchestrator registration is the per-source integration step you greenlight here
after reviewing the dry-run output.

**How to dry-run anything below** (from the repo root, in the venv):

```
.venv\Scripts\python.exe scripts/<driver>.py <args>
```

"Good output" universally means: a `=== <source> — DRY RUN ===` banner, a
non-absurd `fetched` count, `would-insert/update/skip` counts, and 3 sample
records whose fields look right (titles, dates, URLs, venues). `NEEDS_PROD_VERIFY`
sources may return 0 / error from a datacenter IP — re-run from prod or via the
proxy env vars before judging them.

---

## Task 0 — conditions display swap (already an approved live change)

Not a scraper. Casey action: set `OPENUV_API_KEY` in Railway (free tier, 50
req/day) for the live UV primary path. Without it, UV automatically degrades to
the keyless EPA Envirofacts forecast — no action required for a working tile.

---

## Group A — City & civic

| # | Source | Dry-run command | Good output |
|---|--------|-----------------|-------------|
| 1 | lhc_newsflash | `scripts/lhc_civicplus_pull.py --feed newsflash` | Several road-closure / PD / city items with titles, dates, categories |
| 2 | lhc_alerts | `scripts/lhc_civicplus_pull.py --feed alerts` | **0 items is healthy** (Alert Center is usually empty); any item is a real alert |
| 3 | legistar | `scripts/legistar_pull.py --top 20` | Council / P&Z meetings with body name, date/time, agenda/minutes View.ashx URLs |
| 4 | lhusd (events) | `scripts/lhusd_pull.py --feed events` | Board/school calendar events; month-long academic spans (Summer School) absent |
| 4 | lhusd (news) | `scripts/lhusd_pull.py --feed news` | District announcements (NEEDS_PROD_VERIFY field names) |
| 5 | mcso_press | `scripts/mcso_press_pull.py` | 2-3 sheriff releases with title/date/lede (NEEDS_PROD_VERIFY selectors) |

## Group B — News

| # | Source | Dry-run command | Good output |
|---|--------|-----------------|-------------|
| 6 | news_herald (news) | `scripts/news_herald_pull.py --feed news` | ~10+ articles with title/date/keywords; **no body text beyond free lede** (rule 6) |
| 6 | news_herald (fishing) | `scripts/news_herald_pull.py --feed fishing` | Recent weekly fishing-column entries |
| 7 | river_scene_news | `scripts/river_scene_news_pull.py` | 2-4 recent community/news posts (full text available, excerpt shown) |
| 8 | abc15_havasu | `scripts/abc15_pull.py` | Sporadic; 0 items is normal. Major-incident articles when present |

## Group C — Events & entertainment

| # | Source | Dry-run command | Good output |
|---|--------|-----------------|-------------|
| 9 | allevents | `scripts/events_pull.py --source allevents` | ~100+ events incl. bar/nightlife; deduped within batch on (title, date, venue) |
| 10 | bandsintown | `scripts/events_pull.py --source bandsintown` | Regional concerts tagged `regional` (needs `BANDSINTOWN_APP_ID`; 0 without it) |
| 11 | movies | `scripts/events_pull.py --source movies` | Movies Havasu showtimes; kids summer movies family-tagged (NEEDS_PROD_VERIFY XHR) |
| 12 | eventbrite_orgs | `scripts/events_pull.py --source eventbrite` | Org events, worship listings excluded (needs `EVENTBRITE_API_TOKEN`). **Relevance gate — review samples** |
| 13 | senior_center | `scripts/events_pull.py --source senior_center` | Classes/activities. **Relevance gate — review samples** (NEEDS_PROD_VERIFY) |
| 25 | parks_rec_calendar | `scripts/parks_rec_calendar_pull.py` | Monthly Parks & Rec calendar IMAGE → events via vision LLM. `=== parks_rec_calendar — DRY RUN ===` banner, would-insert/skip, `would-hold-hidden` + confidence histogram, 3 samples. Needs `OPENAI_API_KEY` (0 fetched without it — not a bug). **VISION GATE — review samples AND held (confidence<0.75) rows.** NEEDS_PROD_VERIFY: datacenter IP may get an empty Cloudflare body for the ImageRepository |
| 26 | parks_rec_flyers | `scripts/parks_rec_calendar_pull.py --source flyers` | Individual event-flyer images → events (one flyer ≈ one event). Cap with `PARKS_REC_FLYER_MAX` (default 8). Same vision gate |
| — | marquee coverage | `scripts/verify_marquee_event_coverage.py` | `[OK]`/`[GAP]` per marquee event (Speedway/Desert Storm/Balloon/Boat Show). Read-only |
| — | parks-rec coverage | `scripts/verify_parks_rec_coverage.py` | `[OK]`/`[GAP]` per Parks & Rec surface (webtrac / aquatic / civic-iCal / calendar-image). Also flags whether civic `catID=23` carries Events vs meetings-only. Read-only, no LLM |

## Group D — Conditions & outdoors

| # | Source | Dry-run command | Good output |
|---|--------|-----------------|-------------|
| 14 | nws_extras | `scripts/conditions_extras_pull.py --source nws_extras` | windGust/twentyFootWind (mph), WBGT (°F); AZZ036 coverage line (expect GAP today) |
| 15 | rise_water_temp | `scripts/conditions_extras_pull.py --source rise` | `feature_enabled:false` + no HTTP unless `FEATURE_FLAG_WATER_TEMP_RISE_6127` set (NEEDS_PROD_VERIFY) |
| 16 | wildfire | `scripts/conditions_extras_pull.py --source wildfire` | 0..N AZ incidents within ~100mi, sorted by distance, with acres/containment |
| 17 | az511 | `scripts/conditions_extras_pull.py --source az511` | SR-95/US-95/I-40 + Mohave/La Paz events + WZDx work zones (event API needs `AZ511_API_KEY`; WZDx keyless) |
| 18 | azgfd_fishing | `scripts/conditions_extras_pull.py --source azgfd` | Latest bulletins' Lake Havasu sections (set `AZGFD_SCRAPE_PROXY_URL`/`GAS_SCRAPE_PROXY_URL`; NEEDS_PROD_VERIFY) |

## Group E — Business & community

| # | Source | Dry-run command | Good output |
|---|--------|-----------------|-------------|
| 19 | food_inspections | `scripts/business_pull.py --source food_inspections` | Lake Havasu establishments w/ address/date/result from the latest PDF (NEEDS_PROD_VERIFY layout) |
| 20 | chamber_directory | `scripts/business_pull.py --source chamber` | Member list (enrichment signal `chamber_member=true`); NOT new providers |
| 21 | reddit_havasu | `scripts/business_pull.py --source reddit` | Recent posts: permalink + snippet + extracted business mentions (NEEDS_PROD_VERIFY egress) |
| 22 | downtown_lhc | `scripts/business_pull.py --source downtown` | Main Street members (enrichment signal `downtown_member=true`); events skipped |
| 23 | zillow_research | `scripts/business_pull.py --source zillow` | ZHVI/ZORI latest value for LHC + ZIPs (set `ZILLOW_ZHVI_CSV_URL`/`ZILLOW_ZORI_CSV_URL` if rotated) |
| 24 | p2c_bulletin | `scripts/business_pull.py --source p2c` | `backend_present: true/false` + note. If false: documented + stop (NEEDS_PROD_VERIFY) |

---

## Env vars / Casey actions before turning sources on

| Env var | For | Notes |
|---------|-----|-------|
| `OPENUV_API_KEY` | Task 0 UV primary | Free 50/day; EPA fallback works without it |
| `BANDSINTOWN_APP_ID` | #10 bandsintown | Free app_id registration |
| `EVENTBRITE_API_TOKEN` | #12 eventbrite_orgs | Private token |
| `AZ511_API_KEY` | #17 az511 event API | Free; **10 calls/60s** throttle (limiter already paces) |
| `AZGFD_SCRAPE_PROXY_URL` / `GAS_SCRAPE_PROXY_URL` | #18 azgfd_fishing | Cloudflare-protected origin |
| `FEATURE_FLAG_WATER_TEMP_RISE_6127` | #15 rise_water_temp | Default OFF (no HTTP) |
| `ZILLOW_ZHVI_CSV_URL` / `ZILLOW_ZORI_CSV_URL` | #23 zillow_research | Only if the published file URLs have rotated |
| `MOVIES_WEBEDIA_API_URL` | #11 movies | Override once the real XHR endpoint is captured |
| `LHC_NWS_ZONE_ID` | #14 nws_extras | Add `AZZ036` to catch Lake Wind Advisories |
| `OPENAI_API_KEY` | #25/#26 parks_rec_calendar/flyers | Vision LLM call. Already set in prod; without it the source fetches 0 (graceful) |
| `PARKS_REC_VISION_MODEL` | #25/#26 parks_rec | Override the vision model (default `gpt-4o`) |
| `PARKS_REC_FLYER_MAX` | #26 parks_rec_flyers | Cap flyer vision calls per run (default 8) |

## Integration step (NOT done in this branch)

For each approved source: add the persistence path (news_items store or
contribution-queue routing for news/events; reconciler enrichment for
provider-signal sources; conditions-cache registration for conditions sources)
and register it in the relevant orchestrator/cron. That is the work `--apply`
currently refuses to do.
