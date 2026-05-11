# ChatGPT Prompt — Home Services Category Landing Page UX/Copy Spec

> **For the operator (Casey):** Paste everything inside the `~~~` fence below — top to bottom — into a fresh ChatGPT chat as the first message. When ChatGPT returns, paste the response back to Cowork primary. I'll polish into a Cursor implementation brief once the profile-page lane lands.
>
> This is the natural next implementation lane after the Provider profile page lands. The profile page is the per-record view; this is the list above it. Authored 2026-05-13 by Cowork primary; mirrors the structure of the profile-page UX prompt that ChatGPT shipped well.

~~~

You are helping me design the Home Services category landing page for a small local-discovery product called Havasu Chat. I need a UX/copy spec — a markdown document of about 150–250 lines — that I can hand to an engineer to implement. **Do not write any HTML, CSS, React, or backend code.** Your job is to spec the page; mine is to polish your spec into an implementation brief.

You previously shipped me the **Provider profile page** UX/copy spec for this same product. This category page is the list above those profile pages — same visual language, same voice, same operational tone. When in doubt, defer to the patterns you established there.

## Context (read carefully)

**What havasu-chat is.** A local-only directory + chat product for Lake Havasu City, Arizona. Three front doors: browse categories, search, ask the chat. We pivoted from chat-first to directory-first; V1 category is **Home Services** (plumbers, HVAC, pool service, electrical, landscapers).

**What this page is.** The landing page at URL `/category/home-services`. End-users arrive here from the homepage's category grid, from search, or from a chat handoff. They see a filtered, sorted list of Home Services providers in Lake Havasu City, and click through to individual `/provider/<slug>` pages.

**Why it matters.** This is the V1 directory proof. It's the surface that has to be *measurably better than Google* for "plumber Lake Havasu" — faster, more local, more trustworthy. If users prefer Google, the directory bet is wrong.

**Sponsor packaging context.** The category page is where the **Category Visibility ($349/mo)** sponsor slot lives. One sponsor per category in V1 (we may rotate later). The sponsor slot is a labeled card that's clearly distinguished from organic listings — not a stealth-injection. Verified Presence ($79/mo) providers do NOT appear in the sponsor slot; they appear in the organic list with their Verified Presence badge.

**Tone anchor.** Plain, local, direct, no marketing-speak, no AI-jargon. Same voice as the profile page you specced. Examples from my cold pitch:

- "Verified businesses get the verified stamp, last verified date, photos, service info."
- "I'm not selling guaranteed leads. I'm not replacing your Google listing."
- "This is verified local presence inside a Havasu-specific discovery tool."

The page header copy should be operationally honest, not "Discover amazing local plumbers!" energy.

## Available data per provider card

Each provider on the list page renders as a card. The data behind each card includes (subset of the full Provider record you've already seen in the profile-page spec):

- `provider_name`, `slug`, `category` (canonical: "Home Services")
- `description` (used for a 1–2 line preview), `featured_description` (sponsor-supplied — only used for the sponsor slot)
- `verified` (bool), `last_verified_at`, `tier` ("free" | "verified" | "sponsored")
- `phone`, `address` OR `service_area` list (per the service-area-only attribute from the profile-page spec)
- `hours_structured` (used for "Open now / Closed" badge), `lat`, `lng`
- `google_rating`, `google_review_count`
- `attributes.sub_trades` (list of strings — e.g. `["plumbing", "drain cleaning"]`), `attributes.emergency_service` (bool), `attributes.licensed` (bool), `attributes.weekend_service` (bool)
- `featured` (editorial "Hava's pick" flag — same as profile page; render the subtle badge here too)
- `attributes.hero_pin_photo_url` (sponsor's pinned hero) OR `google_photo_refs[0]` (first Google photo) — for a small card thumbnail

## What to spec

Markdown document, sections numbered §1, §2, etc. No HTML, no CSS, no JSX. Tables OK when they help.

### §1 Page goal (3–5 sentences)
Restate what this page is for in plain language. Lead with "measurably better than Google for 'plumber Lake Havasu'" as the explicit standard.

### §2 Page anatomy
Top-to-bottom regions. Be specific about what each contains and why. Required regions (you may add):

- Page header (category title + count + freshness signal)
- Sub-trade filter chips (Plumbing / HVAC / Pool / Electrical / Landscaping / All — from `attributes.sub_trades` aggregated)
- Sort bar (Default / Most-verified-first / Open-now-first / Closest — see §4 for the sort question)
- Sponsor slot (Category Visibility — ONE card, clearly labeled)
- Organic list (cards in resolved sort order)
- "About Home Services in Lake Havasu" footer block (the editorial copy that adds local context — see §6)
- Pagination or infinite scroll (you pick — see §11 question)

### §3 Provider card anatomy
What does a single card look like top-to-bottom? Specify:

- Hero thumbnail behavior (hero_pin → google_photo[0] → placeholder)
- Card header line (provider_name + verification badge + Hava's pick badge if applicable)
- Sub-line (sub-trade chips: top 2–3 from `attributes.sub_trades`; emergency_service indicator if true)
- Status row ("Open now" / "Closed" / hours range; rating + review count if available)
- Preview line (1–2 sentences from `description`)
- Inline actions on the card (Call, Directions, Ask Hava — same as profile page action row, OR a more minimal version — your call, see §11)
- Tap-target behavior (whole card → `/provider/<slug>` OR just the title — your call, see §11)

### §4 Sort and filter behavior
For each:

- **Default sort.** What's the order? Specify the tiebreak rules. Suggested ranking input: verification tier (sponsored > verified > free, BUT sponsor lives in the slot above so not in the list), then `last_verified_at` recency, then `featured`, then rating, then alphabetical. Justify.
- **Most-verified-first.** Same as default? Or strictly verified-first regardless of `last_verified_at`?
- **Open-now-first.** Bubble currently-open providers (per `hours_structured` and `America/Phoenix` timezone) to the top.
- **Closest.** Requires user geolocation. Behavior when permission denied vs granted. For V1, we don't have user lat/lng; this might be a Phase 2 sort — propose how to handle (gray out vs hide).
- **Sub-trade filter.** Chip selection (single-select? multi-select?). When filter is active, the URL should be `?sub_trade=plumbing` (single) or `?sub_trade=plumbing,drain-cleaning` (multi) — pick one and justify.

### §5 Sponsor slot
The Category Visibility ($349/mo) slot is one card, placed above the organic list. Specify:

- Visual treatment that makes it CLEARLY a sponsor slot (not stealth-injected). Use the existing `disclosure_renderer` label — you saw it on the profile page; same approach here.
- Position: top of the organic list, above the first organic card? Or in a separate section? Justify.
- If no sponsor for this category, what shows? Suggest: a small "Sponsor this category — $349/mo" link visible only to logged-in business owners; render nothing for end-users.
- Sponsor card content. Bigger than organic cards? Same size with a distinguishing accent? You decide — preserve "operational, not loud."

### §6 Editorial copy block ("About Home Services in Lake Havasu")
A short paragraph at the bottom of the page (~80–150 words) that adds local context — e.g. mentioning that many home-service providers serve seasonal residents, that emergency service is rare on Sundays, that licensed contractors should be cross-checked against the AZ ROC database. Write this paragraph in plain Havasu-local voice. Operator note: include 1–2 SEO-useful phrases (e.g. "Lake Havasu City plumbers", "Mohave County electricians") but don't keyword-stuff. This is content for both human readers and search engines.

### §7 Empty / sparse states
- Zero providers in category → what shows? (Shouldn't happen in V1 but spec it.)
- Filter that returns zero results → "No providers match. Clear filters." with a working reset link.
- Fewer than 3 providers → still render the cards; hide pagination; don't render an empty editorial-copy block.

### §8 Mobile-first sizing
- Card size on mobile portrait (height in approximate lines, not px).
- Filter chips on narrow mobile — scroll horizontally, wrap, or collapse into a dropdown? Pick one.
- Sponsor slot on mobile — full-width hero or same as organic? Pick one.

### §9 Chat handoff
The header should include a "Ask Hava about Home Services" inline link — prefilled query "What home service providers are recommended in Lake Havasu City?" Same `/chat?q=...` pattern as the profile page's Ask Hava button.

### §10 Copy bank
~10 short strings the page will need. Examples: page title, count line ("12 home service providers in Lake Havasu City"), sponsor-slot empty state, filter-reset link, sort labels, the editorial-copy paragraph (see §6), the Ask Hava header link copy. Match the voice anchor.

### §11 Open questions for me (Casey) to resolve
3–8 questions where you weren't sure which way to spec it. Number them. Examples likely to land here:

- Card-wide tap target vs title-only tap target — which is right for V1?
- Pagination vs infinite scroll for the organic list?
- Sub-trade filter: single-select or multi-select?
- "Closest" sort — gray out vs hide for V1 when we don't have user lat/lng?
- Inline card actions (Call / Directions) — include or click-through-to-profile-first only?

## Output format

Markdown. Sections numbered as §1, §2, etc. No emojis. No HTML. Tables when they help (sort behavior table in §4, copy bank in §10). 150–250 lines.

## What NOT to do

- Don't write HTML, CSS, JSX, backend, or migrations. Spec only.
- Don't invent provider fields not in the Available Data list. (You may propose new `attributes` keys, since the schema is open.)
- Don't write marketing copy. Match the cold-pitch voice anchor.
- Don't spec a review-submission system, booking flow, or payment flow.
- Don't be vague. "Show the rating prominently" is wrong; "show `4.6 ★ (213)` immediately right of `provider_name`" is right.

Begin.

~~~
