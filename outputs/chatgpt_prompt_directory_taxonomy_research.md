# ChatGPT Prompt — Lake Havasu Directory Taxonomy (Deep Research)

> **For the operator (Casey):** Paste everything inside the `~~~` fence below into a fresh ChatGPT chat with **deep research mode** enabled (the one that takes longer and pulls web data). When the spec returns, paste back to Cowork primary; I'll fold it into the pivot doc and use it to drive the remaining category page builds. Authored 2026-05-14 by Cowork primary.

~~~

I need a comprehensive directory-category taxonomy for Lake Havasu City, Arizona. Use deep research — pull from real web data about Lake Havasu's demographics, tourist patterns, business landscape, and seasonal rhythms. Don't rely on your training knowledge alone; this needs to be grounded in what's actually in Lake Havasu in 2026.

## What I'm building

A local-only directory + chat product for Lake Havasu City. End-users — residents AND visitors — browse categories manually OR ask a chat ("who fixes AC after hours?" / "where can I take my dog for breakfast?" / "what's open for date night downtown?"). The directory must be **everything anyone in Lake Havasu would find useful** — a one-stop hyperlocal database that's measurably better than Google for "X in Lake Havasu" queries.

The product is bootstrapped, founder-led, and built around the premise that the generic internet can't compete on hyperlocal context. The defensible angle is local-context depth: knowing the bridge backs up Sunday afternoons, knowing English Village is a different vibe than the 95 corridor, knowing emergency plumbers in Havasu operate differently than what Phoenix Yelp would return.

## What we currently have (starting point — NOT a constraint)

A locked taxonomy of 12 canonical categories from an earlier strategy pass:

1. Eat & Drink
2. Events
3. Family
4. Home Services
5. Health
6. On the Water
7. Outdoors & Parks
8. Shopping
9. Auto & Gas
10. Lodging
11. Pets
12. Community

This list was sized for the initial 90-day product plan, not the full "every useful directory" vision. **Treat it as a starting point. Expand, contract, split, or restructure as the research warrants.** The final number might be 14, 18, 22 — whatever the data supports.

## Who the users are (every demographic must be served)

Locals AND visitors. Within each, multiple slices:

- **Year-round residents** (35% age 65+ per US Census; lots of retirees, lots of homeowners with pools and seasonal-home upkeep needs)
- **Snowbirds** (winter residents October-April)
- **Younger working residents** (families with kids, service-industry workers, hospitality workers)
- **Tourists / weekend visitors** (boating, Desert Storm, IJSBA World Finals, spring break crowds, family vacationers)
- **Out-of-town homeowners** (vacation rental owners, second-home owners who need property management)

Each demographic asks different questions:

- **Singles / younger crowd wanting to party** — bars, late-night, live music, weekend events, ride-share, hangover-friendly breakfast
- **Families** — kid-friendly restaurants, swim lessons, kids' sports, summer programs, family events, pediatricians, kid-friendly attractions
- **Couples / date night** — date-night restaurants, romantic spots, scenic drives, special-occasion dining, couples activities, anniversary venues
- **Elderly / retirees** — senior-friendly restaurants, medical specialists, accessibility-aware businesses, senior activities, support services, hearing-aid clinics, home modifications
- **Dog lovers / pet owners** — dog parks, dog-friendly restaurants/patios, off-leash areas, dog beaches, pet boarding, vets, groomers, pet supplies, dog-friendly hikes
- **Outdoor lovers** — hiking, kayaking, fishing, ATV, paddleboarding, boating, jet ski rentals, hunting, dirt biking, scenic overlooks
- **Lake / water enthusiasts** — boat rentals, marinas, boat repair, fuel docks, beaches with boat access, slip rentals, water sports
- **Self-care / wellness** — yoga, massage, spas, gyms, personal training, mental health services
- **Business travelers / professionals** — co-working, decent wifi cafes, business catering, professional services
- **Vacation rental guests** — recommendations for first-time visitors, quick local advice
- **Specialty interests** — pickleball, golf, classic cars, hobbyist groups, classes, lessons

Add any demographic slice the research surfaces. These are starter examples — the real list is what your research finds.

## What I need from you

A markdown spec, **400-800 lines**, with this structure:

### §1 Executive summary

3-5 paragraphs. State the proposed number of top-level categories, the major changes from the current 12 (additions, splits, renames, mergers), the demographic coverage validation, and the 3-5 biggest taxonomy decisions you're making with rationale.

### §2 Proposed top-level categories (table)

Table with columns: **Category name** | **Slug** | **Sub-trade count** | **Primary demographics served** | **Estimated Lake Havasu inventory** | **Sponsor potential (low/med/high)** | **Change vs current 12** (new / kept / renamed-from-X / split-into-X+Y / merged-from-X+Y).

Sort by inclusion priority — most-critical categories first.

### §3 Per-category detail

One subsection per proposed top-level category. For each:

- **Why this category exists** — 2-3 sentences. What user query/intent does it serve? Why can't it be folded into another category?
- **Demographic mapping** — which user slices use this category. Use the demographic list above.
- **Sub-trades / sub-types** — full enumerated list with brief descriptions. Be specific (e.g., for Eat & Drink: Mexican / American / Pizza / Seafood / Asian / BBQ / Sushi / Steakhouse / Coffee / Cafe / Bar / Brewery / Breakfast / Fast Food / Dessert / Food Truck / each with a one-line "what fits here" clarifier).
- **Filter dimensions** — beyond sub-trade, what other filters does this category need? (e.g., Eat & Drink needs district + price + dietary + open-now; Lodging needs star rating + price + boat-access + pet-friendly.)
- **Cross-cutting overlaps** — what other categories does this one share concepts with? (e.g., Dog Parks could be in Outdoors OR Pets — explain why your taxonomy puts it where it does.)
- **Example Lake Havasu businesses or places** — 5-10 real names if research surfaces them. This grounds the abstract category in actual local inventory.
- **Estimated inventory count** — rough order of magnitude (e.g., "60-120 restaurants total citywide; 30-50 sit-down").
- **Sponsor potential** — would merchants in this category realistically pay $79/month for a verified listing? Would the category support a $349/month category-sponsor slot? Low/medium/high with rationale.

### §4 Demographic-coverage check

For each of the demographic slices above (singles, families, couples, elderly, dog lovers, outdoor lovers, water enthusiasts, self-care, business travelers, vacation rental guests, specialty interests, plus any new demos your research surfaces), confirm which categories serve them. If a demographic has a gap — i.e., no category cleanly serves them — call it out as a structural taxonomy problem to fix.

### §5 Cross-cutting concepts that DON'T deserve their own category

Some user intents cut across many categories rather than living in one. Examples:

- "Date night" — pulls from Eat & Drink + Events + Shopping + scenic spots
- "Family-friendly" — pulls from Eat & Drink + Outdoor + Lodging + Events + Health
- "Dog-friendly" — pulls from Eat & Drink + Lodging + Outdoor + Pets
- "Open now" — temporal, cuts across everything
- "Boat-accessible" — geographic, cuts across Eat & Drink + Lodging + Outdoor

Identify these. Recommend treating them as either **filter facets** (a "dog-friendly" toggle across all categories), **chat-driven cross-category queries**, or **curated landing pages that pull from multiple categories**. Don't elevate them to top-level categories.

### §6 What you're explicitly NOT including (and why)

Categories you considered but rejected. Each gets a brief explanation:

- "Too thin in Lake Havasu specifically" (e.g., probably no luxury yacht broker market)
- "Better as a sub-trade in another category"
- "Not enough user-query volume to justify"
- "No realistic sponsor revenue potential"

Be honest. A leaner taxonomy with rich sub-trades beats a bloated one with empty categories.

### §7 Sponsor-package implications

Given the proposed taxonomy, what does sponsor packaging look like? Current packages are Verified Presence ($79/mo, any business), Category Visibility ($349/mo, one sponsor per category), and Seasonal Takeover ($1500-5000, homepage). Should pricing or structure change based on your taxonomy? Are some categories worth more than others (Home Services restaurants vs. Pets vs. Auto)? Should some categories have NO sponsor package because the inventory is too thin or the user-trust dynamics are too sensitive (e.g., medical specialists)?

### §8 Geographic / temporal patterns specific to Lake Havasu

Brief section on what makes this taxonomy Havasu-specific vs. generic. Examples:

- District/neighborhood patterns (English Village vs. Downtown vs. 95 corridor vs. lakefront vs. islands)
- Seasonal rhythms (Desert Storm in late winter, IJSBA World Finals, spring break, summer boating, snowbird season)
- Local quirks (the London Bridge as a focal point, lake-access vs. landlocked, RV crowd, weekend-vs-weekday dynamics)
- Demographics (older homeowners, vacation rental density, second-home market)

If the research surfaces other patterns, include them.

### §9 Open questions for Casey

3-8 genuinely ambiguous calls where you're not sure which way to spec it. Number them. Examples might land here:

- "Should 'Classes' (yoga, art, swim lessons, pickleball lessons) be its own top-level category or live as a sub-trade in Family / Health / Outdoor?"
- "Should 'Professional Services' (lawyers, accountants, insurance) be split from Community, given Community currently feels like it absorbs too much?"
- "Is there enough Lake Havasu nightlife to justify a 'Nightlife' top-level category, or does it live as a sub-trade in Eat & Drink?"

### §10 Recommended sequencing for build-out

Given that we're building one category page at a time, which order should we tackle them in for maximum strategic value? Consider:

- User-search volume (build high-traffic categories first)
- Sponsor revenue potential (build categories where merchants will pay)
- Inventory completeness (build categories where we can launch with real data, not stubs)
- Defensibility (categories where the generic internet is weakest)

## Research grounding requirements

- Use US Census data for Lake Havasu City demographics (age distribution, household composition, owner-occupied rates)
- Use Google Maps / Yelp / Tripadvisor / AZ Office of Tourism for business inventory estimates
- Use Lake Havasu Chamber of Commerce data if accessible
- Use Lake Havasu News, River Scene Magazine, Today's News-Herald for local-color and event patterns
- Cite specific numbers and sources where possible (e.g., "Lake Havasu has approximately X restaurants per Yelp's 2026 listing count")
- Don't fabricate. If you can't find data on something, say so.

## Output format

Markdown. Sections numbered §1, §2, etc. No emojis. Tables where they help (especially §2). Cite sources inline where you ground specific claims. 400-800 lines total.

## What NOT to do

- Don't anchor on the current 12 as either floor or ceiling. Recommend whatever the research warrants — could be 8, could be 22.
- Don't include categories you can't justify with concrete Lake Havasu inventory.
- Don't write marketing copy. This is structural research.
- Don't fabricate business names or counts. If you don't know, say "estimated" or "TBD pending operator confirmation."
- Don't treat "date night" or "dog-friendly" as top-level categories. They're cross-cutting filter facets (per §5).

Begin.

~~~
