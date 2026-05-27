# Hava — Build Brief

The mockups at `mockups/00-final.html`, `mockups/04-answer-rendering.html`, `mockups/05-home-light-touch.html`, and `mockups/07-business-answer.html` show **what** to build. This brief captures **why** — the rules, trade-offs, and decisions that aren't visible from the markup alone.

> **Mockups are direction, not pixel-rigid.** The typography, palette, editorial pacing, and component patterns are the spine. Card densities, hero heights, sponsor card layout, and component micro-decisions are open to refinement when there's a reason — especially for mobile. Pixel-fidelity is not the goal where mobile UX requires a different approach.

## What we're building

Hava is an AI local of Lake Havasu City. Production at https://havasu-chat-production.up.railway.app. Postgres on Railway. The catalog has hundreds of providers, 200+ events, 100+ programs, and every registerable activity from the city's WebTrac registration system (`register.lhcaz.gov`), refreshed every 6 hours via GitHub Actions.

The product today is a single-page chat. We're rebuilding the home page into something locals open as their default for everyday town info — the page they reach for instead of Google or a Facebook group. Chat stays at the center, but the page now also has a body the user can skim before typing.

**Catalog scope: everything in Havasu, not just events.** Hava is a directory + editorial hybrid. The catalog includes plumbers, electricians, HVAC, pool service, contractors, restaurants, retail, salons, auto shops, junk removal — every business and service in town — plus events, programs, and editorial picks. Events drive discovery and habit; businesses drive revenue (spotlight placement). A user asking "who's a good plumber" is as first-class as a user asking "what's on tonight." This shapes every section of this brief.

## Who Hava serves

Locals first. A resident checking what's on tonight, what classes are running this week, where to take a date Saturday. Visitors are welcome but they're not the primary user. The aspirational frame: "one stop shop for everything in Havasu — better than search, kinder than scrolling Facebook groups."

## Voice principles (non-negotiable)

These are the brand. Every Hava response must follow them.

Hava speaks AS THE LOCAL, not a service rep. Direct, declarative, no customer-service phrasing — never "you might want to check…", "I'd be happy to help…", "feel free to…".

Responses are 1–3 short sentences ending in a period. Question marks only when the user asked a question.

The only markdown allowed in the answer text is `[venue name](url)` — deep links to venue websites, registration pages, or Google Maps as a fallback.

When something isn't in the catalog, Hava says so plainly and points to ONE concrete external resource (the CVB site, or `/contribute`). Never a list of options.

If a query naturally returns many items (e.g. "what's happening Friday" returns 8 events), Hava's voice still stays in 1–3 sentences. The data renders as a component below the voice answer. See "Answer rendering contract" below — this is the most important architectural rule.

These voice rules apply to **Hava's chat responses**. Page-level editorial copy — the hero headline, section names, footer prose, sponsor labels — is written in editorial voice and may be a fragment, a statement, or whatever the design wants. The mockup's `What's happening in Havasu.` is a statement, not a question, and that's correct. Don't "fix" page headlines to follow chat-voice rules.

## Home page structure

Order matters. Each section earns its position. Canonical reference: `mockups/05-home-light-touch.html` (editorial-led with a directory surface).

1. **Topbar** — wordmark + dateline + Add to catalog
2. **Hero** — eyebrow ("Today in Havasu" with pulse dot), big serif headline, lede that names both surfaces ("a plumber, a date spot, what's on tonight"), search bar, chips. Chips mix editorial and directory examples ("date night", "find a plumber", "open right now", "tonight").
3. **Pros & services strip** — horizontal pill row of business categories (Plumbers, Electricians, HVAC, Pool service, Contractors, Restaurants, Cleaning, Auto, Junk removal, Salons…). Tap takes the user into chat with that category as the query. Surfaces the directory side without converting the home into Yelp.
4. **Hava's read on tonight** — single italic-serif pullquote in Hava's voice, refreshed hourly. The personality moment.
5. **Tonight row** — featured-card pattern (1 big + 2 stacked) for immediate-now content (events, classes, what's open).
6. **Sponsor slot** — single editorial banner, native-feeling, clearly labeled. See "Sponsor slot architecture."
7. **Local pros row** — 3 spotlight cards. Paid placement, clearly disclosed ("SPOTLIGHT" badge). See "Spotlight architecture."
8. **This week row** — 3 equal cards (events / programs).
9. **New on Hava row** — 3 equal cards, recently added catalog items. Mix of new businesses and new events.
10. **Footer** — quote line + meta links (Add to catalog, List your business, Sponsor a slot, About).

Two distinct monetization surfaces: the **sponsor slot** (one editorial banner) and the **Local pros row** (paid spotlights). Both go after Tonight and Hava's read so editorial momentum is established before any commerce. The sponsor slot is one section, not interleaved with editorial content; the Local pros row is its own clearly-labeled section. Removable cleanly.

## Answer rendering contract

When the user asks Hava a question, the answer has two parts.

**Hava's voice answer.** 1–2 sentences in her voice. The local's read on what was asked.

**A structured component.** Renders the data Hava was talking about. Pattern depends on query shape:

| Query shape | Component |
|---|---|
| "What's happening on Friday?" | `day_agenda` — time-grouped, tabular times, save/tap rows |
| "What's on this week?" | `week_strip` — 7-day tappable strip, agenda below for selected day |
| "Where's good for date night?" | `card_row` — 3 horizontal mini-cards with images |
| Single venue or business lookup | `single_card` (events / venues) or `single_business_card` (services) |
| "Find me a plumber" / category service search | `business_list` — list of businesses with phone/hours/spotlight disclosure |
| No-answer ("I don't know that") | `none` — plain voice + ONE pointer (CVB site or `/contribute`) |

Reference implementations live in `mockups/04-answer-rendering.html` (events) and `mockups/07-business-answer.html` (businesses, including spotlight disclosure). Build them as reusable components, not query-specific renderers — the answer payload should declare which component the front-end renders.

A loose schema for the answer payload:

```json
{
  "voice": "Friday's busy — eight things, mostly at the Aquatic Center, plus the Pro Watercross weekend kicks off at noon.",
  "component": {
    "type": "day_agenda",
    "data": {
      "date": "2026-05-08",
      "events": [
        { "title": "Lap Swim", "start": "05:00", "end": "07:45", "venue": "Lake Havasu City Aquatic Center", "category": "aquatic", "url": "..." }
      ]
    }
  }
}
```

`type` values: `day_agenda`, `week_strip`, `card_row`, `single_card`, `single_business_card`, `business_list`, or `none` (voice answer only).

The chat backend needs refactoring to support this. The LLM chooses the component type as part of its response, the backend validates and shapes the payload, the front-end renders by `component.type`.

**Loose schemas for the other component types:**

```
week_strip:
  days: [{ date, count, top: { title, time } }]      # 7 entries, dot-indicator capped at 6
  selected_date
  agenda: [<day_agenda items>]                        # same item shape

card_row:
  items: [{ title, blurb, meta, image_url, url, category }]  # 3 items typical

single_card (event / venue):
  title, image_url, description, hours, address,
  phone, website, category, registration_url

single_business_card:
  name, image_url, summary, category, status (open/closed + when),
  hours_block, phone, address, website, rating, review_count,
  recent_review { text, attribution },
  spotlight: bool                                     # if true, render disclosure

business_list:
  category               # "Plumbers", "Pet grooming"
  total_count            # for "3 of 14" footer
  items: [{
    name, thumb_url, category, rating, review_count,
    status, blurb, phone, address_short, url,
    spotlight: bool                                   # tinted row treatment
  }]
  disclosure: bool       # show "Spotlight = paid placement" footer when any item is spotlight
```

The `agenda_row` item shape is shared between `day_agenda.events` and `week_strip.agenda`. Reuse, don't fork.

## Design tokens

Use these throughout. The mockup CSS is the canonical source — copy variable names and values from there. Don't re-invent.

**Color philosophy.** Quiet, grounded base palette doing the heavy lifting; one or two saturated accents carrying personality; contrast not optional. Maps to 2026 trends: Cloud Dancer canvas + Transformative Teal + earthy terracotta + a single dopamine pop for live/urgent states. Avoid Walnut Retro (browns) — fights the lake-water character. Avoid neo-brutalism / dopamine-everywhere — fights the editorial calm.

**Surface colors:**
- `--bg: #f7f5ef` — warm paper background (Cloud Dancer with warmth)
- `--bg-2: #f1eee5` — secondary surface
- `--paper: #ffffff` — card surface
- Rules: `rgba(20,20,15,0.10)` / `0.06` / `0.04` for primary / soft / hairline

**Ink scale (AA-aware).** Body copy never goes below `--ink-2`. `--ink-3` is for meta, eyebrows, labels, and small UI text only. `--ink-4` is decorative — never used for text.
- `--ink: #14140f` — body, headings (15:1 vs paper)
- `--ink-2: #4a4a44` — secondary body, lede (8.7:1)
- `--ink-3: #6e6e67` — meta, labels, eyebrows (5.1:1, AA-safe at small sizes — darkened from #8b8b82 for compliance)
- `--ink-4: #a8a89f` — decorative only (dividers, placeholder dots)

**Tonal teal (primary accent — Havasu lake water).**
- `--accent-50: #e8f1f3` — surface tint
- `--accent-100: #c6dde2` — hover surface
- `--accent-soft: rgba(14,110,124,0.08)` — alpha tint for focus rings
- `--accent: #0e6e7c` — primary (CTAs, links, active states)
- `--accent-deep: #064551` — emphasis, hover-dark, text-on-tint

**Terracotta (editorial accent — desert clay).**
- `--warm: #b8623d` — festivals, time-of-day, pulse dot, spotlight badge
- `--warm-soft: rgba(184,98,61,0.10)` — spotlight row tint, user bubble bg

**Status colors.**
- `--open: #5a8a4f` — "Open · until 6" pill (green-sage, AA on `--open-soft`)
- `--open-soft: rgba(90,138,79,0.10)` — pill background

**Dopamine pop (sparingly).**
- `--live: #e8654a` — saturated coral. Used only for live-now / urgent states (live music tag, "happening right now" flag, important notifications). Never for general CTAs — that's `--accent`'s job.

**Cinematic gradients.**
- Hero ambient glow: very subtle radial of `--accent-soft` behind the headline
- Card image overlay: `linear-gradient(180deg, transparent 50%, rgba(20,20,15,0.18) 100%)`
- Sponsor card surface: subtle mesh of `--bg` to `--bg-2` to feel native, not overlaid
- Agenda/biz-list header: `linear-gradient(180deg, rgba(247,245,239,0.5) 0%, transparent 100%)`

**Typography:**
- Sans: Inter (400, 500, 600) — UI, body, meta
- Serif: Fraunces (300, 400, italic at variable optical sizes) — headlines, card names, Hava's voice pullquote
- Both loaded from Google Fonts

**Type scale:**
- Hero headline: `clamp(60px, 10vw, 124px)` Fraunces 300, line-height 0.94, letter-spacing -0.028em
- Section h2: 32px Fraunces 400, letter-spacing -0.018em
- Card name: 22px Fraunces 400; 36px on featured cards
- Body: 14.5–17.5px Inter 400, line-height 1.55
- Eyebrow: 11px Inter 500, uppercase, letter-spacing 0.18–0.22em

**Spacing:** Generous. Section gaps 88–96px desktop, 56–64px mobile.

**Radius:** 999px for pills, 18px for cards, 14px for chips, 12px for inner image frames.

## Sponsor slot architecture

Single editorial banner between Tonight and This week. Max-width 880px, centered, with generous whitespace.

**Sponsors are not Providers.** A sponsor is whoever paid for the editorial banner — could be a real estate agency, a hotel, a tour operator, a brand without a Provider record at all. Build the new `sponsors` table independently. Don't conflate with `Provider.tier` / `Provider.sponsored_until` / `Provider.featured_description` — those columns belong to **business spotlights** (see "Spotlight architecture" below), which is a separate monetization concept.

**Markup pattern:**
- "SPONSOR" eyebrow above (10px caps, letter-spacing 0.28em, ink-4)
- Card with image (~220×165), name, line, "Reserve →" pill CTA
- "Sponsored" tag in top-right corner of the card itself
- Tiny footer line: "Hava is supported by local sponsors. Sponsor a slot."

**Two fill paths:**

1. **Native (preferred).** Hand-sold local sponsor. Backend serves an active sponsor record; card renders with sponsor's image, name, line, CTA. Higher margin, premium look.
2. **Programmatic (fallback).** When no native sponsor is booked, fall back to AdSense (or similar). The slot is sized to host a 728×140-ish creative without breaking layout.

Build the slot as a server-rendered partial that takes a sponsor object or null. When null, recommend rendering a "Sponsor this slot →" fallback card pointing to a contact page — better than empty space, and it's marketing for the sponsor program. Don't enable programmatic ads until you have a reason to.

Rough sponsor record shape:

```
sponsors:
  id
  name             "Havasu Outdoor Co."
  eyebrow          "Local sponsor · on the water"
  line             "Kayaks, SUPs, and tubes…"
  cta_label        "Reserve"
  cta_url          "https://example.com"
  image_url        "..."
  starts_at, ends_at
  active           bool
  weight           int   -- for rotation when multiple are active
```

Removable cleanly when business spotlights are doing the editorial-banner job — the slot is one section, not interleaved with editorial content.

## Spotlight architecture (business monetization)

Separate from the sponsor slot. Spotlights are paid placement for **businesses** in the catalog — appearing in two places:

1. **Local pros row on the home page.** Three spotlight cards between the sponsor slot and This week. Eyebrow "SPOTLIGHT" with a warm dot. Each card shows a business: image, category, name, blurb, hours-now status pill, click-to-call phone, →.
2. **Inside `business_list` answers in chat.** When a user asks "find me a plumber," the spotlight provider in that category gets a tinted row at the top with a "Spotlight" tag, plus a footer disclosure: "Spotlight = paid placement. Hava's recommendations aren't pay-to-play."

**Disclosure is non-negotiable.** Trust depends on it. Both surfaces:
- Visible "SPOTLIGHT" badge or row treatment (warm tint, "Spotlight" tag)
- Footer disclosure line in `business_list` and home Local pros row
- Hava's voice answer never names a spotlight by virtue of it being a spotlight; voice picks are editorial. If the spotlight is also Hava's recommendation, fine — but that's coincidence, not promotion.

**Backed by `Provider.tier` / `Provider.sponsored_until` / `Provider.featured_description`.** These columns already exist on the Provider model and were built for this. `tier` ∈ {free, spotlight, …}; `sponsored_until` is the contract end date; `featured_description` is the spotlight blurb. Server-side query: `WHERE tier = 'spotlight' AND sponsored_until > now() AND category = $cat ORDER BY weight, random()`.

**Voice and ranking.** Hava's voice should be uncontaminated by spotlight status. The voice answer is generated from a Hava-curated short-list (or LLM-picked top-3); the `business_list` payload then surfaces the spotlight row separately, even when it's not in Hava's voice picks. Two surfaces, one set of data, clear separation.

## "Hava's pick" badges

Frosted-glass badge in the top-left of card images, with a star glyph and "HAVA'S PICK" caps. Distinct from spotlights — picks are *editorial* (Hava's recommendation), spotlights are *commercial* (paid placement). They look different and never appear on the same card.

- Hand-curated for now via a `featured: bool` column on each of `events`, `programs`, `providers`. One column per table, set true to surface
- Home page renders at most one pick per row (three total) to preserve signal
- Could later become rotational, popularity-weighted, or LLM-driven (Hava picks one per row)

**Surfacing the toggle in `/admin` is deferred.** BUILD.md's `Don't touch /admin` rule still holds. For now, flip the `featured` flag via DB script or migration. When we're ready, options are: (a) add a toggle to existing admin, (b) build a tiny separate admin surface for editorial curation only, (c) make picks fully algorithmic and drop the flag. Decide at step 8.

## Catalog data shapes (current)

Read the actual schema in `app/db/models.py` before locking in front-end types. Highlights:

- **Provider** — `provider_name`, `category`, `address`, `phone`, `email`, `website`, `facebook`, `hours`, `hours_structured` (JSON), `description`, `tier`, `sponsored_until`, `featured_description`, `lat`/`lng`, `google_place_id`, `google_primary_category`, `google_rating`, `google_review_count`, `google_review_snippets` (JSON), `google_photo_refs` (JSON), `google_hours` (JSON), `is_active`. Rich enough for `business_list` and `single_business_card` rendering — ratings, hours, photos already there.
- **Event** — `title`, `date`, `end_date`, `start_time`, `end_time`, `location_name`, `description`, `event_url`, `tags` (JSON), `provider_id` (FK), `is_recurring`, `status`.
- **Program** — `title`, `schedule_days` (JSON), `schedule_start_time`, `schedule_end_time`, `age_min`/`age_max`, `cost`, `provider_name`, `contact_*`, `tags`, `provider_id` (FK).
- **WebTrac items** — registerable activities, refreshed every 6 hours via GitHub Actions, stored in events/programs.
- **Aquatic Center weekly schedule** — also in the catalog.
- **New columns to add (step 2):** `featured: bool` on each of `events`, `programs`, `providers` for Hava's pick curation.
- **New table (step 3):** `sponsors` for the editorial sponsor slot.

## Surfaces that already exist

- `/` — current chat interface. Stays for now; the new home is built at `/home` first. After dogfooding, `/home` becomes `/` and the old chat-only `/` redirects to `/chat` (or retires).
- `/home` — **new home page**, built fresh at this path during dogfooding. Cuts over to `/` after a few days of confidence-building. As of PR D6 (2026-05-26), `/home` defaults to the Direction C dark-chrome template (`home_c.html`); the legacy `home.html` only renders when an operator sets `HOME_REDESIGN=0` (or appends `?redesign=0`) for a one-env-var rollback.
- `/chat` — **new chat surface**, where the home composer's submission lands. Renders the answer-rendering components. Session ID persisted in the URL so users can return to a conversation.
- `/admin` — review user-submitted contributions. **Don't touch.**
- `/contribute` — user submission form. Keep functional; restyle to match new design system as part of step 1.5 (so users clicking "Add to catalog" from the new home don't hit a style cliff).

**Category surfaces (two routes, deliberate editorial split — PR D6).** Two category-page routes co-exist on different URLs and serve different points in the funnel:

- `/categories/{slug}` (plural) — Direction C chrome-driven nav. The five mega-category routes that the topbar tabs link to (`today`, `eat-drink`, `on-the-water`, `things-to-do`, `services`). Aggregates multiple `Provider.category` slugs into one editorial grid. No filter chips per the "no filters in chrome / chat" rule. Lightweight template (~77 LoC). Lives in `app/categories/`.
- `/category/{slug}` (singular) — Phase 6.2 SEO landing pages with intent-led narrowing. Twelve Tier-1 slugs (`plumbers`, `electricians`, `eat-drink`, `pets`, …) with sub-trade and operational filter chips, ranked by `closest_now` or `editorial_pick`. Entity / EntityCategory-backed. Heavier template (~1150 LoC). Lives in `app/api/routes/category_pages.py`.

When the slug overlaps (`eat-drink`, `on-the-water`, `pets`, …) the routes serve different UX. The intended funnel is: chrome tab → `/categories/services` (plural, mega-grid) → tap a service tile → `/category/plumbers` (singular, SEO page with filters). Don't collapse these without a stronger reason than "two routes for the same noun."

## Open questions / explicitly deferred

Don't waste cycles re-deciding these — they're flagged for a later moment.

- **Photography sourcing.** Mockups use stock Unsplash photos. Real photos for hundreds of providers is a content problem, not a build problem. For launch: ship with placeholder gradients on cards without photos, real photos where available. `Provider.google_photo_refs` already stores Google Places photo IDs for many providers. Sourcing for the rest decided later.
- **Search-result monetization beyond spotlights.** Spotlight placement is the v1 monetization. Other paths (premium listings, paid Hava recommendations) — defer until spotlight revenue is proven.
- **Pinning / saved places.** Discussed in design exploration, not in canonical design. Revisit if usage shows users wanting to return to specific items.
- **Accounts / cross-device memory.** Not yet. localStorage-only state is fine for v1.
- **Dark mode.** Defer. Light mode is the canonical experience. If dark mode ships later, it's a purpose-built palette (not an inversion) — own ramp, own contrast logic, own dark-aware accents.
- **Self-hosted fonts / strict CSP.** Defer. Google Fonts CDN for now. Revisit if/when CSP gets strict.
- **Civic content (trash schedule, road closures, lake levels).** Aspirational — the "one stop shop" trajectory. Catalog needs to grow into this. Possibly a separate content type and a separate row.

## Mobile

Mobile is a first-class canvas, not a media-query afterthought. Build mobile-first:

- Base CSS targets ~380px viewport; `@media (min-width: 720px)` adds desktop progressive enhancement.
- Hero is tighter on mobile (smaller headline, fewer chips, shorter lede). Content peeks above the fold.
- Composer in `/chat` is sticky-bottom on mobile (chat-app expectation). On `/home` it's in the hero — not sticky.
- Sponsor card stays side-by-side at small widths (image + body) — stacking it makes it look more like an ad.
- Day agenda preserves the save action (don't `display: none` it below 720px). Use a smaller tap target if needed.
- Week strip on mobile: 7 day cells with at least 44px tap height. Dot indicator capped at 6.
- Category strip is a horizontal scroll-snap on mobile, wraps to flex on desktop.

The mockups in `mockups/05-home-light-touch.html` and `mockups/07-business-answer.html` already use this mobile-first structure. Reuse their CSS organization.

## Suggested build order

1. **Static `/home` page with mocked data** — full structure (hero with directory-aware lede, category strip, Hava's read, Tonight feature row, sponsor slot, Local pros row, This week, New on Hava, footer). Refined design tokens (AA-safe ink, tonal teal, dopamine coral). Mobile-first CSS. `prefers-reduced-motion: reduce` for the pulse animation. Live alongside `/`; no cutover yet.
1.5. **`/contribute` restyle** — restyle the existing form to match the new design system. Topbar matches `/home`. Don't change form behavior or schema; visual only. Folded into step 1 so users clicking "Add to catalog" from the new home don't hit a style cliff.
2. **Wire Tonight / This week / New on Hava / Local pros to live catalog data.** Add `featured: bool` columns to `events`, `programs`, `providers` (Alembic migration). Build `/api/home/*` endpoints. Replace mocked data in the home template. Placeholder gradients for missing photos.
3. **Sponsor partial + `sponsors` table** — Alembic migration for the new table; server-rendered partial that takes a sponsor record or null and renders a fallback "Sponsor this slot →" card when null. No programmatic ads.
4. **Hava's read pullquote** — server-side LLM generator with stale-while-revalidate caching. 1-hour TTL: serve cached on every request, regenerate in the background when expired. System prompt enforces voice principles. No per-request latency, no cold-start LLM hit, no calls during quiet hours.
5. **Answer-rendering refactor — voice + component schema.** Extend `ConciergeChatResponse` with `voice` and `component: { type, data }`. Update `unified_router`, `tier2_formatter`, `tier3_handler`, and prompts so Tier 2/3 declare a component type. Build `day_agenda` first — highest-impact, fixes the wall-of-text screenshot. New `/chat` route renders by `component.type`, falls back to plain voice when `type === "none"`.
6. **`week_strip` and `card_row` components.**
7. **`single_card` and no-answer treatments.**
7.5. **`business_list` and `single_business_card` components + spotlight disclosure.** Render `Provider.tier = 'spotlight' AND sponsored_until > now()` rows with the warm-tinted treatment. Footer disclosure when any spotlight is in the list. Service queries ("find me a plumber", "junk removal") route here.
8. **"Hava's pick" curation** — for now, leave the `featured` flag DB-only and flip via script. Document the deferred admin-UI options. Local pros spotlight rotation uses `Provider.tier`/`sponsored_until` (already wired in step 7.5).

## Don'ts

- Don't add filters, facets, or sort dropdowns on the home page or in chat answers. The category strip is a tap-to-search affordance, not a filter UI. That's Yelp, not Hava.
- Don't add account creation or login.
- Don't let answers break the voice rules. If the LLM can't honestly say something in 1–3 sentences, the data goes in a component.
- Don't put ads in the hero or before the first row of editorial content.
- Don't add more than one sponsor slot per page.
- Don't add tokens outside the documented palette. New surface or status colors need a semantic justification (e.g., the addition of `--open` for "Open now" status pills, `--live` for live-now state). New decorative colors are out.
- Don't let Hava's voice answers be contaminated by spotlight status. Voice is editorial; spotlights are commercial; the disclosure pattern keeps them separate.
- Don't touch `/admin`. Even when the `featured` flag eventually wants a UI, decide separately at step 8.
- Don't rewrite the existing chat router (`unified_router`, tier 1/2/3 handlers) outside step 5's scope. The voice + component refactor is the only allowed surgery on that pipeline.

## Accessibility notes

- All cards are anchors with descriptive names. Image `alt` attributes should describe the venue or event, not be empty (current mockups leave them empty as placeholders).
- Color contrast: the ink scale meets WCAG AA against the paper background. Don't lighten text below `--ink-3`.
- The Hava voice pullquote and editorial type are large enough not to need a `prefers-reduced-motion` accommodation, but the pulse animation in the eyebrow should respect `prefers-reduced-motion: reduce`.
- The week strip in the answer-rendering mockup is keyboard-navigable (`<button>` elements) — preserve that pattern.
