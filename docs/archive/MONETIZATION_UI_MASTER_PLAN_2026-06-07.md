# Ask Hava — Monetization & UI Master Plan
**Date:** 2026-06-07 · **Owner:** Casey · **Status:** Approved direction (founding-member pricing, manual invoicing first, week-view calendar)

## 0. Strategy frame

Users are the product; businesses are the customers. The site earns money only if it (a) looks credible enough that a business owner trusts it with $100+/mo, and (b) demonstrably puts their business in front of locals and visitors. Everything below serves those two tests.

Revenue model: **sell scarce, exclusive placement** — not programmatic ads. A 58k-person market can't support CPM display, but it strongly supports "be THE plumber Hava recommends." Competitors charge these same businesses $150–180/mo (Yelp floor), $40–90/lead (Google LSA), $300+/mo (Angi, shared leads). We sell exclusivity below that floor.

## 1. What exists already (don't rebuild)

- **Product catalog** (`app/portal/products.py`): 5 products with $20–400 price ranges, awaiting an operator pricing decision (master plan Phase 11).
- **Sponsor slot system** (`app/home/sponsor_store.py`): 4 live tiers — Marquee (1), Spotlight (2), Promoted (1), Supporter (4) — with scarcity logic and impression/click tracking already wired to `analytics_events`.
- **Portal pages**: `/portal`, `/portal/advertise` (catalog w/ live availability), `/portal/claim` (free claim, magic-link auth, human approval). Payments intentionally not wired; CTAs route to enquiry.
- **Admin**: sponsor inventory + upgrade-request queues already exist (`admin_sponsors_inventory.html`, `admin_upgrade_requests.html`).
- **Redesign direction**: Sandstone theme shipped on home, 12 category pages, events, map.

This plan is therefore mostly *pricing decisions + UI fixes + order-flow wiring*, not greenfield.

## 2. Usability audit — what's broken (verified live 2026-06-07)

### P0 — kills trust with both users and paying businesses
1. **Stale event data on `/events-ui`** — page served "Today: 2 events" listing June 2 events on June 7; "This Weekend" showed a Wednesday. A sponsor checking their own event and seeing week-old data is a refund request. (Matches audit theme #4, cross-request cache inversions.)
2. **Calendar unreadable** — month-grid day cells stuffed with 30–50 recurring Aquatic Center class instances ("Motion & Mobility Margie Tai Chi Vince +44"); one-off events buried. Week strip shows fake "12 AM" times, 5 AM Lap Swim as a day's headline, duplicate entries (Lady Lee's ×2, Farmers Market ×2 from two sources).
3. **Weekend bucket gap** (B-03) — Sat/Sun events fall between "This Week" and "Next Week" in a weekend-tourism town.
4. **Chat transcript CSS blowup** (B-01) — flagship surface unusable when SVGs render 900px tall.
5. **Miscategorization** (tow company #1 in Restaurants) — directly undermines the sales pitch that placement here is valuable.
6. **`/terms` lawyer placeholders live** — must be fixed before taking money.

### P1 — polish needed before asking for money
- Event dedup across sources; fake-noon/12 AM times for missing `start_time`; chip-filter dead ends; pagination caps; timezone math; nav "Explore all" mega-menu renders awkwardly in crawl/text view (verify on mobile).

## 3. Calendar redesign (approved: week view with category rollups)

**Default view = 7-day week strip** (home and `/events-ui`):
- Each day card: date header, then **category rollup lines with counts** — e.g. `🎟 Events 2 · 🏊 Fitness 14 classes · 🎵 Music 1` — plus the top 1–2 *named one-off events* (ranked: special > music/nightlife > community > water; never a recurring class).
- **Recurring classes collapse to a single count** ("14 classes") linking to the day detail filtered to classes. They never appear as a day's headline.
- **Time display**: events missing `start_time` show "time TBD" (never "12 AM"/fake noon) and sort after timed events.
- Day tap → day detail grouped by category; classes collapsed by venue (existing pattern).
- **Month grid demoted** behind a List | Week | Month toggle; cells show ≤2 named one-off events + a small "N classes" badge — never raw class lists, never "+44".
- **Buckets fixed**: Today / This Weekend / This Week / Next Week computed correctly (weekend = upcoming Sat+Sun, always present).
- **Dedup**: fuzzy match on (title, date, venue) across sources before render.

## 4. Pricing (founding-member launch rates)

Anchors: Yelp Ads from $150/mo + Upgrade $180/mo; Nextdoor $32–150/ZIP/mo; small-market chamber banner $100/mo; Angi leads $15–85 *shared*; Google LSA $40–120/lead; Patch event promo ~$60/mo. Full research in §8.

| Product | Founding rate (12-mo lock) | At-scale rate | Slots | Anchor logic |
|---|---|---|---|---|
| Verified & Enriched Listing | **$39/mo** ($390/yr) | $79/mo | unlimited | Chamber $95/yr < us < Yelp Upgrade $180/mo |
| Category Sponsorship (exclusive) | **$129/mo** — premium cats (eat-drink, on-the-water, lodging, home-services) **$179/mo** | $249–399/mo | 1 per category (12) | "Own the category" vs. Angi shared leads $300+/mo |
| Homepage Marquee | **$199/mo** | $399/mo | 1 | Lakewood chamber marquee $400/mo |
| Homepage Spotlight | **$99/mo** | $199/mo | 2 | Below Yelp floor |
| Supporter (footer logo) | **$25/mo** | $49/mo | 4 | Impulse tier; feeds upgrades |
| Event Boost | **$19/event** or $49/mo unlimited | $39/event | n/a | Patch ≈$60/mo |
| Gas/Utility Marquee | **$149/mo** | $299/mo | 1 | High-frequency surface |
| **Founding Partner bundle** | **$149/mo** | retired at scale | 10 max | Enriched listing + spotlight rotation + 2 event boosts/mo + first-dibs on category sponsorship |

Revenue math (conservative): 6 category sponsors + marquee + 2 spotlights + 8 listings + 4 supporters + a few boosts ≈ **$1.7–2.5k MRR** within 2–3 months of selling; full category sell-out + at-scale repricing ≈ $5–8k MRR year-one ceiling.

Seasonality: snowbird season (Oct–Apr) is peak inventory value — sell annual contracts now that smooth it; consider +20% seasonal pricing at-scale, not at launch.

## 5. Business portal (manual invoice first)

**Flow (Sprint 2):** `/portal/advertise` shows real prices + live availability (already has scarcity logic) → "Reserve this slot" → order form (business, product, term, contact) → creates an upgrade-request row (existing admin queue) → email notification to Casey → Casey closes by phone/email, sends **Stripe payment link** → admin marks paid → sponsor record activated → placement live.

- No Stripe integration code required for revenue #1 — payment links are created in the Stripe dashboard.
- Every sponsor gets a **monthly performance email**: impressions + clicks from the existing `analytics_events` tracking. This is the retention product.
- **Self-serve Stripe Checkout** (subscriptions, card on file) is Sprint 4+, only after ≥5 manual sponsors prove the products.

## 6. Roadmap

| Sprint | Work | Outcome |
|---|---|---|
| **1 (now)** | Calendar week-view rollup + time-TBD fix + weekend bucket + month-grid demotion; portal rate card with founding prices + reserve flow | Site readable; rate card real |
| **2** | P0 trust fixes: stale cache root-cause, event dedup, chat CSS blowup, terms copy, top-50 miscategorizations | Site credible enough to sell |
| **3** | Sales kit: one-page PDF rate card, screenshot-quality polish, sponsor performance report email; pitch 20 founding prospects (chamber list, current event venues, boat rentals) | First 5 paying sponsors |
| **4** | Stripe Checkout self-serve, sponsor self-service dashboard (view stats, update creative), newsletter product when digest ships | Scalable revenue |

Sales motion note: the first 10 sponsors are sold by Casey in person/phone — Havasu is a relationship town. The portal's job at launch is to look professional and capture the order, not to close cold.

## 7. Success metrics
- Sponsor-side: reserved slots, paid MRR, sponsor click-through (target ≥1% on marquee), churn after month 3.
- User-side (Plausible): weekly pageviews, events-page share, chat queries, return visitors. Publish a simple traffic number on `/portal/advertise` once it's flattering ("X,XXX locals used Ask Hava last month").

## 8. Market pricing research (sources)
- Yelp: Ads from $150/mo, Upgrade Package $180/mo, bundle from $270/mo — business.yelp.com/local-business-pricing (Oct 2025).
- Nextdoor: neighborhood sponsorships ~$32–150+/ZIP/mo; deals from ~$1/neighborhood — taradel.com, powerdigitalmarketing.com (2025).
- Small-market news comps: News & Tribune (IN) $12 CPM display, $150/day homepage takeover, $175/day newsletter sponsorship — CNHI 2025 rate card.
- Chambers: Carlisle PA — banner $100/mo, enhanced listing $95/yr, e-blast slot $200/mo; Lakewood OH — marquee w/ $400/mo sponsorship. Havasu Chamber + Go Lake Havasu rates are quote-only — **worth a direct inquiry for local comps**.
- Lead platforms: Angi $15–85+/shared lead + ~$300/yr; Thumbtack $10–50/lead; TripAdvisor Business Advantage typ. ~$499/yr.
- Google: LSA $40–120/lead (home services); search CPC restaurants ~$2.05, home improvement ~$7.85 (WordStream 2025).
- Newsletters: $25–50 CPM local; ~$50/send at sub-5k lists; Patch event promo $2/community/day.
