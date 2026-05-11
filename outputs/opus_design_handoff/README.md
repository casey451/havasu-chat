# Opus 4.7 UI Design Handoff — Synthesis

> **Origin:** Opus 4.7 response 2026-05-14 to `outputs/opus_47_prompt_ui_and_revenue_optimization.md`. Delivered as a zip package of 6 files: `hava_design_handoff.docx` (the load-bearing design doc, ~150 paragraphs) + 5 HTML mockups showing iterative design evolution. All files saved alongside this README.
>
> **Notable scope decision Opus made:** Question A (UI/UX) is answered extensively with mockups + design principles. Question B (revenue optimization) is **explicitly deferred** per build-first sell-after sequencing. Section §11 of the handoff doc names monetization models intentionally dropped (pay-per-call lead-gen, end-user paid tier, featured-listings auction, banner ad networks) but doesn't propose the revenue mechanisms that fit. **If revenue analysis is needed, that's a separate Opus round** with a tighter scope.

---

## §1 The 5 HTML mockups (evolution order)

Open each in any browser to view. Static HTML; no build step.

1. **`hava_mockup.html`** — foundational mobile pass. Three core mobile screens (homepage, category landing for Restaurants, Provider profile for Mudshark Brewery). Establishes the visual primitives that carry through.
2. **`hava_schedules_mockup.html`** — **SUPERSEDED approach**. Treated events as a separate destination ("Today agenda" timeline + class-series profile page + schedule region on gym profiles). Opus tried this then abandoned it in favor of integration. Useful for thinking through the schedule data model but not the target UX.
3. **`hava_integrated_mockup.html`** — **primary mobile reference**. Events woven into the unified card system. Three screens: homepage with slim "Happening soon" strip, fitness category landing with interleaved place + event cards, gym profile with a "What's on at this gym" region inserted between service details and hours+location.
4. **`hava_browse_mockup.html`** — **primary browse reference**. Adds the missing structural browse hierarchy. Two screens: revised homepage with 8 themed group tiles + "Browse all 47 categories A-Z" link, and a themed group landing page (On the Water) with sub-category chips at top + unified stream.
5. **`hava_desktop_mockup.html`** — **primary desktop reference**. All three core surfaces in desktop form (homepage with real top nav + conditions bar + hero with centered Ask Hava box + 4-column grids + real footer; category landing with filter sidebar + 2-col results grid + persistent map column; profile with two-column body + sticky action card with call/directions/Ask Hava + hours + mini-map).

---

## §2 The four load-bearing patterns

Everything else in Opus's design serves these four. Memorize them.

### §2.1 Unified Hava card grammar — THE LYNCHPIN

One card component renders everywhere a business or event appears outside its own profile: category pages, search results, group landing, chat responses, embedded references. The card carries: name, freshness dot (green/amber/red), status line, district/distance, operational pills, ranking explainer line, three action buttons.

**Place vs event differentiation is subtle and content-driven, not chrome-driven:**

- **Place status:** "Open until 10pm" in green text with green pre-dot
- **Event status:** "Tonight at 6:00pm" or "Starts in 18 min" in lake-blue text with lake-blue pre-dot
- **Same shell, same dimensions, same action row, same freshness dot**

This is the single most important pattern. It collapses what would otherwise be three separate templates (provider card / place card / event card) into one. Future implementation lanes propose changes to it only with explicit operator approval.

### §2.2 Three front doors, one directory

Browse + Search + Ask Hava are co-equal entry points returning content in the unified card grammar. None is privileged. A user might enter through Ask Hava ("yoga tonight?") then navigate to a venue profile, OR browse to Restaurants → English Village → Open Now then ask Hava a follow-up about one. The three doors must feel like one product.

### §2.3 Honest freshness as a first-class signal

Three levels, displayed as a colored dot on cards AND as a colored band at the top of profiles:

| Color | Age | Profile copy |
|---|---|---|
| Green | <60 days | "Verified by owner 3 weeks ago." |
| Amber | 60–180 days | "Last verified 4 months ago — info may have changed." |
| Red | >180 days | "Not recently verified — call ahead to confirm hours and details." |

**Schedules use a tighter decay curve:** green <7 days, amber 7–21 days, red >21 days. A venue and its schedule have INDEPENDENT freshness — both display on the same profile (venue's band + schedule region's "Updated 2 days ago").

### §2.4 District context — the hyperlocal moat

Each named district in Havasu gets **one operator-written paragraph** stored in a districts table. The paragraph renders on every business profile in that district. This is **uncopyable by national platforms** because the snowbird/seasonal/local-traffic patterns only exist in a few US cities.

Sample paragraphs Opus wrote:

> "English Village fills up after 5pm Fri–Sun — parking lots near the bridge get tight by 6. Walkable to the lighthouse loop and three bars next door. Snowbird-heavy crowd Nov–March."

> "The main strip running south from the bridge — busy after work and on weekends. Parking is easier than English Village. Heavy snowbird crowd Nov–March; tourist crowd thins after spring break."

One paragraph → context on dozens of business profiles. High-leverage operator authoring effort.

---

## §3 The 4-level browse hierarchy

**Homepage → Themed group → Sub-category → Profile.**

- **Homepage** — orientation (conditions + Ask Hava + Happening soon), contextual recommendations (Today tiles), and structural browse (themed group tiles).
- **Themed group landing** — editorial scope-setter (e.g. "On the Water" with its own copy), sub-category chips at top, unified stream of relevant venues + events for the whole group.
- **Sub-category landing** — the existing locked category page pattern: 3-row chip system (cuisine/sub-trade · district · operational+time), sort dropdown, sponsor slot, organic stream.
- **Profile** — the 11-region deep view (now 12 with What's-on region for venues that host events).

**Power-user shortcut:** "Browse all 47 categories A–Z" link bypasses the group layer.

**Ask Hava shortcut:** chat queries can return results from any level, skipping the hierarchy entirely.

### Suggested 8 themed groups (with ~4-6 sub-categories each)

1. **Eat & Drink** — Restaurants · Bars · Coffee · Bakeries · Breweries · Markets
2. **Stay** — Hotels · Vacation Rentals · RV Parks · Campgrounds
3. **On the Water** — Boat Rentals · Watersports · Charters · Marinas · Launches
4. **Outdoors** — Hiking · Trails · Parks · Beaches · Off-road · Disc Golf
5. **Things to Do** — Live Music · Museums · Classes · Events · Kids · Tours
6. **Health & Fitness** — Doctors · Dentists · Urgent Care · Gyms · Yoga · Spa
7. **Home & Auto** — HVAC · Plumbing · Electrical · Pool · Auto · Boat Repair
8. **Shopping** — Grocery · Hardware · Boutiques · Marine Supply · Antiques

Real Estate / Pro Services (legal, insurance, accounting) aren't in this 8-cut. They could be a 9th group, folded into Home & Auto, or absorbed elsewhere. **Operator call during master plan.** This recommendation aligns with ChatGPT's locked 12 categories — the 8 themed groups are a UI/UX layer ABOVE the 12 categories (groups bundle related categories for browsing).

---

## §4 Events as a third entity type (data model implications)

Events, classes, recurring sessions, and time-windowed offerings (happy hour, taco Tuesday, lap swim hours) are first-class entities alongside Provider and Place. They live INSIDE existing surfaces — no separate "events finder."

Rough data model shape Opus proposed:

- Events table with `event_type` discriminator: `one_off`, `recurring_class`, `lesson_series`, `amenity_session`, `time_window`
- Fields: `name`, `venue_id` (FK to Provider/Place — i.e. ENTITY under the locked ENTITY schema), `start_time`, `end_time`, `recurrence_rule` (RRULE format), `capacity`, `booking_url`, `price_text`, `host_url`, `scraped_from`, `last_verified`, `category`, `sub_category`
- **Freshness anchor for scraped events is the scrape timestamp, NOT the event date**
- **Capacity/availability is OPTIONAL** — only display "3 spots open" / "Full" when the venue actually publishes real availability. Otherwise omit. **Do not manufacture scarcity.**

This reconciles with the locked ENTITY schema: Event becomes an ENTITY row with `entity_type="event"` + extension table for event-specific fields (recurrence_rule, capacity, etc.).

---

## §5 Open design questions (Opus's §12)

Opus surfaced 8 questions intentionally unanswered:

1. **Themed group cuts** — are 8 right? Real Estate / Pro Services as 9th group, folded into Home & Auto, or absorbed elsewhere? Should overlapping categories appear in multiple groups (boat tours in both On the Water AND Things to Do)?
2. **Place vs event visual differentiation** — currently status-line color + content; fallback if too subtle is a small "Class" or "Event" word tag (NOT colored background or badge)
3. **Persistent map vs toggle on desktop category pages** — Opus recommends default-on with collapse option
4. **Hero treatment on desktop homepage** — keep marketing-y tagline ("Lake Havasu City, end to end · Ask anything, browse anything") or drop and lead with just Ask Hava box
5. **Browse menu flyout structure** — desktop top nav has "Browse ▾"; flyout not shown in mockup
6. **Ask Hava as search vs parallel surfaces** — desktop has both Search input AND Ask Hava button; alternative is collapse into one input that detects search-like vs question-like queries and routes accordingly
7. **Capacity display on schedule entries** — only honest if venue publishes real data; if not, OMIT (don't fake or estimate)
8. **Mobile-vs-desktop interaction differences** — bottom-sheet map on mobile becomes persistent right rail on desktop; sticky status bar on mobile becomes sticky action card on desktop. These are intentional — small screen demands compression, large screen affords visible state.

---

## §6 Texture rules confirmed (Opus's §3)

Opus restated the texture rules and called them "firm ground." Re-quoted here so they don't drift:

- Calm, not loud. No popups. No engagement tricks. No clickbait headers. Loading states say "Loading…"
- Honest about uncertainty. Show staleness explicitly.
- Hyperlocal context visible throughout.
- Mobile-first responsive.
- Sponsor labeling loud-and-clear, not stealth.
- No persuasion design tricks (no FOMO, no scarcity manufacturing, no countdowns).
- Trust signals always visible.
- No engagement loops (no streaks/badges/leaderboards/"you've used 3 of 5 free actions" pressure).
- No native user reviews — already deferred; do not propose adding them.

---

## §7 Implications for the master build plan

This handoff enriches the UI layer of the master plan significantly. Specific integration points:

1. **Unified Hava card grammar** becomes Phase 2 work — single shared component renders across category pages, profile pages, search results, group landing, chat responses. Replaces what would have been separate Provider card / Place card / Event card templates. Land this BEFORE other UI work.

2. **Themed group hierarchy (8 groups)** becomes a UI layer ABOVE the locked 12 categories. Implementation: a new `themed_group` data layer (could be a small `themed_groups` table OR an in-code mapping from group_slug → list of category_slugs). New homepage region (the "Browse Havasu" tile grid) + new themed group landing page template. Casey defers question of whether 8 is right + Real Estate placement until master plan.

3. **District context table** is a new data model addition. A `districts` table with district_slug + operator_written_paragraph + display_metadata. Renders on every business profile in that district. **Operator authoring effort:** one paragraph per district (~8-12 districts in Havasu = manageable). Goes in the v1.1 schema pass.

4. **Events as third ENTITY type** — already locked under ENTITY schema. Opus's design fleshes out the event-specific extension table fields + RRULE-based recurrence + scrape-timestamp freshness anchor + optional-capacity rule.

5. **Honest freshness band** as colored dot on cards + colored band on profile — slots into the Provider profile design already shipped. Adds the cards-side rendering across all surfaces using the unified card. Schedule-specific tighter decay curve (green <7 / amber 7-21 / red >21) is new.

6. **Same templates, responsive grids** — Jinja partials with CSS breakpoints, not two separate sites. Mobile-first build order; desktop layers on top.

7. **Build sequencing Opus recommended** aligns with build-first: read pass → propose smallest integration point (freshness band or unified Hava card) → land that → proceed. Event entity model before event rendering. Mobile-first, desktop-as-breakpoints. Skip browse hierarchy until late. Don't build monetization surfaces yet.

---

## §8 Revenue optimization — NOT addressed

Opus explicitly deferred this per build-first / sell-after sequencing. The handoff doc's §11 lists models intentionally dropped (pay-per-call, end-user paid tier, featured-listings auction, banner ad networks) but doesn't propose the mechanisms that fit. Casey can decide:

- **Accept the deferral** — monetization decisions wait until the product is built and there's real data to ground-truth pricing. ChatGPT's taxonomy research already proposed intent-cluster pricing + season+district+intent bundling for sponsor packages (see `chatgpt_taxonomy_research_synthesis.md` §4). Combined with the current default plan (Verified Presence $79 / Category Visibility $349 / Seasonal Takeover $1,500-$5,000), that's enough monetization framing to carry through the build phase.
- **Dispatch a separate Opus round on revenue alone** with a tighter scope and a different prompt frame. The current prompt's two-question structure may have been too broad; a revenue-only prompt would force focus.

Recommend accept the deferral. Build the product; revenue optimization at build-complete via cold-pitch testing.

---

## §9 What this means right now

The architectural foundation is essentially complete. With this handoff plus the ChatGPT taxonomy synthesis, the master build plan now has every input it needs:

- 12 categories (Tier 1/2/3 sequencing locked)
- ENTITY schema (locked)
- 8 themed groups (provisional; finalize in master plan)
- Unified Hava card grammar (Opus design)
- 4-level browse hierarchy (Opus design)
- District context paragraph data layer (Opus design)
- Events as third ENTITY (locked)
- Honest freshness band (Opus design)
- Boat-access mode (Opus #4 locked earlier)
- "Today in Havasu" conditions panel + alerts (Opus #1 + #8 locked earlier)
- 7 other Opus feature suggestions (locked earlier: heat-aware ranking, seasonal hours, crowd context, mobile-services, Hava's pick, etc.)
- 8 design memos (audit + Place + account-lite + background-jobs + scrape + conditions + image storage + search + boat-access mode)

Master plan can be written now.
