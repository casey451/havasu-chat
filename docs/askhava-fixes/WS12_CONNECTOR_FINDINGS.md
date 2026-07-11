# WS12 Coverage Connectors — build findings & source-access reality

**Prepared:** 2026-07-09, during the WS12 build session.
**Companion:** `WS12_CREDENTIAL_CHECKLIST.md` (the pre-build access list).

This records what each Phase-1 (public) connector source *actually* exposes when
probed live, so the connector decisions are auditable. The credential checklist
was written from the spec's assumptions; a few of those assumptions changed once
the sources were probed cold.

Every connector routes through the same pipeline: normalize → WS4 venue-match →
WS5 dedup → WS6 classify → **review queue** → gated publish → WS1 purge. None is
auto-approved (WS12 §4 "training wheels").

## Framework note

The `EventIngestClient` connector framework (`app/events/scrapers/`) already
existed from Phase 9b. Several sources the WS12 spec names as "new" were already
built and registered:

| Spec source | Status in repo |
|---|---|
| C2 Trumba (Mohave County Library) | **already built** — `lhc_library` (parses `trumba.com/calendars/havasu.ics`) |
| RiverScene Magazine (spec §12 c) | **already built** — `river_scene` (`RiverSceneV2Client`) |
| C3 Chamber (GrowthZone/ChamberMaster) | **already built** — `chamber` |
| City CivicPlus calendar | **already built** — `lhc_parks_rec` |

So the genuinely-new WS12 connector work is C5 (museum), C1 (Facebook, interface
only), C7 (venue-watcher), the salvaged youth connectors, and the Split Finger
directory add — plus the freshness heartbeat that exposes per-connector
last-success to the canary.

## Connector-by-connector

### C5 — Havasu Museum of History (Squarespace) ✅ BUILT
- **Probe:** `GET https://www.havasumuseum.com/upcoming-events?format=json` →
  `200 application/json`, `collection.typeName == "events-stacked"`, `items: []`.
- **Contract:** clean. Squarespace exposes the events collection as JSON with
  `startDate`/`endDate` (epoch ms), `fullUrl`, `excerpt`, `location`. No key.
- **Built as:** `SquarespaceEventsClient` (reusable base) + `HavasuMuseumClient`
  (`source=havasu_museum`). Weekly cron (`museum-events.yml`). Live smoke test:
  runs clean, returns 0 payloads (0 upcoming events today — correct, not a bug).
- **Reusable:** any Lake Havasu Squarespace venue (e.g. Grace Arts Live, if it
  runs an events collection) is a ~10-line subclass.

### C4 — AZ State Parks (Lake Havasu SP + Cattail Cove) ⏸ DEFERRED → venue-watcher
- **Probe:** `https://azstateparks.com/lake-havasu/events` 302-redirects to the
  park page; no `.ics`, no RSS, no `application/ld+json`, no `/api/*` JSON
  endpoint in the markup. The events calendar is JS-rendered with no accessible
  structured feed. The Lake Havasu SP events list is **currently empty**.
- **Decision:** do **not** ship a brittle HTML-scrape connector against a
  JS-rendered page with no stable contract. AZ State Parks is a better fit for
  the **venue-watcher (C7)**: hash-diff the events page weekly and extract on
  change into the review queue. Tracked as a C7 watch target.
- **Re-open if:** AZ State Parks publishes an iCal/JSON feed (many CMS platforms
  add one) — then it becomes a clean `ical_parse`-based connector like the
  library/city ones.

### C6 — Havasu 95 Speedway (MyRacePass) ⏸ DEFERRED → verify slug / venue-watcher
- **Probe:** the speedway is **not on MyRacePass** under any tried slug
  (`/tracks/havasu-95-speedway`, `havasu95speedway`, `havasu-95`,
  `lake-havasu-95-speedway` all 404). Their own site `havasu95speedway.com`
  runs a Squarespace-style site with a **PDF schedule** (`/s/2526Sched.pdf`) and
  currently shows *"See you in October!! 2026-2027 schedule will be released
  soon."* — the season is Oct–Apr, exactly as the spec predicted (zero summer
  rows is correct).
- **Decision:** the spec's "via MyRacePass" assumption is **stale** — there is no
  MyRacePass surface to wire. Two honest paths, both deferred until the 2026-27
  schedule posts (~October):
  1. If they return to MyRacePass, add a `MyRacePassClient` against the track's
     `/schedule` JSON.
  2. Otherwise, `havasu95speedway.com/schedule` is a **venue-watcher (C7)**
     target (hash-diff; the schedule is a PDF + page), or a Squarespace
     connector if their events live in a Squarespace collection.
- **Do not** build a connector now: off-season + no confirmed feed = nothing to
  test against and a high chance of building against the wrong endpoint.

### C1 — Facebook ⏸ INTERFACE ONLY (separate PR) — Casey access/spend decision
See the Facebook decision brief. Interface built to the same normalize/publish
contract; activation gated behind a future secret. No FB scraping in this build.

### C7 — Venue-watcher (separate PR)
Weekly hash-diff of feedless venue pages (Dynamix camps, Grace Arts Live,
AZ State Parks, `havasu95speedway.com/schedule`) → on change, extract → review
queue.

## Summary table

| Connector | Source contract | Decision | Yield today |
|---|---|---|---|
| C5 museum | Squarespace JSON | **built** (`havasu_museum`) | 0 (no upcoming) |
| C4 azstateparks | none (JS-only) | defer → C7 venue-watcher | 0 |
| C6 speedway | not on MyRacePass; off-season | defer → verify Oct | 0 (correct) |
| C1 Facebook | bot-walled | interface only; gated | n/a |
| C7 venue-watcher | page hash-diff | build | on change |

"Zero rows today" for C4/C5/C6 is the expected state, not a failure: it is
mid-summer and these are low-cadence/seasonal sources. The connectors exist so
that the *moment* those sources post, the events flow into the review queue.

---

## Addendum 2026-07-10 — Altitude booking connector (ROLLER) ✅ BUILT

Altitude Trampoline Park has "no events calendar" but a first-party **ROLLER**
booking storefront (`lakehavasu.altitudetrampolinepark.com/activitycamps`). Its
public JSON API gives the day-camp product + bookable dates + price directly.

**Endpoint contract (discovered via a one-shot Playwright XHR capture — pure curl
alone 404'd because the `/api/` path segment + the `x-api-key` header were only
visible in the live request):**
- base: `https://api.roller.app/api/checkout/activitycamps`
- headers: `x-api-key: altitudelakehavasu` (public storefront key = the subdomain,
  shipped to every browser — not a secret), `x-cell-id: a`
- `GET {base}/products` → catalog (list). Only "Activity Camp- Full Day" is
  event-worthy (ages 5–12, 9 AM–4 PM, member $26.99 / non-member $36.99); the
  rest are memberships / socks / cups.
- `GET {base}/availability?dateIndex=YYYYMMDD&days=N` → `[{date, availability}]`.
  **`days` is capped at 31** (42 → 400), so the connector pages the horizon.

**Connector `altitude_booking`** (`app/events/scrapers/altitude_booking.py`):
pure-HTTP, review-queue-first, price captured, `source_ref` = the booking URL
(doubles as the registration link). Emits one event per available **weekday**
camp date (day camps are M–F; availability is storefront-level). Live smoke:
returns real camp dates. Registered in the freshness canary + `ws12-connectors`
cron. Name contains "Camp" → lands on `/family/camps`.

**Reconcile with `havasu_youth` fixtures:** the weekly Glow / Junior Jump
*open-jump* sessions are **not** on this storefront — sibling checkout slugs
(`book-now`, `general-admission`, `openjump`, …) all return empty product lists.
So the hand fixtures **stay authoritative** for Glow/Junior Jump; `altitude_booking`
is authority for the **camps** (booking-platform > fixture, the WebTrac>flyer
pattern). If a general-admission slug is later found, retire the fixture overlap.

**Pattern for other watchlist venues:** a venue with "no events calendar" often
has a **bookable-products subdomain** (ROLLER / RunSwift / etc.), discoverable via
the booking links on their site or FB (`fbclid` URLs). Worth a probe before
assuming a venue needs the FB connector or a hand fixture.

---

## Addendum 2026-07-10 — Split Finger Athletics connector (RunSwift) ✅ BUILT

The "full scraper, separate effort" flagged during WS12 (provider directory row
added via `scripts/add_split_finger_athletics.py`; the dated camps/classes held
for this pass — see `docs/prompts/PROMPT_CC_SPLIT_FINGER_SCRAPER_2026-06-24.md`).

**Discovery surprise — the source moved, and improved.** The prompt doc assumed a
RunSwift Next.js SPA with "no capturable XHR → needs Playwright." Probing live
(2026-07-10, Browser/Playwright XHR capture + curl reproduction) found:

1. `splitfingerathletics.com` is now a **Wix** single-pager. Its Wix Bookings
   widget exposes exactly **one** service — an appointment-type "Private Lesson"
   (no fixed date → a Program, not an event). The endpoint
   (`POST /_api/bookings/v2/services/query`, `Authorization: <instance>` from the
   public `/_api/v1/access-tokens`) works, but yields **no event-worthy data**.
   Every "Camps / Classes / Lessons / Reserve A Cage" button on the Wix page
   still deep-links out to RunSwift. So "their booking is Wix" is only half-true.
2. **RunSwift now serves a clean first-party public JSON API** (the doc's
   "no capturable XHR" is stale) — pure-HTTP reproducible with just a User-Agent,
   **no key** (even simpler than ROLLER's `x-api-key`). This is where the events
   live, so the connector targets RunSwift, not Wix.

**Endpoint contract** (facility `760`, `getFacilityBySubdomain?subdomain=split-finger-athletics`):
- base: `https://book.runswiftapp.com/api/public`
- `GET {base}/camp?facilityId=760&registrationStatus=OPEN&…` → `[camp]`
- `GET {base}/class?facilityId=760&registrationStatus=OPEN&…` → `[class]`
- `GET {base}/lesson?facilityId=760&…` → private lessons (on-demand appointments)
- Session dates live under each item's `service.bookingGroups[].bookings[]`
  (UTC `startTime`/`endTime`; facility tz `America/Phoenix`, UTC-7 no DST);
  price `prices.basePrice.cost`; ages `min/maxAgeLimit`.

**Connector `split_finger`** (`app/events/scrapers/split_finger.py`): pure-HTTP,
review-queue-first.
- **Camps → one multi-day Event each.** RunSwift names ("Softball Summer Session
  #1") carry no camp keyword, so the title gets a `— Camp` suffix — the gate the
  `/family/camps` bucket filters on (`family_hub._CAMP_RE`), same trick as
  `lhc_bmx`'s "BMX <name>". Description carries `Ages X–Y · From $N` so the
  camps-card detail parser (`_AGES_RE`/`_PRICE_RE`) fills in.
- **Classes → one Event per session occurrence**, bounded by `CLASS_HORIZON_DAYS`
  (45). Recurring classes collapse at render time into one "runs regularly" feed
  entry (WS5 series, keyed on title+location+start_time) — exactly how the gym /
  pool schedules render — so the year-round Strength/Conditioning class doesn't
  flood the feed. Each occurrence carries a distinct `?classId=&date=` URL so it
  lands as its own contribution (and is the Register link) and dedups on re-run.
- **Private lessons + cage rentals are NOT events** (on-demand appointments /
  bookable inventory) — the provider directory row + the site's booking links
  already cover those. Skipped on purpose.

Registered in the freshness canary + `ws12-connectors` cron (schedule + dispatch).
**Live dry-run 2026-07-10 (`today`):** 34 payloads — 4 camps (Jul 13–15 & 20–22,
9 AM / 11:15 AM, $70) + 30 class occurrences across 4 classes
(Strength/Conditioning 25 → collapses to one series card, TRX & Tabata 1,
Team Speed & Agility 3, Mom's Softball Night 1). First batch sent to Casey for
approval before any publish.
