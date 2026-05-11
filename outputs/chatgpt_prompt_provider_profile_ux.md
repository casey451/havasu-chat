# ChatGPT Prompt — Provider Profile Page UX/Copy Spec (havasu-chat)

> **For the operator (Casey):** Paste everything inside the `~~~` fence below — top to bottom — into a fresh ChatGPT chat as the first message. When ChatGPT returns, paste the response back to Cowork primary. I'll polish into a Cursor implementation brief.
>
> Re-authored 2026-05-13 after prior-session-sandbox-loss; grounded against current `app/db/models.py` Provider schema and `docs/sponsor_outreach/verified_presence_pitch.md` voice anchor.

~~~

You are helping me design the Provider profile page for a small local-discovery product called Havasu Chat. I am the founder and only product person. I need a UX/copy spec — a markdown document of about 150–250 lines — that I can hand to an engineer to implement. **Do not write any HTML, CSS, React, or backend code.** Your job is to spec the page so the engineer can build it; mine is to polish your spec into an implementation brief.

## Context (read this carefully — most of your job is honoring this context)

**What havasu-chat is.** A local-only directory + chat product for Lake Havasu City, Arizona. Three front doors: browse categories, search, ask the chat. We just pivoted from chat-first to directory-first; V1 category is Home Services (plumbers, HVAC, pool service, electrical, landscapers). Bootstrapped, founder-led sales. I sell to local business owners in person.

**Why this page matters.** The Provider profile page (`/provider/<slug>`) is the gating piece for our first sponsor package: **Verified Presence ($79/mo)**. The pitch I make to local merchants is, roughly: "you get a verified listing, you control your own business info, you appear in chat results, and your customers see a real profile page instead of scraped junk." That promise is what this page must visibly deliver.

**The Verified Presence value prop in my own words** (so you can tune copy/UX to it):
- Verified stamp + "last verified" date that's visibly recent
- Owner-claimed listing (the owner controls the info, not scraped data)
- Photos and service info the owner provides
- Action buttons that actually work (call, directions, website, ask Hava)
- Surfaces in relevant chat answers (off-page, but reinforces the value)
- I am NOT promising leads, I am NOT replacing Google, I am NOT doing fake scarcity. The page must reflect that honesty.

**Tone anchor.** Plain, local, direct, no marketing-speak, no AI-jargon. Examples from my actual cold pitch:
- "Verified businesses get the verified stamp, last verified date, photos, service info, and the owner can claim and update the listing directly."
- "I'm not selling guaranteed leads for $79. I'm not replacing your Google listing."
- "This is verified local presence inside a Havasu-specific discovery tool."
- A Hava-voice elsewhere in product: helpful, conversational, no emoji-storms, no exclamation points stacked, no "Discover amazing local businesses!" style.

## Available data fields (from our Provider schema — assume the engineer can render any of these)

Identity:
- `provider_name` (required), `slug` (URL-derived, e.g. `acme-plumbing`)
- `category` (legacy free-text string, e.g. "Plumbing"), `category_id` → `Category.name` (canonical, e.g. "Home Services"), `district` (optional, e.g. "North Side" — currently used for Eat & Drink but available)
- `description` (free text), `featured_description` (sponsor-supplied longer copy when present)

Contact / location:
- `address`, `phone`, `email`, `website`, `facebook`
- `lat`, `lng` (for map embed)
- `hours` (free-text), `hours_structured` (JSON: day-of-week ranges; treat as source of truth when present)

Trust / verification:
- `verified` (bool), `last_verified_at` (datetime), `verification_method` (e.g. "owner_confirmed", "phone_call", "manual", "scraper")
- `source` (e.g. "seed", "google_places", "operator_added"), `tier` ("free", "verified", "sponsored" — we use this to flag Verified Presence subscribers)
- `sponsored_until` (datetime; when present + in future, this is an active sponsor)
- `featured` (editorial "Hava's pick" flag — rare, hand-curated)

Google-sourced enrichment (when available):
- `google_rating` (float, e.g. 4.6), `google_review_count` (int), `google_review_snippets` (list of short review excerpts), `google_photo_refs` (list of photo URLs/refs)

Operator-curated structured data:
- `attributes` (JSON; freeform but for Home Services we expect things like `{"service_area": ["Lake Havasu City", "Parker"], "sub_trades": ["plumbing", "drain cleaning"], "emergency_service": true, "licensed": true, "license_number": "..."}`. Schema is open; you can propose what should live here.)

What we do NOT have (don't spec around these):
- User reviews native to our product (we surface Google review snippets but no havasu-chat review system yet)
- Booking / appointment scheduling
- E-commerce / payment on the page
- Live chat embedded on the page (the chat is its own front door)

## Sponsor labeling

If `tier == "sponsored"` AND `sponsored_until > now`, the page should carry a small, plain "Sponsored" or "Verified Presence" indicator near the verified stamp. Honest, not loud. We have a `disclosure_renderer` library that produces the exact label text — you can just say "render via disclosure_renderer with regime=provider_profile" and the engineer will wire it. Don't try to write the label copy yourself.

## The spec I need from you

A markdown document with the following sections. Be specific about content; be brief about styling.

### §1 Page goal (3–5 sentences)
Restate what this page is for, in plain language, anchored to the Verified Presence promise.

### §2 Page anatomy
Top-to-bottom list of every region on the page. For each region: name it, say what it contains, say in 1–2 sentences why it's there. Include order and rough vertical priority. **Include a free-tier vs verified-tier vs sponsored-tier delta**: which regions are present/absent/styled-differently by tier. (We need free providers to still have a respectable page — that's what makes the sponsored upgrade feel earned, not extorted.)

### §3 Above-the-fold zone
The first ~600px on mobile. What MUST appear here, in priority order. Includes: provider name, category, verification badge + last-verified date, primary action buttons. Specify the exact 3–4 buttons and their order.

### §4 Action buttons
For each of {Call, Directions, Website, Ask Hava}: button label, what it does on click, mobile-vs-desktop behavior delta (e.g. `tel:` link on mobile, copy-to-clipboard on desktop), what happens if the underlying field is empty (hide the button entirely vs show disabled vs show with a tooltip — pick one and justify).

### §5 Trust strip
The verified stamp + last-verified date + verification method + source. Specify exact copy. How recent does "last verified" need to be to read as fresh? What if it's stale (>90 days, >180 days)? Specify the copy at each freshness band. **This is the single most important UX element for the sponsor pitch** — the merchant should see this strip and immediately understand it's the visible proof of the $79/mo value.

### §6 Body content
Description, hours, address (with map embed placeholder — assume Leaflet+OSM), service area / sub-trade chips (from `attributes`), Google-sourced snippets section if present. For each: when present what to render, when absent whether to hide entirely or show a placeholder.

### §7 Photos
What if there are zero photos? What if there are 1–3 vs 4+? Carousel or grid or single hero? Specify the behavior, not the CSS. What's the rule for which photo is hero — sponsor-supplied first, else Google's first photo, else nothing?

### §8 Sponsor & claim CTAs
Two distinct CTAs that may appear on the page:
- "Claim this listing" — for unclaimed providers. Where does it go (route + flow handoff)?
- "This is your business? Upgrade to Verified Presence" — for claimed-but-not-sponsored providers. What's the copy, where does it appear, how loud is it? **Be careful: this CTA exists for me to convert merchants, but it should not make the page feel salesy to end-users (who are typically locals looking for a plumber).** Suggest placement that's visible to a business owner who's reviewing their own page but unobtrusive for end-users.

### §9 Edge cases (each gets 2–3 lines of spec)
- Free-tier provider with sparse data (no phone, no website, no hours)
- Sponsored provider but `last_verified_at` is stale
- Provider with `verified=False` but `tier="sponsored"` (data inconsistency — what shows?)
- Provider in a category we don't have a landing page for yet
- Mobile-portrait, mobile-landscape, desktop — note any layout-changes
- A merchant viewing their OWN provider profile (logged in via account-lite — that's coming, but spec the visibility-of-edit-affordances now). Different from a logged-out viewer.

### §10 Copy bank
Provide the exact text for ~10 short strings that will appear on the page. Examples: the verified stamp text, the "Last verified [date]" pattern, the empty-state for missing description, the "Claim this listing" CTA, the "Upgrade to Verified Presence" CTA, the chat hand-off CTA ("Ask Hava about this business"), the freshness-degraded states. **Tone-match the cold-pitch anchor above.**

### §11 Open questions for me (Casey) to resolve
3–8 questions where you weren't sure which way to spec it. Number them. I'll answer in the next round. Examples of what might land here: should free-tier providers show Google reviews or not? Should we show a photo of the building on Google Street View if no photos exist? Should the "Ask Hava" button take a pre-filled query or open a blank chat?

## Output format

Markdown. Sections numbered as §1, §2, etc. No emojis. No HTML. Tables OK when they help (e.g. tier-delta table in §2, copy bank in §10, freshness bands in §5). Aim for 150–250 lines total — long enough to be useful, short enough that I can read it in one sitting and turn it into an implementation brief.

## What NOT to do

- Don't write HTML, CSS, JSX, or backend code. This is a spec, not an implementation.
- Don't invent fields that aren't in the Available data fields list above. (Exception: §6 `attributes` JSON — you may propose new keys, since the schema is open.)
- Don't write marketing copy. Match the voice of the cold-pitch anchor.
- Don't spec a review-collection system, booking flow, payment flow, or user-account features beyond "logged-in owner sees edit affordances."
- Don't be vague. "Show the rating prominently" is wrong; "show `google_rating` as `4.6 ★` next to `google_review_count` in parentheses, immediately under the provider name" is right.

Begin.

~~~
