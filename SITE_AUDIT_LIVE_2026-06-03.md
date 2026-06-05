# Live Site Audit — Pre-Production Review (2026-06-03)

**Site:** https://havasu-chat-production.up.railway.app
**Audit window:** Wednesday 2026-06-03, ~4:45–5:30 PM America/Phoenix
**Method:** 7 fetch-based auditors (server-rendered HTML + read-only API GETs, files 01–07) + 1 live-browser ground-truth pass (file 08, Claude-in-Chrome, JS-rendered, one permitted chat message, ~657px mobile floor).
**Conflict rule applied:** where the browser pass (08) contradicts a fetch-based observation, the browser pass wins. The fetch-pass *cross-request* flapping (counts 308→269, 82°F→108°F, category membership changing between fetches) remains real — the browser pass confirmed same-session stability, which means the flapping is stale/split cache serving at the edge across different requests/instances, not client-side flicker.

---

## 1. Executive summary

The product's bones are good — chat answer quality and latency are genuinely strong, the 404/robots/sitemap/login plumbing is clean, responsive breakpoints work, and the `/today` "show Unavailable rather than guess" policy is exactly the right editorial stance — but the site is not shippable today. Three classes of failure are launch-fatal: (1) the chat transcript, the single flagship surface, is visually destroyed by unconstrained inline SVGs; (2) the events list silently drops Saturday and Sunday — the highest-value content in a weekend-tourism town — and the home month calendar renders misaligned and clipped; and (3) trust-killing data: a tow-truck company is the #1-ranked "restaurant," open/closed status and listing counts differ depending on which cache instance answers, sunset is shown ~100 minutes early, and the live `/terms` page contains bracketed lawyer placeholders. Roughly 130 raw findings across the eight auditors collapse into eight root-cause themes; fixing the themes, not the symptoms, is the plan.

**The 8 themes that explain most findings:**

| # | Theme | Representative symptoms |
|---|-------|------------------------|
| T1 | **Miscategorization / taxonomy** (no enforced primary category; catch-all subtypes; chip sets diverge from stored subtypes) | A Toe Truck in Restaurants; detailers in On the Water; Walmart in Cafés; dead `?sub=` chips; 39-vs-220 count mismatch; map taxonomy drift |
| T2 | **Stale / split cache serving at the edge** (different requests hit different snapshots) | Counts 308↔269, 1496↔1238; 82°F↔108°F; Open↔Closed inversions between fetches; cross-category bleed appearing/disappearing |
| T3 | **Event ingestion corruption + venue misattribution** | Organizer/source-site address as venue; description in venue/address fields; Visitor Center as Farmers Market venue; dual-source duplicates; fake-noon times; scraped footer junk in descriptions |
| T4 | **Time / timezone / window math** | Weekend bucket missing entirely; "Tonight = Lap Swim 5:00 AM"; sunset 6:00 PM vs ~7:43 PM actual; fetch-pass "Jun 2 under Today" (UTC boundary on SSR); staleness thresholds wrong for daily feeds |
| T5 | **The 60-card pagination cap** | Every category page renders exactly 60 cards; `?page=2` ignored; up to 95% of a category unreachable; invisible to crawlers too |
| T6 | **Data hygiene / duplicates** | `-2`/`-3` slug dupes (ZENSHI, New Day School, Holiday Inn, vacation rentals ×3); OTA listing titles as business names; "Air conditioning contractor" as a name; junk records (Jaque Meng); scraped `<title>` as name |
| T7 | **Presentation bugs** | Chat SVG/CSS blowup (P0); month-calendar grid misalignment (P0); map pin navigates instead of popup; unstyled chat chips; missing-whitespace text runs; lock-block dead space |
| T8 | **Legal / copy / brand debt** | /terms placeholder + lawyer notes live; "no accounts" claim vs live /login; three product names (Ask Hava / Hava / havasuchat.com); two bottom navs; "your menu" claim copy on banks and vets; sponsor page names don't match rendered slots |

---

## 2. Ship-blockers (P0)

| ID | Page(s) | Evidence (verbatim) | Suspected root cause | Reported by |
|----|---------|--------------------|--------------------|-------------|
| B-01 | /chat (response transcript) | "Each result card renders a full-width phone SVG (~900px tall) and full-width star SVG between text lines; photos full-bleed … the whole response is many viewport-heights of giant icons." Also "Pizza Spots5 of 12", "Call (928) 855-4404Directions" (missing whitespace). | Missing CSS constraints on inline SVGs/images in chat response cards — "one CSS file likely fixes the whole transcript." Content underneath is good (pizza query returned 5 genuine pizzeria results in ~9s). | 08 |
| B-02 | /home#calendar (month calendar) | "7 weekday headers (SUN–SAT) but day cells render shifted — June 1 sits under WED (June 1, 2026 is a Monday), days 5–6/12–13/19–20/26–27 overflow off the right edge of the card and are clipped. 'Battle for the Buoy' (Jun 6) lives in a clipped cell." Day cells/"+N" not clickable. | Grid CSS — "likely an 8-column template or missing leading-empty-cell logic." Data layer is correct (events sit in the right cells). | 08 (new vs fetch pass; 01 flagged run-together cell text as P3) |
| B-03 | /events-ui (list view) | Browser-confirmed: "Sat June 6 + Sun June 7 events ('Battle for the Buoy', Foreigner/Styx tribute, etc.) appear NOWHERE in the list view — 'This Week' ends at Jun 5, 'Next Week' starts Jun 8. There is no 'This Weekend' section at all." API holds ≥6 Jun 6–7 events (Battle for the Buoy, FOREIGNER & STYX, Baby Sitting Class, Farmers Market ×2, Sunday Open Swim). | Bucketing math: weekend days fall through the gap between "This Week" (weekdays-only) and "Next Week" (starts Monday). Ties directly to triage E-1 (`event_window_for_chip` boundary math). For a weekend-tourism town this hides the core content. | 04 (EV-01), 08 (confirmed "worse than reported"), 01 (H-04 related) |
| B-04 | All category pages (observed on /categories/eat-drink, /categories/services, /categories/public-civic-resources; header strip global) | "Eat & drink '308 listed' → '269 listed'; Services '1496 listed' → '1238 listed'" between back-to-back requests; "82°F → 104°F → 108°F; AQI 20 → 46 → 51" within ~10 min; "'Closed Siddhartha's Garden' … ~1 minute later … 'Open now Siddhartha's Garden'"; civic page fetch 1 = "66 listed" with off-category rows (Tinnell Memorial Sports Park, English Village Fountain), fetch 2 = "60 listed" without them; "Lake Havasu City Library" Closed→Open, "Calvary Baptist Church - McCulloch Campus" Open→Closed. Browser pass REFUTED same-session flapping (3 reloads stable) — so this is **stale/split cache serving across requests/instances** (one path serving an hours-old morning snapshot with a different category dataset), not client flicker. | Two backend instances or cache layers with divergent snapshots — one stale (morning data, old category mapping, 82°F at 4:45 PM on a 108°F day). Every Open/Closed pill, count, and category membership is untrustworthy until serving is consistent. | 02 (A-02, A-03, A-16, A-17), 03 (B-01, B-13), 05 (stale-render observation), 08 (scoped it to cross-request) |
| B-05 | /categories/eat-drink, /provider/a-toe-truck (+ class of records) | "A Toe Truck ★ 4.9 (999)" is the #1/#2 ranked card under **Restaurants** ("Locals' favorites"); breadcrumb "Home › Eat & Drink › A Toe Truck"; claim CTA "Claim it to add photos, your menu, and offers — and stand out in Eat & Drink."; its reviews: "Coolest tow truck driver to have!", "The wrecker driver Chris P. found me…". Same class: Detail Specialties & Ceramic Coating, Sunshine Indoor Play, Grace Arts Live (theater), London Bridge Beach (public beach), Lake Havasu Cigars, Havasu 95 Speedway — all labeled Eat & Drink. Browser pass confirmed it tops the browse page (though the chat ranker did NOT recommend it for "best pizza"). | Category-mapping/classifier bug bucketing non-food Google place types into Eat & Drink; review-volume-weighted sort then promotes the worst offender to #1. Structural fix = triage R2 primary-category work; immediate fix = data triage of the offender list. | 02 (A-01), 05 (PR-01), 07 (07-02), 08 (#5) |
| B-06 | /terms | §9: "These terms are governed by the laws of **[jurisdiction to be specified]**. … Which country, state or region applies is something you and your lawyer will fill in. (This is a **placeholder** for review.)" §7: "we are not setting a dollar cap in this document—that is a topic for **lawyer review** before a broad public release." §11: "U.S. 'DMCA agent' registration … are a separate step for **lawyer review**". | Draft legal page shipped to prod with bracketed placeholders and internal drafting notes. Page-only but legally global. | 01 (H-01, H-02) |
| B-07 | /categories/classes-sports-recreation, /categories/lodging-vacation-rentals (chip URLs) | "`?sub=martial-arts` → 'No listings here yet.' Yet the unfiltered page lists 'Havasu Martial Arts Academy', 'Arizona Kravmaga', 'Elite Martial Arts, Inc.' … all subtyped 'Kids Lessons'." "`?sub=vacation-rentals` → 'No listings here yet.' despite ~45 vacation-rental cards"; "`?sub=rv-parks` → 'No listings here yet.'" — every lodging card carries subtype "Hotels". | Chip taxonomy diverges from stored subtypes: rendered chips reference sub keys no record carries. Dead-end UX on first-class filters. (Same root family as T1/triage C-1.) | 03 (B-02, B-07) |
| B-08 | /events-ui + /events/{id} + /api/events | SpongeBob Musical listed twice: "Grace Arts Live Presents The SpongeBob Musical Youth Edition" (venue "2146 McCulloch Blvd", source `river_scene_import`, end_at 48h later) AND "GraceArts Live presents The SPONGEBOB Musical" (venue "GraceArts Live", source `go_lake_havasu`) — same organizer_url. "Battle for the Buoy" twice — both link to **the same Facebook event** (facebook.com/events/916195421442604), one venued "Dillard's Parking lot", the other at "5601 Hwy 95 N 404-D" (Altitude Trampoline Park's suite — the *organizer's* address). Farmers Market Sat 8:00 AM @ "Go Lake Havasu Visitor Center" AND Sat 12:00 PM @ "2144 McCulloch Blvd NLake Havasu City, AZ 86403". | No dedupe across `go_lake_havasu` and `river_scene_import` sources even when canonical URL (Facebook event ID / organizer URL) is identical. Triage already flagged dedupe as event-one-off-only (C-4/E-4). | 04 (EV-02), 01 (H-09) |

**P0 count: 8.**

---

## 3. Major (P1) — grouped by theme

### T1 — Miscategorization / taxonomy

| ID | Page(s) | Evidence (verbatim) | Suspected root cause | Reported by |
|----|---------|--------------------|--------------------|-------------|
| M-01 | /categories/shopping-essentials | Top 60 includes "Anderson Toyota ★ 4.8 (5938) Specialty", "Anderson Nissan", "Big O Tires", "Concierge Health AZ ★ 5.0 (612)", "Barnet Dulaney Perkins Eye Center" (eye surgeons), "Mission Accomplished Heating and Cooling", "Arizona VIP Plumbing Sewer & Fire Protection ★ 4.8 (80) Home Goods" (plumber tagged Home Goods), "Optimum" (cable ISP). | "Specialty" subtype is a catch-all leaking into Shopping; several of these simultaneously appear under Services. | 02 (A-05) |
| M-02 | /categories/things-to-do | Hub says "39 listings", page header "220 listed"; visible list ~15 churches ("Kingdom Hall of Jehovah's Witnesses--North English, South English…", "Victory Chapel"), ~12 gyms, "HCHF Community Food Bank", "Nomadic ★ 5.0 (17) Beauty", "K9 Pawfidence ★ 5.0 (11) Pets". "A tourist looking for 'what to do tonight' gets a food bank and a Kingdom Hall above the visitor center." | Things-to-do aggregates Fitness + Civic + everything (multi-parent slug reuse — triage R2: `religion_community` → things-to-do + public-civic-resources); plus hub/page count skew. | 02 (A-06, A-11) |
| M-03 | /categories/eat-drink?sub=cafes-coffee | "Walmart Supercenter ★ 4.1 (3841) Cafes Coffee", "Smith's ★ 4.5 (2074)", "Safeway", "Albertsons", "BlondZee's Steak House ★ 4.1 (1161) Cafes Coffee", "Sunshine Indoor Play". | In-store bakery/coffee tags mapped to Cafés drag whole supermarkets in; review-weighted sort then ranks Walmart above real cafés. | 02 (A-08) |
| M-04 | /categories/on-the-water | "Superior Detailing ★ 5.0 (35) On The Water", "Above All Mobile Detailing", "JT KUSTOM DETAILING", "Mystique detailing llc", "Premier Detailing"; "Altitude Trampoline Park ★ 4.6 (224) Parks Beaches" (indoor). Hub cover for the category is "Crown Mobile Detailing". Chips ("Trails & Off-road", "Golf", "Disc Golf", "Biking") don't match the stated theme "Marinas, rentals, lake stays". | Marine-adjacent keyword over-match ("boat detailing" → On the Water); category is really "Outdoors", mislabeled. | 02 (A-09, A-13), 01 (H-13) |
| M-05 | /categories/attractions (+ things-to-do parent) | "The Wedding Specialist", "High End Productions Llc", "Simply Savage Designs", "Jaque Meng" (a person's name, no descriptor), "Game Spot llc", "Christine's Fine Art LLC", "American Legion ★ 4.7 (140)", "Elks Lodge #2399 ★ 4.6 (388)" all as Attractions. Conversely "Hooks Boat Rentals", "Beach Shack Rentals", "London Bridge Beach boat rental" live ONLY under Attractions and are absent from On the Water where users would look. | Attractions subtype polluted with junk/low-data records; rental operators mis-homed. | 03 (B-04, B-14), 05 (PR-05) |
| M-06 | /categories/classes-sports-recreation | "Knights of Columbus ★ 4.4 (22) Kids Lessons", "Mohave Traffic School Kids Lessons", "Family Tree Daycare", "Hava Math Tutor Kids Lessons", "Bella Faccia Skincare and Pilates ★ 5.0 (10) Gyms", "Sand Volleyball, Rotary Park… Gyms". H1 says "Fitness & sports" while nav/hub/breadcrumb say "Classes, Sports & Recreation"; "Pickleball & Tennis" chip returns 2 tennis listings while "Shah Racquetball Club" is subtyped "Gyms" and excluded. | "Kids Lessons" subtype is a dumping ground; page display names diverge from nav names; chip keys miss natural members. | 03 (B-05, B-12) |
| M-07 | /categories/lodging-vacation-rentals | "Havasu Realty, Inc. Hotels", "Integrity Arizona Real Estate Sales, LLC Hotels" (brokerages as lodging); "Black Meadow Landing" (~40 min away near Parker Dam, CA side) and "Havasu Springs Resort" (Parker side) with no distance hint; every one of 60 cards subtyped "Hotels". | Subtype never differentiated for OTA-ingested rentals (root of B-07's dead chips); no geo-fence on out-of-area properties. | 03 (B-07, B-08) |
| M-08 | /map vs /categories | Map "Categories" row has 12 scopes vs 15 site categories — omits Things to Do, Attractions, Beauty & Personal Care, Professional, Services; adds Outdoors/Parks/Trails (not on /categories) and Events. | Two hand-maintained category lists (triage S1/M-1 family). | 06 (MAP-2) |
| M-09 | /provider/london-bridge | Attractions category page lists "London Bridge ★ 4.7 (10164) Attractions" but the profile breadcrumb is "Home › On the Water › London Bridge". | Multi-category entity renders breadcrumb from a different parent than the surface the user came from (triage P-1/R2 family). | 05 (PR-06) |

### T2 — Stale / split cache serving

(Core entry is ship-blocker B-04. P1 satellites:)

| ID | Page(s) | Evidence | Suspected root cause | Reported by |
|----|---------|----------|--------------------|-------------|
| M-10 | /home + /events-ui strip vs /gas vs /today | Same minute: strip "⛽ $4.35 Cheapest gas" (no staleness flag, tooltip "Love's Travel Stop"); /gas table Love's regular **$4.39**; /today "Cheapest gas **Unavailable** — Updated >8h ago". "A user tapping the $4.35 strip lands on a page that says $4.39." | Conditions cache vs gas service use different snapshots AND different staleness policies; header strip bypasses the staleness rule /today enforces. | 06 (GAS-2), 01 (H-07), 07 (07-06) |
| M-11 | /gas, /today | "/gas warning: 'Prices may be out of date (Updated >6h ago)'; footer: prices 'update **once daily**'; /today hides the price at >8h." Data at audit time genuinely ~26h old (updated 2026-06-02T15:05Z) — the June 3 refresh may also have failed. | Staleness thresholds (6h/8h) contradict the daily cadence — guarantees a warning most of every day. Matches triage G-2 (🔴 confirmed: TTL 86400s but stale at ≥2h). Also check the ingest job for the missed refresh. | 06 (GAS-3) |

### T3 — Event ingestion corruption + venue misattribution

| ID | Page(s) | Evidence (verbatim) | Suspected root cause | Reported by |
|----|---------|--------------------|--------------------|-------------|
| M-12 | Events with `go_lake_havasu` source (systemic) | Farmers Market venued at "**Go Lake Havasu Visitor Center**" while its own description says it's "at The KAWS… in the heart of Downtown"; "Free Movies & Fun at Star Cinemas" series also venued at the Visitor Center; Buoy fundraiser pinned at "5601 Hwy 95 N 404-D" — Altitude Trampoline Park's suite, because "Organizer: Altitude Trampoline Park: Randi Lugo"; Buoy description embeds the Visitor Center's footer contact block verbatim ("422 English Village … (800) 242-8278 … Who We Are"). | Scraper takes source-site footer / organizer block as venue — the owner's reported "tow company event at a restaurant" failure class, confirmed. Triage ED-1 (`go_lake_havasu.py:80-86`, `venue = loc.get("name") or loc.get("address")`) is the confirmed code locus. | 04 (EV-05), 07 (07-04 adjacent) |
| M-13 | Event detail pages (systemic, esp. river_scene_import) | Venue field is name+address mashup or bare address: "Flying X Saloon 2030 McCulloch Blvd. Lake Havasu City, AZ.", "2146 McCulloch Blvd" (should be "GraceArts Live"), "Lighthouse House 317 S. Lake Havasu Ave…". In the API, "`venue` and `address` are the **same string** on every record". Moonshot event: "Venue: Do you have a 'moonshot' business idea…" — full description paragraphs in venue/address fields, address begins with a zero-width character. | Venue/address never split on ingest; no shape/length validation, so multi-paragraph description text passes into address fields. | 04 (EV-04), 07 (07-04), 01 (H-10, H-11) |
| M-14 | Event descriptions (systemic) | "Venue: GraceArts Live Address: 2146 McCulloch Blvd … **Coordinates: 34.4746143,-114.3262645**" raw in body copy; "To purchase tickets, click here ." (dead link, space before period); Canvas & Cocktails embeds London Bridge Resort website nav ("Find A Room … 1477 Queens Bay …"); one event's *entire* description is "Venue: Lighthouse House 317 S. Lake Havasu Ave." | Ingest cleanup missing: key-value dumps, stripped links, source-site boilerplate all rendered verbatim. | 04 (EV-06, EV-16) |
| M-15 | Events with unknown start times (systemic) | "**Lady Lee's Monday Night Dance Party** — Monday, June 8, **12:00 PM**" (a night dance party at noon); "Satin Steele at Hangar 24 — Friday, June 5, 12:00 PM" (bar live music at noon); "Summer Camp at Altitude … 12:00 PM"; eight JS-variant items at 12:00 PM. Confirmed in JSON: `"start_time": "12:00:00"`. | Missing time defaults to noon and the renderer always prints a time — "publishing a fabricated noon time will send people to a closed bar." Render "Time TBD" or fetch the real time. | 04 (EV-08), 07 (07-07) |
| M-16 | /events/{id} (past events) | "Sunrise Kayak June 2" and "Canvas & Cocktails — Tuesday, June 2" (day before audit) still live with no "this event has passed" notice; the series' next instance exists separately. | No past-event handling on detail pages. (The fetch-pass claim that they showed under "Today" was REFUTED by the browser pass — that was a UTC boundary on SSR output; real browsers see Jun 3 under Today.) | 04 (EV-07), 08 (refutation) |
| M-17 | /events/b031fcfd… (+ all detail pages) | "Event Link: https://www.havasuchamber.com/?fbclid=IwY2xjawSGu6x…" — 250+ chars of fbclid tracking garbage as visible link text; every detail CTA is "Event Link:" + raw URL, never a labeled button. One event's link is a raw Facebook *photo* permalink. | Detail template uses URL as anchor text (triage ED-4); no fbclid/UTM stripping on ingest. | 04 (EV-09, EV-16) |

### T4 — Time / timezone / window math

| ID | Page(s) | Evidence | Suspected root cause | Reported by |
|----|---------|----------|--------------------|-------------|
| M-18 | /today, /night, /lake | "Sunset **6:00 PM** — NWS forecast · Updated 15 min ago" on all three surfaces. Actual LHC sunset June 3 ≈ 7:39–7:45 PM MST — off ~100 minutes. "For a boating town, wrong sunset is a safety-adjacent error." | Conditions pipeline grabbing the wrong NWS forecast period or mangling the UTC→Phoenix conversion on the sunset field. NEW vs triage. | 01 (H-05), 06 (TOD-1), 07 (07-05) |
| M-19 | /home "Today around the lake" | `<div class="k">Tonight</div><h4>Lap Swim</h4><p>5:00 AM · Lake Havasu City Aquatic Center</p>` rendered at ~4:46 PM. Linked event page confirms "Wednesday, June 3, 5:00 AM" — ended ~11 hours earlier. Browser pass confirmed ("TONIGHT: Lap Swim 5:00 AM"). | "Tonight" selector picks first event of the calendar day regardless of time-of-day/passed status; recurring pool schedule pollutes the slot (ties to triage H-1). | 01 (H-03), 06 (HOME-1), 07 (07-12), 08 (#11) |

### T5 — Pagination cap

| ID | Page(s) | Evidence | Suspected root cause | Reported by |
|----|---------|----------|--------------------|-------------|
| M-20 | All category pages | Browser-confirmed: "hard 60-card cap, no lazy-load. … DOM contains exactly 60 /provider/ links; no load-more/pagination controls in the accessibility tree. Header says '269 listed' — ~209 listings unreachable." Professional: "253 listed", 60 cards (193 unreachable). `?page=2` on Services "returned the identical first 60 cards" AND drops the sub-chip row entirely. Content also invisible to crawlers. | Query LIMIT 60 with no pagination implementation; `page` param silently ignored. NEW vs triage. | 02 (A-04), 03 (B-03), 08 (#4, confirmed no lazy-load) |

### T6 — Data hygiene / duplicates

| ID | Page(s) | Evidence | Suspected root cause | Reported by |
|----|---------|----------|--------------------|-------------|
| M-21 | Provider records (systemic) | "ZENSHI Handcrafted Sushi" ×2 (slugs `…sushi`, `…sushi-2`); "Bad Miguel's" + "Bad Miguel's Mexican Restaurant ★ 4.3 (1042)"; "The Broken Yolk" + "Broken Yolk Cafe"; "Dos Amigos Tacos" + "Dos Amigos Taco's"; "Foothills Bank" ×2 (★5.0/184 and ★4.9/188); "Lake Havasu Family Eyecare" ×2 (★4.9/1787 and ★5.0/134 — likely a true dupe); "Beautiful Beards Pet Spaw" ×2; "New Day School" ×2 (`-2`, `-3`); "Holiday Inn Express & Suites… by IHG" ratinged + ratingless twin; vacation rental "…RV Hookups WOW!" ×3 (`-wow`, `-wow-2`, `-wow-3`); The Human Bean ×3 with raw `-2`/`-3` slugs and no card disambiguation. | Ingest dedupe gap — triage C-4 confirmed: `core/dedupe.py` is event-only, provider merge is manual, `google_place_id` nullable/non-unique. "-2"-suffixed slugs are the tell. | 02 (A-10, A-22), 03 (B-06, B-10, B-15), 05 (PR-17), 07 (07-19) |
| M-22 | Lodging + Professional + scattered | OTA listing titles as business names: "Vanderpump Rules Lake Havasu Luxury Villa w Pool", "2 Mi to Lake Havasu & Dtwn: Home w/ Game Room!", "Lake Havasu Retreat, Sleeps 8, … and Boat Parking, ." (trailing ", ."). Corrupted names: "Home \| RockerBens Music Lessons" (scraped `<title>`), "Air conditioning contractor ★ 4.7 (12)" (category string as name), "Travis Redman, Realtor of Lake Havasu City I Coldwell Banker Realty" (capital I for pipe), bare "Chevron" (no station identifier), "Farn stand goods" (typo), single-word "Havasu". | Names ingested raw from OTA/scrape sources with no cleaning or validation pass. | 03 (B-16, B-10, B-18, B-22), 02 (A-15, A-20) |
| M-23 | /api/map_data/* | "308 entities, only 279 unique coordinate pairs. Many entities carry coordinates truncated to 2 decimal places — e.g. Dos Amigos Taco's, Kegler's Pub, Megan & Erik's Water and Ice all at exactly (34.48, -114.32)" ≈ 1.1 km grid. Browser pass downgraded visible impact ("could not visually confirm exact-stacking … small clusters persist at high zoom which is consistent with snapped coordinates") — keep as P1 data issue pending a data check. | One ingest path rounded coordinates; affected pins render up to ~500 m off. | 06 (MAP-3), 08 (#partial refutation/downgrade) |
| M-24 | /api/events (whole dataset) | "On all 100 records sampled: `category: 'events'` (constant), `host: null`, `lat: null`, `lng: null`, `image_url: null`, `cost: null` (even where the description states '$20 General Admission')." | Schema fields never populated by ingest → no events on /map, no og:image, no category filtering, cost prose-only. | 04 (EV-13) |

### T7 — Presentation / product surface

| ID | Page(s) | Evidence | Suspected root cause | Reported by |
|----|---------|----------|--------------------|-------------|
| M-25 | /map | Browser-confirmed: "Single click on a pin navigates away to the provider page (no popup-first preview on first tap) — map state lost on every exploration tap. A popup component exists (shown on history-restore) but is not the first-click behavior." | Pin click handler wired to navigate; popup component built but bypassed. NEW vs triage (M-2 was "verify live"). | 08 (#6) |
| M-26 | /map | "'Eat & Drink' and 'On the Water' chips duplicated across COLLECTIONS row (scope=eat-drink-group) and CATEGORIES row (scope=eat-drink) with identical labels — indistinguishable to users." Tiny 0.72rem/65%-opacity row labels don't help. | Group scopes + category scopes resolve to the same display labels — triage M-1 (🔴 confirmed, `home/router.py:458`). | 06 (MAP-1), 08 (#7, confirmed) |
| M-27 | /provider/* (all 29 sampled) | "zero `rel='canonical'`, zero `og:` tags, zero `application/ld+json`" on every profile `<head>` — only `<title>` + meta description. | Profile template missing SEO/meta block; for a local directory, no LocalBusiness JSON-LD or og:image hurts SEO and link sharing. NEW vs triage. | 05 (PR-02) |
| M-28 | /provider/* "While you're here" | "Every Eat & Drink profile shows the identical trio: In-N-Out Burger / Juicy's / London Bridge Beach … Every Auto profile: Anderson Toyota / Anderson CDJR / Anderson Nissan … Every Beauty profile: **Lake Havasu City Aquatic Center** (a municipal pool) labeled 'Beauty & Personal Care'." Not proximity-based. "A tow truck's 'While you're here' suggesting a burger and a beach compounds the weirdness." | Hardcoded-per-category picks, not nearby/relevant; labels come from single legacy category (triage P-4 family). NEW specifics vs triage. | 05 (PR-03) |
| M-29 | /provider/* missing hours | "Profiles without hours render nothing at all — no badge, no 'Hours not available', no 'Call to confirm': a-toe-truck (a towing service most users need to know is 24/7), camel-towing, chevron (a gas station), star-cinemas (a cinema)…" ~1/3 of sample. Related: map data shows 80/308 (26%) "Hours unknown" and 19 "Open until 11:59 PM" (24-hour encoding artifact); In-N-Out profile "Closes at 11:59 PM" (closes 1:00–1:30 AM — midnight clamp). | Hours section silently absent when data missing; overnight hours clamped to 11:59 PM in the pipeline. | 05 (PR-04, PR-10), 06 (MAP-4) |
| M-30 | /events, /programs (routing) | "`GET /events` returns a raw JSON array … including internal fields users should never see: `'embedding': null`, `'source': 'admin'`, `'created_at'`, internal UUIDs. The human events page lives at /events-ui — the clean /events slug is squatted by the API." | API routes mounted at root without /api prefix; "/events-ui naming is a workaround that confirms the collision." Hands scrapers the full dataset and leaks schema internals. NEW vs triage. | 07 (07-01) |
| M-31 | sitewide navigation | Two different bottom navs: marketing pages (/home, /lake, /night, /family, /gas) get "💬 Ask ⛵ Lake 🍸 Night 🪁 Family"; utility pages get "Home Events Ask Explore Map Saved". "'Saved' and 'Map' are unreachable from the home-style nav, while 'Lake/Night/Family' vanish on the app-style nav." Also: /home's "💬 Ask" chip links to /home itself; the "☰" icon links to /lake; map page chrome is a third design system; event detail pages use lake_light (Playfair/Poppins) vs list's sandstone (Fraunces/Figtree) — "clicking any event visibly switches brands." | Two (three counting map) base template families diverged in prod. Product decision needed on which nav wins (see §6 Wave 3). | 01 (H-08), 07 (07-10), 04 (EV-17), 08 (#9) |
| M-32 | /terms, /privacy vs /login | Terms §2 verbatim: "**We do not offer user accounts or logins.** No persistent user profile is created…"; Privacy: "no persistent account ties you to past conversations." Live site ships /login ("We will send a one-time sign-in link"), /account/favorites, and a sign-in-gated claim flow — all collecting email. | Legal pages (Terms dated 2026-04-22) predate auth shipping. "A legal/compliance gap, not just copy rot" — privacy policy doesn't disclose account-email collection or favorites storage. | 01 (H-06), 07 (07-03) |

**P1 count: 32 (M-01 … M-32).**

---

## 4. Minor & polish (P2/P3)

| ID | Sev | Page(s) | Issue | Reported by |
|----|-----|---------|-------|-------------|
| N-01 | P2 | /chat | Suggested-prompt chips and "Photo" upload render as unstyled native buttons/plain text; composer photo button is the bare word "Photo". Raw hours/tags strings dumped into chat card descriptions ("Sun-Mon 11am-8pm Tue Closed … Stay Connected"); no link from result cards to provider profiles, no citations. | 08 (#12, #13) |
| N-02 | P2 | /chat | No AI-accuracy disclaimer anywhere in the chat shell; only caveat is buried in Terms §2. | 07 (07-09) |
| N-03 | P2 | /chat shell markup | Hard-coded "#ll-loading-overlay" with "SPONSORED / Finding the best spots / Brought to you by a local sponsor: check today's gas deals…" placeholder. NOT REPRODUCED visually in the browser session — exists in shell markup; remove or wire to real inventory before it ever shows. | 07 (07-11), 08 (not reproduced — softened to P2) |
| N-04 | P2 | /provider/* | Claim copy "Photos, **full menu** and offers unlock when X claims its listing" verbatim on banks, dentists, tow trucks, vets (29/29 unclaimed). Also the lock block is "dominant dead space above the fold on desktop." | 05 (PR-07, PR-08), 08 (#14) |
| N-05 | P2 | /provider/* reviews | Review excerpts have no reviewer name, date, or per-review link — only one "From Google reviews" header (Google content-policy/labeling risk). ShotVet renders the header with zero reviews under it and "★ 5.0 (1)". Luna's Massage (★4.9) shows a 1-star excerpt first. Rating display threshold inconsistent between card and profile (Abnorm Al's). | 05 (PR-09, PR-12, PR-13, PR-16) |
| N-06 | P2 | /provider/* | No website link row on any profile, even national brands. In-N-Out address renders "81-101 London Bridge Rd" (stray leading range fragment). | 05 (PR-11, PR-10) |
| N-07 | P2 | /today, /home, /events-ui, /lake | Lake level "48.9 ft" labeled "Lake level/Lake gauge" — it's USGS gauge height, not pool elevation (~448 ft); "locals/boaters expecting ~448 ft may read 48.9 ft as a catastrophic drop." Relabel "Gauge height" or convert. (Fetch pass initially suspected a dropped digit; the gauge-height explanation supersedes.) | 01 (H-14), 06 (TOD-4) |
| N-08 | P2 | /home | "Water" card kicker with no water data renders "Air 108°F / Heat index 99°F" under the Water label; heat index below air temp reads as a bug (plausible in dry air — use "feels like" or suppress). Water temp "Unavailable" in June at a lake site is also a product gap. | 06 (HOME-2, TOD-2), 01 (H-15, H-21), 08 (#11) |
| N-09 | P2 | /events-ui ↔ /home#calendar | Circular navigation: list's "See the month calendar →" → /home#calendar; calendar's "Full calendar →" → /events-ui. No real full-calendar page; the #calendar anchor doesn't scroll (lands at top of /home). | 08 (#10), 04 (EV-18) |
| N-10 | P2 | /map | Unknown scope (`?scope=nonexistent`) renders a blank grey void, no empty-state message, chip highlight wrongly defaults to "Eat & Drink". Initial load shows blank grey ~5s with no loading indicator. | 08 (#8, #9) |
| N-11 | P2 | /gas | Raw ISO timestamp rendered: "25 stations · updated 2026-06-02T15:05:09.401158Z · city avg regular $4.733" (also 3-decimal average). NOTE: triage marked G-1/G-4 ✅ already-fixed in code — live still shows both → deploy-lag or a second template (see §5). | 06 (GAS-1, GAS-4) |
| N-12 | P2 | /gas | Unlinked stations: Pilot (#2 in Today's 5 cheapest), Hacienda Mini Mart, Terrible Herbst — no provider records/slugs (triage G-3 confirmed live). | 06 (GAS-5) |
| N-13 | P2 | events meta | `og:description` truncated mid-URL: "…current pricing at https://www.lhcaz.gov/parks-recreation/o" on every Aquatic Center class page; no og:image anywhere (see M-24). | 04 (EV-15) |
| N-14 | P2 | event titles/copy | Instructor names + room numbers concatenated into titles: "Fit & Flex (155) Stephanie", "Tai Chi Vince", "Aqua Challenge Margie"/"Aqua Challenge Vince" (same class reads as two series). Raw ISO dates in body copy: "Tai Chi Vince on 2026-06-03 at 8:00 AM…", "Dodgeball June 5. 2026-06-05 (F) at…". | 04 (EV-11, EV-10) |
| N-15 | P2 | /events-ui counts | Three counts for the same data: SSR "28 coming up", JS variant "Events 25", API total 100 instances; headline excludes the dropped weekend events (B-03). Triage E-5 relabel applies. | 04 (EV-12), 01 (events count note) |
| N-16 | P2 | /categories templates | "Tap a type to narrow — the list updates right here." rendered on pages with ZERO chips: health-wellness-care, home-property-services, professional, beauty-care, auto-rv-fuel, public-civic-resources, attractions, pets. Triage C-5 said code returns 8 chips for civic — live shows none (see §5). | 02 (A-12), 03 (B-20) |
| N-17 | P2 | /categories/eat-drink filters | Active cuisine filter collapses the sub-chip row to just "restaurants" (can't pivot to Bars/Cafés without backing out). "Cuisine: All \| Breakfast" row renders on /categories/on-the-water (one stray breakfast tag drags a food filter onto a marina page). | 02 (A-21, A-13) |
| N-18 | P2 | /categories hub | Cover labels jam raw business names against category names with literal `&amp;` **in markup**: "Jennings &amp; Larson Family Dentistry - Lake Havasu ServicesPlumbers, contractors…". Browser pass REFUTED on-screen `&amp;` (renders as styled &) — markup/meta-only artifact + run-together text in source. Same dentist faces both Services and Health cards; Things to do and Attractions both faced by "Simply Savage Designs"; "Fitness & sports" card has no cover label at all. | 01 (H-12, H-13, H-17), 02 (A-14, A-25), 03 (B-19), 08 (refuted on-screen) |
| N-19 | P2 | sitewide brand | Three product names: titles split "— Ask Hava" vs "— Hava"; body copy "Back to Hava", "Hava grows from what locals share"; Terms §8 says "Havasu Chat"; sponsor contact sponsors@havasuchat.com. | 07 (07-08), 01 (H-18) |
| N-20 | P2 | /contribute | No "what happens next" copy after "Submit for review"; page branded "Hava"/"Add to catalog" while the nav link says "Add to Hava"; category-hint placeholder oddly niche ("BMX, gymnastics, dance studio"). | 07 (07-13) |
| N-21 | P3 | /login | Wall is clean but context-free — never says why ("Sign in to see your saved places"); same generic copy serves /claim/*. "We will send" reads stiff. | 07 (07-14) |
| N-22 | P3 | /sponsor | Sells "Marquee / Local Spotlight / Promoted" but home renders "Featured around town" and no surface is labeled "Local Spotlight" — advertiser can't map packages to placements. /advertise etc. 404 (consider redirect). | 07 (07-15) |
| N-23 | P3 | /privacy, /terms | Bottom-nav "Saved" tab marked `is-active` on legal pages (active-tab fallthrough). | 07 (07-17) |
| N-24 | P3 | /provider/a-toe-truck | "★ 4.9 (999)" — exactly 999 reads as a capped/sentinel review count; verify against source. | 07 (07-16) |
| N-25 | P3 | /events-ui Classes | "Lap Swim" appears as two identically-named series (Mon–Fri 5:00 AM; Tue/Thu 12:00 PM) — needs a differentiator. Recurring aquatic classes also dominate home calendar day cells ("+7…+11" counters; specials buried; cells not clickable). | 04 (EV-19), 06 (HOME-1 note), 08 (#16) |
| N-26 | P3 | /events misc | "FOREINER & STYX" source typo rendered; tag taxonomy inconsistent ("aquatics", "events", "Summer Camp", "Farmer's Market" — mixed case, "events" tag meaningless; stray space "theater , youth"); "Elective Theater at Lighthouse Lounge" title/venue disagree ("Lighthouse House"); venue concat artifact "2144 McCulloch Blvd NLake Havasu City" (missing space). | 04 (EV-20, EV-21, EV-16, EV-14), 07 (07-18), 01 (H-10) |
| N-27 | P3 | /gas | Footer claims "crowd-sourced (GasBuddy) and official-feed (Google)" but every row's Source = "gasbuddy"; "and … and" phrasing. Double "Updated" phrasing on /gas header ("Updated Jun 3, 2026 8:20 AM. Updated >8h ago"). | 06 (GAS-6), 01 (H-23) |
| N-28 | P3 | /today | Wind shows "10 mph" with no direction (NWS provides it; boaters want "10 mph SSW"). | 06 (TOD-3) |
| N-29 | P3 | /home, /events-ui strip | Conditions strip has no "updated X ago" label anywhere (only /today and /gas carry freshness); /categories has no strip at all — inconsistent surface coverage. | 06 (STR-1, cross-surface check) |
| N-30 | P3 | marketing pages | Tile link targets inconsistent: most deep-link to /chat?q=… but some go to plain category pages (/night "Bars & Lounges" and "Breweries & Wineries" both → generic /categories/eat-drink). Marketing footer omits Terms (only Home/Explore/Privacy). | 01 (H-20, H-24) |
| N-31 | P3 | /chat hero | "I'm *your local*." reads truncated; no rotating word ever appears; (earlier "stray space before period" not present in current build). | 01 (H-16), 08 (#15, softened) |
| N-32 | P3 | /categories sort | `?sort=closest` reorders with no location prompt or reference-point disclosure — closest to what? | 03 (B-21) |
| N-33 | P3 | /gas, quick-bites | Gas stations "Maverik", "Love's Travel Stop" under Quick Bites (defensible, reads odd). Venue profiles (Grace Arts Live, Havasu 95 Speedway) have no events section at all — events not wired to profiles. | 02 (A-23), 05 (PR-14) |
| N-34 | P3 | /provider/* About | 23/29 profiles' entire About is the auto-built boilerplate sentence — combined with the lock cover, the left column is effectively empty. | 05 (PR-15) |
| N-35 | P3 | events JSON | Adventure Camp description says "Ages 8-15" while structured field says `"age_max": 14`. | 07 (07-01 bonus) |

**P2/P3 count: 35 (N-01 … N-35; 20 × P2, 15 × P3).**

---

## 5. Cross-reference with the earlier code triage (AUDIT_TRIAGE_2026-06-03.md)

The new audit was run blind to the triage. Verdicts per triage item:

### 🟡 Needs-live-check items

| Triage item | Live-audit verdict | Detail |
|---|---|---|
| **S3 symptom** ("open now" wrong site-wide; code already Phoenix-correct) | **CONFIRMS the symptom, but reframes the cause.** No same-session timezone wall-of-Closed (08 refuted same-session flapping; 03 found plausible statuses on fresh renders; 05 found profile-level statuses correct). BUT cross-request Open↔Closed inversions are rampant (B-04): one serving path returns an hours-stale snapshot whose statuses are wrong *for the current time*. The triage's "data/deploy issue, not a TZ patch" call was right — specifically it's **stale/split cache serving**, not hours data or TZ code. |
| **S4** (counts don't reconcile) | **CONFIRMS — two distinct problems.** (a) Cache-skew counts: Eat & drink 308↔269, Services 1496↔1238, civic 66↔60 — same B-04 root. (b) A hard mismatch in *both* states: hub "Things to do 39" vs page "220 listed" (A-06/A-11) — that one is the different-COUNT-query bug the triage identified. |
| **C-4** (possible provider dupes) | **CONFIRMS, extensively.** M-21: ZENSHI ×2, Bad Miguel's, Broken Yolk, Dos Amigos, Foothills Bank ×2, Eyecare ×2, Beautiful Beards ×2, New Day School ×2/×3, Holiday Inn ×2, vacation rentals ×3, Human Bean ×3. Dedupe on place_id/address per triage fix sketch is warranted. |
| **C-5** (Community/civic chips — code returns 8, audit saw 0) | **CONFIRMS the live symptom — chips are absent in prod.** Both 02 (A-12) and 03 (B-20) found zero `?sub=` links on health-wellness-care, home-property-services, professional, beauty-care, auto-rv-fuel, public-civic-resources, attractions, pets — with the "Tap a type to narrow" copy still rendered. Either deploy lag or the chip-emitting code path isn't reached in prod. Plus the new dead-chip variant (B-07): where chips DO render (martial-arts, vacation-rentals, rv-parks) they match no stored subtype. |
| **H-1** (recurring classes bury one-offs) | **CONFIRMS.** Home "Tonight" slot is Lap Swim 5:00 AM (M-19); "nearly every day [of the month calendar] leads with 'Lap Swim'" with +7…+11 overflow counters burying specials (N-25); 13 of 28 events-list slots are classes. |
| **P-3** (address stray leading fragment) | **CONFIRMS.** In-N-Out renders "81-101 London Bridge Rd" (PR-10/N-06). One confirmed instance; sweep warranted. |
| **P-5** (three claim prompts — consolidate?) | **PARTIALLY REFUTES.** 05 explicitly checked: "Exactly one claim box + one lock banner per page — not redundant spam." Two surfaces, not three; current live state is acceptable. Drop from scope. |
| **M-2** (map pins/cluster/empty-state) | **CONFIRMS with new specifics.** Markers render (after ~5s blank, no loader); pin→business mapping accurate; BUT first click navigates away instead of opening the existing popup (M-25, new P1); invalid scope = blank grey void + wrong active chip (N-10); coordinate truncation in the data (M-23, visual stacking not confirmed). |
| **G-3** (some gas stations unlinked) | **CONFIRMS.** Pilot, Hacienda Mini Mart, Terrible Herbst unlinked (N-12) — missing provider records, per the triage's data-dependent diagnosis. |
| **CB-2** (claim-form required-field markers) | **DIDN'T REACH.** No auditor exercised /claim/* beyond confirming the 303→login redirect; the contribute form (different form) has proper required markers (07-13 noted "`Name *`" etc.). CB-2 remains open. |

### ✅ Deploy-verification items (triage said "already fixed in code — verify live")

| Triage item | Live-audit verdict | Detail |
|---|---|---|
| **S5** (conditions strip differs per page) | **CONFIRMS the fix within an instance; REFUTES across instances.** 06's cross-surface check: /home, /events-ui, /lake strips identical at the same minute — the shared cache works. But the cross-request flap (82°F↔108°F, B-04) means different instances/caches hold different snapshots, and /today applies a different staleness policy than the strip (M-10). The 5-min-TTL design is fine; the split serving is not. |
| **S6** (stale hardcoded date on Explore) | **CONFIRMS fixed — with a caveat.** No stale "May 29"-style date observed anywhere; /categories headers showed the current date. The B-04 stale-snapshot path could still serve an old render, but the hardcoded-date bug itself is gone. |
| **G-1** (raw ISO gas timestamp; code humanizes) | **REFUTES "fixed" — live still broken.** /gas renders "updated 2026-06-02T15:05:09.401158Z" verbatim (GAS-1/N-11). Either the fix isn't deployed, or a second template/code path renders the header. Investigate before assuming a redeploy suffices. (Note: 01 separately saw "/gas: Updated Jun 3, 2026 8:20 AM. Updated >8h ago" — humanized — so two render paths likely exist, consistent with the split-serving theme.) |
| **G-4** (city avg 3 decimals; code uses %.2f) | **REFUTES "fixed" — live still broken.** "/gas … city avg regular $4.733" (GAS-4/N-11). Same investigation as G-1: which template actually serves /gas in prod? |

### NEW issues the triage never saw

The triage was a confirmation pass over a prior audit; this live audit surfaced significant problems with no triage counterpart:

1. **Weekend bucket missing on /events-ui** (B-03) — Sat/Sun events invisible; the single worst content bug for the product's use case. (Triage E-1 touched window math but not this failure mode.)
2. **Chat transcript CSS blowup** (B-01) — flagship surface unusable; pure presentation.
3. **Month-calendar grid misalignment + clipping** (B-02).
4. **60-card pagination cap, `?page` ignored** (M-20) — up to 95% of inventory unreachable and uncrawlable.
5. **`/events` and `/programs` raw JSON squatting clean URLs**, leaking `embedding`/`source`/internal UUIDs (M-30).
6. **/terms placeholder text + lawyer notes live in prod** (B-06).
7. **Sunset shown 6:00 PM vs ~7:43 PM actual** (M-18) — safety-adjacent.
8. **Fake-noon event times** ("Monday Night Dance Party — 12:00 PM") (M-15).
9. **Hardcoded "While you're here" picks**, incl. the Aquatic Center labeled Beauty & Personal Care (M-28).
10. **Missing canonical/og/JSON-LD on all provider profiles** (M-27).
11. **Stale/split cache serving** as a distinct infra root cause (B-04) — the triage's S3/S5 framing assumed one serving path.
12. **Dead filter chips** (`?sub=` keys matching no stored subtype) (B-07) and **subtype monoculture** (all lodging = "Hotels", martial arts = "Kids Lessons") (M-07).
13. **Dual-source event duplicates with venue misattribution to organizer/source-site addresses** (B-08, M-12) — confirms and sharpens triage ED-1 as the top ingest fix.
14. **Map pin first-click navigates instead of popup** (M-25); **gas staleness thresholds vs daily cadence** (M-11 — triage G-2 confirmed live); **legal "no accounts" contradiction** (M-32); **coordinate precision truncation** (M-23); **OTA titles as business names** (M-22); **the (999) review-count sentinel** (N-24).

---

## 6. Remediation plan

> Repo rules apply throughout: feature branch off `main`, pytest + ruff green before every commit, PR and stop — merging is Casey's gate. **Every prod-data operation in Wave 1 follows dry-run → show counts → Casey approves → apply.**

### Wave 0 — today, low risk (pure presentation/copy; no data ops)

| Item | Fixes | Notes |
|---|---|---|
| W0-1 | **B-01** chat CSS: constrain SVG/icon and image sizing in chat response cards; fix missing-whitespace runs ("Pizza Spots5 of 12", "Call …Directions"); style the prompt chips + Photo button (N-01). | "One CSS file likely fixes the whole transcript" (08). Highest leverage fix on the site. |
| W0-2 | **B-02** month-calendar grid: 7-col template + leading-empty-cell logic; stop row overflow/clipping. | Data layer already correct. |
| W0-3 | **B-06** /terms: take the page down to a minimal honest stub or strip the placeholder/§-note text pending lawyer review. Do NOT invent jurisdiction language — that's the lawyer's call; the bug being fixed is *shipping draft notes*, not the legal content. | Coordinate with M-32 (accounts claim) — see Wave 3 decision D-1. |
| W0-4 | **N-11** /gas ISO timestamp + 3-decimal average — but first resolve the G-1/G-4 contradiction (§5): find which template actually renders /gas in prod; the "fixed" code may be on a dead path. | Also fix double-"Updated" phrasing (N-27). |
| W0-5 | Labels & copy batch: remove "Tap a type to narrow" where no chips render (N-16); "Tonight" badge logic guard so a passed 5:00 AM event can't be "Tonight" (M-19 — selection-logic part may slip to Wave 2; the *label* fix is Wave 0); "Water" card retitle/hide when no water data + "feels like" copy (N-08); lake-level label → "Gauge height 48.9 ft" (N-07); raw-ISO dates out of event body copy (N-14); "Event Link" → labeled button + strip fbclid/UTM at render (M-17 render half); og:description word-boundary truncation (N-13); events headline relabel "25 coming up" (N-15 / triage E-5); #calendar anchor scroll fix (N-09); "Saved" is-active fallthrough (N-23); brand-name sweep to one name in titles/copy (N-19) — *which* name is Wave 3 D-6 but "— Ask Hava" titles are the current majority convention. |
| W0-6 | Chat shell: remove the hard-coded SPONSORED loading overlay markup (N-03); add a one-line AI-accuracy disclaimer near the composer (N-02). |

### Wave 1 — data triage (**PROD DATA OPS — each item: dry-run → counts → Casey approval → apply**)

| Item | Fixes | Op shape |
|---|---|---|
| W1-1 | **B-05** miscategorization hot list: A Toe Truck, Detail Specialties, Sunshine Indoor Play, Grace Arts Live, London Bridge Beach, Lake Havasu Cigars, Havasu 95 Speedway out of Eat & Drink; the detailing cluster out of On the Water (M-04); Walmart/Smith's/Safeway/Albertsons out of Cafés (M-03); dealers/medical/HVAC out of Shopping (M-01); brokerages out of Lodging (M-07); Attractions junk purge incl. Jaque Meng (M-05); rental operators re-homed to On the Water (M-05). | Write an audit query that lists every (provider, category, subtype) suspected mismatch → dry-run report with counts per category → Casey reviews list → targeted UPDATE. Don't hand-fix one-by-one; this is the triage R2 interim until Wave 2. |
| W1-2 | **B-08 / M-12 / M-13** event venue misattribution + dual-source dupes: dedupe on canonical URL (Facebook event ID / organizer URL); null out organizer-address-as-venue and source-site-footer venues; split venue/address; purge description-text-in-venue records (Moonshot); fix the NLake concat and Lighthouse House/Lounge record. | Triage ED-1 is the code half (fix `go_lake_havasu.py` venue extraction + add shape validation) — ship the parser fix first, then backfill existing records (prod-data op, dry-run first). |
| W1-3 | **M-21** provider dedupe: merge `-2`/`-3` slug duplicates on google_place_id/address (NOT name); reconcile the Eyecare pair; add street disambiguators to chain cards (Human Bean ×3). | Dry-run merge report → approval. Per triage C-4: make `google_place_id` the dedupe key. |
| W1-4 | **B-07** dead chips: either backfill subtypes (martial-arts studios off "Kids Lessons"; lodging records into hotels/vacation-rentals/rv-parks) or drop chips with zero members. Backfill is the right fix; chip-drop is the stopgap. | Subtype backfill = prod-data op. |
| W1-5 | **M-15** fake-noon times: flag `start_time == 12:00:00` records from river_scene_import, null the time, render "Time TBD". **M-16**: add "this event has passed" handling. **M-22**: name-cleaning pass (OTA titles, scraped `<title>`s, "Air conditioning contractor"). **M-23**: re-geocode the 2-decimal-truncated coordinates. **N-24**: verify the (999) cap against source. | Each a scoped dry-run + counts. |
| W1-6 | **N-12**: create provider records for Pilot, Hacienda Mini Mart, Terrible Herbst (gas links). Check why the June 3 gas refresh didn't land (M-11 ingest-job half). | Small inserts; still prod writes → approval. |

### Wave 2 — structural (code; feature branch + PR per repo rules)

| Item | Fixes | Notes |
|---|---|---|
| W2-1 | **Taxonomy / primary category** (B-05 root, M-01…M-09, N-18 multi-face cards) — triage R2: introduce primary category/subtype, filter listings on it only, single source of truth for Home/Explore/Map label sets (kills M-08 drift), validate card subtype ∈ page chip set (triage C-1), invariant test for single membership. Decision gate: extend existing deterministic `subcategory` system vs richer primary_category+tags model — triage recommends the former (no LLM needed for the bulk). | The main event. Wave 1 buys time; this prevents recurrence. |
| W2-2 | **Weekend bucket + window math** (B-03): add "This Weekend" (or extend "This Week" through Sunday); fix triage E-1 boundary math (`(6-weekday)%7` Sunday collapse); anchor to `now_lake_havasu().date()`; reconcile SSR vs JS bucketing so both variants agree; "Tonight" selector excludes passed events and caps recurring-class pollution (M-19, triage H-1). | Test matrix: render the buckets for a Wed, Sat, Sun anchor date. |
| W2-3 | **Pagination** (M-20): implement real pagination or load-more on category pages; honor `?page=`; keep sub-chips on paged views; emit crawlable next links. | SEO-relevant. |
| W2-4 | **Cache consistency** (B-04, M-10): find the split — two instances? CDN/edge cache without proper keys/TTL? — and make serving deterministic; one staleness policy shared by strip//today//gas (fix triage G-2 thresholds to match daily cadence, ~24–30h); add "as of h:mm" to the strip (N-29). | This unlocks trusting every Open/Closed pill and count. Investigate Railway replica count + any response caching first. |
| W2-5 | **Routing**: move JSON off `/events` and `/programs` to `/api/*`; redirect `/events` → `/events-ui` (or swap so the clean slug is the human page); stop serializing `embedding`/`source`/internal fields (M-30). | |
| W2-6 | **Search fallback**: home search routes 100% into AI chat with no keyword fallback if the LLM pipeline is down; `/search` is 404 (07-20). Build at least a degraded keyword-results path, or accept the risk explicitly (Wave 3 D-7). | |
| W2-7 | Profile/meta batch: canonical + og + LocalBusiness JSON-LD on profiles (M-27); replace hardcoded "While you're here" with proximity/category query + correct labels (M-28, triage P-4); "Hours not available — call to confirm" fallback + fix the 11:59 PM overnight clamp (M-29); website link row (N-06); per-review attribution or relabeling per Google policy (N-05, pending Wave 3 D-4); map pin first-click opens the existing popup (M-25); map empty-state + loading indicator (N-10); map scope-row labeling (M-26, pending Wave 3 D-5); sunset extraction fix (M-18); event fields population — lat/lng/cost/category — so events reach the map (M-24). |

### Wave 3 — product decisions for Casey (judgment calls; STOP-and-ask items per repo rules)

| # | Decision | Context |
|---|---|---|
| D-1 | **Accounts vs the privacy/terms "no accounts" claim** (M-32, B-06): rewrite legal pages to disclose magic-link email accounts + favorites storage (lawyer involved), or gate/remove the account features until the docs catch up. Can't ship with the contradiction. |
| D-2 | **Two bottom navs** (M-31): pick one nav identity (marketing Ask/Lake/Night/Family vs app Home/Events/Ask/Explore/Map/Saved) or define an intentional two-mode scheme; also the third design system on /map and the lake_light vs sandstone event-template split (which one is canonical? — triage flagged the same question for E-3). |
| D-3 | **Claim-CTA copy per vertical** (N-04): "your menu" on banks/vets/tow trucks — per-category copy ("your services", "your rates") vs generic "your details". Also: keep the big lock block above the fold, or compress it? |
| D-4 | **Google review labeling** (N-05): keep excerpts with per-review attribution added (name/date/link, per Google content-display policy), or drop excerpts entirely. Triage P-6 already marked this DECISION. |
| D-5 | **Map scope rows** (M-26): collapse Collections into Categories, or keep two tiers with disambiguated labels ("Eat & Drink +")? Which 15-vs-12 taxonomy does the map adopt post-W2-1? |
| D-6 | **One product name** (N-19): Ask Hava vs Hava vs havasuchat.com (incl. the sponsors@ email domain). |
| D-7 | **Search = chat-only** (W2-6): accept AI-only search (with a documented degradation story) or build a keyword results page? Related: what is the chat **Photo upload** for (07-20's product question)? |
| D-8 | **Sponsor program surface naming + the interstitial pattern** (N-03, N-22): align /sponsor package names with rendered slots; decide whether a sponsored loading interstitial is ever acceptable given the "No engagement loops" footer promise. |
| D-9 | **Out-of-area listings** (M-07): keep Parker-side properties (Black Meadow Landing, Havasu Springs) with a distance hint, or geo-fence them out? |
| D-10 | **"On the Water" category identity** (M-04): its chips and contents say "Outdoors" — rename/split the category, or purge to marinas/rentals/lake-stays? |
| D-11 | **Low-data record policy** (M-05, M-22, A-19/A-20 tail noise): set a minimum-quality bar (rating count, descriptor, verified address) below which records are hidden from browse until claimed/verified? |
| D-12 | **Rating display threshold** (N-05/PR-16): minimum review count to show a star rating, applied consistently on cards and profiles. |
| D-13 | **Events on venue profiles** (N-33/PR-14): wire events to provider pages (the one thing users want from a theater's page) — scope/priority call. |

---

## 7. Verification checklist (re-test after fixes)

**After Wave 0:**
- [ ] /chat "best pizza" query: cards render with constrained icons/photos; "Pizza Spots 5 of 12" and "Call … | Directions" spacing correct; chips styled; no SPONSORED overlay in shell markup; disclaimer visible.
- [ ] /home month calendar: June 1 under MON; no clipped columns; Jun 6 cell (Battle for the Buoy) visible; verify at ≤390px (browser pass only reached 657px).
- [ ] /terms: zero bracketed placeholders, zero "lawyer review" notes; reachable from the marketing footer.
- [ ] /gas: humanized timestamp, 2-decimal average — confirmed on the *production* render path (this is also the G-1/G-4 dead-template investigation closure).
- [ ] No "Tap a type to narrow" on chip-less pages; "Tonight" never labels a passed event; lake metric labeled "Gauge height"; events show "Time TBD" not 12:00 PM where time was nulled.

**After Wave 1 (each op verified against its dry-run counts):**
- [ ] /categories/eat-drink: A Toe Truck absent; top 10 are restaurants; ?sub=cafes-coffee has no supermarkets.
- [ ] /categories/on-the-water: no detailing companies; /categories/shopping-essentials: no dealers/surgeons/plumbers; /categories/attractions: no Jaque Meng/wedding planners; boat-rental operators present on On the Water.
- [ ] /events-ui + API: one SpongeBob, one Battle for the Buoy (correct venue "Dillard's Parking lot"), one Farmers Market (correct venue + time); no venue equal to "Go Lake Havasu Visitor Center" unless the event is actually there; no description text in venue/address fields.
- [ ] Provider dupes merged: zenshi-handcrafted-sushi-2, new-day-school-3, foothills-bank-2 etc. 301 or gone; Human Bean cards show street qualifiers.
- [ ] ?sub=martial-arts, ?sub=vacation-rentals, ?sub=rv-parks return non-empty lists.
- [ ] Pilot/Hacienda/Terrible Herbst linked on /gas; gas data refreshed within 24h.

**After Wave 2:**
- [ ] /events-ui on a Wednesday: Today=Wed, This Week=Thu–Fri, This Weekend=Sat–Sun present, Next Week=Mon+; re-test with anchor on Sat and Sun (triage E-1 Sunday collapse). SSR and JS renders agree; headline count matches visible events.
- [ ] Two fetches of any category page 10 min apart (and via different IPs/instances): identical counts, identical Open/Closed pills, header temps within plausible drift. /today, /gas, header strip agree on gas price or all show the same staleness state.
- [ ] /categories/services?page=2 returns cards 61–120 with chips intact; all "N listed" reachable; crawler can discover deep pages.
- [ ] /events returns the human page (or redirects); JSON only under /api/*; no `embedding`/`source` fields in any public payload.
- [ ] Hub count = page count = sum of chip counts for every category (S4 closure); map Categories row matches /categories taxonomy.
- [ ] Sunset on /today within ±5 min of NOAA value; wind shows direction.
- [ ] Profiles: canonical + og + JSON-LD present; "While you're here" differs between two profiles in different parts of town; missing-hours profiles show "Hours not available"; no "Closes at 11:59 PM" on late-night venues; map pin first click opens popup; invalid map scope shows an empty-state message.
- [ ] Search degradation: with the chat API disabled in staging, the search box still yields a usable result path (per D-7 outcome).

**After Wave 3 decisions land:**
- [ ] Privacy/Terms accurately describe accounts, favorites, email collection (lawyer-approved).
- [ ] One bottom nav (or documented two-mode scheme) across /home, /events-ui, /chat, /map, legal pages; event detail pages share the list's design system.
- [ ] One product name in every title, body string, and the sponsor contact email.
- [ ] Claim CTA copy is category-appropriate on a bank, a vet, and a restaurant.
- [ ] Review excerpts carry attribution per D-4, consistently with the rating-threshold rule (D-12).

**Regression guards to add (test suite):**
- [ ] Invariant: every provider has exactly one primary category; card subtype ∈ page chip set.
- [ ] Bucket math unit tests for Wed/Sat/Sun anchors incl. weekend coverage.
- [ ] Event ingest: venue field rejects multi-paragraph/description-shaped input; venue ≠ organizer address when both present; canonical-URL dedupe across sources.
- [ ] No route serves raw JSON at a non-/api path.
