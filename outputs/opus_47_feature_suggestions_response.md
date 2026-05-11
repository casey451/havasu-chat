# Opus 4.7 Feature Suggestions — Response

> **Origin:** Opus 4.7 response on 2026-05-14 to the prompt at `outputs/project_summary_for_external_review.md`. Eight feature ideas with effort estimates + cross-cutting notes. Cowork primary will integrate into the master build plan once ChatGPT taxonomy returns.

---

Eight ideas, ranked roughly by how distinctively Havasu-shaped they are. Each is in the 5-element format (what / audience / fits texture / why generics can't / effort).

## 1. "Today in Havasu" conditions panel + chat awareness

**What:** A homepage strip and chat-accessible context layer showing real-time conditions that actually drive Havasu decisions: lake surface temp, channel wind, UV index, heat advisory level, air quality (AQI from AirNow), sunset/civil twilight, water level if USGS gauges exist nearby. Not a weather widget — a "what does today actually mean for what I should do" panel. Powers chat answers: "is it a good lake day?", "is it too hot to hike Sara Park?"

**Audience:** outdoor enthusiasts, water enthusiasts, tourists, families, snowbirds new to desert conditions.

**Fits texture:** pure utility, no upsell, real data from authoritative sources. Calm by construction.

**Why generics can't:** Google shows weather as a generic widget. Yelp shows nothing. None of them synthesize lake-relevant condition bundles for one specific city, and none of them feed those conditions into chat ranking.

**Effort:** M (data plumbing + display + chat hook).

## 2. Indoor/Shaded/Outdoor tagging + heat-aware ranking

**What:** Tag every venue with a structured indoor/shaded/outdoor/water-adjacent classification. When heat advisory or AQI is bad, default ranking shifts toward indoor/shaded. Chat answers diverge: "kid activities" in March vs. "kid activities when it's 115" surface meaningfully different sets. Same time-aware heuristic you already use for breakfast-vs-bars, just keyed on conditions instead of hour.

**Audience:** families, elderly, tourists who underestimate Havasu summer, anyone with kids or pets in July-September.

**Fits texture:** quietly serves a real pain point, no claims of intelligence beyond a heuristic.

**Why generics can't:** no national platform encodes this dimension because it doesn't matter in Boston. Hyperlocal climate-shaped ranking is exactly the kind of thing Yelp will never bother to build.

**Effort:** M — the tagging work is the bulk; the ranking shift is a few rules.

## 3. Seasonal-hours data model + snowbird-aware UX

**What:** Promote hours to a structured `seasonal_hours` model (e.g., summer/winter/shoulder), not one flat block. Surface honest copy: "reduced summer hours — last verified June 2024" or "reopens October per owner." When a returning snowbird logs in in October, the homepage greets them with a "what's reopened since you left" view.

**Audience:** snowbirds (huge), locals, tourists who hit closed places in July.

**Fits texture:** trust-first, honest about staleness, snowbirds are an underserved audience nationally.

**Why generics can't:** Google Places stores a single weekly hours block. Yelp the same. The seasonal model is a schema gap nobody fills because nobody else cares about snowbird cities.

**Effort:** M (schema + admin intake + display).

## 4. Boat-access mode

**What:** A directory-wide toggle that re-keys filtering by water access. Restaurants with dock tie-ups, fuel docks with current pricing if obtainable, ramps with parking-fills-by-time annotations, anchorages near specific beaches, marine services that come to your slip. Map view shows water vs road overlays. Chat handles "where can we tie up for lunch within 20 min of Site Six?"

**Audience:** boaters (the dominant tourist/second-home dollar), water enthusiasts, vacation-rental guests with rented boats.

**Fits texture:** bone-deep local. Either you know which docks are usable or you don't.

**Why generics can't:** this isn't a Yelp filter and never will be. Google Maps shows ramps as POIs but doesn't model dock-tie-up as a venue capability.

**Effort:** M-L (data is the work; UI is small).

## 5. Crowd & congestion context ("quiet finder")

**What:** Per-venue and per-area annotations of when it's busy, drawn from a mix of Google popular-times (where available) and hand-curated operator notes. "Bridge backs up Sunday 2–5 PM May–October." "Channel impassable during World Finals weekends." "Cattail Cove fills by 9 AM on three-day weekends." Chat handles "where's not crowded right now?" with honest hedges.

**Audience:** locals avoiding tourists, tourists who want the local feel, elderly who avoid crowds, anyone planning around major events.

**Fits texture:** calm-by-design. The whole point is helping people avoid the loud, packed places.

**Why generics can't:** Google's popular-times is generic. The Havasu-specific overlay (bridge dynamics, event spillover, channel congestion) is hand-curated local knowledge no national tool will gather.

**Effort:** M (small CMS field + chat surface).

## 6. Mobile-services cross-cut

**What:** A first-class capability flag and filter for providers who come to you: mobile detailers, mobile vets, in-home health and PT, mobile RV/marine mechanics, on-water service techs, in-home senior care, mobile windshield repair, mobile pet grooming. Surface as both a category-spanning filter and a chat capability ("who can come fix my boat at my slip?").

**Audience:** elderly, snowbirds (don't want to deal with shop visits), second-home owners (often not in town when the service is needed), busy families.

**Fits texture:** practical, underserved, no gimmick.

**Why generics can't:** "mobile" isn't a Yelp facet. You have to know which providers actually travel.

**Effort:** S-M (it's a boolean + UI surface; the data work is real but bounded).

## 7. Local Peer Recommendation web

**What:** A lightweight, moderated mechanism where verified merchants can publicly recommend providers in other categories. Plumber endorses an electrician they trust. Restaurant endorses a wine shop. Veterinarian endorses a mobile groomer. Surfaced on profile pages as "Recommended by 4 local businesses (verified)." Not a review, not pay-to-play, not stars — a curated peer-trust signal. Caps + moderation to prevent reciprocal-back-scratching games.

**Audience:** anyone hiring a home service or specialist, but especially newcomers and snowbirds who lack a personal network.

**Fits texture:** trust-first without inviting review-war dynamics. This is the structural substitute for the user-review feature you deliberately deferred.

**Why generics can't:** Yelp won't curate. Facebook groups do this informally and noisily. Capturing it as structured data inside a directory requires direct merchant relationships — your sales motion supplies them.

**Effort:** M.

## 8. Opt-in protective alerts

**What:** Magic-link account holders can opt into a small, well-scoped set of alerts: heat advisory (with curated indoor alternatives for whatever they typically do), AQI deterioration affecting outdoor venues on their favorites list, lake hazards or closures from the city, major event traffic warnings. Calm tone — no engagement-loop language, no streaks, no badges. Email-only at first; SMS optional later.

**Audience:** elderly, asthmatics, parents, outdoor enthusiasts, snowbirds who don't yet read desert conditions correctly.

**Fits texture:** protective, not promotional. The texture of an alert that says "AQI is climbing; here are three of your favorites that are indoor" vs. a generic National Weather Service push is the entire pitch.

**Why generics can't:** Nobody currently links condition triggers to hyperlocal venue context for one city.

**Effort:** M (relies on #1 already existing).

## Cross-cutting notes (from Opus)

A few of these compound: #1 unlocks #2 and #8 cheaply. #5 and #4 share a CMS surface. #3 and #6 are both boolean-or-enum additions to the existing schema and could ship together as a "directory v1.1 schema pass."

If forced to pick the two to build first for moat purposes: **#3 (seasonal hours) and #5 (crowd context)** — both are pure data moats where every entry filled is a thing Google structurally cannot match, and they don't require infrastructure you don't already have. **#1 is the most visible**, but it's also the most likely to feel like a gimmick if the rest of the product isn't denser than Google around it.

Two things Opus deliberately did NOT suggest:

(a) anything review-shaped — the deferral is correct and #7 is the cleaner trust substitute.

(b) accessibility-as-a-feature in the standard ADA-yes/no sense — the right version is a structured accessibility profile (transfer space, step count, lighting, noise, parking proximity) and it's worth doing, but it's a data-collection program more than a feature, and it competes for the same field-trip hours as everything in #3–#6. Worth queueing as a v1.2 push once the schema spine is settled.
