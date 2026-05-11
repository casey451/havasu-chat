# Provider Profile Page — UX/Copy Spec

> **Origin:** ChatGPT-drafted 2026-05-13 in response to `outputs/chatgpt_prompt_provider_profile_ux.md`. Saved verbatim for the implementation lane reference. Cowork primary will polish into `outputs/cursor_brief_provider_profile_page.md` after Casey resolves the 4 outstanding §11 questions (the other 4 are primary-resolved with notes inline).

---

# §1 Page goal

The Provider profile page is the durable, shareable identity page for a local business inside Havasu Chat. It should answer a basic user question quickly: "Is this business real, current, and usable?" The page exists to make business information feel owner-controlled instead of scraped and stale.

For end-users, the page should function like a clean local directory listing with working actions, trustworthy hours, clear service info, and enough detail to decide whether to call. For merchants, the page should visibly demonstrate what "Verified Presence" means: recent verification, editable business-controlled data, better photos, richer service information, and a more complete presence inside the product.

The page should not feel like an ad landing page. It should feel like a reliable local utility page that happens to make the sponsor value obvious.

---

# §2 Page anatomy

## Overall structure (top → bottom)

1. Above-the-fold identity + actions
2. Trust strip
3. Photo region
4. Description + service details
5. Hours + address/map
6. Service area / sub-trade chips
7. Google review snippets
8. Ask Hava contextual CTA
9. Claim / upgrade CTA region
10. Footer metadata

Vertical priority should heavily favor:

* trust
* actionability
* owner-controlled data
* fast scanning on mobile

Do not force long scrolling before primary actions are visible.

---

## Region 1 — Identity header

Contains:

* Provider name
* Category
* District (if present)
* Verification indicator
* Sponsored indicator (via `disclosure_renderer`)
* Google rating summary (if present)

Purpose: Establish who the business is and whether the listing is trustworthy/current.

Priority: Highest.

---

## Region 2 — Primary actions row

Contains:

* Call
* Directions
* Website
* Ask Hava

Purpose: Convert page visits into immediate utility.

Priority: Highest.

---

## Region 3 — Trust strip

Contains:

* Verified status
* Last verified date
* Verification method
* Source attribution

Purpose: Visually prove the "Verified Presence" value proposition.

Priority: Highest after actions.

---

## Region 4 — Photos

Contains:

* Hero photo
* Supplemental gallery/grid

Purpose: Make the business feel current and real.

Priority: High.

---

## Region 5 — Description block

Contains:

* `featured_description` when present
* fallback to `description`

Purpose: Provide operator- or owner-controlled context.

Priority: Medium-high.

---

## Region 6 — Service details block

Contains:

* sub-trades
* emergency service
* licensed status
* license number
* service area
* additional structured attributes

Purpose: Help users qualify the provider quickly.

Priority: Medium-high.

---

## Region 7 — Hours + location

Contains:

* structured hours
* free-text fallback hours
* address
* map embed placeholder

Purpose: Operational utility.

Priority: Medium.

---

## Region 8 — Google enrichment

Contains:

* rating
* review count
* short snippets

Purpose: Supplement trust without becoming "another Google page."

Priority: Medium-low.

---

## Region 9 — Ask Hava contextual CTA

Contains:

* "Ask Hava about this business"

Purpose: Bridge the directory and conversational product surfaces.

Priority: Medium-low.

---

## Region 10 — Claim / sponsor CTA

Contains:

* claim listing CTA OR sponsor upgrade CTA

Purpose: Merchant conversion surface.

Priority: Low for consumers, high visibility for merchants reviewing their own listing.

Should feel secondary and non-disruptive.

---

## Region 11 — Footer metadata

Contains:

* source attribution
* listing ID metadata if needed
* update/report issue link

Purpose: Operational transparency.

Priority: Lowest.

---

## Tier delta behavior

| Region                 | Free                         | Verified                 | Sponsored                     |
| ---------------------- | ---------------------------- | ------------------------ | ----------------------------- |
| Verification badge     | Hidden unless truly verified | Visible                  | Visible                       |
| Last verified date     | Optional if stale/imported   | Visible                  | Strongly visible              |
| Sponsored disclosure   | Hidden                       | Hidden                   | Visible                       |
| Photos                 | Google only / limited        | Full owner photos        | Full owner photos prioritized |
| Featured description   | Hidden                       | Visible                  | Visible                       |
| Service chips          | Basic                        | Full                     | Full                          |
| Google snippets        | Visible                      | Visible                  | Visible                       |
| Ask Hava CTA           | Visible                      | Visible                  | Visible                       |
| Claim CTA              | Visible if unclaimed         | Hidden                   | Hidden                        |
| Upgrade CTA            | Hidden                       | Visible if not sponsored | Hidden                        |
| Owner edit affordances | Hidden                       | Visible to owner only    | Visible to owner only         |

---

# §3 Above-the-fold zone

First ~600px on mobile MUST contain, in this order:

1. Provider name
2. Category line
3. Verification badge + freshness status
4. Sponsored disclosure (if applicable)
5. Google rating summary (if available)
6. Primary actions row
7. First photo OR placeholder
8. Short description preview (2–3 lines max)

## Priority order

### Line 1: `provider_name`

Largest text on page.

### Line 2: Category + district

Example: `Plumbing • North Side`

Hide district if absent.

### Line 3: Verification cluster

Example:

`Verified business`
`Last verified May 2, 2026`

Must appear above action buttons.

### Line 4: Action buttons

Order:

1. Call
2. Directions
3. Website
4. Ask Hava

Reasoning:

* Calling is the highest-intent action.
* Directions is commonly second for local services.
* Website is useful but often secondary on mobile.
* Ask Hava is exploratory/supportive.

---

# §4 Action buttons

## Call

Label: `Call`

Behavior:

* Mobile: opens `tel:` link
* Desktop: copies phone number to clipboard. Show temporary confirmation: `Phone number copied`

Missing field: Hide entirely. Reason: Dead buttons damage trust faster than missing buttons.

## Directions

Label: `Directions`

Behavior:

* Mobile: open native maps app
* Desktop: open Google Maps in new tab

Uses: address if present, fallback to lat/lng.

Missing field: Hide entirely.

## Website

Label: `Website`

Behavior: Open external site in new tab. If URL malformed: normalize before render if possible.

Missing field: Hide entirely.

## Ask Hava

Label: `Ask Hava`

Behavior: Open chat with prefilled query. Example: `Tell me about ACME Plumbing in Lake Havasu City`. Should preserve conversational continuity.

Missing field: Always visible. Reason: This is a product-navigation action, not provider data.

---

# §5 Trust strip

## Purpose

This strip is the visible proof that the listing is maintained and locally monitored. It should read more like operational status than marketing language.

## Components

1. Verified status
2. Last verified date
3. Verification method
4. Source attribution
5. Sponsored disclosure if applicable

## Exact structure (fresh verified example)

```
Verified business
Last verified May 2, 2026
Verified via owner confirmation
```

Optional final line: `Listing managed by business owner`

## Verification method mapping

| Method          | Copy                                     |
| --------------- | ---------------------------------------- |
| owner_confirmed | Verified via owner confirmation          |
| phone_call      | Verified via phone confirmation          |
| manual          | Verified manually                        |
| scraper         | Imported listing — not recently verified |

## Freshness bands

| Age         | Status     |
| ----------- | ---------- |
| 0–30 days   | Fresh      |
| 31–90 days  | Acceptable |
| 91–180 days | Aging      |
| 180+ days   | Stale      |

## Copy by freshness band

| Band   | Copy                                    |
| ------ | --------------------------------------- |
| 0–30   | `Last verified May 2, 2026`             |
| 31–90  | `Verified 2 months ago`                 |
| 91–180 | `Verification may be outdated`          |
| 180+   | `Business information may have changed` |

## Sponsored + stale handling

If sponsored but stale:

* still show sponsor disclosure
* degrade trust copy honestly
* do NOT fake freshness

Example:

```
Verified Presence subscriber
Business information may have changed
Last verified November 2025
```

This is important operational honesty.

---

# §6 Body content

## Description block

Priority logic:

1. `featured_description`
2. `description`
3. Empty state

Empty state copy: `No business description has been added yet.`

Do not generate AI summaries.

## Hours block

Source priority:

1. `hours_structured`
2. `hours`
3. hidden entirely

Structured hours behavior:

* Render current day status first
* Weekly schedule below

Example:

```
Open now
Closes at 5 PM
```

## Address block

Render full address; tap-to-open map. If missing: hide entire section.

## Map embed placeholder

Use Leaflet + OSM. Behavior:

* static/non-interactive preview initially acceptable
* tap expands to map app

## Service details block

Suggested attribute keys:

* `service_area`
* `sub_trades`
* `emergency_service`
* `licensed`
* `license_number`
* `insured`
* `bonded`
* `years_in_business`
* `weekend_service`
* `after_hours_service`

## Service chips examples

* Emergency Service
* Licensed
* Weekend Service
* Drain Cleaning
* Pool Repair
* HVAC Repair

Hide entire chip row if empty.

## Google snippets section

Render only if:

* `google_review_snippets` exists
* AND length > 0

Structure: rating summary first, max 3 snippets.

Example: `4.6 ★ (213 Google reviews)`

Snippets should be visually secondary to owner-controlled content.

---

# §7 Photos

## Hero selection priority

1. Sponsor-uploaded photo
2. Owner-uploaded photo
3. First Google photo
4. No image placeholder

## Zero photos

Show:

* neutral branded placeholder
* NOT stock photography

Copy: `No business photos available yet`

## 1–3 photos

* single hero image
* thumbnails underneath if >1

## 4+ photos

* hero image
* horizontal swipe gallery on mobile
* grid expansion on desktop

Do not autoplay.

## Photo behavior

* tap opens lightbox
* preserve aspect ratio
* prioritize exterior/storefront photo as hero when detectable

---

# §8 Sponsor & claim CTAs

## Claim this listing

When shown:

* provider unclaimed
* verified=false

Placement: Bottom-third of page after main business info. Not above trust strip.

CTA copy: `This your business? Claim this listing and manage the information customers see.`

Destination route: `/claim/<provider_slug>`

Flow handoff: account-lite onboarding + verification workflow.

## Upgrade CTA

When shown:

* claimed provider
* tier != sponsored

Placement: Small card below body content and above footer metadata. Should not interrupt browsing flow.

Tone: Operational, not sales-heavy.

Suggested copy:

```
Upgrade to Verified Presence to add owner-managed photos, recent verification status, and expanded business details.

This listing already appears in Havasu Chat results.
```

Loudness: Low-medium visual weight. No popups. No sticky banners. No countdowns or scarcity messaging.

---

# §9 Edge cases

## Sparse free-tier provider

Hide empty regions entirely. Do not render skeleton sections with "coming soon."

Minimum viable page:

* name
* category
* whatever actions exist
* source attribution

## Sponsored provider with stale verification

Show sponsor disclosure honestly. Do not suppress stale messaging. May additionally show: `Owner verification recommended`.

## verified=False but tier="sponsored"

Treat as data inconsistency. Render:

* sponsor disclosure
* NO verified badge

Show fallback: `Sponsored listing`

Internally flag for admin review.

## Unknown category

Render provider normally. Category text remains visible even without landing page support. Category should not become a dead link.

## Layout behavior

* Mobile portrait: single-column stack
* Mobile landscape: actions remain above fold
* Desktop: two-column body acceptable (left = content, right = hours/map/actions)

## Logged-in owner viewing own profile

Add lightweight edit affordances:

* Edit business info
* Update hours
* Upload photos
* Reverify listing

Do not expose admin terminology. Edit affordances should appear inline near each section, not in a separate dashboard-first flow.

---

# §10 Copy bank

| Context              | Copy                                                                             |
| -------------------- | -------------------------------------------------------------------------------- |
| Verified badge       | Verified business                                                                |
| Sponsored label area | Render via disclosure_renderer with regime=provider_profile                      |
| Fresh verification   | Last verified May 2, 2026                                                        |
| Aging verification   | Verification may be outdated                                                     |
| Stale verification   | Business information may have changed                                            |
| Missing description  | No business description has been added yet.                                      |
| Claim CTA            | This your business? Claim this listing and manage the information customers see. |
| Upgrade CTA          | Upgrade to Verified Presence                                                     |
| Ask Hava CTA         | Ask Hava about this business                                                     |
| Missing photos       | No business photos available yet                                                 |
| Imported listing     | Imported listing — not recently verified                                         |
| Source attribution   | Business information provided by owner and public sources                        |
| Empty hours          | Hours not available                                                              |
| Review summary       | 4.6 ★ (213 Google reviews)                                                       |

---

# §11 Open questions for Casey to resolve

1. Should free-tier providers be allowed to show Google review snippets, or should snippets be reserved for verified/sponsored listings?
2. Should "Ask Hava" open a side-sheet/modal chat, or navigate to the dedicated chat route with a prefilled query?
3. Should providers be allowed to upload logos separately from photos, or should logos simply be treated as another image type?
4. Should the page display the full street address for all home-service businesses, or should some categories support "service area only" visibility?
5. Should sponsored providers be allowed to pin a preferred hero image, or should hero ordering remain automatic?
6. Should owner-managed providers be able to temporarily mark themselves "closed today" or "holiday hours" without editing the full schedule?
7. Do you want the "featured" editorial flag surfaced visually on the page, or used only internally/ranking-side?
8. Should "years in business" become a first-class Provider field instead of living inside `attributes`?
