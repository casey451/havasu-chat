# Phase 9 — Event Source Feed Research

**Author:** general-purpose research agent
**Date:** 2026-05-19
**Companion to:** `outputs/phase_9_architecture_design.md` (§5 Five sources table)
**Status:** factual findings only — operator-actionable

This document captures the **concrete URLs, scrape formats, and data shapes** for the 5 event sources Phase 9 will ingest into the ENTITY table. All five surfaces were probed live on 2026-05-19. Probes were run via Python `urllib.request` (no curl/wget per policy); raw payload shapes pasted below are from actual responses.

---

## Source 1: Lake Havasu Area Chamber of Commerce — community events calendar

- **Canonical URL:** `https://business.havasuchamber.com/community-event-calendar/Search?showpastevents=false`
- **Platform:** GrowthZone (formerly ChamberMaster). TenantId 3629; TenantKey `57b1c578-12d2-4cee-be17-6cfaf6a292e4`. Page header confirms: `<!-- TenantId: 3629; TenantKey: 57b1c578-12d2-4cee-be17-6cfaf6a292e4 -->`.
- **Scrape format:** **HTML with schema.org microdata + JSON-LD** (server-side-rendered, NO public iCal/RSS export). Tried `/events/catgid/0/ical`, `/events/calendar/ical`, `/events.ics`, `/list/calendar/ical`, `/community-event-calendar.rss` — all 404. Per GrowthZone's own docs the iCal feed URL is admin-only; not exposed unauthenticated.
- **List page yields:** **70 detail-page slugs in one fetch** of `?showpastevents=false`. Each event card has schema.org microdata. Card-level snippet:

  ```html
  <div class="card-body gz-events-card-body">
      <h5 class="card-title" itemprop="name">
          <a href="https://business.havasuchamber.com/community-event-calendar/Details/ami-trivia-1627610?sourceTypeId=Website"
             class="gz-card-title gz-event-card-title" itemprop="url">AMI Trivia</a>
      </h5>
      <h5 class="gz-event-card-time">4:00 PM - 6:00 PM</h5>
      <meta itemprop="startDate" content="5/19/2026 4:00:00 PM">
      <meta itemprop="endDate"   content="5/19/2026 6:00:00 PM">
  </div>
  ```

- **Detail page yields:** Each `Details/<slug>-<id>?sourceTypeId=Website` page is a full `itemtype="http://schema.org/Event"` block with:

  ```html
  <h1 class="gz-pagetitle" itemprop="name">Taste of Havasu 2026</h1>
  <h5 class="gz-subtitle">
      Thursday, October 22, 2026 (8:00 AM - 5:00 PM)
      (<abbr title="(GMT-07:00) Mountain Time - Arizona">MST</abbr>)
  </h5>
  <div class="row gz-event-description" itemprop="about">
      <h3 class="gz-subtitle">Description</h3>
      Annual fundraiser to benefit the LHUSD teachers and schools...
  </div>
  <meta itemprop="eventStatus" content="EventScheduled">
  ```

- **Auth:** none (public scrape).
- **Update cadence:** Continuous publishing during business hours (member-driven). Daily scrape is appropriate per design doc §5 (cadence: Daily 04:00 LHC local).
- **Scrape disposition:** **GREEN** — list page is fully server-rendered, includes all 70 events with `startDate`/`endDate`/`name`/`url` in microdata. Detail page extra fields (venue, description, organizer) are also clean HTML.
- **RRULE applicability:** **expanded instances**. The list page shows the same event ID family repeating (e.g., 4 separate `ami-trivia-162761X` slugs for May-June Tuesdays). GrowthZone expands recurring events into per-occurrence detail pages. **No explicit RRULE.** Phase 9's `event_recurrence.py` does NOT need to expand anything; just ingest each occurrence.
- **Effort estimate:** **3–4 hours** (list-page parse + detail-page parse + microdata extraction + tests).
- **Notes / gotchas:**
  - 70 events on a single page is a comfortable batch — no pagination needed for Phase 9 V1.
  - `sourceTypeId=Website` is a tracking param; safe to strip when computing `source_url` for dedup, OR keep verbatim (it's a stable click-through URL).
  - The detail page also has the **MST/MDT** abbr title literal — Arizona doesn't observe DST so always `America/Phoenix`. Confirm with `app/core/timezone.py`.
  - The "Time" field `4:00 PM - 6:00 PM` parses cleanly via `dateutil.parser`.
  - GrowthZone is a managed SaaS — HTML template is **highly stable** (very low template-churn risk).

---

## Source 2: Go Lake Havasu (tourism DMO) — events listings

- **Canonical URL:** `https://www.golakehavasu.com/events/`
- **Platform:** **Simpleview CMS** (the standard DMO platform). Confirmed by `dmsEventName` / `eventListings` / `listingType` config JSON embedded in page, and Simpleview-style imager URLs (`/imager/cmsimages/...`).
- **Scrape format:** **HTML with JSON-LD (`@type: Event`)**. Tried `/events/?ical=1`, `/events/feed/` (404), `/plugins/core/get_events/`, `/includes/rest_v2/plugins_events_events_by_date/` — Simpleview's public REST endpoints exist but require an API key on their hosted aggregator (`cs.simpleviewnc.com`). The DMO's own site does not expose this publicly.
- **List page yields:** Event detail links in `/events/<slug>/` format. Visible on the live list: `/events/ami-trivia-tournament/`, `/events/uncorked-bunco/`, `/events/sip-mingle-shop/`, `/events/sip-mingle-shop-1/`. The list page is **partly client-side hydrated** (the `Upcoming Events` widget reads from a Vue component), so HTML scraping of the list yields the link set but date ranges only via per-detail fetch.
- **Detail page JSON-LD shape (from `/events/ami-trivia-tournament/`):**

  ```json
  {
    "@context": "http://schema.org",
    "@type": "Event",
    "name": "AMI Trivia Tournament",
    "description": "TAP TRIVIA TUESDAYS  Think fast. Tap faster.Every Tuesday from 5–7 PM...",
    "startDate": "2025-11-18T17:00:00-07:00",
    "endDate":   "2025-11-18T19:00:00-07:00",
    "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
    "eventStatus": "https://schema.org/EventScheduled",
    "image": {"@type":"ImageObject","url":"https://www.golakehavasu.com/imager/files_idss_com/.../...png"},
    "location": {"@type":"Place","address":"AMI Trivia Tournament","name":"AMI Trivia Tournament"},
    "mainEntityOfPage": "https://www.golakehavasu.com/events/ami-trivia-tournament/",
    "organizer": {"@id":"https://www.golakehavasu.com/#identity"},
    "url": "https://www.golakehavasu.com/events/ami-trivia-tournament/"
  }
  ```

- **Auth:** none (public scrape).
- **Update cadence:** Daily (per design doc §5: Daily 04:30 LHC local). Tourism DMO sites republish nightly.
- **Scrape disposition:** **GREEN** — JSON-LD per-detail is canonical structured data with ISO 8601 timestamps. List → enumerate `/events/<slug>/` links, then per-detail fetch + parse `@type: Event` JSON-LD.
- **RRULE applicability:** **expanded instances**. Like the Chamber, Simpleview shows recurring events ("Every Tuesday" in description) as a single canonical detail page with one `startDate`/`endDate`. The `description` contains the human-readable recurrence hint but it's not machine-structured. For V1, treat each scraped page as a single event; recurrence-expansion is a V1.5 enhancement.
- **Effort estimate:** **3–4 hours** (list-link discovery + per-detail JSON-LD extraction + tests).
- **Notes / gotchas:**
  - `location.address` is sometimes the event name (not a real address) — venue normalization will need a fallback.
  - The Simpleview-hosted REST endpoint pattern `cs.simpleviewnc.com/feeds/events.cfm?apikey=...` IS a real Simpleview thing, but for golakehavasu.com it requires a tourism-board-issued API key. **Operator follow-up:** if the chamber/DMO can be persuaded to share a key, that flips this from HTML-scrape to JSON API. Document as a V1.5 ask.
  - Page is 194 KB and has heavy JS framework — fetch only `/events/<slug>/` detail pages (not the list page) to minimize bandwidth after V1 link discovery.
  - Per-detail JSON-LD timestamps are ISO 8601 with explicit `-07:00` offset (Arizona). Clean to parse.

---

## Source 3: RiverScene Magazine — local events listings

- **Canonical URL (RSS feed):** `https://riverscenemagazine.com/events/feed/`
- **Canonical URL (sitemap, used by existing scraper):** `https://riverscenemagazine.com/wp-sitemap.xml` → `wp-sitemap-posts-events-*.xml`
- **Platform:** WordPress 6.9.4 (custom theme by Neil Betrue; `Events` is a custom post type).
- **Scrape format:** **RSS (XML) + HTML** for full detail. The RSS feed at `/events/feed/` returns standard RSS 2.0 with `title`, `link`, `pubDate`, `description`, `content:encoded`. Event detail pages have a labelled table (Start Date / End Date / Time / Venue / Organizer / Website / Facebook / Event Category) that the **existing** `app/contrib/river_scene.py` already parses.
- **Sample RSS item (from live `/events/feed/`):**

  ```xml
  <item>
    <title>The Substitutes</title>
    <link>https://riverscenemagazine.com/events/the-substitutes/</link>
    <dc:creator><![CDATA[Shannon Terenti]]></dc:creator>
    <pubDate>Fri, 15 May 2026 05:56:27 +0000</pubDate>
    <guid isPermaLink="false">https://riverscenemagazine.com/events/</guid>
    <description><![CDATA[Bringing energy, nostalgia, and a fresh edge to every stage...
      Show: 7:00 p.m. No Cover Charge ]]></description>
    <content:encoded><![CDATA[
      <div>Bringing energy, nostalgia, and a fresh edge...</div>
      <div>Show: 7:00 p.m.<br>No Cover Charge</div>
    ]]></content:encoded>
  </item>
  ```

- **Sample detail page (from existing scraper, `app/contrib/river_scene.py` lines 35-48):** event details live in an HTML table with the label set:

  ```
  Start Date | End Date | Event Category | Facebook | Organizer | Time | Venue | Website
  ```

- **Auth:** none (public scrape).
- **Update cadence:** WordPress reports `hourly` in `<sy:updatePeriod>`. RiverScene's actual publication is multiple events per week. Phase 9 design: Daily 05:00 LHC local.
- **Scrape disposition:** **GREEN — already implemented**. Phase 9 adapter (`RiverSceneV2Client` in design doc §5.8) is a thin wrapper around the existing `fetch_sitemap_urls` + `fetch_and_parse_event` from `app/contrib/river_scene.py`.
- **RRULE applicability:** **no-recurrence**. Each RiverScene event is a single post with a date range (`Start Date` / `End Date` columns); recurring events are published as separate posts. Existing scraper already handles `event_end_date != event_start_date`.
- **Effort estimate:** **2 hours** (thin EventIngestClient wrapper + protocol-conformance tests).
- **Notes / gotchas:**
  - `<guid>` is shared across all items (`https://riverscenemagazine.com/events/`) — **do NOT use `<guid>` for dedup**. Use `<link>` (the per-event permalink), which matches the existing scraper's behavior.
  - RSS body is a teaser; the structured fields (Time, Venue, Organizer, etc.) only appear on the detail HTML page. The existing scraper already does sitemap → detail-page-fetch, which is the right pattern. The RSS feed is a complementary discovery surface (recently-published) if needed.
  - The existing scraper drops events whose `start_date < today`, which is the desired behavior for Phase 9.

---

## Source 4: Lake Havasu City Library — branch events calendar

- **Canonical URL (iCal):** `https://www.trumba.com/calendars/havasu.ics`
- **Canonical URL (RSS):** `https://www.trumba.com/calendars/havasu.rss`
- **Canonical URL (JSON):** `https://www.trumba.com/calendars/havasu.json`
- **Canonical URL (Atom XML):** `https://www.trumba.com/calendars/havasu.xml`
- **Embed page:** `https://www.mohavecountylibrary.us/lake-havasu-city-branch/` (this is the human-facing page; the library is operated by **Mohave County Library District**, not the City of LHC — calendar published via Trumba SaaS).
- **Platform:** **Trumba Calendar Services 0.11.25718** (a major library/civic SaaS).
- **Scrape format:** **iCal (preferred) + JSON + RSS + Atom** — all FOUR are publicly exposed, no auth. Recommend **iCal** for ingestion (best structure, includes RRULE/recurrence).
- **Sample iCal entry (from live `/calendars/havasu.ics`):**

  ```
  BEGIN:VEVENT
  SUMMARY:LHC - Bereavement Support Group - Conf
  DTSTART;TZID=America/Phoenix:20260520T094500
  DTEND;TZID=America/Phoenix:20260520T110000
  X-MICROSOFT-CDO-ALLDAYEVENT:FALSE
  X-TRUMBA-CUSTOMFIELD;NAME="Organization Name";ID=32970;TYPE=SingleLine:Beacon of Hope Hospice
  X-TRUMBA-CUSTOMFIELD;NAME="Location Details";ID=24894;TYPE=CustomAsset:1770 N. McCulloch Blvd - Lake Havasu City\, AZ 86403 / 928-453-0718
  X-TRUMBA-CUSTOMFIELD;NAME="Audience";ID=24893;TYPE=CustomAsset:Non-Library Event
  DTSTAMP:20260427T150132Z
  DESCRIPTION:Organization Name: Beacon of Hope Hospice<br>Location Details: 1770 N. McCulloch Blvd...<br>Contact: Joshua Chavez 928-854-4200<br>Hospice Bereavement support group.
  CATEGORIES:Lake Havasu City Branch
  UID:http://uid.trumba.com/event/201145370
  X-TRUMBA-LINK:https://www.mohavecountylibrary.us/lake-havasu-city-branch/?trumbaEmbed=view%3devent%26eventid%3d201145370
  END:VEVENT
  ```

- **Sample JSON entry (from `/calendars/havasu.json`):**

  ```json
  {
    "eventID": 191326595,
    "template": "Mohave County Library",
    "title": "Get Crafty! Adult DIY @ the Library",
    "description": "<p align=\"center\"><strong>Ages: 18+...</strong></p>",
    "locationType": "In-Person",
    "startDateTime": "2026-05-19T09:30:00",
    "endDateTime":   "2026-05-19T11:30:00",
    "allDay": false,
    "startTimeZoneOffset": "-0700",
    "endTimeZoneOffset":   "-0700",
    "repeats": "Monthly on the 3rd Tuesday of the month",
    "seriesID": 191326588,
    "detailImage": {"url":"https://www.trumba.com/i/...jpg","alt":"","size":{"width":879,"height":1137}},
    "customFields": [
      {"fieldID":24890,"label":"Event Category","value":"Arts & Crafts, Hobbies/Nature","type":17},
      {"fieldID":24893,"label":"Audience","value":"Kids","type":17},
      {"fieldID":65094,"label":"Room","value":"Storytime Room","type":17},
      {"fieldID":24895,"label":"Library Branch","value":"<a href=\"...\">Lake Havasu City Library</a>","type":17}
    ],
    "permaLinkUrl":    "https://www.mohavecountylibrary.us/lake-havasu-city-branch/?trumbaEmbed=view%3devent%26eventid%3d191326595",
    "eventActionUrl":  "https://www.trumba.com/eventactions/Havasu#/actions/s430kyeaxyb470j0sxmcwge58d",
    "categoryCalendar": "Lake Havasu City Branch"
  }
  ```

- **Auth:** none (public SaaS-hosted feed).
- **Update cadence:** Continuous publishing by library staff (`pubDate` values seen ranging from October 2025 to March 2026). Phase 9 design: Weekly Sunday 03:00 LHC local. **Recommend bumping to daily** — the feed is so structured and small that polite scraping daily is cheap, and library events change weekly.
- **Scrape disposition:** **GREEN — best-in-class**. Trumba publishes a standards-compliant iCal feed with RRULE support and custom-field metadata.
- **RRULE applicability:** **yes-expanded-instances by default** in the iCal export, but the JSON feed has a human-readable `repeats` field ("Monthly on the 3rd Tuesday of the month", "Every Tuesday through May 30, 2026"). Trumba expands recurring events into individual `VEVENT` blocks in the iCal output — Phase 9 just ingests each as it appears. **No need for `dateutil.rrule` expansion.**
- **Effort estimate:** **2–3 hours** (iCal parsing with `icalendar` library + custom-field extraction + tests).
- **Notes / gotchas:**
  - The host is `mohavecountylibrary.us`, NOT the City of LHC. Provider/sponsor attribution in ENTITY should reflect Mohave County Library District (use `provider_name = "Mohave County Library District — LHC Branch"` to be precise).
  - The `CATEGORIES:Lake Havasu City Branch` field is the geographic filter — confirm all events in `havasu.ics` are LHC-branch (a quick scan of fetched 14 KB confirms yes; calendar ID `749094` in Atom feed = "Lake Havasu City Branch").
  - `UID:http://uid.trumba.com/event/<eventID>` is the stable dedup key. Use this for `source_url` (NOT the embed URL with the dynamic `trumbaEmbed` query string).
  - "Non-Library Event" rows (e.g., conference room rentals like the Christian men's meeting) are visible in the feed — Phase 9 should likely filter via the custom field `Audience=Non-Library Event` to skip these, OR show as a separate category (operator choice).
  - Python `icalendar` library handles `X-TRUMBA-CUSTOMFIELD` extras cleanly as `Component[...]` access.
  - `eventActionUrl` is the registration link (separate from `permaLinkUrl` which is the info page).

---

## Source 5: City of Lake Havasu City — parks-and-rec / city calendar

- **Canonical URL (RSS, all categories):** `https://www.lhcaz.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml`
- **Canonical URL (iCal, all categories):** `https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?feed=calendar` (returned HTML on direct GET — appears to require a `catID` param; use per-category iCal below)
- **Canonical URL (iCal, default city events category — CID 23):** `https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?catID=23&feed=calendar`
- **Canonical URL (iCal, holidays/observances — CID 14):** `https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar`
- **Human-facing landing:** `https://www.lhcaz.gov/Calendar.aspx` (CivicPlus URL pattern: `/Calendar.aspx?EID=<event_id>` for detail pages)
- **Platform:** **CivicPlus / CivicEngage** (confirmed by `/Calendar.aspx`, `/RSSFeed.aspx?ModID=58&CID=...`, `/common/modules/iCalendar/iCalendar.aspx` URL family — these are CivicPlus's standard module URLs, used by hundreds of US municipal sites).
- **Scrape format:** **RSS (XML) + iCal**, both public, no auth.
- **Sample RSS item (from live `RSSFeed.aspx?ModID=58&CID=All-calendar.xml`):**

  ```xml
  <item>
    <title>Planning and Zoning Commission</title>
    <link>https://www.lhcaz.gov/Calendar.aspx?EID=1017</link>
    <pubDate>Fri, 15 May 2026 09:44:23 -0700</pubDate>
    <description><![CDATA[<strong>Event date:</strong> May 20, 2026 <br>
      <strong>Event Time: </strong>09:00 AM - 11:59 PM<br>
      <strong>Location:</strong> <br>92 Acoma Blvd. N.<br>Lake Havasu City, AZ 86403]]></description>
    <calendarEvent:EventDates> May 20, 2026 </calendarEvent:EventDates>
    <calendarEvent:EventTimes>09:00 AM - 11:59 PM</calendarEvent:EventTimes>
    <calendarEvent:Location>92 Acoma Blvd. N.Lake Havasu City, AZ 86403</calendarEvent:Location>
    <guid isPermaLink="false">https://www.lhcaz.gov/Calendar.aspx?EID=1017/639144422630000000</guid>
  </item>
  ```

- **Sample iCal `VEVENT` (from `iCalendar.aspx?catID=23&feed=calendar`):**

  ```
  BEGIN:VEVENT
  DESCRIPTION: https://www.lhcaz.gov/calendar.aspx?EID=1026
  DTEND;TZID=America/Phoenix:20260624T235900
  DTSTAMP;TZID=America/Phoenix:20260515T094906
  DTSTART;TZID=America/Phoenix:20260624T090000
  LAST-MODIFIED;TZID=America/Phoenix:20260515T094906
  LOCATION: - 92 Acoma Blvd. N.  Lake Havasu City AZ 86403
  SEQUENCE:0
  SUMMARY:Board of Adjustment (Canceled)
  UID:1026
  URL:/common/modules/iCalendar/iCalendar.aspx?feed=calendar&catID=23
  END:VEVENT
  ```

- **Auth:** none.
- **Update cadence:** Weekly (event publication is staff-driven; mostly board meetings). Phase 9 design: Weekly Sunday 03:30 LHC local. Adequate.
- **Scrape disposition:** **GREEN for civic meetings; YELLOW for parks-rec activity content.** See gotcha below.
- **RRULE applicability:** **expanded instances** — each meeting occurrence appears as its own `VEVENT` (e.g., monthly Planning & Zoning shows as separate UIDs `1017`, `1024`, `1022` etc.). **No explicit RRULE strings in the iCal**, just per-occurrence VEVENTs.
- **Effort estimate:** **2–3 hours** (per-feed iCal/RSS parser + tests).
- **Notes / gotchas:**
  - **Critical content gap:** The CivicPlus `/Calendar.aspx` only carries **city-government meetings** — Planning & Zoning, City Council, Parks-Rec Advisory Board, Board of Adjustment. It does NOT carry parks-rec **activity** content (swim classes, dance classes, youth camps, etc.). Those live in two surfaces already scraped:
    - **WebTrac** (`https://register.lhcaz.gov/webtrac/web/`) — `app/contrib/webtrac.py`
    - **Aquatic open-swim schedule** (`https://www.lhcaz.gov/parks-recreation/open-swim-schedule`) — `app/contrib/lhcaz_aquatic.py`
  - For Phase 9 the **city/parks-rec source** should be understood as: the CivicPlus default-calendar feed (board meetings + occasional public events). The activity/program content is already in ENTITY via the Phase 5.7 sidecar work.
  - `LOCATION` in iCal has a leading ` - ` prefix and concatenated address — light cleanup needed.
  - `UID` is just a numeric `EID` (not a URN). Use `https://www.lhcaz.gov/Calendar.aspx?EID=<UID>` as the canonical `source_url`.
  - The RSS feed uses a custom `calendarEvent:` XML namespace with structured `EventDates`, `EventTimes`, `Location` children — easier to parse than `description` if you only need the basics. iCal is still preferred for `DTSTART`/`DTEND` with `TZID`.
  - `Calendar.aspx` returns only ~8 KB of HTML on direct GET — this is a JS-shell page; the actual calendar widget is hydrated client-side. **Use RSS/iCal — do not try to scrape the HTML calendar.**
  - The "(Canceled)" suffix in event titles is the city's actual notation — handle by either skipping these or marking `event_status = "cancelled"`.

---

## Summary table — ease-of-scrape ranking + recommended dispatch order

| Rank | Source | Format | Disposition | Effort | Dispatch order (recommend) |
|------|--------|--------|-------------|--------|----------------------------|
| 1 | **RiverScene Magazine** | RSS + HTML (existing scraper) | **GREEN — already shipped** | 2 hr (adapter) | **Phase 9.0** — thin wrapper, smoke test the EventIngestClient pattern with known-good source first |
| 2 | **LHC Library (Trumba)** | iCal + JSON + RSS + Atom | **GREEN — best-in-class** | 2–3 hr | **Phase 9.1** — proves the iCal-feed path; cleanest data shape; library events are easy to QA |
| 3 | **LHC City (CivicPlus)** | RSS + iCal | **GREEN** | 2–3 hr | **Phase 9.2** — proves the RSS/iCal-with-municipal-noise path; low event volume → safe to debug |
| 4 | **Chamber (GrowthZone)** | HTML + schema.org microdata + JSON-LD | **GREEN** | 3–4 hr | **Phase 9.3** — first HTML-scrape; 70 events per page; high-velocity production source |
| 5 | **Go Lake Havasu (Simpleview)** | HTML + JSON-LD per-detail | **GREEN** | 3–4 hr | **Phase 9.4** — Vue-hydrated list page; per-detail JSON-LD is canonical |

**Total estimated scraper-authoring effort: 12–16 hours** (well within the design doc §11.x budget of `1 day × 4 new scrapers + 0.25 day adapter = 4.25 days`).

### Dispatch rationale

- Start with **RiverScene** because the parsing logic already exists; the only deliverable is the `EventIngestClient` adapter. This validates the new abstraction before authoring net-new scrapers.
- **Library next** because Trumba is the gold-standard format (true iCal with custom fields, no HTML parsing). Any debugging here is about the framework, not the source.
- **City CivicPlus** third — same iCal-ish pattern as Library but with municipal noise (cancellations, all-day meetings). Forces the team to confront edge-case data quality before going to HTML scrape sources.
- **Chamber + Go Lake Havasu last** because they are HTML-scrape (highest template-churn risk per design doc §10 threat model), but both have schema.org structured data inside their HTML, making them more tractable than pure HTML parsing.

### Cross-cutting findings

1. **No source requires auth or API keys.** All five publish public feeds suitable for a polite daily/weekly cron.
2. **All five sources expand recurring events into individual instances.** Phase 9's `app/core/event_recurrence.py` does NOT need to expand RRULEs at scrape-time — recurrence-expansion is only needed if the operator later wants to **collapse** these into UI groupings ("This event happens every Tuesday").
3. **Time-zone handling: all sources are `America/Phoenix` (MST, no DST).** Trumba and CivicPlus emit explicit `TZID=America/Phoenix` in iCal. Go Lake Havasu emits `-07:00` offset. Chamber emits MM/DD/YYYY local time in microdata (no offset — assume Phoenix). RiverScene's existing scraper already handles this.
4. **Dedup strategy:** for sources with stable IDs (Chamber `1627610`, GLH slug, RiverScene permalink, Trumba `eventID`, CivicPlus `EID`), use the canonical detail URL as `source_url`. Multi-source dedup (per design doc §6.x) will need a name+date+venue fuzzy match because the same event will appear under different IDs in each source.
5. **HTML-scrape risk mitigation:** for Chamber + Go Lake Havasu, **prefer the structured-data extractors** (schema.org microdata, JSON-LD) over CSS selectors. Microdata/JSON-LD survives visual template redesigns; CSS selectors do not.

### Pre-positioned operator follow-ups (V1.5)

- **Chamber:** ask Lake Havasu Chamber of Commerce admin to share their **GrowthZone iCal feed URL** (admin-only feature per GrowthZone docs). Would flip Chamber from HTML-scrape to iCal feed, eliminating template-churn risk entirely.
- **Go Lake Havasu:** ask Lake Havasu Tourism Bureau (`info@golakehavasu.com`) for a **Simpleview events API key** for `cs.simpleviewnc.com/feeds/events.cfm?apikey=...`. Would flip GLH to structured JSON.
- **LHC parks-rec activities:** the city's CivicPlus calendar does NOT carry rec-program content. Phase 9's "parks-rec" source label should be reviewed — either rename to "City of LHC public meetings" (truthful) or accept that the WebTrac + Aquatic scrapers (already shipped) cover the activity content and the CivicPlus feed is a meeting-focused supplement.

### Sources

- [Community Event Calendar - Lake Havasu Area Chamber of Commerce](https://www.havasuchamber.com/community-event-calendar/)
- [Chamber search/list page (GrowthZone-rendered)](https://business.havasuchamber.com/community-event-calendar/Search)
- [Chamber sample detail page (Taste of Havasu 2026)](https://business.havasuchamber.com/community-event-calendar/Details/taste-of-havasu-2026-1546335?sourceTypeId=Website)
- [Explore the Latest Lake Havasu Events Here (Go Lake Havasu)](https://www.golakehavasu.com/events/)
- [Go Lake Havasu sample event detail (AMI Trivia)](https://www.golakehavasu.com/events/ami-trivia-tournament/)
- [RiverScene Magazine — Events](https://riverscenemagazine.com/events/)
- [RiverScene Magazine — Events RSS feed](https://riverscenemagazine.com/events/feed/)
- [Lake Havasu City Branch — Mohave County Library](https://www.mohavecountylibrary.us/lake-havasu-city-branch/)
- [Trumba Library calendar iCal feed](https://www.trumba.com/calendars/havasu.ics)
- [Trumba Library calendar JSON feed](https://www.trumba.com/calendars/havasu.json)
- [Trumba Library calendar RSS feed](https://www.trumba.com/calendars/havasu.rss)
- [Lake Havasu City Calendar (CivicPlus)](https://www.lhcaz.gov/Calendar.aspx)
- [LHC CivicPlus RSS — all categories](https://www.lhcaz.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml)
- [LHC CivicPlus iCal — CID=23 (default city events)](https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?catID=23&feed=calendar)
- [GrowthZone iCal feed documentation](https://helpdesk.growthzone.com/kb/article/1576-calendars/)
- [Simpleview Ticketed Event Feed Integration](https://www.simpleviewinc.com/company/partners/ticketed-event-feed/)
