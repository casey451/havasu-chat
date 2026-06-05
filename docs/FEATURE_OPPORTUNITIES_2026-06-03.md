# Hava Site Review — Feature Opportunities & Layout Recommendations
**Date:** 2026-06-03 · **Scope:** end-user experience only (no merchant/revenue-side) · **Lens:** impact vs. effort for a solo dev
**Method:** 6 parallel agents across two passes. Pass 1 (features): 2 agents crawled production (havasu-chat-production.up.railway.app) as end users; 1 researched Lake Havasu demographics/seasonality; 1 researched comparable products (Yelp, Nextdoor, Do512, 6AM City/Naptown Scoop, DMO AI concierges). Pass 2 (layout): 1 agent reviewed live page structure; 1 reviewed templates/CSS/routing. Site findings verified against `origin/main` (zero diff with deployed code). Recommendations cross-checked against `docs/BACKLOG.md`.

---

# Part 1 — Who the user actually is

- **Median age ~56; ~35% of residents are 65+; 73% homeowners.** The default user is a 55–75 year-old on a phone — 76–78% of 65+ adults now own smartphones (Pew, Jan 2026), but they're light users who need big type, shallow nav, visible anchors, and tap-to-call.
- **Snowbirds:** ~15–20k seasonal residents Oct–Apr (city swells to ~75k). They re-discover the town every fall: clubs, pickleball, churches, recurring socials, dining.
- **Tourists:** ~1.5–2M visitors/yr, ~$835M spend. Event megacycle: Balloon Fest (Jan) → Winterfest/Rockabilly (Feb) → spring break + Run to the Sun (Mar) → Desert Storm (Apr) → IJSBA (Oct). They want conditions, rentals, itineraries.
- **The opening:** local info is fragmented across 4+ Facebook groups, RiverScene, the paywalled News-Herald, and GoLakeHavasu — which is in a public credibility crisis (2025 council hearings, leadership churn). A calm, complete, trustworthy one-stop is exactly the gap.

**Single highest-leverage design decision:** build for 60-year-old eyes and thumbs by default. Stylesheets are dominated by 11–13px fixed fonts; bottom-nav labels are 11px; ribbon labels are .67rem.

---

# Part 2 — Feature opportunities

## Tier 1 — Quick wins (high impact, low effort, days not weeks)

| # | Feature | Why it matters | Evidence / effort note |
|---|---------|----------------|------------------------|
| 1 | **Restore chat feedback thumbs + add Save and Share to chat answer cards** | Users can't flag wrong answers or keep good ones. | Backend exists (`POST /api/chat/feedback`, `chat_log_id` returned); the orphaned `chat.js` had thumbs and share — `chat-new.js` dropped them. Mostly re-wiring. |
| 2 | **Pagination / "load more" on category pages** | Eat & Drink shows 60 of 269+ listings — ~78% of the directory is unreachable by browsing. | Observed live: exactly 60 `/provider/` links, zero page/offset controls. |
| 3 | **Add-to-calendar (.ics), directions, share, and price/registration info on event pages** | Snowbirds plan weeks ahead; event detail pages have none of this. Price + registration data already exists in the events JSON but isn't rendered. | Zero `.ics`/calendar refs in templates (verified). `.ics` generation is trivial. |
| 4 | **A real `/search` results page** | `/search` 404s — the only search is AI chat. A 70-year-old typing "plumber" should get a scannable list with phone numbers, not a streamed AI answer behind a sponsored interstitial. | No `/search` route exists (verified). Simple keyword query over providers/events + list template. Chat stays as the smart layer on top. |
| 5 | **Base font bump to 16px+ and/or a text-size toggle** | Median resident age is 56; current type is 11–13px nearly everywhere. NN/g minimum for older adults is 16px body. | CSS-only change; biggest accessibility ROI available. |
| 6 | **Full weekly hours table + website link on provider profiles** | Profiles show only "Open now · Closes 9:30 PM." A snowbird planning Sunday lunch can't see Sunday hours; no link to the business's own site. | Display change, data permitting. |
| 7 | **Event filters on `/events-ui`** (category, date range, free/paid, kid-friendly) | The events page has zero form controls; `?when=weekend` already works server-side but no UI exposes it. | Mostly template work over existing queries. |
| 8 | **Trust pages: About, Help/FAQ, Contact + "report wrong info" link on every profile** | None exist (no routes — verified). Trust is the wedge vs. GoLakeHavasu's credibility crisis. | Static templates. |
| 9 | **Redirect `/events` → `/events-ui`** | `/events` currently dumps 497KB of raw JSON on end users. | One-line route change. |
| 10 | **PWA manifest + favicon/touch icons; Open Graph tags on provider and category pages** | "Add to Home Screen" is the install path for a daily-habit app; sharing any page to Facebook (the dominant 55+ channel) produces a bare imageless preview. OG exists only on event permalinks. | Static files + meta tags. |

## Tier 2 — Habit & retention builders (medium effort)

| # | Feature | Why it matters | Effort note |
|---|---------|----------------|-------------|
| 11 | **Weekly "This Weekend in Havasu" email digest** | The most proven retention engine at exactly this town size: Naptown Scoop (Annapolis, ~40k) hit ~18–21k subscribers at 65% open rates as a solo operation; 6AM City targets towns of 20k. Directly attacks Facebook-group fragmentation. | Email pipeline (Beehiiv/SES) + AI-draft curation. Alerts system already does email. |
| 12 | **Persistent chat history** | Sessions are in-memory with a new ID per page load — close the browser and yesterday's "find a plumber" answer is gone. | Sessions → DB keyed to account (or anon cookie); pairs with magic-link auth. |
| 13 | **Water temp + richer lake conditions on `/today`** | Water temp shows "Unavailable." Free NOAA NWPS / USGS gauges cover it; DesertUSA's combined lakes page proves demand. | Free keyless APIs; one cached fetch job. |
| 14 | **Expanded alerts: weekend-events digest, AZ511 road closures, big-event-weekend traffic warnings, per-business alerts** | Nextdoor's 2025 relaunch made Alerts pillar #1. Current alerts: 3 weather/condition types, email-only. Desert Storm weekend alone justifies this. | AZ511/NWS feeds free; reuse alert plumbing. Snooze field should pre-fill (currently can't see/clear an active snooze). |
| 15 | **Save-from-anywhere + a usable Saved page** | Hearts exist only on provider profiles; favorites page is a bare list, no remove button, no events, no notes. Hearts hidden entirely for logged-out users — no "sign in to save" prompt. | Extend favoritable entities to events; richer list template; anon-tap → login prompt. |
| 16 | **Voice input on the chat composer** | Nothing in the codebase (verified). Key for 55+ thumbs and boaters with wet hands; Yelp shipped voice search in 2025. | Web Speech API — progressive enhancement. |
| 17 | **Distances + geolocation prompt on "Closest" sort; combinable filters** | "Closest" shows no distances and odd ordering without location; cuisine/open-now/sort can't be combined in the UI. | Geolocation prompt + distance display; querystring composition. |
| 18 | **Trade subtype tabs for Home & Property Services (237 listings)** | Plumber vs. HVAC vs. landscaper can't be narrowed — the core 55+ homeowner use case the strategy bet on. | Same tab pattern already built for Eat & Drink. |

## Tier 3 — Strategic bets (higher effort, segment-defining)

| # | Feature | Why it matters | Effort note |
|---|---------|----------------|-------------|
| 19 | **Snowbird mode / "New this winter?" onboarding pack** | 15–20k people re-arrive every October needing clubs, pickleball, churches, recurring socials, healthcare, seasonal services. Nothing local serves this. | The onboarding API (`POST /api/chat/onboarding` for visitor status) already exists — the new chat UI just never calls it. |
| 20 | **Itinerary builder in chat ("plan my Saturday")** | The marquee DMO-AI feature (HelloBC, Visit Estes Park, iWander). Turns chat from Q&A into a planning tool tourists screenshot and share. | Prompt orchestration over existing directory + events + conditions data. Backlog has this in Phase 3 — this argues for pulling it forward. |
| 21 | **Photos on unclaimed listings** | Every profile shows "🔒 Photos unlock when claimed" — the directory is effectively imageless, and photos drive decisions everywhere. **Tension flag:** unlock-on-claim is part of the monetization funnel; consider a middle path (one hero photo for all; gallery/menu stays claimed-only). | Sourcing/licensing + moderation. Decision needed before build. |
| 22 | **SMS channel for alerts/digest** | Retiree-heavy markets respond to text; on-water hazard alerts arguably *need* SMS, not email. | Twilio already planned for Phase 2 deals — same integration. |
| 23 | **Account preferences page** | Account page is just email + two links. Visitor/local status, boat-mode default (API exists, no UI), text-size preference, digest frequency. | Template work + a few columns. |

---

# Part 3 — Layout & information architecture

## The critical structural finding: two design systems, and the directory pages have no mobile nav

The site runs two complete visual systems:

- **Sandstone** (`sandstone_base.html`, Fraunces/Figtree): home, modes, category pages, events, provider profiles — the core directory content. Sticky desktop header, **no bottom nav**.
- **Lake Light** (standalone templates + partials, Playfair/Poppins): chat, map, today, categories index, account/login, permalinks. Fixed **bottom tab bar** (Home / Events / Ask / Explore / Map / Saved).

Verified in `sandstone.css:232–240`: at ≤900px the nav links hide; at ≤680px the mode tabs hide too. What remains on every Sandstone page on a phone is a logo and a **☰ button that is not a menu** — it cycles browse modes/themes (`sandstone.js:16–23`). So the pages where users spend the most time (home, listings, profiles) have **zero mobile navigation**, while utility pages have a proper tab bar that appears and disappears between adjacent taps. The most common journey — home (Sandstone) → chat (Lake Light) → provider (Sandstone) — swaps fonts, palette, and the entire nav model twice.

Also verified: **there is no sign-in entry point anywhere** — no header, footer, or nav links to `/login`; users only find it via the Save-heart redirect. And the bottom nav itself has a bug: **6 links in a `repeat(5, 1fr)` grid** (`lake_light.css:425`), so the 6th item wraps.

## Layout recommendations (ranked)

| # | Recommendation | Rationale / files |
|---|----------------|-------------------|
| L1 | **Put the bottom nav (Home/Events/Ask/Explore/Map/Saved) on every page, all breakpoints ≤900px** — add to `sandstone_base.html` with bottom padding on `main`; fix the grid to `repeat(6, 1fr)` (or fold Map into Explore). | One change fixes nav consistency, utility discoverability (Map/Saved/Today are currently unreachable from home on mobile), and thumb reach. The single highest-leverage layout fix. |
| L2 | **Make ☰ a real menu (or remove it); expose modes as labeled tabs.** | A hamburger that silently teleports to `/lake` violates the strongest icon convention this demographic knows. `sandstone_base.html:64`, `sandstone.js`. |
| L3 | **Homepage reorder: category tiles ("Explore Havasu") + trades up to position 2, right under the hero; replace the month calendar with a "next 5–7 days" event list + "Full calendar →" link; demote the sponsor row below content; drop the conditions row that duplicates the ribbon.** | The month grid eats a full screen of scroll and renders as anonymous dots on phones (`.ev{display:none}` ≤680px). Browse-by-category is the recognition-over-recall path seniors prefer, and it's currently dead last. `home_sandstone.html`. |
| L4 | **Provider page mobile: "Good to know" (address/hours/phone) directly under the Call/Directions buttons, before description and reviews; move the 🔒 lock banner off the top of the page into the claim box; "Ask Hava" above the claim box; make Call/Directions a sticky bottom CTA bar ≥48px tall.** | On mobile the single-column collapse buries hours/address under description, 8 gallery slots, and 3 full reviews. Visitor needs before owner-acquisition copy. An unused `.ll-sticky-cta` pattern already exists in `lake_light.css:1123`. `provider_profile.html`, `sandstone.css:211,236`. |
| L5 | **Category listings: sort open-now businesses above closed within the default ranking (or move the Open-now toggle next to the subtype chips).** | The default view opens with a wall of "Closed" badges — wrong first screen for "where do I eat now." Also: add a back-to-top/filters affordance after ~20 cards; replace the redundant sub-category tag on each card with hours-until-close or distance. |
| L6 | **Converge the themes structurally:** one events template (`events_lake_light.html` is orphaned — no route), one category system (`/category/{slug}` is a full parallel unlinked implementation — delete or merge with `/categories/{slug}`), a shared `lake_light_base.html` (11+ pages hand-repeat their `<head>` and use 3 different topbars), one back-affordance pattern, matching footers (Sandstone omits Terms). | The home→chat→provider loop should feel like one product. Palettes can differ; header anatomy, bottom nav, and footer must not. |
| L7 | **Add Sign in / Account to both headers; add Events to the Sandstone desktop header.** | Zero nav path to `/login` today; Events — the #1 content type for retirees — is absent from every persistent Sandstone nav surface (`app/home/sandstone.py:127–133`). |
| L8 | **Conditions ribbon: stop relying on horizontal scroll on mobile** — wrap to two rows or cut to gas + heat + lake level, with the whole strip tapping through to `/today`. | Older users rarely scroll sideways; items past the first two are invisible. Keep the gas pill — it's one of the best placements on the site. |
| L9 | **Map page: one header (two currently stack), show the 5 grouped chips only, rest behind "More filters," map above the fold.** | 17 chips in two rows (with duplicate "Eat & Drink" labels pointing at different scopes) push the map off-screen on phones. `map_c.html`. |
| L10 | **Chat: fix the composer overlapping the bottom nav** (composer z-55 sits on the nav z-40 in the same bottom strip) — lift the composer with explicit clearance or hide the nav while composing. | `lake_light.css:415–427, 990–996`, `chat.html`. |
| L11 | **Events list cards: date/time leftmost and bold; ♡ save right-aligned; make the calendar view a true toggle, not an appendix below 25 cards.** | Protects scanning, prevents mis-taps on small inline hearts. The Today → This Week → Next Week → Classes ordering is right — keep it. |
| L12 | **/today: heat/temp card first** (it's the #1 daily-planning fact in Havasu and currently isn't a card at all), then gas, lake level/wind, AQI/sunset. **/gas: replace the raw ISO timestamp with relative time; collapse the 5-column table to station rows with Regular prominent + tap-to-expand.** | Both pages are otherwise well-structured — honest staleness labels are great for this audience. |
| L13 | **Categories index: group the 15 cards under 3 subheads ("Go out" / "Get something done" / "Living here"); move featured-sponsor names to a separated "Featured:" caption.** | "Services 1238" overlaps four other service categories; sponsor names currently read as part of category titles. |
| L14 | **Type/tap-target floor: nav labels and ribbon text ≥13–14px, primary CTAs ≥48px, AA contrast check on muted colors.** | Bottom-nav labels are 11px; Call/Directions compute to ~41px; chat send is 38px. |

### What's already right (keep)
Hero question + Ask box first on the homepage; Call as the primary CTA under the provider name; filter-above-sort-above-list on category pages with plain-language sort explainers; Today → This Week → Next Week → Classes event ordering; "5 cheapest first" on /gas; honest "Unavailable" states on /today; magic-link login; the gas pill in the ribbon.

---

# Part 4 — Suggested sequencing (features + layout together)

If I had to pick the first seven things:

1. **L1 — bottom nav everywhere.** The cheapest structural fix with the broadest reach; everything else benefits from findability.
2. **F2 — pagination on categories.** Unbreaks ~78% of the directory.
3. **F5 + L14 — font/tap-target pass.** One CSS sweep serves the median user on every page.
4. **L3 — homepage reorder.** Categories up, calendar → next-7-days list, sponsor demoted.
5. **L4 — provider page mobile reorder + sticky call bar.** The money page for the 55+ caller-first audience.
6. **F3 — event page upgrades (.ics, directions, price).** Ship before snowbirds return in October.
7. **F11 — weekly digest.** The retention flywheel; everything above makes it richer.

Then: F4 (real /search), F1 (chat thumbs/save/share), L6 (theme convergence — do it before building more pages on two systems).

## Already on the backlog — excluded from recommendations above
Weather widget (NWS), list/map toggle on category pages, Eat & Drink / Home Services category pages, account-lite favorites + alerts v0.1, deals/QR wallet (Phase 2), itinerary builder (Phase 3 — item F20 argues for pulling it forward), real-time gas prices and ramp conditions.

## Small adjacent fixes spotted
Contribute form lacks address/phone/photo fields; cuisine filter leaks into non-food categories; gas shows $4.35 in the ribbon while /today says "Unavailable" (pick one truth); no `prefers-reduced-motion` in `lake_light.css`; chat error bubbles have no retry target; the sponsored interstitial holds every chat answer ~1.1s minimum (consider first-question-only); "Tonight: Lap Swim 5:00 AM" — events labeled *Tonight* with morning times read wrong; non-food listings appear in Eat & Drink (data hygiene, hurts first-screen scannability).

---

### Source notes
Demographics: Census QuickFacts / ACS via Data USA, Neilsberg, World Population Review. Seasonality: Havasu News-Herald, ASU News, Phoenix New Times, Go Lake Havasu annual calendar. Tech behavior: Pew Research (Jan 2026), NN/g senior-usability guidance. Comparables: Yelp Fall 2025 release, Nextdoor relaunch press, Axios on Patch AI newsletters, Do512, Eventbrite, 6AM City and Naptown Scoop coverage, Tourism AI Network DMO case studies, NWS/NOAA/USGS/USBR/AZ511 API docs. Site observations: live crawl 2026-06-03 (`/home`, `/events-ui`, `/categories`, `/categories/eat-drink`, `/provider/*`, `/chat`, `/today`, `/gas`, `/map`) + template/CSS verification against `origin/main` (`sandstone_base.html`, `home_sandstone.html`, `provider_profile.html`, `lake_light.css`, `sandstone.css`, `sandstone.js`, routers), which auto-deploys to production. Full URLs available in agent transcripts on request.
