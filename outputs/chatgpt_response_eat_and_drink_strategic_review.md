# Eat & Drink Category Page — Strategic Review (ChatGPT)

> **Origin:** ChatGPT response 2026-05-14 to the prompt at `outputs/chatgpt_prompt_eat_and_drink_category_page.md`. ChatGPT did NOT ship the markdown spec format requested; instead delivered strategic review/critique of the framing in the prompt. Content is high-value — informs the spec rather than replacing it. Cowork primary will integrate these insights when authoring the Eat & Drink Cursor implementation brief (which is gated on the Home Services category page implementation landing first).

---

## §1 Strategic framing — the two mental models

The product is starting to naturally separate into two different mental models:

1. **"Find me a provider/service"** — Home Services flow (lookup + trust).
2. **"Help me decide where to go right now"** — Eat & Drink flow (discovery + mood + context).

> Home Services is mostly lookup + trust. Eat & Drink is much more discovery + mood + context. That distinction matters because the UX shouldn't just be "same page but restaurants." The restaurant flow needs to feel faster, more situational, and more emotionally driven.

---

## §2 Already-correct calls in the original prompt/spec direction

- District filtering is the right move.
- Making "Open now" visually dominant is correct.
- Separating cuisine from operational filters is correct.
- Price range matters more than ratings in food discovery.
- The "Place model deferred" constraint is smart — avoiding premature architecture.

---

## §3 Things to tighten before Cursor implementation

### §3.1 Districts are more important than the prompt assumed

For Havasu specifically, districts are not just geographic filters. They imply:

- vibe
- parking difficulty
- boating access
- tourist density
- nightlife
- local-vs-tourist feel
- walkability

"English Village" means something completely different from "95 corridor."

**Implication for the spec:** do NOT bury district inside a dropdown. Recommended chip-row structure:

- Row 1: cuisine chips
- Row 2: district chips
- Row 3: operational chips

District is one of the main decision drivers in Havasu. People think:

- "somewhere downtown"
- "somewhere by the water"
- "north side"
- "near the bridge"

Not:

- "show me all providers in district_id=3"

This is a local behavior product. Lean into that.

### §3.2 Operational filters should NOT live in cuisine chips

Do not mix:

- Mexican, Sushi, Breakfast (cuisine = identity)

with:

- Open Late, Delivery, Open Sunday (operational = logistics)

Those are different cognitive categories. Separate rows. Otherwise the chip row becomes visually noisy and mentally confusing.

### §3.3 "Open now" should probably affect default ranking

Time-aware ranking becomes valuable here. Example weighted heuristic:

- currently open = +30
- verified recently = +15
- sponsored = separate insertion layer
- high ratings = +10
- matching district = +15
- matching cuisine = +25

At 8:30 PM:
- closed breakfast places sink hard
- bars/open-late restaurants rise

At 8 AM:
- coffee and breakfast naturally rise

No ML needed. Simple weighted heuristic. This is where the product starts becoming more useful than Yelp — not because the database is bigger, but because the ranking is more situational.

### §3.4 Add "Boat Access" as a first-class filter

In Havasu this matters enough to deserve elevation. Not buried inside attributes.

**Recommended:**

- Boat Access (operational filter)
- Outdoor Seating (operational filter)

Both are highly local-contextual discovery features. Exactly the kind of thing generic search engines are weak at.

### §3.5 Provider cards should become more visual than Home Services

Home Services survives on trust/reviews/verification/responsiveness. Restaurants cannot.

Even in V1:

- one photo thumbnail matters
- food photo matters
- patio photo matters

Otherwise the page feels directory-heavy instead of discovery-heavy. Recommended for V1:

- 16:9 hero thumbnail
- fallback placeholder
- image prioritization rules (food → patio → lake view → bar atmosphere eventually)

### §3.6 "Hava's Pick" needs strict governance

The second editorial curation is implied, people will assume pay-to-play. Make "Hava's Pick" extremely constrained. Possible rules:

- verified
- high review count
- recent verification
- no unresolved flags
- strong metadata completeness
- maybe manually assigned

Otherwise local businesses will immediately think: "the sponsor bought the badge." That can poison trust early.

---

## §4 Strategic observation — feature sprawl warning

The product is accidentally becoming:

- part Yelp
- part Google Maps
- part concierge
- part local search engine
- part chamber-of-commerce layer

**The danger:** feature sprawl.

**The opportunity:** local context depth.

The advantage is NOT: "we list businesses."

The advantage IS: "We understand Havasu context better than generic search."

That means leaning into:

- boating
- snowbird season
- heat
- off-season hours
- bridge/downtown traffic
- lakefront
- RV crowd
- weekend vs weekday dynamics
- local knowledge

The more the UX reflects those realities, the more defensible this becomes. The generic internet can't compete well on hyperlocal nuance.

> The product gets interesting when it starts behaving like a local person instead of a database.

---

## §5 Integration plan for Cowork primary

When authoring the Eat & Drink Cursor implementation brief (after Home Services category page lands), integrate these insights:

1. **Three chip rows** (cuisine / district / operational) — not the original prompt's "second row of chips below sub-trade chips OR sidebar OR dropdown" open question. **LOCK:** three rows.
2. **Time-aware default sort** — new feature not in original spec; reasonable to lock in as the default. Author the weighted heuristic in `queries.py` with the suggested weights as starting points (operator-tunable).
3. **Boat Access + Outdoor Seating as first-class operational filters** — add to operational chip row, not buried in `attributes`. May need new `attributes` keys (`boat_access`, `outdoor_seating`) until/unless promoted to first-class columns.
4. **16:9 hero thumbnail spec** — more prominent than Home Services. Photo prioritization rules (food first, then patio, then lake view, then bar atmosphere — implementer can stub the prioritization logic for V1 using whatever metadata is available).
5. **"Hava's Pick" governance** — operator decision: lock the rules now or defer? Recommendation: defer the formal governance doc but in V1 the `featured` flag is hand-curated by Casey only (never auto-derived), which is implicit governance.

These integrations turn ChatGPT's strategic-review-instead-of-spec response into actionable spec content. The original Home Services spec patterns still carry over for everything not called out here.
