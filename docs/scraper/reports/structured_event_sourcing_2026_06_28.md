# Structured event sourcing — live verification (2026-06-28)

Investigation for "sustainable event sourcing" Item 2 (expand structured iCal
coverage so flyer content comes from the city feed). **Verified live against
lhcaz.gov and register.lhcaz.gov, not the deployed askhava site.**

## TL;DR

Expanding the **city CivicPlus iCal** is a dead end — it has only three
categories and the non-meeting ones carry holidays or nothing. The structured
home for the Parks & Rec program content we OCR off flyers (craft series, swim
lessons, aquatic) is **WebTrac** (`register.lhcaz.gov`) — and it is **already
ingested into the catalog and running in production** (corrected 2026-06-28; an
earlier draft and a stale `webtrac_pull.py` docstring wrongly said "not yet
wired"). The `parks-rec-scrapes` cron runs `run_scrapes.py` (writes a webtrac
snapshot) → `parks_rec_load.py` → `app.contrib.parks_rec_loader`, which routes
recurring sections to a **Program** (class path) and single-day sections to an
**Event**. Prod today: **22 active WebTrac Programs + 42 WebTrac Events.**

So the flyer/OCR vision sources were a **redundant, lower-fidelity duplicate** of
content WebTrac already carries (the craft series, etc.) — and the source of the
cross-contaminated descriptions. **PR #605 closes the loop**: it stops those OCR
sources from auto-publishing (they now land pending for review). The genuinely
flyer-only remainder (full moon / Kids Fishing, public Open Swim 12–4 PM) stays
on that review-gated path — the intended design. **No new pipeline is needed.**

## City CivicPlus iCal — full category inventory (live)

The calendar at `https://www.lhcaz.gov/Calendar.aspx` exposes exactly **three**
category checkboxes (`chkCalendarID_*`):

| catID | Name | iCal content (live) | Useful to ingest? |
|------:|------|---------------------|-------------------|
| 14 | **Events** | 11 VEVENTs, **all federal holidays** (New Year's, Christmas, Independence Day across years) | No — noise |
| 23 | **Meetings** | 8 VEVENTs — City Council, Planning & Zoning, Board of Adjustment, Parks & Rec Advisory Board | **This is what we currently pull** (`CIVIC_ICAL_URL` catID=23). Civic governance, not programs |
| 24 | **Aquatic Center Swim and Exercise Schedule** | **0 VEVENTs** — valid VCALENDAR, empty body | No — the label exists but the feed carries nothing |

`iCalendar.aspx` with no `catID` returns an empty body; the all-calendar RSS
(`RSSFeed.aspx?ModID=58&CID=All-calendar.xml`) returns only 3 items. So there are
**no additional iCal categories** to add — the prompt's assumed catIDs ~22–26
carrying Aquatic/Parks programs do not exist in the feed.

**Conclusion:** the current single hardcoded `catID=23` is, ironically, the only
city iCal category with real (non-holiday) content — civic meetings. There is
nothing useful to expand to. Wiring catID=14 would inject holidays; catID=24 is
empty.

## WebTrac — the real structured source (already ingested)

`app/contrib/webtrac.py` parses `register.lhcaz.gov` (Vermont Systems WebTrac)
into Program→Section records with date/time/days/ages/cost/availability, and
`app/contrib/parks_rec_loader.py` **already loads those into the catalog** on the
`parks-rec-scrapes` cron (recurring → Program, single-day → Event). Live keyword
probes confirm the content:

- **`craft` → 11 sections**: "Art & Craft Classes" — incl. **June 26 (F) 17:30**
  and **June 27 (Sa) 13:00**. These are exactly the "Free Summer Craft Series"
  rows we have been cleaning by hand — structured, re-pullable, correct dates and
  ages.
- **`swim` / AQUA type → 20 sections, 4 programs**: Frogs / Guppies / Starfish /
  Jr Guards swim **lessons**. Structured.
- **`fishing` → 0 sections**: the "Strawberry Full Moon Fishing" / "Kids Fishing"
  program is **not** in WebTrac.
- **Public "Open Swim 12–4 PM" → 0**: WebTrac AQUA carries only lessons, not the
  public open-swim sessions.

So WebTrac covers the **craft series and swim lessons** (today's flyer OCR pain),
but **not** fishing or public open-swim.

## What is structured-sourceable vs. genuinely flyer-only

| Content | Sustainable structured source | Status |
|---------|-------------------------------|--------|
| Free Summer Craft Series | **WebTrac** ("Art & Craft Classes") | **ingested** (Program + single-day Events) |
| Swim lessons (Frogs/Guppies/…) | **WebTrac** (AQUA) | **ingested** (Programs) |
| Free Swim Day / public swim | **go_lake_havasu** JSON-LD (the swim-card we fixed) | live |
| Civic meetings | city iCal catID=23 | live (current source) |
| **Full moon / Kids Fishing** | none found (WebTrac 0, iCal 0) | **flyer-only → review-gated (#605)** |
| **Public Open Swim 12–4 PM** | none found in WebTrac | **flyer-only → review-gated (#605)**, unless go_lake carries it |

## Conclusion (corrected) — the pipeline exists; #605 completes it

There is **no new pipeline to build.** WebTrac → catalog ingestion already exists
(`parks_rec_loader`) and runs in prod, and it already does the right routing
(recurring → Program/class path, single-day → Event). The product decision the
old `webtrac_pull.py` docstring deferred was, in fact, already made and shipped.

What was actually wrong was the **second, redundant flyer-OCR path** publishing
lower-fidelity duplicates of the same content (with the contamination). **PR #605
fixes that** by review-gating the three vision sources. Combined with the
survivor-rank fix (PR #603, authoritative source wins on merge), the structured
WebTrac row is the one users see; the flyer OCR only supplies the genuinely
flyer-only remainder, now via human review.

### Coverage audit (read-only)

`scripts/audit_flyer_vs_webtrac_coverage_2026_06_28.py` classifies the 38 live
flyer-originated events: **7** already merged onto a WebTrac row (`webtrac_url`),
**2** match a distinct WebTrac event/program, **29** `flyer_only` — but that last
bucket is a *conservative upper bound* (the matcher keys on exact title+date; many
rows there, e.g. Line Dancing / Tiny Tots / Art Camp / Adventure Camp, are Parks
& Rec programs WebTrac carries under a different title). Genuinely flyer-only =
fishing, special one-offs, public open-swim.

### Optional cleanup (gated — Casey's call)

The 38 live flyer-originated rows predate #605. The `webtrac_url` / `webtrac_match`
ones are redundant duplicates and safe to retract; the rest want a human glance
(some are real programs WebTrac also has under a cleaner title; a few are
genuinely flyer-only). A dry-run retraction can be scoped to the audited
duplicates — **not run without sign-off.**
