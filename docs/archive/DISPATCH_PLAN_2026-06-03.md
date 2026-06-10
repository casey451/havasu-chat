# Dispatch Plan — fix everything, fast (2026-06-03)

Execution plan for all findings in `SITE_AUDIT_LIVE_2026-06-03.md`, `AUDIT_TRIAGE_2026-06-03.md`,
`GAP_SWEEP_2026-06-03.md`, and the launch-relevant items from `docs/FEATURE_OPPORTUNITIES_2026-06-03.md`.
Designed for parallel dispatch to Cursor / Claude Code / Cowork agents **with zero clarifying questions**:
§2 pre-answers every judgment call; §3 gives each packet exclusive file ownership; §4 is the
paste-ready brief per packet.

## §0 Hard rules (paste into EVERY packet brief verbatim)

1. Work in a **dedicated git worktree** on a fresh branch off latest `origin/main`
   (`git worktree add ../wt-<packet> -b <branch>`). NEVER work in the main checkout —
   other sessions are active there.
2. NEVER push or merge to `main`. Open a PR and STOP. Merging is Casey's gate (main auto-deploys to prod).
3. Before every commit: `python -m pytest -q` green AND `ruff check .` clean (whole repo, not per-file).
   PowerShell: use `.venv\Scripts\python.exe -m pytest -q`.
4. Stage by explicit path. NEVER `git add -A`. ASCII only in edited files (use `--` and `'`).
5. Touch ONLY the files listed under "Files owned" in your brief. If a fix seems to require another
   file, note it in your PR description as a follow-up — do NOT edit it.
6. Do NOT create Alembic migrations unless your brief explicitly designates you the migration owner.
7. No prod DB access, no `railway` commands, no secrets, no env-var changes.
8. Update/add tests in the same commit as behavior changes. New behavior = new test.
9. Your PR description must list: every finding ID you closed (e.g. B-01, A3, C7), test count delta,
   and anything you deliberately did NOT do.

## §1 Wave 0 — Casey + assistant session, BEFORE dispatch (blocks nothing below from being *written*, but blocks merging/verifying)

| # | Task | Who |
|---|------|-----|
| 0.1 | **Two-builds investigation (A1/B-04):** In Railway dashboard check (a) replica count, (b) whether an old deployment is still receiving traffic, (c) any CDN/edge cache. Two different builds of /events-ui are serving simultaneously — one with a day-stale "Today" bucket. Kill the stale path; confirm one build serves 10/10 consecutive fetches. | Casey (dashboard) + assistant |
| 0.2 | Confirm prod schema/SHA: `alembic current` == `alembic heads`; deployed SHA == origin/main. Confirm PR #63 state. | Casey terminal |
| 0.3 | Rotate prod Postgres password + Bright Data key (exposed in chat per GOLAKEHAVASU closeout). | Casey |
| 0.4 | Confirm the scraper-cohort session's file scope. If it touches `app/events/scrapers/*`, `app/events/dedup.py`, or `app/contrib/event_reconciler.py`, hold WP-4 until it lands; otherwise WP-4 dispatches in Wave 1. | Casey |
| 0.5 | Approve or amend the §2 Decision Lock. One pass through one table = no agent ever asks a question. | Casey |

## §2 Decision Lock (PROPOSED defaults — Casey approves/amends once, then they are law)

| ID | Decision | LOCKED ANSWER |
|----|----------|---------------|
| DL-1 | Legal pages vs accounts (B-06, M-32, A4) | Rewrite /terms + /privacy factually: disclose magic-link email accounts, favorites storage, chat-log retention. Strip ALL bracketed placeholders and lawyer notes. Keep a single line "Under legal review" at top. Replace the phantom "feedback button" references with the support email AND ship real per-response feedback (WP-2). |
| DL-2 | Navigation identity (M-31, L1, C1, C2) | Converge on the Lake Light bottom tab bar (Home/Events/Ask/Explore/Map/Saved) on EVERY page ≤900px, all template families. Desktop ≥900px: one shared topbar (the map_c `ll-desktop-topbar` pattern) on every page. Sandstone stays the visual skin; mode pills remain on marketing pages as secondary chips. Grid fixed to `repeat(6,1fr)`. |
| DL-3 | Product name (N-19) | **"Ask Hava"** everywhere in titles and UI copy; "Hava" allowed as the persona's first-person name inside chat responses only. Email/domain refs stay havasuchat.com for now. |
| DL-4 | Google reviews (N-05, P-6, D4) | Keep excerpts. Label each block "From Google reviews", clamp excerpts to ~40 words with no per-review star glyphs, max 3, link "Read all on Google" using the place_id. Show numeric rating only at >=3 reviews (DL-12), applied identically on cards and profiles. |
| DL-5 | Map scope rows (M-26) | Collapse Collections row into the Categories row; one chip set, labels matching the canonical taxonomy. |
| DL-6 | Search (D-7, A2, F4) | Wave 1: header search input on every page, GET to `/chat?q=`. Wave 2: real `/search` keyword results page (providers + events, plain list, phone numbers visible) and the header input points there; chat becomes the "Ask instead" secondary CTA. |
| DL-7 | Photos on unclaimed profiles (F21, A5) | Use the already-stored category-card photo as the profile cover. Gallery (>1 photo), menu, offers stay claim-gated. Lock copy becomes "Add more photos, your menu, and offers". |
| DL-8 | Out-of-area listings (D-9) | Keep, with a visible "~40 min away · Parker area" style distance hint on card + profile. |
| DL-9 | "On the Water" identity (D-10) | Keep the name. Membership = marinas, rentals, lake tours, launch/fuel docks, lake-adjacent lodging. Detailing/trails/golf/biking move to their correct categories during the W1 data triage; chips regenerate from actual subtypes. |
| DL-10 | Low-data records (D-11) | No hard hiding. Bury via the liveness dampener (WP-10) + unrated cards get a "No reviews yet" badge and sort after rated peers within the same tier. |
| DL-11 | Claim CTA copy (D-3) | Generic per-vertical-safe copy: "Claim this listing to add photos, details, and offers." No "menu" outside eat-drink. Lock block compressed below the Good-to-know block. |
| DL-12 | Rating display threshold | Stars render only at >=3 reviews; below that show "New / few reviews yet". Cards and profiles read the same field via one helper. |
| DL-13 | Sponsor surfaces (D-8, N-03, N-22) | Remove the sponsored loading interstitial entirely. Rename /sponsor packages to match the actually-rendered slots ("Featured around town"). No other sponsor work this wave. |
| DL-14 | Events on venue profiles (D-13) | Already built (`venue_events_region.html`) — fix the missing CSS link (E5) and ship it. No new work. |
| DL-15 | Event template family | `events_sandstone.html` + `event_permalink.html` are canonical. `events_lake_light.html` and its JS are DELETED (E1/E2). Event detail pages move to the Fraunces/Figtree font stack (fixes the Georgia fallback). |
| DL-16 | "Tonight"/calendar slot policy (B3, M-19, H-1) | "Tonight" = next not-yet-started event today preferring one-offs; if none, label switches to "Today" / "Tomorrow". Calendar visible pills prioritize one-offs/specials; recurring classes go into the "+N" count. Recurring series get per-venue collapse on /events-ui. |
| DL-17 | Gas station identity (A6, G-3) | Provider slugs keyed per station (brand + street), e.g. `maverik-sweetwater`. Rows with no confident provider match render unlinked rather than wrong-linked. |
| DL-18 | Trust pages (F8) | Ship /about, /help (FAQ), /contact as static Lake Light pages + "Report wrong info" mailto link on every provider/event page footer. Plain language, no legalese. |
| DL-19 | Brand tagline (D9) | Footer tagline becomes: "Honest. Local. Built in Lake Havasu." |
| DL-20 | Open-now control (C7, L5) | "Open now" becomes a filter chip (not a sort). Default sort gets `is_open_now` as a tiebreak after favorites score (C-3). All "All" chips preserve every other active query param. |

## §3 File-ownership matrix (Wave 1 — exclusive; collisions are a packet bug)

| Packet | Owns (exclusive) |
|--------|------------------|
| WP-1 Shell | `app/templates/sandstone_base.html`, `app/templates/_partials/*` (incl. NEW `lake_light_base.html`, shared topbar/footer partials), `app/static/styles/sandstone.css`, `app/static/styles/lake_light.css`, `app/static/sandstone.js`, all Lake Light page templates' head/nav/footer blocks (`chat.html` shell only, `today.html`, `login*.html`, `account*.html`, `claim_*.html`, `categories_index.html`, `privacy_doc.html`, `not_found.html`, `map_c.html` chrome only), NEW `about.html`/`help.html`/`contact.html` + routes file `app/home/static_pages.py` |
| WP-2 Chat | `app/templates/chat.html` (body only, not shell), `app/static/js/chat-new.js`, NEW `app/static/styles/chat_cards.css`, `app/api/routes/chat.py` (feedback wiring only) |
| WP-3 Events | `app/templates/events_sandstone.html`, `app/templates/event_permalink.html`, `app/static/styles/sandstone_events.css`, `app/home/router.py`, `app/home/queries.py`, `app/events/queries.py`, `app/templates/home_sandstone.html`, NEW `app/api/routes/calendar_feed.py` |
| WP-4 Ingest (gated on §1 0.4) | `app/events/scrapers/go_lake_havasu.py`, `app/events/scrapers/base.py`, `app/events/dedup.py`, NEW `scripts/backfill_event_venues.py`, NEW `scripts/dedupe_events_cross_source.py` |
| WP-5 Browse | `app/categories/*`, `app/templates/category_sandstone.html`, `app/static/styles/sandstone_category.css` |
| WP-6 Profiles | `app/templates/provider_profile.html`, `app/static/styles/sandstone_profile.css`, `app/providers/queries.py`, `app/templates/components/hava_card.html`/`venue_events_region.html` |
| WP-7 Routing/hygiene | `app/main.py`, `app/v1/*`, sitemap/robots generators, DELETIONS (E2 list), `app/templates/sponsor_landing.html`, `app/templates/contribute` template + `contribute.css` |
| WP-8 Gas + modes | `app/templates/gas_prices.html`, `app/static/styles/sandstone_gas.css`, `app/api/routes/gas.py`, `app/templates/mode_sandstone.html`, `app/static/styles/sandstone_modes.css` |
| WP-10 Liveness | NEW `app/core/liveness.py`, `app/core/ranking.py`, `app/search/ranking.py`, `app/search/routes.py`, `app/api/routes/category_pages.py`, `scripts/places_load.py`, NEW `scripts/backfill_liveness.py`, **THE ONLY Wave-1 Alembic migration** |

Seams to respect: WP-1 owns every shared CSS file — WP-2/3/5/6/8 put new rules in their packet-owned
CSS files only. WP-3 owns `home/router.py` entirely (events + calendar + Tonight). WP-5 owns the legacy
category surface; WP-10 owns `category_pages.py` (modern surface). WP-7 owns `main.py` (incl. ED-5 https
og:url fix at ~:688).

## §4 Packet briefs (paste-ready; prepend §0 + the §2 table to each)

### WP-1 — Shell, nav, base templates, a11y, type floor
Branch `feat/wp1-shell`. Closes: L1, L2, L6, L14, F5, C1, C2 (shell half), C3, C10 (active_tab), E3, E4, E7, D9/DL-19, N-23, M-31, DL-18 pages.
1. Create `app/templates/lake_light_base.html`: one `<head>` (Fraunces+Figtree via `<link>` not @import; drop Playfair/Poppins), meta-description block, shared `ll-desktop-topbar` (from map_c) shown >=900px, `ll-utility-header` slot, shared footer (Privacy · Terms · About · Contact + DL-19 tagline), bottom-nav partial, `active_tab` block. Migrate every hand-headed Lake Light template to extend it. Fix bottom nav grid to `repeat(6,1fr)`.
2. Add the same bottom-nav partial to `sandstone_base.html` <=900px with main bottom padding; add desktop topbar links Events + Sign in to the Sandstone header.
3. `sandstone.js`: ☰ opens a real menu (or delete the glyph); "Explore all" first click toggles megamenu containing a final "All categories →" link to /categories; drop `role="menu"`/`menuitem` (plain disclosure + `aria-controls`); single-child columns collapse to bare links; one canonical name per category (matching nav labels).
4. Type/tap pass: body 16px floor, nav/ribbon labels >=13px, primary CTAs >=48px, AA contrast on muted tokens.
5. A11y: `:focus-visible` token block in sandstone.css; skip-link to `#main` in both bases; `prefers-reduced-motion` guards; remove empty `<nav aria-label="Primary">` instances; correct `active_tab` per page (today=home bug, login/claim=saved bug); no active tab on non-nav routes.
6. Header search input (DL-6 Wave-1 form, GET → `/chat?q=`) in both base headers.
7. NEW static pages /about, /help, /contact (DL-18) on the new base; add "Report wrong info" mailto link to the shared footer.
8. Tooltip-only content (D1): render ribbon `title=` text as visible sub-labels; temp tile links to /today; remove `cursor:pointer` from non-links. Ribbon staleness: visible "stale" badge replaces the middot.
Tests: template-render smoke tests for every migrated page (nav present, one h1, skip link); CSS not unit-testable — include a PR screenshot checklist (375px and 1280px for: home, chat, today, events-ui, a category, a profile, login, 404).

### WP-2 — Chat surface
Branch `feat/wp2-chat`. Closes: B-01, N-01, N-02, N-03, A4 (feedback half), F1, L10, E3 (chat items).
1. NEW `chat_cards.css` (loaded by chat.html): constrain all inline SVG/img in response cards (`max-height:1em` for icons, `max-width:100%` + fixed aspect for photos); style suggestion chips + Photo button; fix missing-whitespace runs by adding separators in the card renderer in `chat-new.js` ("Pizza Spots — 5 of 12", "Call (928)… · Directions").
2. Restore feedback thumbs + Save + Share on each answer card: `POST /api/chat/feedback` exists and `chat_log_id` is returned; port the handlers from the orphaned `chat.js` pattern into `chat-new.js`.
3. Remove the hardcoded `#ll-loading-overlay` SPONSORED markup (DL-13). Add one-line disclaimer near the composer: "Hava can make mistakes — confirm hours by phone."
4. Composer: `aria-label="Ask Hava"`; fix `aria-live` + `aria-hidden` contradiction on the overlay; composer clearance above the bottom nav (z-index/padding, coordinate values with the WP-1 partial but implement in chat_cards.css).
5. Result cards link to `/provider/{slug}` profiles.
Tests: feedback POST wiring test; JS escape-helper test if renderer touched; template smoke.

### WP-3 — Events surfaces (list, detail, calendar, home strip)
Branch `feat/wp3-events`. Closes: B-03, E-1, E-5, B-02, A3, B1, B2, B3, B5, B6, B7, M-16, M-17 (render half), N-09, N-15, N-25, DL-16, F3, F (ics feed), 12 (Tonight), E5-adjacent end times.
1. `app/events/queries.py`: fix `event_window_for_chip` boundary math (Sunday `(6-weekday)%7` collapse); anchor all buckets to `now_lake_havasu().date()`; add explicit This Weekend (Sat–Sun) window. Unit tests for Wed/Sat/Sun anchor dates.
2. `app/home/router.py` events windows (~:561-567): separate count query from row query; honest "N total · showing M · See all →" per window; one-offs guaranteed slots before featured/recurring fill the cap.
3. /events-ui: group recurring series by venue (collapsible "Aquatic Center — N classes", compact rows); line-clamp title 2 / venue 1; render start–end times when end known; emit `.ev-flag` text labels (kill the unlabeled 5-color coding); expose `?when=` filters as chips; SSR and JS variants must agree (or delete the JS variant if it's the stale-build artifact — check after Wave 0.1).
4. Detail pages: `white-space:pre-line` (or paragraph split) on description; sparse-event fallback layout (venue card + organizer + map link); "This event has passed" banner; per-event .ics download + Directions link + price line from existing JSON fields; save-heart in detail header; labeled "Event website" button (fbclid/UTM stripped at render).
5. Home calendar: 7-col grid + leading-empty-cell fix; every day cell links to `/events-ui?date=`; mobile shows count badges not dots; legend wired to real pill classes (special/water/class) with one-offs prioritized for visible slots; `#calendar` anchor scroll fix.
6. Home "Tonight" (DL-16): next not-yet-started, prefer one-offs, dynamic label. Fix "What's open now" quicklink → `/categories/eat-drink?open=1`.
7. NEW `app/api/routes/calendar_feed.py`: `/events.ics` (whole-calendar VEVENT feed) + footer link (footer itself is WP-1's partial — note in PR for one-line follow-up).
Tests: bucket math matrix; window cap/total honesty; series grouping; ics validity; Tonight selector (5 AM passed event never shown at 5 PM).

### WP-4 — Event ingestion (HOLD until §1 0.4 confirms no scraper-session collision)
Branch `feat/wp4-ingest`. Closes: ED-1, M-12, M-13, M-14, M-15 (ingest half), B-08, E-4.
1. `go_lake_havasu.py` ~:80-86: parse JSON-LD location into structured venue_name/street/city; NEVER fall back to organizer block or page footer; venue field rejects multi-paragraph/description-shaped input (shape validation in `base.py`: max length, no double newlines, not equal to description prefix); strip source-site boilerplate/key-value dumps from descriptions; strip fbclid/UTM from URLs at ingest; missing time = NULL (never fabricate noon).
2. Cross-source dedupe in `app/events/dedup.py`: canonical-URL identity (Facebook event ID, organizer URL) across `go_lake_havasu` + `river_scene_import`; recurring-series instance dedupe (venue+title+weekday).
3. `scripts/backfill_event_venues.py` + `scripts/dedupe_events_cross_source.py`: DEFAULT DRY-RUN printing per-change counts; `--apply` flag; idempotent. DO NOT RUN against prod — print the command block for Casey.
Tests: parser fixtures incl. the Farmers-Market/Visitor-Center and Buoy/organizer-suite cases from the audit; shape-validation rejections; canonical-URL dedupe.

### WP-5 — Browse loop (legacy category surface)
Branch `feat/wp5-browse`. Closes: M-20 (pagination), C7/DL-20, C8, C-3, N-16, N-17, B4, D7, D8, C4 (breadcrumb), 32 (sort explainer).
1. Pagination: honor `?page=` over the 60-cap (`_DEFAULT_CARD_LIMIT`), keep all chips/params on paged views, emit `rel=next/prev` links, "Showing 1–60 of 308".
2. Filter-state honesty (DL-20): Open-now moves to filter chips; every "All" chip preserves other params; never two `on` chips in one row; active-filter summary line "Mexican · 26 places · ✕ clear"; sort explainer text matches the active sort; default sort tiebreak `is_open_now`.
3. Chips generated from subtypes actually present in the category, ordered by count; zero-member chips never render; remove "Tap a type to narrow" when no chips.
4. Cards: second meta line (cross-street/area; price tier when known); "No reviews yet" badge + sort-after for unrated (DL-10/DL-12 helper); out-of-area distance hint (DL-8).
5. Push open-now/rating predicates into SQL (kill the 2,000-row Python materialize at `queries.py:830`).
6. Breadcrumb `Home › Explore › {Category}` linking the hub; one canonical casing.
Tests: pagination params; param-preservation matrix; chip generation from seeded subtypes; SQL-filter parity with the old Python path.

### WP-6 — Provider profiles
Branch `feat/wp6-profiles`. Closes: A5/DL-7, M-27, M-28, M-29, P-1, P-2, N-04/DL-11, N-05/DL-4, N-06, D4, D5, E5, L4, DL-12, F6.
1. Cover photo = the card photo when present (DL-7); lock copy per DL-11, lock block moved below Good-to-know.
2. Layout (L4): Good-to-know (address/hours/phone/website) directly under name + Call/Directions; sticky bottom Call/Directions bar on mobile (the unused `.ll-sticky-cta` pattern); full weekly hours table; "Hours not available — call to confirm" fallback; fix the 11:59 PM overnight clamp in the hours pipeline.
3. Reviews per DL-4 (label, 40-word clamp, max 3, "Read all on Google" link, no per-review stars — delete the hardcoded ★★★★★ at provider_profile.html:91). Strip trailing taxonomy/"Stay Connected" artifacts from About prose at render.
4. "While you're here": proximity + same-primary-category query replacing hardcoded picks; labels from the entity's own category.
5. SEO block: canonical, og:title/description/image (card photo), LocalBusiness JSON-LD.
6. Link `hava_card.css` so venue events render styled (DL-14); breadcrumb to the real parent category page; card/profile rating read the same field via one helper (D5).
Tests: hours fallback + overnight clamp; review clamp; JSON-LD validity; same-field rating helper.

### WP-7 — Routing, SEO plumbing, dead code, contribute, sponsor
Branch `feat/wp7-routing`. Closes: M-30, C6, E1, E2, E6, ED-5, N-13, N-20, C10 (logout), DL-13 (sponsor rename), 8 (contribute), 17 (sitemap/301).
1. Move JSON off `/events` and `/programs` to `/api/events`, `/api/programs`; `/events` 301s to `/events-ui`; stop serializing `embedding`/`source`/internal UUIDs in public payloads.
2. `/` 301 (not 307) to /home; sitemap: add /map, /events-ui, /categories, /about,/help,/contact; drop `/`; og:url https coercion via BASE_URL (main.py ~:688); og:description word-boundary truncation.
3. DELETE sweep (E2): `static/home_c.css`, `chat.css`, `index.css`, `categories_index.css`, `static/index.html`, `js/{chat,calendar,lake_light_home,gas_ticker,conditions_strip,home-composer,search,events_lake_light}.js`, `templates/events_lake_light.html`, `templates/admin_event_edit.html`, orphan components (`topbar_c`, `scroll_row`, `discover_grid`, `services_grid`, `category_grid`, `themed_tile`, `_partials/marquee.html`). Keep `hava_card.html`, `venue_events_region.html`, `plausible.html`, `lake_light_*` partials. Grep for references before each delete; `python -c "import app.main"` after.
4. SRI hashes on Leaflet/markercluster CDN tags. GET /logout → redirect to / with session clear (no 405).
5. /contribute: move onto `lake_light_base` (WP-1 must land first — declare PR dependency); event date/time `required` when type=event (extend existing `sync()`); "We review most submissions within a few days" near the button; privacy line by the email field.
6. /sponsor: rename packages to rendered-slot names (DL-13); fix /advertise → redirect to /sponsor.
Tests: route status matrix (301s, /api JSON shapes, no internal fields); import smoke after deletions.

### WP-8 — Gas + mode pages
Branch `feat/wp8-gas-modes`. Closes: A6/DL-17, D2, N-11, N-27, M-10/M-11 (copy+threshold half), C5, 7 (mode hero), G-2.
1. /gas: humanized timestamp + 2-decimal average ON THE LIVE RENDER PATH (after Wave 0.1 resolves which template serves); "Cheapest right now" → "Cheapest today (as of {time})"; single "Updated" phrasing; fix sticky thead (viewport-sticky or repeated header); add the Sandstone ribbon to /gas; staleness threshold for daily feeds → 26-28h (constants in `conditions/constants.py` if owned here — if not, note as follow-up).
2. Station linking per DL-17: link only on confident per-station match; both-Maverik bug fixed (data half — emit the audit query for Casey's data-op queue).
3. Mode pages: /lake conditions block links to /today; /night + /family link "This week's events →" to /events-ui; shrink mode hero on mobile so chips are above the fold.
Tests: timestamp/decimal formatting; threshold constants; link-gating logic.

### WP-10 — Liveness ranking (OWNS the only Wave-1 migration)
Branch `feat/wp10-liveness`. Spec: `LIVENESS_RANKING_HANDOFF_2026-06-03.md` — implement EXACTLY as written (constants, formula, dampener `base * (0.5 + 0.5*liveness)`, NULL→1.0, bury-never-hide). Migration adds `providers.newest_review_at`, `providers.liveness_score` (indexed), `entities.liveness_score`. Extraction in `places_load.py` (9-digit fractional seconds), `scripts/backfill_liveness.py --dry-run`, integration in `app/search/ranking.py` + `app/core/ranking.py` + `category_pages.py:rank_inputs_for_category`. Tests per the handoff's test section. DO NOT run the backfill against prod — print the command block.

## §5 Prod data-op queue (Casey's terminal, sequential, each: dry-run → counts → approve → apply)

Run AFTER the corresponding code PR merges. Order:
1. `merge_existing_dups` website pass: commit the uncommitted `--max-distance-m` edit first (tiny PR), then `python -m scripts.merge_existing_dups --reason website --require-identical-name --max-distance-m 500` dry-run → apply. (CROSS_SOURCE_DEDUP carry.)
2. Miscategorization hot list (WP-5/W1-1): audit query CSV → review → targeted UPDATE. Hot list: A Toe Truck, Detail Specialties, Sunshine Indoor Play, Grace Arts Live, London Bridge Beach, Lake Havasu Cigars, Havasu 95 Speedway out of Eat & Drink; detailing cluster out of On the Water; supermarkets out of Cafés; dealers/medical/HVAC out of Shopping; brokerages out of Lodging; Attractions junk (Jaque Meng et al.); boat rentals into On the Water (DL-9).
3. Event venue backfill + cross-source dedupe (`scripts/backfill_event_venues.py`, `scripts/dedupe_events_cross_source.py` from WP-4).
4. Provider `-2`/`-3` slug merges on google_place_id via admin merge UI; Human Bean street disambiguators.
5. Subtype backfill for dead chips (martial-arts; lodging hotels/vacation-rentals/rv-parks).
6. `scripts/backfill_liveness.py --dry-run` → apply (WP-10).
7. Name-cleaning pass (OTA titles, scraped <title>s); re-geocode 2-decimal coords; gas provider records (Pilot, Hacienda, Terrible Herbst + per-station Maverik slugs per DL-17); verify (999) review sentinel.
8. Approve ~91 pending partners at /admin/providers/pending; let Sunday cron apply attractions remap.

## §6 Wave 2 (dispatch after Wave 1 merges)

- **WP-9 Taxonomy/primary category** (R2 — the structural fix): extend the deterministic `subcategory` system to a single primary category; all surfaces (Home/Explore/Map/chat retrieval CH-1) consume one source of truth; invariant test: every provider exactly one primary; card subtype ∈ page chip set. Owns its own migration. Brief to be cut from AUDIT_TRIAGE R2 + SITE_AUDIT W2-1 once Wave-1 conflicts clear.
- **WP-11 /search results page** (DL-6 phase 2).
- **WP-12 S4 count reconciliation** (one count query everywhere).
- **WP-13 Sunset/conditions fixes** (M-18 NWS extraction, wind direction, water temp via NOAA/USGS) — coordinate with conditions cron ownership.
- Post-launch features (from FEATURE_OPPORTUNITIES + GAP_SWEEP §F build list): digest, /outdoors, /summer, ramps/parking pages, print stylesheet, snowbird mode, itinerary builder. Do-not-build list is recorded in GAP_SWEEP §F — don't relitigate.

## §7 Merge order + verification

Merge order: WP-1 first (everything visual sits on it; WP-7's contribute item depends on it), then WP-2/3/5/6/8 in any order, WP-10 anytime (only migration), WP-4 when ungated, WP-7 last of Wave 1 (deletes — easiest rebase last). After each merge Casey watches the Railway deploy log for the alembic preDeploy line.

Verification = `SITE_AUDIT_LIVE_2026-06-03.md` §7 checklist + GAP_SWEEP closures, run against prod after Wave 1 + the data-op queue. Final gate: re-run a scoped multi-agent live audit (same method as the gap sweep) and require zero new P0/P1.
