# Boat-Access Mode — Design Memo

> **Status:** design only; no implementation, no migration.
> **Source feature:** Opus 4.7 suggestion #4 (elevated from "filter chip" to "mode" per Casey's lock 2026-05-14 — see `outputs/opus_47_feature_suggestions_response.md`).
> **Audience:** Cowork primary + Casey; future implementation-lane author.
> **Companion docs:** `outputs/chatgpt_response_eat_and_drink_strategic_review.md` §3.4 (where Boat Access first appeared as an operational filter; this memo elevates the framing), `docs/maintainability/place_model_design.md` (voice anchor + Place model handles ramps/marinas), `docs/maintainability/conditions_panel_and_alerts_design.md` (channel-wind tile feeds boat-day decisions).

---

## §1 Why boat-access is a MODE, not a filter (problem statement)

Lake Havasu's identity is the lake. The city sits on the channel; English Village is on the water; Site Six, Pittsburgh Point, Windsor Beach, and Castle Rock are all water-accessible destinations. Boaters — local owners, snowbird boat-toters, jet-ski renters, fishing crowd, weekend party boats — are the dominant tourist/second-home dollar in Havasu. They make decisions from a boat-first perspective: "where can we tie up for lunch?", "what fuel dock is on the way back?", "which ramps fill up by 9 AM?", "where can we anchor with the kids?"

A boat-access **filter chip** alongside Open Late / Outdoor Seating / Dog Friendly handles the simplest case ("show me restaurants that allow boat tie-up"). It fails the harder cases:

- The user doesn't want to wade through dock-less restaurants then filter — they want their *entire* directory experience reoriented around water.
- Map view should show water vs land overlays prominently, not a generic city map.
- Profile pages should surface dock specs (slip count, max boat length, fuel availability) above hours and address.
- Distance should be measured by water/channel proximity, not street address.
- Chat queries assume boat context ("where can we eat?" becomes "where can we tie up and eat?").

**Boat-access mode is a directory-wide reorientation, not a single facet.** When mode is active, the product behaves as if the user is reading it from a boat. When mode is off, the product behaves normally. The two states share the same data but render and rank it differently.

This is bone-deep local. Either you know which docks are usable or you don't. Yelp won't build it. Google Maps shows ramps as POIs but doesn't model dock-tie-up as a venue capability. The Generic Internet structurally can't match this.

---

## §2 Scope — where mode applies

Boat-access mode is a session-level state that affects:

1. **Homepage** — header shows a small mode indicator; hero area shifts to "today on the water" framing; conditions panel emphasizes channel wind + water level + lake temp.
2. **Category landing pages** — filters reorder so boat-relevant facets are visible first; sort defaults bias toward boat-accessible entries; map view defaults to water-centered.
3. **Profile pages** — boat-access details promoted to above-the-fold; dock specs visible before street address.
4. **Map view** — water/channel overlay enhanced; boat-accessible markers visually distinct; tap markers shows boat-relevant info first.
5. **Chat** — query interpretation biased toward boat-relevant readings; tier 2 retrieval filters by boat-access flags; tier 3 LLM prompt includes a "user is in boat-access mode" preamble.
6. **Search results** — boat-accessible entries ranked higher when mode is active.

Out of scope: the admin tooling, the account-lite signup flow, sponsor-edit UI, ingest scrapers — none of these change based on user-side mode state.

---

## §3 Mode toggle UX

### §3.1 Toggle placement

Two surfaces:

- **Header (everywhere)** — small toggle in the top-right corner of every page. Icon (boat silhouette) + label ("Boat mode"). Single tap toggles on/off. When on, the icon is filled + label has subtle accent color shift.
- **Homepage hero** — for first-time users, a one-time prominent banner: "Visiting Havasu by boat? Switch to Boat mode." Dismissed after first toggle (sticky preference).

### §3.2 State persistence

Three layers of persistence:

1. **URL query param** (`?mode=boat`) — primary mechanism. Shareable URLs work correctly when sent ("here's the restaurant page I told you about — in boat mode").
2. **localStorage fallback** — for users who arrive without the query param, last mode state restored.
3. **User preference on account** (logged-in users) — `User.preferred_mode: enum("default" | "boat")` saved on toggle. Logged-in users get their mode preserved across devices.

Priority order: URL param > localStorage > user preference > default ("default" mode).

### §3.3 Visual indication

When mode is on, three subtle signals:

- Header icon filled + accent color
- Conditions panel emphasizes water-related tiles
- Map markers use boat-icon variant where applicable

Anti-pattern: do NOT make the page dramatically different in mode. Same layout, same calm voice. Mode shapes content priority + ranking, not the visual brand.

### §3.4 First-time user education

When mode is activated for the first time, a small dismissable note explains what changes ("Boat mode reorders results and map by water access. Toggle anytime."). Single dismissal sticks.

---

## §4 Schema for `boat_access` JSON

New field on `Provider` (and `Place` for marinas/ramps): `boat_access: dict | None` — JSON shape per entity type.

### §4.1 Restaurant / commercial venue shape

```json
{
  "dock_tie_up": true,
  "dock_count": 6,
  "dock_max_length_ft": 24,
  "dock_notes": "First-come; outboards on east side only.",
  "fuel_dock": false,
  "boat_proximity_minutes": 5,
  "channel_visible": true
}
```

### §4.2 Marina shape

```json
{
  "dock_tie_up": true,
  "dock_count": 40,
  "dock_max_length_ft": 60,
  "slip_rental_daily": true,
  "slip_rental_monthly": true,
  "slip_rental_seasonal": true,
  "fuel_dock": true,
  "fuel_types": ["regular", "diesel"],
  "marine_services": true,
  "pumpout_station": true,
  "boat_proximity_minutes": 0,
  "channel_visible": true
}
```

### §4.3 Ramp / launch (Place) shape

```json
{
  "ramp_count": 3,
  "ramp_max_boat_length_ft": 30,
  "ramp_concrete": true,
  "trailer_parking_count": 50,
  "fills_by_time": "9 AM on three-day weekends",
  "ramp_lighting": true,
  "ramp_fee_dollars": 10,
  "restrooms": true
}
```

### §4.4 Service-only (mobile marine, on-water tech) shape

```json
{
  "on_water_service": true,
  "service_area_water_zones": ["main_channel", "south_island", "site_six"],
  "service_response_time_minutes": 30,
  "available_during": "weekends_only"
}
```

### §4.5 Schema philosophy

The `boat_access` field is intentionally flexible (JSON, not enumerated columns) because boat-relevant capabilities vary widely across venue types. Implementation lane validates the JSON against a Pydantic model per `entity_type + venue_subtype` combination. Operator admin form generates the right form per venue type.

`Provider.boat_access` is `None` for any venue that's not boat-accessible. Filter `WHERE boat_access IS NOT NULL` to find boat-relevant entries.

---

## §5 Profile-page rendering changes when mode is active

When `?mode=boat` is active and the entity has `boat_access IS NOT NULL`, profile-page region order changes:

**Normal mode order** (per Provider profile UX spec):
1. Identity header
2. Primary actions
3. Trust strip
4. Photos
5. Description
6. Service details
7. Hours + address
8. Reviews
9. CTAs
10. Footer

**Boat mode order:**
1. Identity header (same)
2. Primary actions — add "Get water route" button (links to `https://maps.google.com/?q=<lat>,<lng>` with a marker)
3. **Boat-access dock summary** (new top-of-fold region for boat-mode-active): dock count, max length, fuel availability, channel-visible badge, boat-proximity-minutes label
4. Trust strip
5. Photos
6. Description
7. Service details
8. Hours + service-area (street address de-emphasized)
9. Reviews
10. CTAs
11. Footer

For entities with `boat_access IS NULL`, profile page falls back to normal order even in boat mode (no false signal).

Visual treatment of the new region: distinct from regular sections (different accent color, water-themed icon, brief honest label like "Boat access details — operator-verified").

---

## §6 Map water-overlay implementation

Default Leaflet + OSM tiles per pivot §8.4. In boat mode:

- **Tile layer** — add an OSM water-overlay layer on top of the default tiles. OSM has a separate `water_polygons` layer (or use `cyclosm-base`/`humanitarian` themes which emphasize water differently). The implementation lane can pick the cleanest free option.
- **Boat-accessible marker icon** — entities with `boat_access IS NOT NULL` get a boat-icon variant marker (anchor/boat-hull symbol) instead of the default pin.
- **Centered on the lake** — default zoom/center coordinates shift to mid-channel rather than downtown when no specific coordinate is in the URL.
- **Marker popup ordering** — on tap, popup shows: provider_name → boat-access summary → "Get water route" → standard actions. Boat-access details lead.

**Out of scope for V1:** no nautical chart layer, no live boat traffic, no marine weather radar overlay, no AIS integration. Those are V2 if/when boat-mode usage justifies the integrations.

---

## §7 Chat query interpretation bias

When mode is active, chat tier 2 + tier 3 handlers receive a `mode_context = "boat"` flag. This shapes interpretation:

**Tier 2 query filter modifications:**
- `WHERE boat_access IS NOT NULL` added to retrieval queries when entity is a Provider/Place where mode applies.
- Sort order biased toward `boat_access.dock_tie_up=true` and lower `boat_access.boat_proximity_minutes`.

**Tier 3 LLM prompt preamble:**

```
The user is using Boat mode — they are likely on or about to be on the water. 
When recommending venues, prefer water-accessible options. When mentioning hours 
or location, mention dock availability or water proximity. If the user asks 
"where to eat" or "where to fuel up", interpret as "where to tie up + eat" or 
"where can we fuel the boat".
```

**Confabulation guardrails:** boat-access data is operator-curated and patchy. The LLM must not invent dock specs ("4 slips available" when the data says nothing about slip count). The standard HALT 3 close-out guardrails apply with extra weight here.

**Cross-mode queries:** if the user asks something that doesn't map cleanly ("who's the best plumber?"), mode doesn't filter results — plumbers don't have boat-access. Mode is contextual not exclusionary; if no boat-relevant filter applies, results are normal.

---

## §8 Operator data collection

Boat-access data is operator-curated. Google Places returns nothing about dock count or fuel availability. Field-trip workflow needs new questions per boat-relevant entity:

**For commercial venues with water access** (restaurants on the channel, lake-side cafes):
- Visit by water if possible; if not, observe from a boat-eye view in person.
- Count docks. Estimate max boat length (visual).
- Note fuel pump if visible. Note channel visibility from the dock.
- Estimate boat-proximity-minutes (how long from main channel to dock at no-wake).
- Photograph the dock (one shot from water, one from land approach).

**For marinas:**
- Talk to staff. Ask slip count, max length, daily/monthly/seasonal rental, fuel types, marine services, pumpout availability.
- Photograph fuel dock + slip area.

**For ramps (Place entities):**
- Count concrete ramps. Estimate max boat length per ramp.
- Count trailer parking spaces. Estimate fills-by-time on busy weekends.
- Note lighting + fee + restrooms.

The manual-recovery checklist (`docs/maintainability/manual_recovery_checklist.md`) gets new entry types for boat-accessible venues, with these questions as the operator prompts. The admin form for Provider/Place gets a "Boat access" sub-section that appears when the entity is flagged as boat-relevant.

---

## §9 Open questions for Casey

1. **Mode-toggle visibility for non-boaters.** Most users in Havasu are NOT on a boat. Showing a "Boat mode" toggle on every header may confuse the majority. Options: (a) header toggle always visible (current spec); (b) toggle only in homepage hero region (less obtrusive); (c) only show after user has visited at least one boat-accessible profile. **Recommendation: (a) for V1 — discoverability matters more than reducing toggle noise.** Reconsider if usage data shows non-boaters find it confusing.

2. **Default mode for first-time visitors.** Default is "default" mode (not boat). But during major boating events (Desert Storm, IJSBA, summer holidays) the boater fraction of traffic may spike. Should the homepage hero detect "is this a high-boat-traffic period" and bias toward suggesting boat mode? Probably V1.5 — adds complexity.

3. **Water-route directions accuracy.** "Get water route" links to Google Maps with venue lat/lng. Google Maps does not route by water. The link is a fallback; ideal would be a real water-navigation app integration. V2 candidate; for V1 just link out and label honestly ("opens in Google Maps").

4. **Boat-mode chat handling for distance queries.** "What's the closest fuel dock?" — closest by water or closest by road? Recommendation: water-distance when mode is active AND lat/lng is in the query OR the chat has location context. Default to road-distance otherwise.

5. **`boat_access` schema validation.** Pydantic models per venue type adds operator-form complexity. Alternative: looser JSON validation in V1, tighten in V1.5 if data quality suffers. Recommendation: loose V1 (operator self-disciplines via the admin form's helper text), tighten when patterns emerge.

6. **Mode + sponsor slot interaction.** When boat mode is active, should sponsor slot rotation prefer boat-accessible sponsors? Implementation: filter sponsor candidates by `entity.boat_access IS NOT NULL` when mode is active; fall back to all sponsors if no boat-accessible sponsor exists in the category. Recommendation: yes; aligns sponsor visibility with user context.

---

## §10 Effort estimate

By sub-lane:

- **Schema migration** (boat_access JSON field on Provider + Place; User.preferred_mode enum if implementing account-side persistence): S (hours).
- **Mode toggle UI + URL state + localStorage + account-level persistence**: M (1-2 days).
- **Map water-overlay + boat-icon markers + water-centered defaults**: M (1-2 days).
- **Profile-page boat-mode region** (new top-of-fold region; conditional rendering): M (1-2 days).
- **Chat tier 2 + tier 3 mode-context wiring + LLM preamble**: M (1-2 days).
- **Admin form for boat_access JSON entry**: S-M (1 day; per-venue-type form variations).
- **Tests** (mode persistence, profile rendering, chat interpretation, map): M (1-2 days).

**Total: 6-9 engineering days, dispatchable as 2-3 Cursor or CC lanes.**

The data-gathering operator workload is separate and ongoing (counted in the manual-recovery operator-hours, not engineering days).

---

## §11 Sequencing

**Lands after:**
- Place model migration (boat-access data is on both Provider AND Place; needs Place to exist).
- Map view implementation (Leaflet+OSM base; boat mode adds an overlay).
- Account-lite (user-preference persistence requires User schema).
- Chat directory-data migration (tier 2 needs to query the new schema).

**Lands alongside:**
- Other operator-curated field additions (heat_exposure, crowd_notes, mobile_service flag) — these can be one combined "v1.1 operator-curated fields" migration. Boat-access just slots in.

**Lands before:**
- Initial data-gathering field-trips for boat-accessible categories (Eat & Drink, On the Water, Outdoors & Parks waterfront subset). Operator needs the admin form ready to enter boat-access data while on the dock.
- Launch.

---

## §12 What we explicitly DON'T build in V1

- Nautical charts or marine-specific map tiles (just OSM water overlay).
- Live boat traffic / AIS integration.
- Marine weather radar overlay.
- Tide tables (Lake Havasu has minimal tide influence; not applicable).
- Slip availability real-time (marinas don't expose this; defer).
- Boat-rental booking flow (defer to Phase 3 booking workflows).
- User-submitted dock photos (V1.5 once moderation queue is in place).
- Water-distance routing (just link out to Google Maps with lat/lng).
- Multi-language for boat-mode (no different from rest of product).
- Sponsor-package category specifically for marinas / on-water services (uses existing sponsor model).

---

## §13 Summary

Boat-access mode reorients the directory for users in boat-first decision context. Same data, different ranking + presentation + chat interpretation. Schema is one flexible JSON field + a User preference column. UI work is incremental on top of the standard Provider/Place pages + map view. Total engineering effort 6-9 days; operator data-collection effort folds into the existing field-trip workflow with new boat-relevant questions. The texture moat: behaves like a boater-aware local rather than a generic search engine, and the data is structurally inaccessible to Google/Yelp because it requires direct dock observation.

Open questions are mostly UX-discovery calls (toggle visibility, default mode) — none are architecturally blocking.

Lands in the post-foundation phase alongside other operator-curated v1.1 fields (heat_exposure, crowd_notes, seasonal_hours, mobile_service flag). One combined "v1.1 operator-curated fields" migration captures them all.
