# Lake Havasu — Scraper → Site Data Contract (v0.1 draft)

**Purpose:** Define every type of information the scraper will produce and exactly
where it lands in the existing `havasu-chat` schema, so the site can hold and
format all of it cleanly. This is the "contract" OpenClaw fills.

**Core principle:** Everything scraped lands in a **pending / staging** state with
**source provenance**, and only goes live after a review step. Nothing scraped
auto-publishes.

---

## Pipeline recap

```
OpenClaw (VPS): schedule → fetch (Oxylabs) → extract (cheap model) → JSON
        → POST to havasu-chat ingest endpoint → staging
        → Claude review (dedupe / clean / decide) → publish to live tables
```

- **One-off / dated happenings** → `Event`
- **Ongoing venue deals** (happy hour, daily specials) → `Offering` + `Schedule` on the venue `Entity`
- **Recurring community happenings** (weekly trivia, Friday live music) → recurring `Event` (rrule) linked to its venue
- **Community praise/complaints (Orchids & Onions)** → NEW `community_mentions` model

---

## 1. Events  →  `events` table (already exists)

The events table is already scrape-ready (`source`, `status`, `verified`,
`scraped_at`, `admin_review_by`, full recurrence). Scraper output per event:

| Field | Required | Notes |
|---|---|---|
| `title` | yes | |
| `date` | yes | start date |
| `end_date` | no | multi-day events |
| `start_time` | yes | |
| `end_time` | no | |
| `location_name` | yes | venue name as posted |
| `description` | yes | |
| `event_url` | yes | link (FB event, Eventbrite, site…) |
| `source_url` | yes (scraped) | the FB post/page it came from |
| `contact_name` / `contact_phone` | no | if present |
| `tags` | no | e.g. ["live music","family"] |
| `is_recurring` + `rrule` | if recurring | RFC-5545 rule |
| `entity_id` | resolve | link to the venue Entity if matched |

**Ingest defaults for scraped events:** `source = "facebook:<group>"`,
`status = "pending"`, `verified = false`, `scraped_at = now`. Review step flips
to `status = "live"` / `verified = true`.

---

## 2. Venues / Businesses  →  `entities` (+ satellites, already exist)

Usually the scraper **resolves/links** to an existing Entity rather than creating
one. New-venue discovery is a separate, slower flow (needs human confirm).

Entity satellites available to fill: `Location` (address, city, state, zip,
lat/lng, google_place_id), `Hours` (weekly), `ContactPoint` (phone/email/web/social),
`Category` (taxonomy), `Feature` flags, `Photo`. Every scraped fact should write a
`SourceEvidence` row (field_path, source_type, source_url, verified_at).

---

## 3. Deals — Happy Hours & Specials  →  `Offering` + `Schedule` on the venue Entity

A deal is **not** an event. It is:

- **`Offering`**: `name` (e.g. "Happy Hour"), `description` ("$5 wells, ½-price apps"),
  `price_text`, optional `price_min_cents`/`price_max_cents`, `url`.
- **`Schedule`** (attached to same Entity): `schedule_type = "happy_hour"` (or
  `"special"`), `days_of_week`, `start_time`, `end_time`, optional `recurrence_rule`.

This lets the site show the deal on the venue page **and** in a deals feed, and the
chat can answer "where's happy hour right now?"

---

## 4. Community Mentions — Orchids & Onions  →  NEW `community_mentions` model

No current table fits (your `PeerRecommendation` requires a registered site user).
Proposed new table:

| Column | Notes |
|---|---|
| `id` | uuid |
| `entity_id` | FK → entities (the business). Nullable while unmatched |
| `raw_business_name` | text; what the post named, before matching |
| `sentiment` | `"orchid"` (praise) or `"onion"` (complaint) |
| `summary` | cleaned, **community-attributed** summary — not a verbatim repost |
| `raw_excerpt` | original text; **internal only**, never displayed |
| `source_group` | which FB group |
| `source_url` | link to the post |
| `posted_at` | when it was posted |
| `author_handle` | stored internally, **not displayed** |
| `visibility` | `"public"` (orchids only) or `"internal"` (all onions) |
| `status` | `"pending"` / `"published"` / `"rejected"` |
| `created_at`, `reviewed_at`, `reviewed_by` | moderation trail |

**Behavior:**
- **Orchids:** ingest → `pending`. After review → `visibility = public`,
  `status = published`. Shown as praise on the business's page, and eligible for an
  **"Orchid of the Day"** homepage highlight.
- **Onions:** **always `visibility = internal`, never published.** Used only as a
  private quality/sentiment signal in an admin view. (Your explicit choice.)
- Summaries attribute to "the community," link back to source, and never repost
  individuals verbatim. Businesses can claim their page and respond.

> Note: republishing named complaints carries real defamation/privacy risk — hence
> onions stay internal. (Not legal advice.)

---

## 5. "Ask instead of scroll"

Once events + deals + orchids are in the DB, your existing **chat/concierge** layer
answers "what's going on this weekend?" or "any good happy hours tonight?" — no new
modeling needed, it reads the same tables.

---

## Open build items (not done yet)

1. **New `community_mentions` table** → needs a model + Alembic migration.
2. **Ingest endpoint(s)** for OpenClaw to POST staged records (events already have
   `POST /events`; deals + mentions need ingest paths).
3. **Review step** (Claude) that promotes pending → live and routes onions to internal.
4. **"Orchid of the Day"** homepage component.
5. Confirm OpenClaw can produce this JSON shape (next: interview OpenClaw).
