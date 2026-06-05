# Ask Hava — Source Expansion Research (June 4, 2026)

Deep-dive audit of current data sources plus web research into new candidate sources.
Five parallel research agents covered: news/media, events/entertainment, government/civic,
outdoor/conditions, and community/business. **Every recommended feed below was fetched live
on 2026-06-04 and confirmed working** unless marked otherwise.

---

## Current source inventory (from the codebase)

**Providers (6):** Google Places API, OSM Overpass, golakehavasu.com partner directory,
USA Pickleball/Places2Play, PDGA, WebTrac parks & rec.
**Events (6):** golakehavasu.com, Chamber (GrowthZone), RiverScene events, library Trumba
iCal, lhcaz.gov CivicPlus calendar, civic scrapers (transit/airport/library).
**Conditions (8):** NWS (current/forecast/alerts/sunset), USGS lake level 09427500, USGS
water temp 09426630 (feature-gated), AirNow AQI, OpenUV, GasBuddy + Google fuel fallback.
**Verification (7):** NPI, AZ ROC, BBB, AZDHS, AZMVD, AZRE, AZCC cosmetology/towing.
**Other:** contributions queue, Facebook scrape via OpenClaw ingest API, operator CSVs.

**Biggest gap: zero news ingestion.** Also missing: council agendas, road conditions,
wildfire, fishing reports, nightlife/live-music events, health inspections, new-business
signals, school district, Reddit/community voice.

---

## TOP RECOMMENDATIONS (prioritized by value ÷ effort)

### Tier 1 — Ingest now (verified, free, structured, low effort)

| # | Source | Endpoint (verified live) | What it gives | Effort |
|---|--------|--------------------------|---------------|--------|
| 1 | **lhcaz.gov News Flash RSS** | `https://www.lhcaz.gov/RSSFeed.aspx?ModID=1&CID=All-newsflash.xml` | Road closures w/ dates & streets, PD announcements, city press releases | Trivial — feedparser already in stack |
| 2 | **lhcaz.gov Alert Center RSS** | `https://www.lhcaz.gov/RSSFeed.aspx?ModID=63&CID=All-0` | Emergency alerts (currently 0 items — poll hourly) | Trivial |
| 3 | **Today's News-Herald** ("the News-Herald") | News sitemap: `https://www.havasunews.com/tncms/sitemap/news.xml` | Daily hard local news: council, P&Z, crime, development. ~10+ items/day with titles, dates, rich keywords | Low. **Caveat:** TownNews/BLOX metered paywall — headline + first ~2 paragraphs (lede) are served free; rest is ROT47-obfuscated. Ingest title/lede/keywords + link out, or buy a digital sub for full text. The classic BLOX `?f=rss` feed is dead on this site — use the sitemap. Per-topic RSS search feeds DO work, e.g. weekly fishing column: `https://www.havasunews.com/search/?q=fishing+report&t=article&f=rss&s=start_time&sd=desc&l=5` |
| 4 | **RiverScene news articles** (events already ingested) | WP REST: `https://riverscenemagazine.com/wp-json/wp/v2/posts` (also `/feed/`) | Full-text free community news, school stories, business spotlights, 2–4 posts/wk. Cleanest news path found — JSON, no auth, no paywall. Extends existing river_scene module | Low |
| 5 | **Legistar Web API — council agendas/minutes** | `https://webapi.legistar.com/v1/lakehavasucity/events?$top=10&$orderby=EventDate+desc` (JSON, no auth) | Council, P&Z, Board of Adjustment meetings w/ dates, agenda/minutes PDF links (`View.ashx?M=A&ID=..`). City migrated off CivicPlus AgendaCenter to Legistar | Low. Flagship feature: "what's on the council agenda Tuesday?" |
| 6 | **NWS gridpoint extra fields** (existing integration!) | `https://api.weather.gov/gridpoints/VEF/141,19` | Already-fetched payload contains `windGust`, `heatRisk`, `wetBulbGlobeTemperature`, `twentyFootWind` — boater wind + extreme-heat answers at zero new cost. Confirm Lake Wind Advisory zone AZZ036 is in the alert filter | Parse-only |
| 7 | **LHUSD (school district) Thrillshare API** | Live feed: `https://thrillshare-cmsv2.services.thrillshare.com/api/v2/s/322922/live_feeds?page=1` · Events: `.../api/v2/s/322924/events?start_date=..&end_date=..` · iCal: `.../api/v4/o/19160/cms/events/generate_ical` | Board meetings, school calendar, closures, registration. JSON + iCal (reuse Trumba parser) | Low |
| 8 | **AllEvents.in Lake Havasu** | `https://allevents.in/lake-havasu-city` (+ `/this-weekend`) | ~130 rolling events incl. **bar/nightlife events no current source has** (Flying X Saloon, Sky Lounge, The Office). Serves clean markdown to bots; JSON-LD on detail pages | Low–Med. Dedupe on (title, date, venue) vs golakehavasu/RiverScene |
| 9 | **Bureau of Reclamation RISE — Parker Dam water temp** | Catalog 4371; item **6127 = daily water temp °F at Parker Dam**; 6126/6130 releases; `https://data.usbr.gov/rise/api/result?itemId=6127&dateTime[after]=...` (send `Accept: application/json`; re-verify from prod IP) | Authoritative "is the lake warm enough to swim" — replaces the flaky Bill Williams sensor (currently returning sentinel −100000, down since 5/21) | Low–Med |
| 10 | **NIFC WFIGS wildfire ArcGIS API** | `https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query?where=POOState='US-AZ'&f=json` | Live AZ fire incidents (name, acres, containment), geo-queryable to ~100 mi of Havasu. Free, no key | Low |

### Tier 2 — Strong candidates (small friction: key signup, scrape, or records request)

| # | Source | Access | Notes |
|---|--------|--------|-------|
| 11 | **az511 / ADOT road conditions** | Official REST API, free key via az511 account; 10 calls/60s. Docs: `https://az511.gov/developers/doc`. Also keyless WZDx work-zone feed `https://az511.com/api/wzdx` and unofficial JSON `https://az511.gov/List/GetData/Incidents` | "Is SR-95 closed?" — filter to SR-95/I-40/Mohave. Poll 5–15 min |
| 12 | **Mohave County food inspections** | Monthly PDFs (verified through Apr 2026): `https://www.mohave.gov/departments/public-health/environmental-health/reports/` e.g. `/media/ldcfiinh/food-safety-inspections_2026-04-apr.pdf` | Establishment, address, date, status, Lake Havasu section. pdfplumber parse. Differentiating feature, zero legal risk |
| 13 | **Chamber member directory** (events already ingested) | GrowthZone `FindStartsWith?term=A..Z` returns plain HTML member listings w/ detail pages | Membership = legitimacy signal Google can't give. Gentle rate + attribution |
| 14 | **Bandsintown** | Free Events API (register app_id), query by location + radius | Regional concerts: BlueWater (Parker), Laughlin casinos — covered nowhere else. Tag "nearby/regional" |
| 15 | **AZGFD fishing report** | Monthly GovDelivery bulletins (plain HTML): archive at `azgfd.com/fishing-2/where-to-fish/fishing-report-archive/`; FishAZ WP REST `https://fishaz.azgfd.com/wp-json/wp/v2/posts?search=havasu` (azgfd.com is Cloudflare-protected to datacenter IPs — verify from prod / use proxy) | Pair with News-Herald weekly fishing column RSS (#3) |
| 16 | **r/LakeHavasu Reddit** | Public `.json` endpoints (`/r/LakeHavasu/new.json`, `search.json`) w/ descriptive UA, ~10 req/min. (reddit.com blocked from the research sandbox; endpoints fine from prod) | Community voice: "best mechanic?", openings/closings chatter. ToS gray zone — store permalink + snippet, attribute and link out. Don't train on it |
| 17 | **LHC business licenses + AZ Business Center** | No public register found. (a) Records request to BusinessLicense@lhcaz.gov for monthly new-license list; (b) **eCorp is DEAD (decommissioned Jan 2, 2026)** → new portal `https://arizonabusinesscenter.azcc.gov/`, no API — consider ACC bulk-records request | Earliest "new business in town" signal. One email each |
| 18 | **LHCPD Daily Bulletin (P2C)** | `https://p2c.lhcaz.gov/dailybulletin.aspx` — CentralSquare P2C, AJAX-loaded; probe known `/jqHandler.ashx?op=s` JSON backend | Daily arrests/incidents/accidents. Med effort |
| 19 | **ABC15 Lake Havasu RSS** | `https://www.abc15.com/news/region-northern-az/lake-havasu.rss` (Scripps, free, full text) | Sporadic but covers major incidents free of paywall; cheap to poll |
| 20 | **Zillow Research CSVs** | `https://www.zillow.com/research/data/` — free ZHVI/ZORI by city/ZIP (86403/04/06), monthly, attribution required | Housing-market context. Don't scrape listing pages |
| 21 | **MCSO press releases** | `https://www.mohave.gov/departments/sheriff/press-release/` — HTML scrape, ~2–3/wk | River/desert incidents outside city limits |
| 22 | **Downtown Lake Havasu** | WordPress site w/ member pages + The Events Calendar (likely `/events/?ical=1` + WP REST) | Main Street directory + grand openings. Events syndicate from golakehavasu — dedupe |

### Tier 3 — Seasonal / niche / static

- **Havasu 95 Speedway** (`havasu95speedway.com/schedule`) — Squarespace HTML; race nights Oct–Apr. Activate seasonally.
- **Signature event sub-schedules** — desertstormlhc.com, havasuballoonfestival.com/schedule-of-events, havasuboatshow.com. Marquee events already listed by golakehavasu; the value is day-by-day detail ("what time is the Shootout Saturday"). Quarterly seed refresh, not a crawler.
- **Movie showtimes** — Movies Havasu is JS-rendered (Webedia CMS, theater id X0QCN — has an XHR JSON API worth one sniff); Star Cinemas second screen. Or scrape a showtimes aggregator.
- **AZ State Parks** — fees/hours verified ($20 Mon–Thu, $25 Fri–Sun, $5 individual; 54 campsites, 13 cabins, 3 ramps). Static knowledge + scrape `azstateparks.com/alerts` for closures. Reservations (Tyler/US eDirect) would need reverse-engineering — defer.
- **Craggy Wash / BLM** — dispersed camping, $5/night, 14-day, **not reservable** → no availability feed exists; encode rules as static knowledge.
- **Sun/moon/stargazing** — `api.sunrise-sunset.org` verified (free, no key) or compute in-process with `astral`. Cheap add.
- **Eventbrite organizer feeds** — public search API is dead (2020), but `GET /v3/organizations/:id/events/` works; seed with local org IDs (e.g. Havasu Community Health Foundation org 40584556073). Filter recurring LDS worship-service spam.
- **Senior Center** (`lakehavasuseniorcenter.com/current-events`) — small HTML scrape.
- **CareerOneStop API** — free US-DOL jobs API (Indeed's API is dead; scraping it is ToS-blocked).
- **Kingman Daily Miner / Mohave Valley Daily News** — same TownNews `tncms/sitemap/news.xml` pipeline as News-Herald if county/tri-state coverage ever wanted. Parker Pioneer now lives inside havasunews.com (`/parker_pioneer/` prefix); old parkerpioneer.net domain is dead.
- **InciWeb RSS** (`inciweb.wildfire.gov/incidents/rss.xml`) — verified; redundant with WFIGS but trivial.
- **Mohave County BOS** — agendas in Laserfiche (`lfp.mohave.gov/bos/Browse.aspx?startid=743016`), no RSS; county open-data ArcGIS hub for GIS layers.

### Skip / defer (researched, not worth it)

- **Havasu Scanner Feed** — the most-followed real-time safety source (~36k FB followers) but membership-gated ($15/mo app), no API. **Pursue as a partnership conversation, not a scrape.**
- **Yelp Fusion** — free tier gone; $7.99–14.99/1k calls, and ToS restricts storing review text (the main differentiator). Attributes-only batch maybe later.
- **TripAdvisor Content API** — 5k free calls/mo but heavy display requirements, mostly overlaps Google Places.
- **Nextdoor** — real Display APIs exist (Search, Trending, Public Agency Feed) but access is a discretionary form (`forms.gle/ub9nd2LacrLH4fJ67`). Submit the form, then wait. Never scrape (hard ToS prohibition).
- **Meetup** (paid API, tiny local scene), **AllTrails/Fishbrain/GolfNow/Windy** (no viable free APIs), **MLS** (LHC is WARDEX/Momentum, broker-gated — not ARMLS), **Indeed scraping**, **Burbio scraping** (use it only to discover org calendars), **UniSource outage map API** (returns 403 "3rd-party use not permitted" — deep-link users instead), **NOAA marine forecasts** (don't exist for inland Lake Havasu), **recreation.gov availability** (nothing reservable nearby), **KNTR radio** (audio-only archives), **Legacy.com obituaries** (no API, restrictive), legacy Havasu forums (dead — community is in Facebook groups, already OpenClaw's beat).

---

## Suggested implementation order

1. **Sprint 1 (all verified, ~no new deps):** lhcaz.gov News Flash + Alert RSS → existing feedparser path; RiverScene WP REST news; News-Herald news sitemap (title/lede/keywords); Legistar events API; parse extra NWS gridpoint fields.
2. **Sprint 2:** LHUSD Thrillshare; AllEvents.in (with cross-source dedupe keyed on normalized title+date+venue); RISE Parker Dam water temp (prod-IP verify); WFIGS wildfire; sunrise-sunset/astral.
3. **Sprint 3:** az511 key + integration; food-inspection PDF parser; Chamber directory scrape; Bandsintown app_id; AZGFD fishing (proxy-aware); ABC15 RSS.
4. **Parallel paper trail (no code):** records request emails for LHC business licenses + ACC bulk filings; Nextdoor API access form; Havasu Scanner Feed partnership outreach; decide on a News-Herald digital subscription for full-text rights.

## Cross-cutting notes

- **Dedupe:** AllEvents/Eventbrite/golakehavasu/RiverScene will triple-list marquee events. Key on normalized (title, start date, venue) in `decide_ingest` before adding aggregators.
- **Paywall ethics/legal:** News-Herald body text beyond the lede is paywalled (ROT47-obfuscated). Do not decode it — that's circumvention. Lede + link, or subscribe.
- **Sandbox vs prod egress:** azgfd.com, dffm.az.gov, open-meteo, and RISE result endpoints failed from the research sandbox's datacenter IP but are expected to work from Railway (or via the existing Bright Data/Nimble proxy env vars). Re-verify each from prod before building.
- **Existing proxy infra** (`GAS_SCRAPE_PROXY_URL` pattern) covers the Cloudflare-protected targets (AZGFD).
