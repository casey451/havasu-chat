# Strategic Pivot — 2026-05-12

**Audience:** the next agent, the next-next agent, and Casey six weeks from now when this is no longer fresh. This doc captures a strategic call that materially changes what havasu-chat is becoming. Read this before reading `PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md`, or `BACKLOG.md` — those docs still describe the pre-pivot product and have not yet been rewritten.

**Read time:** ~5 minutes.

**Trigger artifact:** `uploads/deep-research-report.md` (ChatGPT-authored strategic plan based on a long conversation Casey had about product direction).

**Companion docs:**

- `docs/SESSION_HANDOFF_2026-05-12.md` — the session this pivot was decided in
- `uploads/deep-research-report.md` — the strategic plan that triggered the pivot
- `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md` — pre-pivot architectural docs; still accurate as code-level reference; need narrative rework

---

## §1 — The call

havasu-chat is pivoting from **chat-first concierge** to **structured local directory with chat as one of three front doors** (browse + search + ask, three interfaces on one underlying graph).

Four strategic answers locked this session:

| Question | Answer |
|---|---|
| Does the deep-research report capture the actual target vision? | **Yes** — the directory-first "three front doors" framing is the real endpoint. The current chat-first codebase is a starting point, not the endpoint. |
| Funding model for the next 12 months? | **Bootstrapped / revenue-funded.** Cannot absorb $80k-$190k 12-month build cost on faith. Time-to-first-dollar matters more than the 12-month ceiling. |
| Who's doing local sales? | **Casey, primarily.** Founder-led sales rate-limits the ramp. Sponsor packages must be cold-sellable; defer infrastructure-heavy packages (Deals, Lead-gen) to Phase 2. |
| Immediate next move? | **Pivot now.** Pause the existing 50-business enrichment sprint as-scoped; redirect operator effort to feeding the new directory shape; start building category landing pages in parallel. |

V1 directory category: **Home Services** (plumbers, HVAC, pool, electrical, landscapers). Rationale: older homeowner demographic (35.2% age 65+, 73.2% owner-occupied per US Census), urgent intent, highest revenue-per-merchant ceiling for early sponsors, partly already in the enrichment pipeline.

---

## §2 — What this changes vs the pre-pivot trajectory

| Dimension | Pre-pivot trajectory | Post-pivot trajectory |
|---|---|---|
| **Front door** | Chat composer (`/api/chat`) | Browse + search + chat as three equal interfaces |
| **Inventory shape** | Events + Programs + Providers (River Scene seed) | Above + Places (parks/ramps/beaches) + Deals + real-time utility data |
| **User identity** | None (Terms explicitly say no accounts) | Account-lite (magic-link email + favorites + alerts) |
| **Map UI** | None | List/map toggle on category pages |
| **Monetization** | Sponsor placements via disclosure renderer in chat (Phase 2.5) | 6-stream stack (category sponsors / intent / deals / leads / premium / seasonal) |
| **Revenue ceiling** | Implicit; probably $50–150k/yr ceiling for chat-only inventory | $508k modeled (report); $150–250k conservative Year 1 expectation |
| **Time-to-first-dollar** | Weeks after enrichment completes + flag flip | 4–8 weeks for first Verified Presence sponsors; 8–12 weeks for Category Visibility |

This is a genuine pivot, not a scope expansion. The headline product changes. Some existing work translates cleanly to the new shape; some becomes lower priority; some stays load-bearing under either vision.

---

## §3 — What translates from existing work (don't trash it)

The chat-side engineering investment is **reframed as backend trust infrastructure**, not deprecated. Specifically:

- **`disclosure_renderer` + `placement_regime`** → reused for sponsor labeling on category page cards. The "Sponsored" word constant + regime selection logic + tone allowlist work directly on category card sponsor slots.
- **`confidence_tier` classifier + operator vocab** → becomes the data-quality score that ranks merchants within category pages. Existing tier-weighting work applies as-is.
- **`confabulation_eval` harness (HALT 3)** → still validates the chat front door (now scoped to "Ask Hava" handoff from category pages, narrower surface). Eventual close-out still gates chat-surface monetization; not gating directory-surface monetization.
- **`verification_method` + Lane 3 operator vocab CHECK migration** → directly feeds "verified" / "claimed" / "source: merchant" stamps on category cards. The report's "every record carries source_type, source_url, last_verified_at" rule is already partly implemented.
- **Entity matcher (Tier 1/Tier 2/Tier 3 routing)** → still runs the chat front door; now scoped to one of three doors instead of the only door.
- **Smoke catalog infrastructure** → reused for category-page validation gates.
- **`chat_logs` + disclosure telemetry columns** → reused for chat-handoff attribution from category pages.

**Net:** the trust backbone is mostly built. What's missing is everything *above* the backbone — the directory UI, structured profile pages, account system, category taxonomy, sponsor packaging UI.

---

## §4 — Newly required (Phase 1 of the new vision)

Sequenced for time-to-revenue, not feature completeness. Each block has a target time-to-ship and the sponsor package it unlocks.

| Block | Target | Sponsor package it unlocks |
|---|---|---|
| Canonical category taxonomy (12 categories, locked) | Days 1–7 | Foundation for all category-page packages |
| Schema additions: `Category` model, `category_id` FK on Provider/Program, `Place` model, `attributes` JSON on Provider | Days 1–14 | Foundation |
| Structured Provider profile pages with sponsor labeling | Days 7–28 | **Verified Presence ($79/mo)** |
| Account-lite v0.1 (magic-link email + favorites + alerts) | Days 14–35 | Foundation for retention loops |
| Home Services category landing page (list + filters + sort) | Days 14–35 | **Verified Presence** sales start during this window |
| Sponsor claim/edit UI + basic analytics | Days 21–42 | **Verified Presence** + foundation for Category Visibility |
| Eat & Drink category landing page | Days 42–60 | Second category live; broader sponsor inventory |
| List/map toggle (Mapbox or Leaflet v1) | Days 42–60 | Category Visibility readiness |
| Labeled sponsor slot in category pages + reporting | Days 49–70 | **Category Visibility ($349/mo)** |
| Weather widget on homepage (free NWS API) | Days 56–70 | Retention hook for daily-user habit |

**Deferred to Phase 2** (after first revenue is in): Deals/QR wallet system, Lead-gen attribution (Twilio + reporting), Merchant self-serve full console, Real-time gas/ramp data integration, Place entity ingestion at scale.

**Deferred to Phase 3:** Itinerary builder, membership layer, booking workflows, syndication API.

---

## §5 — 90-day shape

### Days 0–14 — Strategic foundation

- This doc lands ✓
- Lock canonical category taxonomy (12 categories or refined cut — open decision §8)
- Schema additions land in `app/db/models.py` + Alembic migration
- Re-scope enrichment sprint: same operator workflow, new structured-field requirements + new taxonomy mapping. Old enrichment data is not wasted; gets remapped.
- Update `PROJECT.md` + `HAVA_CONCIERGE_HANDOFF.md` with pivot notices + plan substantive rewrites for Phase 2
- Backlog re-prioritization (see §6)

### Days 15–45 — Home Services category end-to-end as proof

- `/category/home-services` landing page: list, filters (sub-category, service area, hours, sub-trade), sort
- Structured Provider profile pages (`/provider/<slug>`) with sponsor labeling, source stamps, verification date, action buttons (call, directions, website, ask)
- Account-lite v0.1: magic-link email, favorites, alert opt-in. No password, no OAuth, no GDPR-extras yet.
- Sponsor claim flow + edit UI (claim → confirm via business phone → edit own profile)
- Basic per-merchant analytics dashboard (impressions, profile views, click-to-call/directions/website)
- Sell **Verified Presence ($79/mo)** during this window. Target: 5–10 paying merchants by Day 45.

### Days 46–90 — Second category + Category Visibility package live

- `/category/eat-and-drink` landing page
- List/map toggle on both category pages
- Labeled sponsor slot inside category page card stack + sponsor reporting
- Weather widget on homepage
- Sell **Category Visibility ($349/mo)** as Eat & Drink launches. Target: 5–10 sponsors by Day 90.

**90-day MRR run-rate target:** $30–55k MRR. ($5–10k MRR per the report's "Public useful launch" Phase 2; tightened because we're starting from existing infrastructure not from scratch.)

---

## §6 — Backlog re-prioritization (three buckets)

Not editing `BACKLOG.md` ticket statuses — preserving historical record. This section is the priority signal for the next agent. When in doubt, this doc supersedes BACKLOG priority.

### Load-bearing under either vision (KEEP)

- **#65 — Phase 2.5 third-party-source rate-limiter (design shipped; impl OPEN).** *Now more urgent, not less.* The directory will hit Places API for map + geocoding + business address validation more than the chat front door ever did. Implement as soon as §8 Casey-decisions land.
- **#18 — Repo hygiene & documentation hierarchy (PM phases A–D).** Ongoing; relevant under either vision.
- **Enrichment toolchain (operator-driven, no ticket).** Pause sprint-as-scoped; redirect operator effort to feed directory shape (richer structured fields, new taxonomy mapping). Toolchain code is fine.

### Promoted — new top-of-queue work

- **Canonical category taxonomy lock** (open decision §8) — gates everything else
- **Schema additions** (`Category`, `Place`, `attributes` JSON on Provider) — gates category pages
- **Provider profile page (`/provider/<slug>`)** — gates Verified Presence sponsor sales
- **Home Services category page (`/category/home-services`)** — V1 directory proof
- **Account-lite v0.1** — gates retention loops
- **Sponsor claim flow + edit UI** — gates Verified Presence sales
- **Per-merchant analytics dashboard** — gates Verified Presence value prop

### Deprioritized — chat-only concerns (don't close; just lower-band)

- **HALT 3 close-out (#53).** Still gates chat-surface monetization, but chat is no longer the headline product. The bands can be set after directory monetization is in motion. *Reasonable to defer 4–8 weeks past current expectation.*
- **#62 — trade-superlative alias-resolution vs disambiguation (P3).** Chat-side concern. Still relevant for chat front door but lower-leverage now.
- **Smoke catalog ambiguity resolution (no ticket; 6 open spec Qs in `post_enrichment_smoke_catalog.md`).** Chat-side validation. Resolve when HALT 3 close-out activates.
- **Phase 2.5 Premier inventory open (P2.PREM.1).** Original framing was a chat-surface placement concept. Under the pivot, "Premier" is reborn as a category-page sponsor slot — needs re-scoping. Treat the original P2.PREM.1 as effectively deprecated; the new equivalent is **Category Visibility package** in §4.
- **#39 — audience signal into placement-regime selection (DEFERRED).** Still deferred; gated on 4–6 weeks of `chat_logs.audience_signal` data which now matters less.

### Forward-looking (no action change)

- **Backlog #2** — `_time_bucket_first_hits` and broad `span`. Phase 2 candidate; unchanged.

---

## §7 — Sponsor packaging strategy

Drawn from report §Monetization design + filtered through "Casey-sells-it cold to a Havasu merchant tomorrow."

### Phase 1 packages (build now, sell during Days 15–90)

| Package | Price | Build effort | Cold-sell difficulty | Target count by Day 90 |
|---|---|---|---|---|
| **Verified Presence** | $79/mo | Low (claim + edit + basic analytics) | Easy (every merchant wants this) | 5–10 |
| **Category Visibility** | $349/mo | Medium (sponsor slot UI + reporting) | Moderate (needs category page to demo) | 5–10 |
| **Seasonal Takeover** | $1,500–$5,000 | Low (homepage takeover module) | Hard cold; easy with one anchor reference | 1–2 |

### Phase 2 packages (build after first revenue lands)

| Package | Build effort | Why deferred |
|---|---|---|
| **Deals Engine ($249/mo)** | High (QR wallet + merchant verification app + redemption ledger) | 6–10 weeks of build before first sale. Defer until Phase 1 revenue covers build cost. |
| **Intent Capture ($499/mo)** | High (Twilio + lead attribution + reporting) | Per-merchant infrastructure cost; needs scale to be efficient. |

### Sales sequence (founder-led; assume Casey cold-calls/walks 5–10 merchants/week)

1. Pitch **Verified Presence** ($79/mo) to enrichment-sprint merchants you've already touched. Lowest friction.
2. As Home Services category page goes live, pitch **Category Visibility** ($349/mo) to top-tier sub-trade merchants in that category.
3. Identify anchor merchant for a **Seasonal Takeover** (Desert Storm period, IJSBA World Finals, spring break, summer boating). One sponsor at this tier = $1,500–$5,000 + halo for the package.
4. As Eat & Drink launches, pitch Category Visibility to top-frequency dining merchants.

---

## §8 — Open decisions for next session

Casey-owned architectural calls. Block the next 2–3 days of work until resolved.

**Status (2026-05-13):** Decisions 1–4 locked this session. Decisions 5–7 still open.

- §8.1 Taxonomy → **LOCKED: 12 as-proposed** (Eat & Drink, Events, Family, Home Services, Health, On the Water, Outdoors & Parks, Shopping, Auto & Gas, Lodging, Pets, Community)
- §8.2 Place model scope → **LOCKED: defer to Phase 2.** Home Services + Eat & Drink ship business-only first; districts handled via string field on Provider rather than first-class Place rows. Place model returns when parks/ramps/beaches inventory becomes a sponsor priority.
- §8.3 Account-lite auth provider → **LOCKED: Resend** (cheapest at bootstrapped scale; modern dev UX)
- §8.4 Map provider → **LOCKED: Leaflet + OSM tiles** (zero cost; adequate polish for V1 directory map)
- §8.5 Pricing finalization → still open (ground-truth via cold-pitch first)
- §8.6 Sponsor package SKU naming → still open
- §8.7 `PROJECT.md` / `HAVA_CONCIERGE_HANDOFF.md` rewrites → pivot-notice banners land this session; substantive rewrites deferred past Day 90

1. **Canonical category taxonomy — lock the 12 (or different cut).** Report suggests: Eat & Drink, Events, Family, Home Services, Health, On the Water, Outdoors & Parks, Shopping, Auto & Gas, Lodging, Pets, Community. Worth reviewing against actual Havasu market shape — maybe consolidate (e.g. Outdoors & Parks ⊃ On the Water?) or split (e.g. Eat & Drink → Restaurants / Bars / Coffee). Lock by Day 7.
2. **`Place` model scope for V1.** Full non-business entity model (parks, ramps, beaches, districts, dog parks) or defer Place entirely to Phase 2 and ship Home Services + Eat & Drink as business-only first? Home Services doesn't need Place; Eat & Drink could use it for districts (English Village, Downtown).
3. **Account-lite auth provider.** Magic-link via SendGrid? Resend? Postmark? Cost matters at bootstrapped scale.
4. **Map provider.** Mapbox ($$$ at scale, beautiful), Leaflet + OSM tiles (free, less polished), Google Maps ($$ + API key headaches). Recommend Leaflet + OSM for V1 cost.
5. **Pricing finalization.** Report's prices ($79 / $349 / etc) are anchored to local market benchmarks but should be ground-truthed against a few cold-pitch conversations before locking. May ship with introductory pricing first.
6. **Sponsor package SKU naming.** "Verified Presence" / "Category Visibility" / "Seasonal Takeover" are the report's names. Worth Casey-tone-checking.
7. **`PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md` rewrites.** Multi-week task. For now, add prominent pivot notices at the top of each pointing to this doc. Full rewrite later (probably after Day 90).

---

## §9 — Honest risk callout

The report's $508k modeled revenue assumes ~100 paying merchants in a city of 59,037. That's ~0.17% of population or roughly 1 in every 6–8 commercial businesses (Lake Havasu has an estimated 600–800 active commercial entities per chamber data; worth verifying). **Achievable but tight for solo founder-led sales over 12 months.**

A more conservative bootstrapped target:
- **Year 1:** $150–250k revenue, 40–60 paying merchants
- **Year 2:** $300–400k revenue with Deals + Lead-gen packages live
- **Year 3:** $500k+ if execution holds and packaging matures

This is a *forecast*, not a ceiling. The ceiling is the report's $508k. The forecast is what Casey should plan against for runway.

**Single biggest risk:** founder-led sales burnout. Casey can sustain cold-outreach to ~5–10 merchants/week, plus product/ops, for some bounded window. If month 6 hits and Casey hasn't hired a Havasu-based BDR or built a chamber/Havasu News channel partnership, the ramp stalls regardless of how good the product is. **Sales channel diversification by Day 90 is as important as product features by Day 90.**

**Second biggest risk:** Lake Havasu user adoption. The report assumes users want a structured directory. They might just keep using Google/Yelp. Mitigation: the V1 Home Services category page needs to be *measurably* better than Google for "plumber Lake Havasu" — faster, more local, more trustworthy. If it's not, the directory bet is wrong and we should retreat to chat-first.

**Third biggest risk:** the existing chat infrastructure becomes a maintenance liability instead of leverage. If the team focuses entirely on directory build and the chat surface decays (HALT 3 close-out slips indefinitely, smoke catalog spec questions never resolve), chat becomes a partially-rotting product surface attached to a healthier directory. Mitigation: keep chat *working*, not *evolving*. Bug fixes only on chat surface until directory has revenue.

---

## §10 — Reference docs

- **The triggering report:** `uploads/deep-research-report.md`
- **Pre-pivot architecture (still accurate for code-level reference):** `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md`
- **Session this pivot was decided in:** `docs/SESSION_HANDOFF_2026-05-12.md`
- **Backlog (ticket priorities are now overridden by §6 of this doc):** `docs/BACKLOG.md`
- **Current state (pre-pivot; substantive infrastructure unchanged):** `docs/STATE.md`
- **Dispatch protocol + channels (unchanged; methodology applies under either vision):** `docs/maintainability/dispatch_protocol.md`, `docs/maintainability/dispatch_channels.md`
- **Eventually-irrelevant chat-tooling docs (won't be cited again until HALT 3 close-out is revisited):** `docs/maintainability/halt3_closeout.md`, `docs/maintainability/halt3_definition.md`, `docs/maintainability/post_enrichment_smoke_catalog.md`, `docs/confabulation-eval-runbook.md`

---

*This doc is the authoritative strategic-priority signal as of 2026-05-12. When BACKLOG.md priority disagrees with this doc, this doc wins until superseded by a later strategy doc. Next agent: read this first; treat `PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md` as code-level reference rather than product-strategy reference until they are rewritten.*
