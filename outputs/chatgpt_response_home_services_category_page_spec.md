# Home Services Category Landing Page — UX/Copy Spec

> **Origin:** ChatGPT-drafted 2026-05-13 in response to `outputs/chatgpt_prompt_home_services_category_page.md`. Saved verbatim for the implementation lane reference. Cowork primary will polish into `outputs/cursor_brief_home_services_category_page.md` after Casey resolves the 2 outstanding §11 questions (the other 6 are primary-resolved with notes inline). Implementation lane is sequential — dispatch only after the Provider profile page lane (`/provider/<slug>`) has landed and been committed, since category cards link to `/provider/<slug>`.

---

# §1 Page goal

The Home Services category page should be measurably better than Google for "plumber Lake Havasu" by being faster to scan, more locally focused, and clearer about which businesses are verified. It is the list view above individual Provider profile pages. The page should help a local resident or visitor quickly narrow down plumbers, HVAC companies, pool service, electricians, landscapers, and related providers in Lake Havasu City. It should also make the sponsor model visible without making the page feel like an ad wall.

---

# §2 Page anatomy

## 1. Page header

Contains:

* Page title: `Home Services in Lake Havasu City`
* Provider count
* Freshness signal
* Ask Hava link

Purpose: Set the category, reassure users this is local-only, and give them a fast chat path if browsing is not enough.

Example:

```
18 home service providers in Lake Havasu City
Verified listings show the last time business info was checked.
```

## 2. Sub-trade filter chips

Contains:

* All
* Plumbing
* HVAC
* Pool Service
* Electrical
* Landscaping
* Other detected sub-trades from `attributes.sub_trades`

Purpose: Let users narrow the page without search.

Order:

1. All
2. Emergency Service
3. Plumbing
4. HVAC
5. Pool Service
6. Electrical
7. Landscaping
8. Remaining sub-trades alphabetically

## 3. Sort bar

Contains:

* Default
* Most verified
* Open now
* Closest

Purpose: Support common local intent without overbuilding.

For V1: Closest is visible but disabled unless location support exists.

## 4. Sponsor slot

Contains:

* One Category Visibility sponsor card
* Disclosure label rendered via `disclosure_renderer` with `regime=category_landing`
* Sponsor provider details
* Actions

Purpose: This is the paid category placement, but it must be clearly labeled and separated from organic results.

Position: Immediately below filters/sort and above organic list.

## 5. Organic list

Contains:

* Provider cards in resolved sort order
* Verified Presence badges where applicable
* Action buttons
* Click-through to `/provider/<slug>`

Purpose: Main directory surface.

## 6. Pagination

Use pagination for V1.

Reason: It is easier to reason about, easier to debug, and avoids hiding footer/context content behind endless scrolling.

Default:

* 20 providers per page
* Hide pagination if providers <= 20

## 7. About Home Services footer block

Contains:

* Short local-context paragraph
* Plain-language safety note
* No sales pitch

Purpose: Adds local usefulness and SEO value without bloating the top of the page.

---

# §3 Provider card anatomy

## Card thumbnail

Priority:

1. `attributes.hero_pin_photo_url`
2. `google_photo_refs[0]`
3. neutral placeholder

Behavior:

* Small thumbnail on mobile
* Larger left-side thumbnail on desktop
* Do not use generic stock images

## Header line

Contains:

* `provider_name`
* verified badge if `verified=true`
* Hava's pick badge if `featured=true`
* rating if present

Example:

```
ACME Plumbing · Verified · 4.6 ★ (213)
```

If not verified:

```
ACME Plumbing · 4.6 ★ (213)
```

## Sub-line

Contains:

* top 2–3 `attributes.sub_trades`
* `Emergency Service` if true
* `Licensed` if true

Example:

```
Plumbing · Drain Cleaning · Emergency Service
```

## Status row

Contains:

* Open/closed state from `hours_structured`
* phone availability
* service area or address cue

Examples:

* `Open now · Closes 5 PM`
* `Closed · Opens Monday 8 AM`
* `Serves Lake Havasu City and Parker`
* `Lake Havasu City`

If hours are missing:

* hide open/closed status
* do not guess

## Preview line

Use:

1. `description`
2. empty fallback hidden

Rules:

* 1–2 lines
* no generated filler
* no AI-written summaries

## Inline actions

Show:

1. Call
2. Directions
3. Ask Hava

Hide action if required data is missing, except Ask Hava.

Reason: The category page should be useful without forcing every user into a profile page.

## Tap behavior

Whole card opens `/provider/<slug>`. Action buttons intercept taps and perform their own action.

Reason: Mobile users expect the whole card to be tappable.

---

# §4 Sort and filter behavior

## Sort behavior table

| Sort          | Behavior                           | Tiebreaks                                                                                              |
| ------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Default       | Verified and useful listings first | verified tier, last verified recency, featured, rating, review count, alphabetical                     |
| Most verified | Strictly verified first            | `verified=true`, freshest `last_verified_at`, sponsored tier excluded from organic boost, alphabetical |
| Open now      | Currently open providers first     | verified, rating, alphabetical                                                                         |
| Closest       | Distance from user                 | requires geolocation                                                                                   |

## Default sort

Recommended order:

1. Verified providers
2. More recent `last_verified_at`
3. `featured=true`
4. Higher `google_rating`
5. Higher `google_review_count`
6. Alphabetical by `provider_name`

Sponsor is not part of this sort because it lives in the sponsor slot.

Justification: The page should reward current verified data without pretending rating is the only signal that matters.

## Most verified sort

Strict verified-first sort.

Order:

1. `verified=true`
2. `last_verified_at` newest first
3. `tier=verified` or `tier=sponsored`
4. alphabetical

Do not rank stale verified listings above fresher verified listings just because they are paid.

## Open-now-first sort

Use `hours_structured` and `America/Phoenix`.

Order:

1. Open now
2. Opening later today
3. Closed / unknown hours

Within each group:

* verified first
* freshest verification
* rating
* alphabetical

If `hours_structured` is missing:

* place in unknown group
* do not infer from free-text `hours`

## Closest sort

Phase 2.

V1 behavior:

* show disabled option: `Closest`
* helper text on tap/click: `Closest sort needs location access. Coming later.`

Do not request browser geolocation until the feature is actually wired.

## Sub-trade filter

Use single-select for V1.

URL format: `?sub_trade=plumbing`

Reason: Single-select is simpler, easier to debug, cleaner for SEO, and enough for launch.

Emergency Service should also be a single-select chip: `?sub_trade=emergency-service`

---

# §5 Sponsor slot

## Position

Place sponsor slot directly above the organic list, after filters and sort.

Reason: Users see it before organic results, but the filters still come first so the page remains useful.

## Disclosure

Use `disclosure_renderer` with `regime=category_landing`.

Do not manually write sponsor label text. The label must appear at the top of the sponsor card.

## Visual treatment

Sponsor card should be:

* same general card structure as organic listings
* slightly larger thumbnail
* clearly labeled
* not visually disguised as organic

Avoid:

* fake urgency
* countdowns
* "top rated" unless data supports it
* unlabeled paid placement

## Sponsor card content

Contains:

* provider name
* sponsor disclosure
* verified badge if verified
* `featured_description` if present
* top service chips
* rating if present
* Call / Directions / Ask Hava
* link to profile

Use `featured_description` only here, not in organic cards.

## No sponsor state

For logged-out end-users: render nothing.

For logged-in business owner: show small link below sort bar — `Sponsor this category`. Optional secondary text: `Category Visibility is $349/month.`

Do not show this to normal consumers.

---

# §6 Editorial copy block

## Heading

`About Home Services in Lake Havasu`

## Paragraph

Home services in Lake Havasu City are a little different than bigger-city directories. A lot of providers serve seasonal residents, rental homes, older properties, pool homes, and weekend emergencies. If you are comparing Lake Havasu City plumbers, HVAC companies, pool service, landscapers, or Mohave County electricians, start with verified business info, current hours, and whether they actually serve your part of town. For licensed trades, cross-check the contractor with the Arizona Registrar of Contractors before hiring. Emergency service is useful, but it is not always available after hours or on Sundays, so call before you assume.

---

# §7 Empty / sparse states

## Zero providers in category

Show: `No Home Services providers are listed yet.`

Secondary: `Check back soon or ask Hava for help finding local options.`

Show Ask Hava link.

## Filter returns zero results

Show: `No providers match this filter.`

Action: `Clear filters`

Reset URL to: `/category/home-services`

## Fewer than 3 providers

Still render available cards.

Hide:

* pagination
* "showing X of Y" language if it feels awkward

Keep editorial copy visible if at least one provider exists.

## Sparse provider cards

If a provider lacks phone, website, hours, photos, or rating:

* hide missing fields
* do not render disabled controls
* do not show placeholders except thumbnail placeholder

---

# §8 Mobile-first sizing

## Mobile portrait card

Approximate structure:

* 1 line provider name
* 1 line badges/rating
* 1 line sub-trades
* 1 line open/closed or service area
* 1–2 line preview
* 1 row actions

Target: scannable in 6–8 text lines plus thumbnail.

## Filter chips on narrow mobile

Use horizontal scroll.

Reason: It keeps filters visible without forcing a dropdown tap.

First chip should always be `All`.

## Sort bar on mobile

Use compact segmented control or dropdown.

Preferred V1: dropdown labeled `Sort: Default`.

Reason: Less horizontal clutter.

## Sponsor slot on mobile

Same structure as organic card, but with:

* disclosure label at top
* larger thumbnail if available
* slightly more text allowed from `featured_description`

Do not make it a full-width billboard.

## Desktop layout

Desktop may use:

* wider cards
* thumbnail left
* content center
* actions right

Filters and sort can sit on one line when space allows.

---

# §9 Chat handoff

Header includes inline link: `Ask Hava about Home Services`

Destination: `/chat?q=What%20home%20service%20providers%20are%20recommended%20in%20Lake%20Havasu%20City%3F`

Behavior:

* opens chat route
* preloads the query
* user can edit before sending if chat supports that

If chat prefill is not available yet:

* route to `/chat`
* preserve copy as-is

---

# §10 Copy bank

| Context                  | Copy                                                        |
| ------------------------ | ----------------------------------------------------------- |
| Page title               | Home Services in Lake Havasu City                           |
| Count line               | 18 home service providers in Lake Havasu City               |
| Freshness line           | Verified listings show when business info was last checked. |
| Ask Hava header link     | Ask Hava about Home Services                                |
| Filter reset             | Clear filters                                               |
| Zero category state      | No Home Services providers are listed yet.                  |
| Zero filter state        | No providers match this filter.                             |
| Open now                 | Open now                                                    |
| Closed                   | Closed                                                      |
| Unknown hours            | Hours not listed                                            |
| Sponsor owner link       | Sponsor this category                                       |
| Sponsor owner price note | Category Visibility is $349/month.                          |
| Sort default             | Default                                                     |
| Sort verified            | Most verified                                               |
| Sort open now            | Open now                                                    |
| Sort closest             | Closest                                                     |
| Closest disabled helper  | Closest sort needs location access. Coming later.           |
| Card CTA call            | Call                                                        |
| Card CTA directions      | Directions                                                  |
| Card CTA chat            | Ask Hava                                                    |
| Editorial heading        | About Home Services in Lake Havasu                          |

---

# §11 Open questions for Casey

> **Status (2026-05-13):** All 8 §11 questions LOCKED. Decisions taken by Cowork primary (Q1, Q2, Q5, Q6, Q7, Q8 — high confidence) and the operator (Q3, Q4 — real product calls). Spec body language above stays as-written; the locked answers below override any §11 phrasing that disagrees.
>
> 1. **Card-wide tap — LOCKED: YES.** Whole card opens `/provider/<slug>`; action buttons intercept their own taps. Mobile standard.
> 2. **Inline Call/Directions on organic cards — LOCKED: YES include.** Removing actions loses to Google for the highest-intent action. The page must be measurably better than Google's local results.
> 3. **Sponsor slot during filtered views — LOCKED: fixed at top of every filtered view.** Sponsor card always renders above the organic list regardless of active filter. Matches sponsor expectation (paid for Home Services category visibility, sees the slot on every Home Services view).
> 4. **Emergency Service as filter — LOCKED: single-select sub-trade chip** (position 2, after "All"). Single chip selected at a time; user filters to Plumbing OR Emergency, not both. V1 simplification; combined-filter toggle is Phase 2 territory.
> 5. **Google rating for free tier — LOCKED: YES show.** Matches profile-page tier-delta (Google snippets visible across all tiers). Suppression feels punitive and breaks the trustworthy-info promise.
> 6. **"Closest" sort visibility — LOCKED: show disabled with helper text.** Signals the feature is coming; better than silently hiding.
> 7. **Pagination — LOCKED: 20 per page.** Home Services V1 has ~18–30 providers expected; 20 means most users see everything on page 1. Revisit when categories grow past 50 providers.
> 8. **AZ ROC mention in editorial — LOCKED: keep current §6 copy** (universal mention conditioned on "for licensed trades"). Per-category editorial copy can diverge when other categories launch.

**Original §11 (retained for narrative continuity):**

1. Should card-wide tap be the V1 behavior, or should only the provider name/photo open the profile?
2. Should organic cards include Call and Directions, or should those actions only live on the provider profile page?
3. Should the sponsor slot stay fixed to the top even after filters are applied, or should it only show when the sponsor matches the active sub-trade?
4. Should Emergency Service be treated as a sub-trade filter, or should it become a separate toggle?
5. Should Google rating be shown for free providers, or only verified/sponsored providers?
6. Should "Closest" be hidden until geolocation exists instead of shown disabled?
7. Should pagination use 20 providers per page, or is 10 better for mobile launch?
8. Should the editorial footer mention AZ ROC every time, or only for licensed trade sub-filters like plumbing, HVAC, and electrical?
