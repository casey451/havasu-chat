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
