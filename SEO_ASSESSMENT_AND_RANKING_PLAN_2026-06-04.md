# SEO Assessment & Category Ranking Plan — 2026-06-04

Goal: every Ask Hava category/listing page ranks for its local query ("plumbers in
Lake Havasu" → our plumbers page, etc.). All findings below verified live on
2026-06-04 (fetches + SERP checks).

---

## 1. Where we stand today

**Google has indexed zero pages.** `site:havasu-chat-production.up.railway.app`
returns nothing. The site doesn't appear for its own brand ("ask hava" lake havasu)
or for any of 13 category queries tested (plumbers, restaurants, boat rentals,
HVAC, hotels, groomers, gyms, auto repair, vacation rentals, urgent care, events,
things to do, business directory). Organic visibility is nil.

**Root cause stack (in order of severity):**

1. **`*.up.railway.app` subdomain.** Shared, zero-trust platform subdomain; can't
   cleanly verify in Search Console, can't accrue citations, inherits the
   reputation of every other Railway app. This is a hard prerequisite — no
   on-page work matters until it's fixed.
2. **Never submitted to Google.** No Search Console property, sitemap never
   submitted, zero external links pointing at the site → Google has no reason to
   crawl it.
3. **Duplicate route families.** `/category/{slug}` and `/categories/{slug}` both
   return 200 with different titles/content for the same category. Sitemap lists
   only `/categories/`. No canonical anywhere resolves the conflict.
4. **Zero structured data.** No JSON-LD at all (no LocalBusiness, ItemList,
   BreadcrumbList, FAQPage, Event). For a local directory this is the core asset.
5. **Provider canonical + og:url emit `http://`** (X-Forwarded-Proto not honored
   on that route — same bug class as the ED-5 events fix). A wrong-protocol
   canonical on our most numerous page type.
6. **`/category/home-property-services` renders zero listings** ("coming soon")
   even though 237 providers exist on the `/categories/` variant. Our single most
   winnable vertical currently serves an empty page. (Verified live.)
7. **Pagination broken** (audit M-20): 27 of 308 eat-drink listings linked, hard
   60-cap elsewhere, `?page=2` ignored. The long tail of ~1,500–2,000 providers is
   sitemap-only orphans with no internal PageRank.
8. **Faceted filter links** (~20–24 per category page: `?trade=`, `?district=`,
   `?open=now`…) with no canonical → crawl-budget bloat and thin duplicates.
9. **Weak NAP**: address appears only URL-encoded inside the Google Maps
   Directions href, not as visible text. NAP is the ranking currency of local pages.
10. Smaller: meta descriptions are raw blurbs truncated mid-word ("…libations.\n\nTh"),
    sitemap `lastmod=today` on every regen (Google learns to ignore it), no
    og:image, homepage H1 carries no directory keyword.

**What's already good:** server-rendered Jinja HTML (crawlable), clean slugs,
robots.txt + dynamic sitemap wired, breadcrumbs on provider pages, no auth walls,
no SPA bundle bloat, meta titles/descriptions exist everywhere.

---

## 2. Who owns the SERPs (and what that means for targeting)

| SERP segment | Who ranks | Difficulty for us |
|---|---|---|
| Tourism (restaurants, things to do, hotels, boat rentals, vacation rentals) | golakehavasu.com (DMO), TripAdvisor, Yelp, OTAs/marketplaces | **Hard** — locked up by authority domains. Long game. |
| Home services (plumbers, HVAC, auto repair, handyman, pool, pest…) | Mostly individual business sites + Yelp/Angi; **mohavelocal.com (small regional directory) cracks top-10 for plumbers and groomers** | **Winnable** — proof a regional directory can rank here. Start here. |
| Events | golakehavasu, riverscenemagazine, Eventbrite, downtown association | **Medium** — freshness wins; we have a live events system. |
| Pets, gyms, urgent care, shopping | Mixed chains + directories | **Medium** |
| "lake havasu business directory" | havasuchamber.com, lhcaz.gov | **Medium** — natural fit for our homepage. |

**Exploitable weakness:** golakehavasu.com's listings load via a JS widget — their
category pages literally render "Please enable JavaScript" to crawlers. They rank
on domain authority alone. A server-rendered directory with dense listing HTML can
out-content them per category page; we cannot out-authority them short-term.

**The repeatable on-page template winners share** (TripAdvisor/Angi/Yelp pattern):

- Title: `THE {N} BEST {Category} in Lake Havasu City, AZ (Updated {Month Year})`
- Meta description leading with aggregate proof: "{X} reviews of {Y} businesses"
- H1 with count + category + city; short intro (40–100 words) — not essays
- Listing cards: name, star rating, review count, attributes, open-now, photo,
  1–2 review snippet quotes
- FAQ block: 3–6 city-templated long-tail Q&As, each with internal links
- Schema: BreadcrumbList + ItemList + FAQPage on category pages; LocalBusiness
  (+AggregateRating when we have ratings) on provider pages
- Three-axis internal link mesh: same-city other categories × subcategory/facet
  pages × related services
- The content moat is **structured first-party data rendered server-side**, not prose.

---

## 3. The plan

### Phase 0 — Prerequisites (Casey decisions; nothing else matters until done)

- [ ] **Buy a custom domain** (e.g. `askhava.com` / `havasu.chat` — geo-brandable,
      .com preferred). Attach to Railway, 301 the entire railway subdomain to it.
      Footer email already says `hello@havasuchat.com` — if you own havasuchat.com,
      that's a candidate.
- [ ] **Search Console**: verify the new domain (DNS property), submit sitemap.
- [ ] Set `BASE_URL` env var to the new domain (code already supports it).
- [ ] Bing Webmaster Tools too (free, feeds DuckDuckGo, ~5 min).

### Phase 1 — Technical fixes (code, ~1 sprint, feature branch → PR)

Ordered by impact:

- [ ] **Pick one category route family and kill the other.** Recommendation: keep
      `/category/{slug}` (cleaner, Tier-1 locked taxonomy) and 301
      `/categories/{slug}` → `/category/{slug}` with a mapping for legacy slugs
      (things-to-do, services, professional, beauty-care, attractions → nearest
      Tier-1). Update sitemap, nav, and breadcrumbs to the surviving family.
- [ ] **Fix `/category/home-property-services` empty render** — it must serve the
      237 providers server-side like the eat-drink page does.
- [ ] **Fix `https` canonical/og:url on provider pages** (honor X-Forwarded-Proto;
      same fix as ED-5). Add `rel=canonical` to ALL page types (home, category,
      provider, events) — absolute https URLs on the new domain.
- [ ] **Real pagination** on category pages: `?page=N` with `LIMIT/OFFSET`,
      `rel=next/prev`-style crawlable links, page number in title ("Page 2 of …").
      Every provider must be reachable by links, not just sitemap.
- [ ] **Faceted URLs**: canonical from every `?trade=/?district=/?open=` variant to
      the clean category URL — EXCEPT facets we deliberately promote to real pages
      (see Phase 2 trade pages).
- [ ] **Sitemap**: emit the surviving route family; real `lastmod` (max provider
      `updated_at` per category instead of `today`); split into sitemap index
      (categories / providers / events) for cleaner Search Console diagnostics.
- [ ] **Visible NAP block** on provider pages: address as text (schema.org
      PostalAddress fields), phone, hours.
- [ ] **Meta description sanitizer**: strip newlines, sentence-boundary truncate
      ~155 chars.
- [ ] **og:image** (site default + provider photo when available), og tags on all
      page types, not just providers.
- [ ] Fix M-21 duplicate provider slugs (ZENSHI ×2 etc.) — merge + 301.
- [ ] Investigate B-04 split-cache (divergent counts between requests) — it will
      cause inconsistent crawls.

### Phase 2 — Page templates that match the winning pattern (~1–2 sprints)

**This is where "rank for every category" actually happens.** The query "plumbers
in lake havasu" needs a dedicated page, not a filter param.

- [ ] **Promote trade/cuisine facets to real subcategory pages** with clean URLs:
      `/category/home-property-services/plumbers`, `/hvac`, `/electricians`,
      `/handyman`, `/pool-service`, `/pest-control`, `/roofers`, `/garage-door`,
      `/landscapers`, `/cleaning`; same for eat-drink cuisines, pets services
      (groomers/vets/boarding), auto (repair/tires/detailing), etc. Each gets its
      own title/H1/intro/FAQ and goes in the sitemap. **These pages ARE the plan**
      — start with the 10 home-services trades (most winnable SERPs).
- [ ] **Category + subcategory page template:**
  - Title: `{N} Best {Trade} in Lake Havasu City, AZ — Ask Hava` (N = live count,
    rendered server-side so it's always current; add "(Updated {Month Year})" once
    content is genuinely maintained)
  - H1 mirrors title; 40–100 word locally-specific intro (mention districts,
    seasonal context — lake season, snowbirds — not boilerplate)
  - Listing cards with rating/review count when available, attributes, open-now,
    photo thumb
  - FAQ block (4–6 templated-but-true Q&As: "Who does emergency plumbing in Lake
    Havasu City?", "How much does X cost in Havasu?") → FAQPage JSON-LD
  - JSON-LD: `BreadcrumbList` + `ItemList` of the listed businesses
  - Internal links: sibling trades, parent category, "near {district}" once dense
- [ ] **Provider page template:**
  - JSON-LD `LocalBusiness` (correct subtype: Restaurant, Plumber, HVACBusiness,
    AutoRepair, LodgingBusiness…) with name, address, phone, geo, url, openingHours,
    image; `AggregateRating` only when we have real ratings
  - `BreadcrumbList` JSON-LD matching the visible breadcrumb
  - Visible NAP block; "While you're here" → proximity/same-trade based (M-28)
- [ ] **Event pages**: `Event` JSON-LD (name, startDate, location, image) — events
      are our most winnable freshness play vs. golakehavasu.
- [ ] **Homepage**: H1 → "Lake Havasu City's local directory & concierge" (keep the
      personality as H2); target "lake havasu business directory".

### Phase 3 — Data depth (ongoing; this is the rank gate)

Google's scaled-content policies punish thin programmatic pages. The template only
works if the database is dense:

- [ ] Hours coverage (Shugrue's — a flagship restaurant — shows "Hours not
      available"). Backfill from Google/owner claims.
- [ ] Photos per listing; unique 1–2 sentence editorial descriptions for top ~200
      providers (start with home-services trades + top restaurants).
- [ ] A ratings/review signal: import-free options = owner-claimed attributes,
      "verified by Hava" badge, lightweight first-party reviews. Without some
      rating signal, cards are visibly thinner than Yelp/TripAdvisor's.
- [ ] Fix categorization noise (T1–T8 audit themes) — miscategorized listings on
      ranking pages are a quality signal Google's raters notice.
- [ ] Keep events fresh (the "this weekend" query family rewards freshness).

### Phase 4 — Off-page: links & citations (parallel, Casey-driven)

A new domain ranks nothing without external trust. Realistic order:

- [ ] **Lake Havasu Area Chamber membership** → member-directory link (their
      directory ranks #1 for "lake havasu business directory").
- [ ] **golakehavasu.com partner/coverage** — we already ingested their 543
      partners (GOLAKEHAVASU_PROJECT_CLOSEOUT); a partnership/blog mention is a
      same-town authority link.
- [ ] **Local press launch story**: Havasu News-Herald, RiverScene Magazine. Pitch
      data angles ("we mapped every plumber/restaurant in Havasu").
- [ ] **"Listed on Ask Hava" badge/widget** for businesses → reciprocal links from
      claimed listings.
- [ ] Presence where SERPs already show demand: the big Lake Havasu Facebook
      groups and riverdavesplace.com forum (genuine participation, not spam).
- [ ] City/civic resource pages (lhcaz.gov links to local resources).

### Phase 5 — Measure & iterate

- [ ] Search Console: weekly indexation coverage + query report per category page.
- [ ] Rank checks for the 13 benchmark queries (section 2) monthly; expand to all
      trade pages. (Can be automated as a scheduled job later.)
- [ ] Plausible: organic landing-page sessions per category.
- [ ] Expectations: indexation within ~2–6 weeks of Phase 0+1; movement on
      low-competition home-services queries in ~2–4 months; tourism queries are a
      6–12+ month authority game.

---

## 4. Query → page mapping (the "every category" matrix)

| Target query family | Page | Status today |
|---|---|---|
| plumbers in lake havasu | `/category/home-property-services/plumbers` | doesn't exist (facet param only; parent page renders EMPTY) |
| hvac repair lake havasu | `/category/home-property-services/hvac` | doesn't exist |
| electrician / handyman / pool service / pest control / roofer / garage door / landscaper / house cleaning + " lake havasu" | one trade page each | don't exist |
| restaurants lake havasu (+ per-cuisine) | `/category/eat-drink` (+ cuisine subpages) | exists, 27/308 listings linked, no schema |
| boat rentals lake havasu | `/category/on-the-water` (+ `/boat-rentals` subpage) | parent only |
| hotels / vacation rentals lake havasu | `/category/lodging-vacation-rentals` (+ split subpages) | parent only |
| pet groomers / vets lake havasu | `/category/pets/groomers`, `/vets` | don't exist |
| gyms lake havasu | `/category/classes-sports-recreation/gyms` | doesn't exist |
| auto repair lake havasu | `/category/auto-rv-fuel/auto-repair` | doesn't exist |
| urgent care lake havasu | `/category/health-wellness-care/urgent-care` | doesn't exist |
| things to do in lake havasu | `/category/outdoors-parks-trails` + home hub | exists |
| lake havasu events this weekend | `/events-ui` (+ "this weekend" view) | exists, no Event schema |
| lake havasu business directory | homepage | exists, H1 doesn't target it |

Priority order for building trade pages: plumbers, HVAC, auto repair, pet groomers,
gyms, urgent care (lowest-competition SERPs with directory precedent) → then
tourism subpages.

---

## 5. Decisions needed from Casey

1. Domain choice + purchase (Phase 0 — blocks everything).
2. Which route family survives (`/category/` recommended).
3. Review-signal strategy (first-party reviews vs. claimed-attributes only).
4. Budget/appetite for Chamber membership + press outreach.

All code work happens on a feature branch → PR per repo rules; nothing here
touches prod data.
