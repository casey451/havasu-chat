# Hava — Build Brief

The mockups at `mockups/00-final.html` and `mockups/04-answer-rendering.html` show **what** to build. This brief captures **why** — the rules, trade-offs, and decisions that aren't visible from the markup alone.

## What we're building

Hava is an AI local of Lake Havasu City. Production at https://havasu-chat-production.up.railway.app. Postgres on Railway. The catalog has hundreds of providers, 200+ events, 100+ programs, and every registerable activity from the city's WebTrac registration system (`register.lhcaz.gov`), refreshed every 6 hours via GitHub Actions.

The product today is a single-page chat. We're rebuilding the home page into something locals open as their default for everyday town info — the page they reach for instead of Google or a Facebook group. Chat stays at the center, but the page now also has a body the user can skim before typing.

## Who Hava serves

Locals first. A resident checking what's on tonight, what classes are running this week, where to take a date Saturday. Visitors are welcome but they're not the primary user. The aspirational frame: "one stop shop for everything in Havasu — better than search, kinder than scrolling Facebook groups."

## Voice principles (non-negotiable)

These are the brand. Every Hava response must follow them.

Hava speaks AS THE LOCAL, not a service rep. Direct, declarative, no customer-service phrasing — never "you might want to check…", "I'd be happy to help…", "feel free to…".

Responses are 1–3 short sentences ending in a period. Question marks only when the user asked a question.

The only markdown allowed in the answer text is `[venue name](url)` — deep links to venue websites, registration pages, or Google Maps as a fallback.

When something isn't in the catalog, Hava says so plainly and points to ONE concrete external resource (the CVB site, or `/contribute`). Never a list of options.

If a query naturally returns many items (e.g. "what's happening Friday" returns 8 events), Hava's voice still stays in 1–3 sentences. The data renders as a component below the voice answer. See "Answer rendering contract" below — this is the most important architectural rule.

## Home page structure

Order matters. Each section earns its position.

1. **Topbar** — wordmark + dateline + Add to catalog
2. **Hero** — eyebrow ("Today in Havasu" with pulse dot), big serif headline, lede, search bar, chips
3. **Hava's read on tonight** — single italic-serif pullquote in Hava's voice, refreshed hourly. The personality moment.
4. **Tonight row** — featured-card pattern (1 big + 2 stacked) for immediate-now content
5. **Sponsor slot** — single, native-feeling, clearly labeled. See "Sponsor slot architecture."
6. **This week row** — 3 equal cards
7. **New in town row** — 3 equal cards, recently added catalog items
8. **Footer** — quote line + meta links (Add to catalog, Sponsor a slot, About)

The sponsor slot is between Tonight and This week, not in the hero. Editorial momentum gets to establish itself first — the user receives Hava's voice and at least one row of recommendations before any commerce shows up. This positioning is intentional and not a small detail.

## Answer rendering contract

When the user asks Hava a question, the answer has two parts.

**Hava's voice answer.** 1–2 sentences in her voice. The local's read on what was asked.

**A structured component.** Renders the data Hava was talking about. Pattern depends on query shape:

| Query shape | Component |
|---|---|
| "What's happening on Friday?" | Day agenda — time-grouped, tabular times, save/tap rows |
| "What's on this week?" | Week strip — 7-day tappable strip, agenda below for selected day |
| "Where's good for date night?" | Card row — 3 horizontal cards with images |
| Single venue lookup | Single venue card |
| No-answer ("I don't know that") | Plain voice + ONE pointer (CVB site or `/contribute`) |

Reference implementations live in `mockups/04-answer-rendering.html`. Build them as reusable components, not query-specific renderers — the answer payload should declare which component the front-end renders.

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

`type` values: `day_agenda`, `week_strip`, `card_row`, `single_card`, or `none` (voice answer only).

The chat backend probably needs refactoring to support this. The LLM gets to choose the component type as part of its response, the backend validates and shapes the payload, the front-end renders.

## Design tokens

Use these throughout. The mockup CSS is the canonical source — copy variable names and values from there. Don't re-invent.

**Colors:**
- `--bg: #f7f5ef` — warm paper background
- `--bg-2: #f1eee5` — secondary surface
- `--paper: #ffffff` — card surface
- `--ink` `#14140f` / `--ink-2` `#4a4a44` / `--ink-3` `#8b8b82` / `--ink-4` `#b3b3aa` — text scale
- `--accent: #0e6e7c` — Havasu lake teal, primary
- `--accent-deep: #064551` — darker teal for emphasis
- `--warm: #b8623d` — terracotta, secondary accent (festivals, time-of-day, pulse dot)
- Rules: `rgba(20,20,15,0.10)` / `0.06` / `0.04` for primary / soft / hairline

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

Single slot, between Tonight and This week. Max-width 880px, centered, with generous whitespace.

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

Removable cleanly when search-result monetization comes online — the slot is one section, not interleaved with editorial content.

## "Hava's pick" badges

Frosted-glass badge in the top-left of card images, with a star glyph and "HAVA'S PICK" caps. One per row recommended (three total on the home page). Curation logic is deferred:

- Hand-curated for now (a `featured: true` flag on a venue/event/program, set in `/admin`)
- Could later become rotational, popularity-weighted, or LLM-driven (Hava picks one per row)
- Whatever the source, render at most one pick per row to preserve signal

## Catalog data shapes (current)

Read the actual schema in production Postgres before locking in front-end types. From the original design context:

- **Provider** — name, category, address, phone, hours, website, description
- **Event** — name, dates (one-off or short-range), venue, time, description, registration_url, tags
- **Program** — name, schedule_days, start_time, end_time, age range, cost, venue, registration_url, tags
- **Tags** — content category (arts, sports, aquatics, food, fitness, recreation) + audience (adult, youth)
- **WebTrac items** — every registerable activity, refreshed every 6 hours via GitHub Actions
- **Aquatic Center weekly schedule** — also in the catalog

## Surfaces that already exist

- `/` — current chat interface (the thing we're rebuilding)
- `/admin` — review user-submitted contributions. **Don't touch.**
- `/contribute` — user submission form. Keep functional; restyle to match new design system.

## Open questions / explicitly deferred

Don't waste cycles re-deciding these — they're flagged for a later moment.

- **Photography sourcing.** Mockups use stock Unsplash photos. Real photos for hundreds of providers is a content problem, not a build problem. For launch: ship with placeholder gradients on cards without photos, real photos where available. Sourcing options (contributor-uploaded, city tourism, paid local photographer) decided later.
- **Search-result monetization.** Sponsor slot is the bridge. Premium listings, sponsored Hava recommendations, paid promotion — all later.
- **Pinning / saved places.** Discussed in design exploration, not in canonical design. Revisit if usage shows users wanting to return to specific items.
- **Accounts / cross-device memory.** Not yet. localStorage-only state is fine for v1.
- **Mobile-specific layout.** Mockup is responsive but desktop-first. If mobile dominates traffic (it probably does), a separate mobile pass may be worth scheduling.
- **Civic content (trash schedule, road closures, lake levels).** Aspirational — the "one stop shop" trajectory. Catalog needs to grow into this. Possibly a separate content type and a separate row.

## Suggested build order

1. **Static home page** with mocked data (hero, Hava's read, three rows, sponsor slot, footer). Match mockup pixel-for-pixel.
2. **Wire Tonight / This week / New in town** rows to live catalog queries.
3. **Sponsor slot** — server partial with a fallback card (no programmatic yet).
4. **Hava's read pullquote** — server-side generator (LLM call hourly with a system prompt that enforces voice principles).
5. **Refactor chat backend** so answer responses can declare a component type. Build the day agenda first — highest-impact, fixes the wall-of-text screenshot problem.
6. **Week strip and card row components.**
7. **Single-card and no-answer treatments.**
8. **"Hava's pick" curation** — hand-curated `featured: true` flags surfaced in `/admin`.

## Don'ts

- Don't add filters, facets, or sort dropdowns. That's Yelp, not Hava.
- Don't add account creation or login.
- Don't let answers break the voice rules. If the LLM can't honestly say something in 1–3 sentences, the data goes in a component.
- Don't put ads in the hero or before the first row of editorial content.
- Don't add more than one sponsor slot per page.
- Don't introduce new design tokens. The palette, fonts, and spacing are fixed.

## Accessibility notes

- All cards are anchors with descriptive names. Image `alt` attributes should describe the venue or event, not be empty (current mockups leave them empty as placeholders).
- Color contrast: the ink scale meets WCAG AA against the paper background. Don't lighten text below `--ink-3`.
- The Hava voice pullquote and editorial type are large enough not to need a `prefers-reduced-motion` accommodation, but the pulse animation in the eyebrow should respect `prefers-reduced-motion: reduce`.
- The week strip in the answer-rendering mockup is keyboard-navigable (`<button>` elements) — preserve that pattern.
