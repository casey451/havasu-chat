# Havasu Chat — Project Summary + Capabilities at Launch

> **For the operator (Casey):** paste this whole document into a fresh Opus 4.7 chat. Then ask: "What features should we add that aren't in this scope?" The doc is self-contained — Opus has no prior context.

---

## What this product is

Havasu Chat is a comprehensive hyperlocal directory and AI chat product for Lake Havasu City, Arizona — population ~59,000, plus seasonal snowbirds and a heavy tourist crowd around the lake. The goal is to be the one site where anyone in Havasu can find every useful business, place, event, class, and service in town. Locals, snowbirds, tourists, dog owners, outdoor enthusiasts, families, retirees, single people looking to party, couples on date night — every demographic.

The strategic bet is that the generic internet (Google, Yelp, Facebook groups, national directories) can't compete on hyperlocal context. Knowing that the bridge backs up Sunday afternoons. Knowing that English Village feels different from the 95 corridor. Knowing that snowbird season changes which businesses are open. Knowing that emergency plumbers in Havasu work differently than what Phoenix Yelp would suggest. Knowing that boat-access matters for some restaurant choices. The product reflects those realities because it's built around the city specifically and the data is verified rather than scraped from random national sources.

It's bootstrapped, solo-founder. No outside funding. Build-first, sell-after sequencing: complete the full site (every relevant category populated, chat polished, merchant tooling working, trust signals live) BEFORE starting any sales. Roughly 6-9 months of build time at solo-founder pace. Then monetization model gets locked + sales begin.

## How users interact with it

Three equal front doors, all hitting the same underlying directory:

1. **Browse manually** by category and sub-category, with filter chips and sort options. Like "Home Services → Plumbing → Emergency Service → North Side." Or "Eat & Drink → Mexican → English Village → Open Now."
2. **Search** with full-text/faceted search across everything.
3. **Ask Hava (chat)** in natural language. "Where can I take my dog for breakfast?" "Who fixes AC after hours?" "What's open for date night in English Village?" "Where's a good boat ramp on the south side?" Chat answers across all categories, knows local context, makes recommendations grounded in the verified directory.

## Audience demographics (every slice gets served)

- Year-round residents (~35% age 65+ per Census; lots of retirees, lots of homeowners with pools and seasonal-home upkeep)
- Snowbirds (winter residents October-April)
- Younger working residents (families with kids, service-industry workers, hospitality)
- Tourists / weekend visitors (boating, Desert Storm, IJSBA World Finals, spring break, family vacationers)
- Out-of-town homeowners (vacation rental owners, second-home owners)
- Single people / party crowd (bars, late-night, live music, weekend events)
- Couples / date-night
- Elderly / accessibility-aware users
- Dog owners (dog parks, dog-friendly patios, off-leash areas)
- Outdoor enthusiasts (hiking, kayaking, fishing, ATV, paddleboarding)
- Water / lake enthusiasts (boat rentals, marinas, ramps, fuel docks, slip rentals)
- Self-care / wellness (yoga, massage, gyms, mental health)
- Hobbyists (pickleball, disc golf, RC tracks, model railroad, car clubs)

## Capabilities at launch (what the finished V1 does)

### Directory shape

- 15-25 top-level categories (final list pending taxonomy research, but covers: Eat & Drink, Home Services, Health, Outdoors & Parks, On the Water, Pets, Family, Shopping, Lodging, Auto & Gas, Community/Civic, Events, Classes, Specialty Venues, etc.)
- Each category has rich sub-trade filtering (cuisine type, sub-category, etc.)
- Roughly 500-1,500 directory entries at launch across all categories
- Two types of entries:
  - **Providers** = commercial businesses (restaurants, plumbers, hotels, vets, lawyers, retail, etc.)
  - **Places** = non-business entities (dog parks, boat ramps, beaches, trails, scenic overlooks, libraries, civic buildings, sports fields, RC tracks, hobbyist venues, landmarks)
- Each entry has: name, slug, category, sub-trade, district, address or service area, lat/lng, hours, photos, verified badge, last-verified date, source attribution

### User-facing pages

- Homepage with category tiles, search bar, "Ask Hava" chat, top-of-mind recommendations, weather widget
- Category landing pages for each category — filter chips (sub-trade / cuisine / sub-type), sort options (default / most-verified / open-now / closest), sponsor slot at top (when monetized), pagination, editorial copy at bottom for SEO + local context
- Individual profile pages for each Provider — verified badge, last-verified date, photos, hours, action buttons (call, directions, website, ask Hava), service details, Google review snippets (if available), claim/upgrade CTAs
- Individual profile pages for each Place — amenities (per place type), hours if applicable, directions, photos, map embed, no commercial fields
- Map view across categories with marker clustering
- Mobile-first responsive across all pages

### Filter and sort dimensions

- Sub-trade chips (per-category)
- District chips (especially for Eat & Drink: English Village, Downtown, Lakefront, North End, 95 corridor)
- Operational chips (Open Now, Open Late, Open Sunday, Takeout, Delivery, Boat Access, Outdoor Seating, Dog Friendly, ADA Accessible)
- Price range (Eat & Drink, Lodging, services)
- Dietary options (Eat & Drink: Vegan, Vegetarian, Gluten-free, Halal, Kosher)
- Sort by: default (verification + recency + featured + rating + alphabetical), most-verified-first, open-now-first, closest (when geolocation granted)
- Time-aware default ranking — at 8 PM, closed breakfast places sink and bars rise; at 8 AM, coffee and breakfast rise. Weighted heuristic, no ML required.

### AI chat capabilities

- Natural-language Q&A across the full directory
- Cross-category queries ("where can I take my dog for breakfast?" pulls from both restaurants and dog parks)
- Local-context awareness (district vibes, seasonal patterns, hyperlocal nuance)
- Tiered routing: deterministic entity match → structured retrieval → LLM synthesis
- Confabulation guardrails (the chat doesn't make up phone numbers or hours)
- Sponsor disclosure on chat responses where applicable (clearly labeled, not stealth-injected)
- Voice is "AI local of Lake Havasu" — plain, founder-direct, no marketing-speak, honest about uncertainty

### User accounts (magic-link via email)

- No passwords, no OAuth — magic-link only via Resend
- End-users get: favorites/saved lists, alerts, personalized recommendations
- Merchants get: claim flow, edit UI for their own listing, per-merchant analytics dashboard
- Admin (operator) gets: moderation, claim verification, content management

### Trust signals

- Verified badges with last-verified date
- Verification method visible (owner-confirmed, phone-call, operator-visit, etc.)
- Source attribution (Google, OSM, city open data, operator-entered)
- Freshness bands (fresh / acceptable / aging / stale — honest copy at each band)
- "Hava's pick" editorial badge (strict governance: verified + recent + complete + manually assigned; NOT pay-to-play)
- No fake urgency, no countdowns, no "limited time" pressure

### Data ingestion

- Layered scrape system:
  1. Google Places API (broadest commercial + many places)
  2. OpenStreetMap + Overpass (parks, trails, ramps, civic — better than Google for non-commercial)
  3. City of Lake Havasu + Mohave County + AZ state open data (civic + licensed contractors)
  4. Specialized APIs (NPI for healthcare, AZ ROC for contractors, USA Pickleball, PDGA, etc.)
  5. Manual recovery (operator field-trips for what no API covers — small parks, RC tracks, hobbyist venues, weekly meet-ups)
- Scheduled scrapers refresh data monthly/quarterly
- Deduplication across sources (geo proximity, normalized name, stable IDs)

### Sponsor system

- Flexible 4-tier sponsor inventory model (marquee, spotlight, promoted, supporter)
- Sponsor state machine (draft → review → approved → live → paused → archived)
- Specific monetization model NOT yet locked — kept flexible. Options under consideration include subscription tiers, pay-per-call lead-gen, featured listings, affiliate on deals, end-user premium, marketplace fees on bookings. The default fallback plan is: Verified Presence ($79/mo subscription for any business, no contract), Category Visibility ($349/mo one-sponsor-per-category slot), Seasonal Takeover ($1,500-$5,000 homepage for big events). All cold-pitch materials for that fallback plan are already written. Final monetization decision happens after the product is built and testable.

## What's intentionally NOT in V1 (deferred to V2 or later)

- Native user-submitted reviews and ratings (we surface Google review snippets; we don't have our own review system — intentional, because review-war dynamics aren't a fit for the trust-first product)
- Deals and coupons with QR code redemption
- Lead-gen attribution (Twilio call tracking)
- Booking / reservation flows
- Itinerary builder ("plan a weekend in Havasu")
- End-user paid tiers (premium / ad-free)
- Membership program for residents
- Syndication API for other apps to consume the directory
- White-label for other small cities
- Social features (user-to-user messaging, follows, etc.)
- Place model entities for ephemeral/recurring (weekly meet-ups treated as Events instead)

## Design principles / texture

The product feels CALM, not loud. No engagement-loop tricks. No popups. No fake urgency. No countdown timers. No "Top 10 Best!" clickbait. Sponsor labeling is honest and visible. The chat says "I don't know" rather than confabulating. The directory pages have white space and respect the reader's time.

It's mobile-first because most local search is mobile. It's HONEST about what's verified and what's stale. It positions itself alongside Google/Yelp/Facebook, not against them — "this sits beside your existing tools, doesn't replace them" is the founder's actual pitch.

The defensible angle is hyperlocal context depth. The product gets interesting when it starts behaving like a thoughtful local person rather than a database with a search box. The Generic Internet can't compete on Havasu-specific knowledge; that's the moat.

## Operator (founder) constraints

- Solo founder, bootstrapped, no outside funding (yet)
- Build-first, sell-after — no sales until the site is comprehensive and working
- Founder-led cold-pitch sales — Casey walks into local businesses in person
- 6-9 month build timeline at solo pace
- No team yet; potentially a Havasu-based BDR by month 6 if revenue justifies

## Tech stack (only relevant for buildability of suggestions)

FastAPI + SQLAlchemy + Postgres (Railway production) / SQLite (local dev). Jinja2 templates for server-rendered HTML (no React frontend). Tailwind-style hand-rolled CSS. Leaflet + OSM tiles for maps. Google Places API + planned OpenStreetMap Overpass + planned city/state open data + planned specialized APIs for scraping. OpenAI gpt-4o-mini for the chat synthesis layer (with confabulation guardrails). Resend for magic-link email. Background-job infrastructure: Railway scheduled-jobs services + FastAPI BackgroundTasks + optional Outbox table for must-not-lose jobs (no Celery/Redis).

## Question for you (Opus 4.7)

Given the project shape, audience, design principles, and what's already in scope:

**What features would you add that aren't in this scope** — that would meaningfully strengthen the product for the audiences listed, fit the calm/honest/hyperlocal texture, are buildable by a solo founder over the 6-9 month build window, and create additional defensibility against generic search/Yelp/Google?

You can suggest:
- Specific user-facing features (new pages, new UX patterns, new interactions)
- Specific data dimensions or filter facets
- Specific chat capabilities or query patterns
- Specific trust/verification mechanisms
- Specific operator workflows
- Specific monetization angles (since model is kept flexible)
- Specific seasonal / event-driven features that lean into Havasu's rhythm
- Specific integrations or partnerships that fit
- Specific accessibility or inclusivity features
- Anything that the audiences listed would genuinely value and would be hard for a generic-internet competitor to copy

For each suggestion, briefly state:
1. What it is
2. Which audience(s) it serves
3. Why it fits the product texture (calm/honest/hyperlocal)
4. Why a generic competitor (Google/Yelp/Facebook) can't easily replicate it
5. Rough effort estimate (S = hours, M = days, L = 1-2 weeks, XL = 2-4 weeks)

Don't suggest things explicitly listed as "intentionally NOT in V1" unless you have a strong argument for promoting them. Don't suggest "national expansion" — this is hyperlocal by design. Don't suggest features that require a team — solo-founder constraint is real.

Be specific. Be opinionated. The goal is fresh feature ideas, not feature lists. Quality over quantity — 5-10 great ideas beats 30 generic ones.
