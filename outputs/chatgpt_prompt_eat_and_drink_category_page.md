# ChatGPT Prompt — Eat & Drink Category Landing Page UX/Copy Spec

> **For the operator (Casey):** Paste everything inside the `~~~` fence below into a fresh ChatGPT chat as the first message. When ChatGPT returns, paste back to Cowork primary. I'll polish into the next Cursor brief once the Home Services category page lane ships. Authored 2026-05-13 by Cowork primary.

~~~

You just shipped me two UX/copy specs for Havasu Chat:

1. The Provider profile page (`/provider/<slug>`)
2. The Home Services category landing page (`/category/home-services`)

This one is the Eat & Drink category landing page (`/category/eat-and-drink`). It's the second category to launch per the strategic pivot (Days 46–60 in the 90-day plan). It builds on the Home Services patterns we already locked.

## What's the same as Home Services

Most of the page anatomy carries over verbatim:

- Page header (title + count + freshness signal + Ask Hava link)
- Sub-trade chips (here: cuisine types instead of trades)
- Sort bar (Default / Most verified / Open now / Closest — same sort behavior table)
- Sponsor slot at top (Category Visibility $349/mo; `disclosure_renderer` with `regime=category_landing`)
- Organic list with the same provider-card anatomy
- Pagination (20/page)
- Editorial copy footer
- Mobile-first sizing rules
- Chat handoff link

Card-level decisions also carry over: card-wide tap target, Call/Directions/Ask Hava inline actions, Google rating visible across all tiers, "Hava's pick" badge for `featured=True`.

**Don't re-derive the parts that match.** Reference the Home Services spec for anything that's the same shape, and only describe deltas where Eat & Drink diverges.

## What's different about Eat & Drink

This is where your work concentrates. Six key differences:

### 1. District filtering (NEW — Eat & Drink-specific)

Eat & Drink providers carry a `district` String(64) column on Provider (added in the 2026-05-13 schema commit — `English Village`, `Downtown`, `North End`, `Lakefront`, `Mesquite Bay`, and similar known Havasu sub-neighborhoods). The category page should expose district filtering separately from sub-trade chips.

UX call: should district be a second row of chips below the sub-trade chips (cuisine type)? Or a sidebar filter on desktop / dropdown on mobile? Or both treated as orthogonal chip groups stacked vertically? Pick one and justify.

Likely Havasu districts (operator note — operator will lock the canonical list later):

- English Village
- Downtown / Main Street
- North End
- Lakefront
- Mesquite Bay
- Highway 95 corridor
- Off-island (Parker, Mohave Valley)

### 2. Sub-trade chips → Cuisine type / category chips

Home Services chips were Plumbing / HVAC / Pool / Electrical / Landscaping. For Eat & Drink, the comparable axis is cuisine or service type. Suggested chips:

- All
- Mexican
- American
- Pizza
- Seafood
- Asian
- BBQ
- Sushi
- Steakhouse
- Coffee / Cafe
- Bar / Brewery
- Breakfast
- Fast Food

Plus operationally distinct categories that aren't cuisine:

- Open Late (after 10 PM — derived from `hours_structured`)
- Open Sunday
- Takeout
- Delivery

Should "Open Late" / "Open Sunday" / "Takeout" / "Delivery" live in the same chip row as cuisines, or be a separate hours/service filter row? Pick one and call it out as an open question if you're not sure.

### 3. Price range filter

A new chip-row dimension Home Services doesn't have. Suggested: `$` / `$$` / `$$$` / `$$$$` chips, single-select. Data source: `attributes.price_range` (operator-curated; ingested from Google's price level when available).

Specify: when `price_range` is missing, what does the card show?

### 4. Dietary options

Vegan / Vegetarian / Gluten-free / Halal / Kosher. Single-select chip filter, like sub-trade. Data source: `attributes.dietary_options` (list of strings).

Spec note: dietary tagging quality will be patchy at launch. If only a handful of providers have dietary tags, show the filter chip row only when at least 3 providers carry at least one of the tags. Otherwise hide the row.

### 5. Hours block more prominent

Restaurants live and die by "is it open now." The provider card's status row should treat "Open now" as more visually prominent than on Home Services. On the Home Services card, "Open now" was a regular line. On Eat & Drink, suggest making "Open now" + close time the single most prominent secondary line after the provider name + verified badge.

### 6. Editorial copy footer is different

Home Services footer mentioned Arizona Registrar of Contractors. Eat & Drink doesn't have that hook. Replacement editorial hook ideas:

- Seasonal-resident-aware language (busy season vs off-season)
- Reservations-versus-walk-in note
- Outdoor seating availability on the river side
- Lakefront vs Downtown vibe difference

Write the actual paragraph in your spec — same length as the Home Services editorial paragraph (~110–140 words), same voice (plain, local, founder-direct).

### Place model caveat

Per the 2026-05-12 strategic pivot §8.2 LOCKED status block, the Place model is deferred to Phase 2. Eat & Drink districts are handled via the `Provider.district` String(64) column for V1, not as first-class Place entities. **Do not spec features that assume Place entities exist** (e.g., a "district profile page" that lists every business in English Village). District is a filter facet on the category page, not a first-class entity in V1.

## Structure I need from you

Markdown spec, ~150–250 lines (shorter than Home Services since most patterns carry over). Sections:

### §1 Page goal
3–5 sentences. Same "measurably better than Google" framing, but adapted for "where should I eat in Havasu" vs "plumber Lake Havasu."

### §2 What carries over from Home Services
Bullet list of regions/components that are identical. One line each. Reference the Home Services spec.

### §3 What's different about Eat & Drink
Detailed treatment of the six differences enumerated above. Each gets its own subsection.

### §4 Updated provider card anatomy
What changes on the card vs Home Services. Likely changes: status row prominence, price range chip, dietary chip, district shown in place of (or alongside) service area, cuisine sub-line different from sub-trade sub-line. Be specific.

### §5 Updated sort behavior
Same sort table as Home Services? Or any Eat & Drink-specific tweaks (e.g., "Open now" as the default sort during evening hours)?

### §6 District filter UX
Detailed treatment of how districts surface (second chip row, sidebar, etc.). This is the most novel piece.

### §7 Edge cases specific to Eat & Drink
- Restaurant with no `price_range` or no `dietary_options` set
- Restaurant in a district we don't show as a chip (e.g., a future district we haven't enumerated yet)
- Sponsor in a different district than the user's filter
- Lakefront vs water-access restaurants (boat-accessible) — should there be a chip?

### §8 Editorial copy block
Actual paragraph (~110–140 words). Plain founder-direct voice. Mention seasonal residents, weekend boating crowd, lakefront-vs-downtown distinction, but do not write a tourism brochure.

### §9 Copy bank
~10 strings the page will need that DIDN'T exist in Home Services. Examples: district filter heading, price-range chip labels, dietary chip labels, "Open Late" chip label, editorial heading.

### §10 Open questions for Casey
3–6 questions. Number them. Examples likely to land here:

- District filter row position (under sub-trade chips, sidebar, modal?)
- Open Late / Sunday / Takeout / Delivery chips — same row as cuisine or separate?
- Default sort: same as Home Services or "Open now" during dinner hours?
- Should the lakefront / water-access distinction be a chip or a sort criterion?

## Output format

Markdown. Sections numbered as §1, §2, etc. No emojis. No HTML. Tables when they help.

## What NOT to do

- Don't re-derive what's identical to Home Services. Reference the existing spec.
- Don't write HTML, CSS, JSX, backend, or migrations.
- Don't spec features that assume a first-class Place model (deferred to Phase 2).
- Don't paraphrase the cold-pitch voice — match it.
- Don't invent provider fields. You may propose new `attributes` keys (e.g., `price_range`, `dietary_options`, `outdoor_seating`).

Begin.

~~~
