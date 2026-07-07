# WS6b Phase 1 — WebTrac as the Parks & Rec datetime authority (plan)

**Status:** planned (Phases 0, 2, 3, 4 shipped 2026-07-07 as PR #748/#749/#750/#751).
This is the deeper fix that Phases 2–4 are the interim for.

## The problem this closes
The monthly **flyer** (a calendar-grid image, vision-LLM parsed) is currently the
de-facto datetime authority for P&R programs, and it is unreliable — it produced
"Glow in the Dark Painting, Tue Jul 7, 5:30 AM, venue Jane Camlin" (reality: Wed
Jul 8, 5:30 PM; Jane Camlin is the instructor). Phases 2–4 hardened ingest to
*quarantine* untrustworthy rows and backfilled the already-live ones. But
quarantine makes the calendar **incomplete**; the real fix is a **trustworthy
source** for the datetime/venue so those programs can publish correctly.

**Goal:** the city's **registration catalog is the datetime/venue authority**; the
CivicPlus iCal is second (meetings only); the monthly flyer is demoted to
**discovery-only** (it tells us an event *exists*; it never supplies the when/where
that goes live).

## Source inventory (verified 2026-07-07)
- **WebTrac registration catalog — `register.lhcaz.gov`** — the authoritative
  program catalog ("Registration for all programs completed online"). **Probed:
  a JS-driven splash + session/CSRF flow** — a bare `search.html?module=AR` bounces
  to `3.1 WEB - Splash`; there is no plain-GET catalog or JSON/iCal export exposed.
- **CivicPlus iCal (`iCalendar.aspx?catID=23`)** — civic **meetings only**
  (Council, Board of Adjustment, P&R Advisory Board). Zero activity programs.
  Real `TZID=America/Phoenix` datetimes. Already ingested by
  `app/events/scrapers/lhc_parks_rec.py`.
- **Monthly grid flyer** (`/185/Parks-Recreation`, ImageRepository image) — one
  image, **no per-event links**. Vision-parsed (unreliable).
- **Individual promo flyers** — separate ImageRepository images that, per Casey,
  **link out via `ayrs.io` short links** to a specific `register.lhcaz.gov`
  activity page (authoritative for that one program).
- **Known facility list** (venue schema) — captured from the page and encoded in
  `lhc_parks_rec_calendar.PARKS_REC_FACILITIES` + the place-signal classifier.

## Architecture options (pick one; they can combine)
### A. Headless-browser WebTrac catalog scraper  *(most coverage, most cost)*
Drive `register.lhcaz.gov` with Playwright (already a dep): load the splash, open
the Activity Search, page the catalog, and read each activity's begin date/time,
facility, fees, ages, and instructor. Map to `Contribution(entity_type=event|
program)` via the existing `parks_rec_loader` seam.
- **Pros:** full, authoritative coverage of every bookable program.
- **Cons:** brittle (session/CSRF/JS, WebTrac markup churn); needs a browser in
  the scrape job; must be a good citizen (rate-limit, cache, respect the site).
- **Effort:** high. Needs its own reliability canary.

### B. `ayrs.io` → activity-page follow  *(promo-scoped, lighter)*
For each **promo flyer**, extract its `ayrs.io` link, resolve it to the
`register.lhcaz.gov` activity page, and read that one program's authoritative
datetime/venue. Still needs the same session/JS handling for the activity page,
but scoped to one activity at a time (and only for promos, which is where the
ayrs.io links live).
- **Pros:** narrower, follows the city's own linking; naturally per-program.
- **Cons:** does **not** cover the monthly *grid* (no links there); promo-only.

### C. Manual WebTrac export → existing loader  *(most reliable, needs Casey)*
Casey exports the WebTrac activity catalog (CSV/report) on a cadence; the existing
`parks_rec_loader.load_webtrac_records` ingests it (that loader already exists and
expects snapshots). No scraper.
- **Pros:** reliable, zero scraping risk, uses machinery already built.
- **Cons:** manual step; freshness depends on the export cadence.

## Discovery → authority matching (shared by all options)
1. Flyer vision = **discovery-only**: it yields `(title, approx-date)` candidates,
   never a published datetime. (Phases 2–4 already hold anything ambiguous.)
2. For each discovery, **match to a WebTrac entry** by fuzzy title + a small date
   window; on match, publish with WebTrac's **authoritative** date/time/venue/
   instructor (instructor → `Event.host`, never the venue).
3. **No match → quarantine** (`pending_review`), per "incomplete beats wrong."
4. Re-runs idempotent (synthetic-URL / reconcile keys as today); America/Phoenix
   throughout.

## Recommendation
Ship **C now** (reliable, uses existing loader, unblocks correct publishing this
week) and **build A next** for hands-off coverage, with **B** as the promo path if
the ayrs.io links prove stable. Gate the flyer to discovery-only the moment a real
authority (C or A) is feeding, so the interim quarantine can relax.

## Acceptance
- A P&R program publishes with a datetime/venue that **matches WebTrac**, not the
  flyer, for the golden set (Glow, the Craft Series, Tiny Tots).
- The §14.3 nightly canary re-verifies every *future* P&R event against the
  authority and pages on drift.
- Flyer-only (unmatched) programs are held, never published with flyer datetimes.
