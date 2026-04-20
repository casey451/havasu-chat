# Havasu Chat — Concierge Build Handoff

**Purpose:** Complete reference document for Claude Code. Read this in full before executing any phase. Every decision below is locked. Do not re-open decisions without explicit owner approval.

**Owner:** Casey
**Location scope:** Lake Havasu City, AZ — single city, no multi-city framework
**Live app (Track A):** `https://web-production-bbe17.up.railway.app`
**Repository:** `https://github.com/casey451/havasu-chat` (main branch, Railway auto-deploys)

---

## 0. How to Use This Document

1. Read the whole thing before starting any phase.
2. Phases execute in order. Do not skip ahead.
3. Owner will feed prompts per phase or sub-phase. Each prompt references section numbers in this doc.
4. Every phase has an exit criterion. Do not mark a phase complete unless the exit criterion is met and verified.
5. When in doubt, match the patterns already in Track A code rather than inventing new conventions.
6. If you discover a decision that is not locked in this doc, stop and ask. Do not invent.
7. Do not self-initiate phases. Messaging such as "ready for Phase X" (or similar) is only a **handshake** — it means the owner is ready to send the next phase prompt. It is **not** a signal to start building. Wait for an **explicit phase or sub-phase prompt** that cites the specific sections of this document before executing changes or writing implementation code.

---

## 1. Product Definition

### 1.1 What the app is

Havasu Chat is a conversational local concierge for Lake Havasu City, Arizona. One text box. Users ask it anything about what to do, where to go, who to call, what's happening. It answers in a local voice, makes recommendations when asked, and learns from the community — users can also contribute new events, programs, and businesses, or correct existing info, all through the same chat interface.

The database is a living thing. Community contributions are the primary source of truth. Seed data is scaffolding that gets overwritten as locals fill in real info. Every field has a provenance chain and a confidence state.

### 1.2 Who it's for

- **Locals** looking for things to do, reliable info on businesses, and a way to contribute local knowledge.
- **Visitors** to Lake Havasu City looking for a real-feeling concierge recommendation.
- **Event organizers** who want a frictionless way to post events without learning a form.
- **Casey (owner)** who moderates contributions, resolves contested fields, and maintains voice quality.

### 1.3 What the app is NOT (out of scope — do not build)

- Restaurants (no restaurant coverage at all — redirect politely)
- Real estate
- Weather integration
- Native mobile app (web only)
- Multi-city framework (Lake Havasu only)
- Review / tip / opinion contributions (facts only; opinions are a different moderation problem, deferred)
- SMS interface
- Push notifications
- Email newsletter
- Public contributor leaderboards
- Translation / multi-language
- Booking infrastructure
- Anything visual beyond the existing HTML frontend

### 1.4 Explicitly deferred (build the primitives, ship the features later)

The following are **not in scope for launch** but the data model and hooks must accommodate them without refactor:

- **Business owner accounts.** A provider `tier` field (`free` / `featured` / `premium`) exists from Phase 1 and is never referenced by response logic until post-launch.
- **Sponsored boosting.** Data model includes `sponsored_until` nullable date field. No boosting logic wired in.
- **Featured listing blurbs.** `featured_description` nullable text field on providers. Unused at launch.
- **Trusted local contributor status.** Contributor session/device tracking exists; tier classification does not.
- **Temporary daily overrides** (e.g., "closed today for family emergency"). Not built. Contested-state covers permanent corrections only.
- **Lead generation / per-referral fees.** Not in data model.
- **Per-user long-term memory across sessions.** Session memory exists within a session; cross-session memory does not.

---

## 1a. Architectural Vision — Community-Grown Knowledge Base

Havasu Chat is not a fixed-schema app with a pre-decided scope. It is a **community-grown local knowledge base** where the shape of the database emerges from what residents and visitors actually ask about and contribute.

### Four principles

1. **Seed is a starter kit, not the final shape.** The 25 providers, 98 programs, and 43 events loaded at launch are enough to make the app useful on day one. They are not the intended end state. The database grows from use.

2. **Growth is URL-backed user contributions.** When a user recommends a place, event, or service the app doesn't know about, the app asks for a URL — Google Business page, official website, venue page, or equivalent. That URL is the trust anchor: it's what distinguishes community knowledge from unverified claims. Structured data (name, address, phone, hours, category) is ingested from the URL rather than entered by hand.

3. **Categories emerge from use.** The operator does not pre-decide what Havasu Chat is "about." Categories are created when contributions accumulate demand for them. Restaurants, kayak rentals, live music, fishing guides — any of these may become categories if the community brings them with URL-backed evidence. The data model adapts to real demand rather than operator guesswork.

4. **Operator stays in the review loop early; automation grows with trust.** New contributions and new categories pass through operator review until patterns are established. Over time, high-confidence contribution paths (e.g. Google Business page → structured import → auto-admit) can be automated. Lower-confidence paths stay in review indefinitely.

### URL-evidence policy

- **Businesses and organizations:** URL required (Google Business, official website, or equivalent authoritative source).
- **Events:** URL preferred (venue page, ticket link, official announcement). Accepted without URL if contributor provides date, time, and location.
- **Tips, favorite spots, local knowledge without a natural URL:** accepted but flagged as "community tip — unverified" in provenance. Displayed differently from URL-backed entries so users can weigh them appropriately.
- All contributions pass through operator review until automation is trusted for that contribution type.

### What this changes about the rest of this handoff

- **§1.3 "What the app is NOT" list** (restaurants, real estate, weather, etc.) should now be read as **"not pre-seeded"** rather than **"permanently excluded."** Any of these may enter the knowledge base if users bring them with URL-backed evidence and operator approves. The exception is items excluded for architectural reasons (native mobile, SMS, multi-city), which remain out of scope.

- **Phase 4 (Intake)** is reframed: it is not just "let users add providers to existing categories." It is the **primary growth mechanism** for the app, and its design centers on URL-backed ingestion (likely via Google Places API or equivalent) with category discovery and operator review.

- **Phase 5 (Corrections)** extends naturally: users can correct field values and also challenge entries with counter-URLs. Contested-state (locked decision #3, field-stakes split) applies to URL-backed disputes.

- **Phase 7 (Tier 2 vector FAQ)** becomes more valuable as the knowledge base grows, since it can surface semantically similar community contributions.

- **Voice decision #1** (community-credit provenance in foreground) is the operating philosophy of the whole app under this vision, not just a tone preference. "This is what your neighbors say, with receipts" is the value proposition. The URL is the receipt.

### What this does NOT change

- Phase 3.2 and 3.2.1 as currently shipped are correct and stay.
- The seven locked decisions stay.
- Phase 3.3 (end-to-end ask-mode tests) proceeds as planned.
- This vision informs Phase 4+ design; it is not a Phase 3 change.

---

## 2. The Seven Locked Decisions

These shape every template, prompt, and rule downstream. Do not deviate.

### 2.1 Voice stance: Option B — In the foreground

The concierge openly credits the community. Provenance is visible in answers. Every interaction invites contribution.

**Example:** *"A local told me Altitude opens at 10 — confirmed last week. Let me know if that's wrong."*

Not: *"Altitude opens at 10."* (too opaque, no trust-building)

### 2.2 Recommendation opinionatedness: Option 2 — Light opinion default, Option 3 when explicitly asked

**Default voice (Option 2):** Lists options, flags the standout.
*"Saturday has a few options — the BMX race at 6 is usually the liveliest. Farmers market in the morning if you want something chill, or Altitude's open till 9."*

**When user explicitly asks for a recommendation** ("what should I do," "pick one," "what's worth it," "best X"): lean into Option 3 energy.
*"Go to the BMX race Saturday at 6 — it's the one thing locals actually show up for."*

System prompt handles the split. Both voices preserve the community-credit stance from 2.1.

### 2.3 Contested-state lead value: Option C — Split by field stakes

**Low-stakes fields** (newer value leads):
- `hours`, `opening_time`, `closing_time`
- `cost`, `cost_description`
- `schedule_days`, `schedule_start_time`, `schedule_end_time`, `schedule_note`
- `description`, `notes`

**High-stakes fields** (NEVER auto-update; always route straight to admin review, established value leads in chat until approved):
- `phone`, `contact_phone`
- `email`, `contact_email`
- `address`, `location_address`
- `age_min`, `age_max`
- `provider_name`, `title` (for providers/programs — event titles can be low-stakes)
- `website`, `contact_url`

**Phrasing during contested state:**

Low-stakes:
*"Opens at 7 — we were recently told it moved from 6. Let me know if that's wrong."*

High-stakes (pending admin review):
*"My info says the phone is 928-555-0100. Someone recently reported a different number — I'll get that confirmed before updating."*

### 2.4 Build pace: Option C — ~20 hours/week, phase structure matches part-time

Phases are broken into sub-phases that end in committable, testable states. Sessions are typically 3–6 hours of focused work. The doc includes enough session-boundary context that work can resume after a gap without rereading everything.

### 2.5 Intake slot-parsing model: Option A — keep `gpt-4.1-mini`

Structured extraction (parsing a messy submission into schema slots) uses `gpt-4.1-mini` via OpenAI. Track A's `app/core/extraction.py` already does this for events. Extend it to programs and businesses. Do NOT rewrite to Claude.

Claude Haiku is used **only for Tier 3 natural-language recommendations**. Clean separation by job type.

### 2.6 Frontend scope: Option A — extend the existing single-file HTML

`app/static/index.html` stays vanilla HTML/CSS/JS. No framework, no build step. Add new UI elements (confirm/dispute buttons, feedback thumbs, onboarding, intake state display) as incremental edits. Do NOT rewrite to React/Vue/Svelte.

### 2.7 Owner tasks are explicitly out of Claude Code's lane

The following are **owner tasks**. Do NOT attempt them in code. Do NOT simulate them. Flag them when they come up and let the owner do them:

- Seed data verification (calling businesses to confirm hours/prices/addresses)
- Voice audit judgment calls (running the audit prompt is fine; deciding if a response "sounds right" is the owner's call)
- Writing the 20–30 local-voice editorial content pieces (opinions must come from the owner)
- Contested-state resolutions when crowd signal is ambiguous
- Terms of service and takedown policy drafting (Claude Code may produce a first draft if asked, but owner owns the final text and legal review)
- Approving admin submissions (ongoing operational work)
- Cultivating power contributors (community management, not code)

---

## 3. Architecture

### 3.1 Tier distribution targets

| Tier | Target % | Method | Cost | Latency |
|------|----------|--------|------|---------|
| Tier 1 | ~55% | Regex + templates | Free | <50ms |
| Tier 2 | ~25% | Structured handlers | Free (or cheap extraction calls) | <100ms ex. extraction |
| Tier 3 | ~20% | Claude Haiku 4.5 | Paid | 1–3s |

If Tier 3 rate creeps above 25% sustained, add Tier 2 handlers. If Tier 1 drops below 50%, add templates.

### 3.2 Query flow

```
User query
    ↓
Normalize
    ↓
Two-stage intent classifier
    ├─ Stage 1: mode → ask / contribute / correct / chat
    └─ Stage 2: sub-intent within mode
    ↓
Entity match (provider/program) — all modes that need it
    ↓
Route to mode handler
    ├─ ask mode → Tier 1 → Tier 2 → Tier 3
    ├─ contribute mode → intake state machine (+ gpt-4.1-mini for slot parsing)
    ├─ correct mode → correction handler → contested-state write or admin queue
    └─ chat mode → Tier 1 templates (greetings, off-topic redirects)
    ↓
Response + analytics log
```

Every response logs `tier_used`, `intent`, `entity`, `latency_ms`, `mode` to the `chat_logs` table.

### 3.3 Tier 1 — Template responses (ask mode only)

Single-intent, single-entity queries with direct data lookup.

**Sub-intents:**
- `DATE_LOOKUP`, `TIME_LOOKUP`, `LOCATION_LOOKUP`, `COST_LOOKUP`, `PHONE_LOOKUP`, `HOURS_LOOKUP`, `WEBSITE_LOOKUP`, `AGE_LOOKUP`

**Tier 1 succeeds only when all are true:**
1. Regex intent classifier returns one intent with confidence.
2. Entity extracted and matches a provider/program in the catalog.
3. The slot for that intent is populated (not null, not `CONTACT_FOR_PRICING`).
4. Field is not in contested state — OR — is in contested state and a dual-answer template variant exists.

If any criterion fails → escalate to Tier 2.

**Cost lookup special case:** If `cost` is `CONTACT_FOR_PRICING`, return the "call for pricing" template variant with the business phone number, not a null response.

**Contested state handling:** Before rendering a Tier 1 response, check `field_history` for the field. If contested, use the dual-answer variant per section 2.3.

### 3.4 Tier 2 — Structured fallback (ask mode)

Queries that need data + logic but not reasoning.

**Handlers:**
- `handle_next_occurrence(entity_id)` — "when's the next bmx race"
- `handle_list_by_category(category, filters)` — "what soccer leagues are in havasu"
- `handle_multi_intent(intents, entity_id)` — "when and where is bmx"
- `handle_open_now(entity_id)` — "is altitude open right now"
- `handle_age_scan(age, filters)` — "do any gyms take 3 year olds"
- `handle_disambiguation(candidates)` — "swim lessons" with 2+ matching providers

Each returns `HandlerResult(success: bool, response: str | None)`. On failure, escalate to Tier 3.

### 3.5 Tier 3 — LLM recommendations (ask mode)

**Model:** `claude-haiku-4-5-20251001`
**Max tokens:** 150 (enforces 1–3 sentence voice)
**Temperature:** 0.3
**System prompt:** `prompts/system_prompt.txt`
**Context block:** trimmed, <2000 tokens, built by `context_builder.py`

**Tier 3 handles:**
- Open-ended queries ("what's going on this weekend")
- Recommendations ("something for my kid after school")
- Comparisons ("sonics or flips for fun for shy kid")
- Multi-step planning ("we're visiting Saturday, plan us a day")
- Anything Tier 1 and Tier 2 couldn't answer

Tier 3 is the **recommendation engine**, not a safety net. The 55/25/20 split is not about avoiding the LLM — it's about using it where reasoning matters.

### 3.6 Contribute mode (intake state machine)

Three contribution types: new event, new program, new business.

**Flow:**
1. Intent classifier identifies contribute mode, sub-classifies type.
2. Entity matcher checks if the thing being contributed already exists (duplicate detection).
3. If duplicate suspected: ask user to confirm ("sounds like the car show at the channel Saturday — already got that one. Anything you wanted to update?").
4. Otherwise: pass user's input to `gpt-4.1-mini` (via existing `extraction.py` pattern) to extract slots in one shot.
5. State machine identifies missing required slots, asks for most-important-missing in a conversational way.
6. User can pause mid-intake to ask a question; session state persists.
7. When all required slots filled: write record with `pending_review = true`, `admin_review_by = now + 72 hours`, response is "got it, pile — anything else?" (voice per section 2.1).

**Required slots per contribution type:** see section 5.3.

### 3.7 Correct mode (contested state flow)

1. Intent classifier identifies correct mode.
2. Entity matcher identifies the entity (provider/program/event).
3. Field identifier (light LLM call or regex) determines which field is being corrected.
4. Proposed value extracted and sanity-checked (see section 5.5).
5. Field stakes checked:
   - **Low-stakes:** write to `field_history` with `state = 'contested'`, newer value leads in chat responses for resolution window.
   - **High-stakes:** write to `field_history` with `state = 'pending_admin'`, established value continues to lead until admin approves.
6. Rate limits applied (see section 5.4).
7. Resolution:
   - Confirmations/disputes accumulate during window.
   - Low-stakes auto-resolve after window expires (promote proposed if no disputes; revert if disputes exist).
   - High-stakes ONLY resolve via admin action.

### 3.8 Chat mode

Greetings, small talk, off-topic queries. All handled by Tier 1 templates. Out-of-scope queries (restaurants, real estate, weather) get a polite redirect template. Some off-topic queries are logged as "not yet covered" for later review.

### 3.9 Voice consistency

All tiers and all modes produce responses that are:

- 1–3 sentences (max 150 tokens on LLM)
- Contractions always ("it's", "they're", "what's")
- No filler ("Certainly", "Absolutely", "I'd be happy to")
- No follow-up questions unless the turn is intake or correction (where a question is the explicit next step)
- Direct answer, then stop
- Community-credit provenance when relevant (section 2.1)
- Light opinion default, stronger when asked (section 2.2)

Users must not be able to tell which tier answered.

### 3.10 Analytics schema

Every response logs to `chat_logs`:

```
id (uuid)
timestamp
session_id
user_hash (device/session-based, not auth)
query_text_hashed
normalized_query
mode (ask / contribute / correct / chat)
sub_intent (nullable)
entity_matched (nullable)
tier_used (1 / 2 / 3 / intake / correction / chat)
latency_ms
response_text
llm_tokens_used (nullable, Tier 3 only)
feedback_signal (nullable: positive / negative / null — set via thumbs UI)
```

### 3.11 Failure handling

- **Tier 1 fails:** fall through to Tier 2 silently. No "I didn't understand."
- **Tier 2 fails:** fall through to Tier 3 silently.
- **Tier 3 fails:** return graceful error: *"Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry."* Log error, alert admin if error rate exceeds threshold.
- **Intake fails mid-flow:** preserve partial state in session, tell user "hang on, let me regroup — [last question]", log error.
- **Correction fails sanity check:** politely reject with reason. "Can't update opening time to 27pm — want to try that again?"

---

## 4. Data Model

All tables in PostgreSQL (Railway production). SQLite for local dev. Migrations via Alembic.

### 4.1 `providers` (new — Phase 1 creates fresh)

Greenfield table. No existing `providers` table in the repo.

```
id                      String  NOT NULL PRIMARY KEY    -- match programs.id convention
provider_name           String  NOT NULL
category                String  NOT NULL                 -- enum: see 4.6
address                 String  nullable
phone                   String  nullable
email                   String  nullable
website                 String  nullable
facebook                String  nullable
hours                   Text    nullable                 -- freeform for now
description             Text    nullable
tier                    String  NOT NULL default 'free'  -- 'free' | 'featured' | 'premium'
sponsored_until         DateTime nullable                -- post-launch, always null at launch
featured_description    Text    nullable                 -- post-launch
draft                   Boolean NOT NULL default false
verified                Boolean NOT NULL default false   -- matches programs.verified convention
is_active               Boolean NOT NULL default true    -- matches programs.is_active convention
pending_review          Boolean NOT NULL default false
admin_review_by         DateTime nullable
source                  String  NOT NULL default 'seed'  -- matches programs.source convention: 'seed' | 'admin' | 'user'
created_at              DateTime NOT NULL
updated_at              DateTime NOT NULL
```

**Conventions locked to match existing Track A patterns:**
- Primary keys are `String`, generated in application code (existing `programs.id` is `String`; use the same generator).
- Provenance/lifecycle fields (`source`, `verified`, `is_active`) use the same names and semantics as `programs` so downstream code can treat providers and programs consistently.

### 4.2 `programs` (exists — Phase 1 RECONCILES, does not create)

**Important:** `programs` already exists in the repo with migrations `c3a9e2f5b801_add_programs_table` and `d4b7e2f1c902_add_source_and_verified`. It has a full `Program` ORM model, `/programs` API router, admin tab, search helpers, entity matcher integration, schemas, seed scripts, and multiple test files depending on its current shape. Phase 1 does NOT create this table. Phase 1 **expands** it with new columns and adds a nullable `provider_id` FK. The existing `provider_name` column stays in place for now (expand/migrate/contract pattern — consumers migrate in later phases, `provider_name` is dropped later).

**Existing columns to PRESERVE as-is (do not drop, rename, or retype in Phase 1):**

```
id                      String  NOT NULL PRIMARY KEY
title                   String  NOT NULL
description             Text    NOT NULL
activity_category       String  NOT NULL
age_min                 Integer nullable
age_max                 Integer nullable
schedule_days           JSON    NOT NULL (list in app)
schedule_start_time     String(5) NOT NULL    -- current shape; Phase 1 does NOT relax this
schedule_end_time       String(5) NOT NULL    -- current shape; Phase 1 does NOT relax this
location_name           String  NOT NULL
provider_name           String                -- stays in place; new provider_id FK added alongside
cost                    String  NOT NULL       -- current shape; Phase 1 does NOT retype this
source                  String  NOT NULL      -- provenance: admin / scraped / user (keep; valuable)
verified                Boolean NOT NULL default false  -- keep; replaces planned needs_verification
is_active               Boolean NOT NULL      -- soft-delete; keep
tags                    JSON    NOT NULL      -- AI-generated tags; keep (useful for context builder)
embedding               JSON    nullable      -- semantic search embedding; keep
created_at              DateTime NOT NULL
updated_at              DateTime NOT NULL
```

**New columns to ADD in Phase 1 (all nullable or with safe defaults so existing rows remain valid):**

```
provider_id             String  foreign key → providers.id  nullable
show_pricing_cta        Boolean NOT NULL default false
cost_description        Text    nullable
schedule_note           Text    nullable      -- freeform, "⚠️ VERIFY" OK
draft                   Boolean NOT NULL default false
pending_review          Boolean NOT NULL default false
admin_review_by         DateTime nullable
```

**Note:** `contact_phone`, `contact_email`, and `contact_url` already exist on `programs` from migration `c3a9e2f5b801`. They are not re-added in Phase 1.

**Column decisions vs. earlier handoff draft:**
- `needs_verification` from the earlier draft is **NOT added**. Use existing `verified` field instead (inverted logic, same information).
- `schedule_start_time` / `schedule_end_time` stay NOT NULL in Phase 1. The handoff originally specified nullable; we defer that change to avoid breaking existing data and consumers. Revisit in a later sub-phase if genuinely needed.
- `cost` stays String in Phase 1. Retyping to numeric would require retrofitting every consumer. Deferred. The new `show_pricing_cta` + `cost_description` columns give us what we actually need for the concierge without touching `cost`.
- `age_min` / `age_max` stay Integer in Phase 1 (the handoff originally specified numeric to support fractional ages like 0.5 for 6-month-olds). Deferred; age precision isn't a launch blocker.

**After Phase 1, `programs` is a superset of its current shape plus concierge fields. No existing code breaks. No existing data is lost. Phase 1 is additive.**

### 4.3 `events` (extend existing — Phase 1 adds provider_id only)

Existing Track A Event table stays fully intact. Phase 1 adds a single nullable column:

```
provider_id             String  foreign key → providers.id  nullable
```

All other existing columns stay as-is. Do not rename, retype, or drop any existing Event column. Do not touch the existing event seed data.

Backfill `provider_id` on existing events where the event's `source` or content matches a seeded provider name. Unmatched events stay `provider_id = null` (valid — one-off community events don't need a provider).

### 4.4 `field_history` (new — Phase 1 creates schema, wired in Phase 5)

Greenfield table. Audit log and contested-state source of truth. Schema is created in Phase 1 and seeded with baseline `established` rows; correction flow writes to it in Phase 5.

```
id                      String  NOT NULL PRIMARY KEY
entity_type             String  NOT NULL         -- 'provider' | 'program' | 'event'
entity_id               String  NOT NULL
field_name              String  NOT NULL
old_value               Text    nullable         -- JSON-serialized if non-scalar
new_value               Text    nullable         -- JSON-serialized if non-scalar
source                  String  NOT NULL         -- 'seed' | 'user' | 'admin' | 'owner'
submitted_by_session    String  nullable
submitted_at            DateTime NOT NULL
state                   String  NOT NULL         -- 'established' | 'contested' | 'pending_admin' | 'resolved'
confirmations           Integer NOT NULL default 0
disputes                Integer NOT NULL default 0
resolution_deadline     DateTime nullable
resolved_at             DateTime nullable
resolved_value          Text    nullable
resolution_source       String  nullable         -- 'auto' | 'admin' | 'expired'
```

Every change to a tracked field on providers/programs/events writes a row here. Current effective value is computed from the most recent `state = 'established'` or `state = 'resolved'` row, with contested/pending rows overlaying per section 3.7 rules.

Indexes: `(entity_type, entity_id, field_name)` for fast lookup; `(state, resolution_deadline)` for the background resolution task.

### 4.5 `chat_logs` (extend existing — Phase 6 migration adds feedback_signal)

Existing table stays. Add:

```
mode                    text nullable          -- Phase 2 adds
sub_intent              text nullable          -- Phase 2 adds
feedback_signal         text nullable          -- Phase 6 adds: 'positive' | 'negative' | null
```

### 4.6 Category enum values

Used on both `providers.category` and `programs.activity_category`:

```
golf, fitness, sports, swim, martial_arts, gymnastics, cheer, dance, theatre, art, summer_camp, bowling, trampoline, bmx, soccer, baseball, jiu_jitsu, tennis, parks_rec, other
```

Add new values only via migration. Do not silently accept freeform strings.

---

## 5. Build Plan

Phases execute in order. Each phase ends with a specific, verifiable exit criterion. If exit criterion fails, do not proceed to next phase.

### Phase 1 — Data Model Reconciliation & Extension (1–2 weeks, 20–30 hours)

**Goal:** Create `providers` and `field_history` fresh. Expand the existing `programs` table with concierge fields (additive only, no breaking changes). Extend `events` with a nullable `provider_id`. Seed providers, link programs and events to providers, establish baseline field_history rows.

**Key constraint:** Phase 1 is **additive only**. No existing column is dropped, renamed, or retyped. No existing Track A test breaks. No existing row is lost. The expand/migrate/contract pattern applies: Phase 1 expands, later phases migrate consumers, a much later sub-phase contracts.

**Sub-phases:**

**1.1 Schema migrations.**
- New migration creates `providers` table per Section 4.1.
- New migration creates `field_history` table per Section 4.4 with indexes.
- New migration expands `programs` with the added columns per Section 4.2 ("New columns to ADD"). All new columns are nullable or have safe defaults so existing rows remain valid. Do NOT touch existing `programs` columns.
- New migration adds `events.provider_id` nullable FK per Section 4.3. Do NOT touch existing `events` columns.
- Test up and down on clean SQLite DB. Test up on a SQLite DB pre-populated with existing Track A data (events + programs rows) to verify no data loss and all existing queries still work.
- Railway migration is an owner task — the prompt flags it but does not execute against production.

**1.2 SQLAlchemy models.**
- Add `Provider` and `FieldHistory` ORM models to `app/db/models.py`.
- Extend the existing `Program` model with the new columns (matching the Section 4.2 additions). Preserve every existing field and relationship. Add a nullable `provider_id` FK relationship to `Provider`.
- Extend the existing `Event` model with a nullable `provider_id` FK relationship to `Provider`.
- Do not modify any existing Program or Event field definitions.

**1.3 Provider seed script.**
- Create `app/db/seed_providers.py` (idempotent, parallel to existing `seed.py`). Parses the 25 businesses from `HAVASU_CHAT_MASTER.md` Section 9.
- Sets `draft = true` for Elite Cheer Athletics (per file's instructions).
- Sets `verified = false` for businesses the master file flags with ⚠️ VERIFY.
- Handles `CONTACT_FOR_PRICING` on provider-level pricing if applicable.
- Sets `source = 'seed'` on every row.
- Idempotent: re-running does not create duplicates. Uses provider_name as the dedupe key.
- Prints summary: providers created / skipped (already existed) / flagged (draft or unverified).

**1.4 Backfill provider_id on existing programs.**
- For each existing program row, attempt to match `provider_name` to a seeded provider's `provider_name`. On match, set `program.provider_id = provider.id`. Log matches and unmatched.
- `provider_name` stays untouched on the program row. Both fields coexist during Phases 1–4. This is the "expand" step of expand/migrate/contract. Consumers are migrated in later phases. `provider_name` is dropped in a much later sub-phase (not in Phase 1).
- Script is idempotent. Re-running updates existing provider_id values if the mapping changes.

**1.5 Extend program seed.**
- The existing program seed (`scripts/seed_from_havasu_instructions.py` per the inspection report) already loads programs. Phase 1 does NOT rewrite this seed.
- Add a follow-up step that runs AFTER provider seeding: re-populates `provider_id` on all program rows (1.4's backfill).
- Add a separate step that populates new concierge fields (`show_pricing_cta`, `cost_description`, `schedule_note`, `contact_phone`, `contact_email`, `contact_url`, `draft`, `pending_review`, `admin_review_by`) on existing program rows where the master file provides that data. Existing fields are not touched.

**1.6 Backfill provider_id on existing events.**
- For each seed event, attempt to match it to a provider (by content, title, or existing source tag). On match, set `event.provider_id`. Unmatched stay null. Community events will always be null — that's expected.
- Idempotent.

**1.7 Field history baseline.**
- For every provider, program, and event: write `field_history` rows for every tracked field with `source = 'seed'`, `state = 'established'`, `submitted_at = now`, `new_value = current field value`.
- This is the baseline for future corrections in Phase 5. Without it, the first user correction has no "established" row to compare against.
- Tracked fields per entity type are defined in `app/core/field_tracking.py`: providers track phone/email/address/hours/website; programs track cost/schedule_start_time/schedule_end_time/schedule_note/age_min/age_max/contact_phone; events track **`date`**, **`start_time`**, **`end_time`**, **`location_name`** (the Event ORM has no single `time` column and no `cost` column — baselines use the actual column names; see `field_tracking.py` docstring).
- Idempotent: re-running does not create duplicate rows for the same (entity_type, entity_id, field_name, state='established') combination.

**Exit criterion:**
- `alembic upgrade head` on a fresh SQLite DB succeeds.
- `alembic upgrade head` on a SQLite DB pre-populated with existing Track A data (events + existing programs rows) succeeds with zero data loss.
- All existing Track A tests still pass (172+ — whatever the current count is).
- Running provider seed + program re-seed + event backfill + field_history baseline produces: 25 providers (or 24 live + 1 draft), existing programs now have provider_id populated where possible, existing events now have provider_id populated where possible, field_history has baseline rows for every tracked field on every seeded entity.
- `app/main.py`, `app/admin/router.py`, `app/programs/router.py`, `app/core/program_search.py`, `app/chat/entity_matcher.py` all still work unchanged (verified by existing tests passing).
- Deploy to Railway (owner action) runs migration cleanly. Existing live app continues to function.

**Owner tasks in Phase 1:**
- Running `alembic upgrade head` on Railway production against live data (after verifying on staging/local).
- Running `SELECT COUNT(*) FROM programs;` on Railway to compare pre- and post-migration row counts for sanity.
- Spot-checking live app functionality after Railway migration.

---

### Phase 2 — Router + Two-Stage Intent Classifier (1–2 weeks, 20–30 hours)

**Goal:** New entry point that routes everything. Tier classifier with ask/contribute/correct/chat branching at the top level, sub-intents below.

**Sub-phases:**

**2.1 Intent classifier (Step 3 of original plan).** Create `app/chat/intent_classifier.py`. Two-stage:

```python
def classify(query: str) -> IntentResult:
    # Stage 1: mode
    mode = classify_mode(normalized_query)  # 'ask' | 'contribute' | 'correct' | 'chat'
    # Stage 2: sub-intent within mode
    sub_intent = classify_sub_intent(normalized_query, mode)
    confidence = <score>
    return IntentResult(mode, sub_intent, confidence)
```

Mode classification: regex + keyword heuristics. Patterns like "there's a [X] happening" / "just opened" / "adding [X]" suggest contribute. Patterns like "actually it's [X]" / "that's wrong" / "moved to" / "changed to" suggest correct. Everything else → ask unless it matches the chat-mode patterns (greetings, off-topic).

Sub-intent per mode:
- **ask:** DATE_LOOKUP / TIME_LOOKUP / LOCATION_LOOKUP / COST_LOOKUP / PHONE_LOOKUP / HOURS_LOOKUP / WEBSITE_LOOKUP / AGE_LOOKUP / LIST_BY_CATEGORY / NEXT_OCCURRENCE / OPEN_NOW / OPEN_ENDED
- **contribute:** NEW_EVENT / NEW_BUSINESS / NEW_PROGRAM
- **correct:** CORRECTION (field identified downstream)
- **chat:** GREETING / OUT_OF_SCOPE / SMALL_TALK

**2.2 Unified router.** Create `app/chat/unified_router.py` with `route(query, session) -> ChatResponse`. Wires: normalize → classify → entity match → route to mode handler. Placeholder mode handlers return a structured response indicating the classification result, so end-to-end works even before tiers are real.

**2.3 API endpoint.** Create `app/api/routes/chat.py` with `POST /chat` endpoint. Request: `{"query": str, "session_id": str | null}`. Response: `{"response": str, "mode": str, "sub_intent": str | null, "entity": str | null, "tier_used": str, "latency_ms": int}`. Rate-limited via slowapi. Old `POST /events` endpoint stays wired to Track A logic for now — do not deprecate yet.

**2.4 Tests.** `tests/test_intent_classifier.py` with ~80 fixture queries (20 per mode) asserting correct classification. `tests/test_unified_router.py` with ~30 queries asserting correct routing. Target: 90%+ accuracy on intent classification tests.

**Exit criterion:**
- 80 test queries classified correctly at ≥90% rate.
- `POST /chat` endpoint returns valid responses (even if placeholder) for all 4 modes.
- Existing `POST /events` endpoint and Track A tests still work.
- Classification results logged to `chat_logs` with `mode` and `sub_intent` populated.

---

### Phase 3 — Ask Mode: Tier 1 + Tier 3 (2–3 weeks, 30–50 hours)

**Goal:** Ship a working concierge for ask mode. Tier 1 for direct lookups, Tier 3 for everything else. Skip Tier 2 for now — adds later in Phase 7.

**Sub-phases:**

**3.1 Tier 1 template library.** Create `app/chat/tier1_templates.py`. Regex patterns per sub-intent. `render(intent, entity, data) -> str | None` returns None if any required slot is null or the field is in a state requiring Tier 3 escalation. Template variants per intent, selected round-robin or by query signal to avoid identical repeats. **All templates honor Section 2.1 voice (community-credit when relevant)** and Section 2.3 contested-state rules.

**3.2 System prompt.** Write `prompts/system_prompt.txt`. Must embody all of section 2.1, 2.2, 3.9. Include explicit instruction: when the user explicitly asks for a recommendation ("what should I do", "pick one", "best X", "worth it"), lean into stronger opinion (Option 3 energy). Otherwise, light opinion default (Option 2). Include a few-shot example block. Cap responses at 1–3 sentences. Community-credit provenance is a required element when the answer involves community-authored data.

**3.3 Context builder.** Create `app/chat/context_builder.py`. Given a query:
- Extract keywords
- Score providers: category match +3, name match +5, program title match +2
- Select top 10 providers (up to 2000 tokens)
- Include relevant events (dates within reasonable window of query date signal)
- For each provider: name, category, address, phone, hours, 2–3 relevant programs with age/schedule/cost
- Include field state annotations for contested fields so the LLM can phrase appropriately
- Reuse Track A's `app/core/search.py` as a retrieval primitive — wrap, don't rewrite

**3.4 Tier 3 LLM integration.** Create `app/chat/tier3_llm.py`. Uses the `anthropic` Python SDK. Add `anthropic` to `requirements.txt`. Add `ANTHROPIC_API_KEY` to Railway env vars (owner task — flag this). Model: `claude-haiku-4-5-20251001`. Max tokens: 150. Temperature: 0.3. On API error, return graceful fallback per section 3.11.

**3.5 Wire ask mode.** Update unified router's ask handler to try Tier 1 first, fall through to Tier 3 on failure. Tier 2 returns `success = False` always for now (stub).

**3.6 Tests.** 75 fixture queries in `tests/test_ask_mode.py` covering all Tier 1 sub-intents and a range of Tier 3 queries. Assert: correct tier used, non-empty response, response meets voice rules (length, no filler). Voice rule checks via assertion helpers — not a full audit yet.

**Exit criterion:**
- 75 test queries answered. Tier 1 handles direct lookups (target: ~55% of the 75). Tier 3 handles the rest.
- Manual voice spot-check: owner reads 20 random responses and confirms voice is consistent with 2.1 and 2.2.
- `/chat` endpoint serves real answers in production, logged correctly.
- Track A's 120-query regression battery still passes at or near its ~96% baseline (the new router may re-route some queries; acceptable if answers are equivalent or better).

---

### Phase 4 — Contribute Mode (2–3 weeks, 30–50 hours)

**Goal:** Schema-driven intake for events, programs, businesses. Duplicate detection. Admin review queue.

**Sub-phases:**

**4.1 Extend extraction for programs and businesses.** Generalize `app/core/extraction.py`. Add `extract_program(text) -> ProgramDraft` and `extract_business(text) -> ProviderDraft` following the same `client.responses.create` pattern using `gpt-4.1-mini` (per section 2.5). Extraction is one-shot: dump user text, model returns structured slots, missing slots come back null.

**4.2 Intake state machine.** Create `app/chat/intake.py`. Per-type state machines:

```python
class IntakeState:
    type: 'event' | 'program' | 'business'
    filled_slots: dict
    required_slots: list[str]   # per type
    last_question_asked: str | None
    session_id: str
```

Required slots per type:

- **event:** title, date, location, start_time (end_time optional), cost (0 if free), description (optional), contact (url or phone)
- **program:** title, provider (existing or new), activity_category, schedule (days + start_time), location_address, cost (or show_pricing_cta), description, contact_phone (optional), age_min (optional but strongly preferred)
- **business:** provider_name, category, address, phone, (at least one of: email / website / facebook), hours (freeform accepted)

On each user turn:
- Run extraction on whatever the user just said
- Merge new slots into filled_slots (user can correct prior slots)
- Pick most-important missing slot, ask for it using conversational template
- If all required slots filled, commit to DB with `pending_review = true`, `admin_review_by = now + 72h`, confirm to user per voice (Section 2.1)

**4.3 Duplicate detection.** Extend `app/core/dedupe.py`. Before committing an intake:
- Fuzzy name match via entity matcher (existing rapidfuzz setup)
- Date + location match for events
- Category + name match for providers
- If duplicate suspected, break out of intake flow: *"sounds like [existing thing] — already got that one. Anything you wanted to update about it?"* If user confirms it's the same, route to correction flow. If user insists it's different, commit with `needs_verification = true`.

**4.4 Session persistence for intake.** Extend Track A's in-memory session pattern. Intake state persists across turns. User can ask an unrelated question mid-intake; the chat answers it and returns to intake on the next relevant turn. If session is idle >30 minutes, intake state is cleared.

**4.5 Admin queue extension.** Extend `app/admin/router.py` with tabs for:
- Pending Events (existing, maybe reskin)
- Pending Programs (new)
- Pending Businesses (new)

Each tab: list, approve, reject, edit-before-approve. 72-hour auto-expiry on unreviewed items (reuse existing logic).

**4.6 Tests.** 20 intake test scenarios: one-shot messy dumps, piecemeal conversations, corrections mid-flow, interruptions with unrelated questions, duplicates, near-duplicates. Assert end state (DB row created correctly, or routed to correction, or flagged as duplicate).

**Exit criterion:**
- 20 test submissions complete successfully with correct end states.
- Admin panel shows all three pending queues with working approve/reject.
- Duplicate detection catches obvious duplicates (same name, same date for events; same name+address for businesses) without false positives on clearly-distinct items.
- Session interruption + resume works.

---

### Phase 5 — Correct Mode and Contested State (2–3 weeks, 30–50 hours)

**Goal:** Community corrections with dual-answer display. Rate limits. Admin resolution tooling. Feedback buttons in UI.

**Sub-phases:**

**5.1 Correction handler.** Create `app/chat/correction.py`. Flow per section 3.7:
- Identify entity
- Identify field being corrected (light LLM call acceptable here, or regex + keyword)
- Sanity-check proposed value (see 5.5)
- Classify field stakes per section 2.3
- Low-stakes: write to `field_history` with `state = 'contested'`, `resolution_deadline = now + 72h`
- High-stakes: write with `state = 'pending_admin'`, do not affect chat responses until admin resolves
- Apply rate limits (section 5.4)
- Respond per voice (Section 2.1): *"got it, noted — I'll flag this and watch for more confirmations"* for low-stakes; *"got it, I'll get that verified before updating"* for high-stakes.

**5.2 Contested-state rendering in Tier 1 and Tier 3.**
- Tier 1: when rendering a response for a field, check `field_history` for current state. If contested, use dual-answer template variant per 2.3.
- Tier 3: context builder includes field state annotations. System prompt instructs the model to phrase contested fields appropriately.

**5.3 Resolution logic.** Background task (reuse existing cleanup loop pattern) runs hourly:
- For each `state = 'contested'` row past `resolution_deadline`:
  - If disputes > confirmations: revert (mark resolved_value = old_value, state = 'resolved', resolution_source = 'auto', notify admin)
  - If confirmations ≥ disputes and confirmations >= 1: promote (mark resolved_value = new_value, state = 'resolved', resolution_source = 'auto')
  - If confirmations = 0 and disputes = 0: escalate to admin queue (state stays 'contested', add admin_flag = true)

**5.4 Rate limits.** Extend slowapi config:
- Max 3 corrections per session per hour
- Max 10 corrections per session per 7 days
- Max 3 corrections per field across all sessions per 24h (past that, freeze field, escalate to admin)

**5.5 Sanity checks per field type.**
- Time fields: valid 24h format, within 00:00–23:59
- Cost fields: non-negative number, not absurdly large (>$10,000)
- Phone: US format, 10 digits
- Email: basic RFC validation
- Address: non-empty, contains at least one digit and one alpha token
- Age: 0 ≤ age ≤ 99

Sanity failure → polite rejection, no DB write, no rate-limit hit.

**5.6 Confirm/dispute UI.** Extend `app/static/index.html`:
- When chat response includes a contested field, render two small inline buttons: "✓ correct" and "✗ wrong"
- Click posts to new endpoint `POST /chat/feedback` with `{field_history_id, signal: 'confirm' | 'dispute'}`
- Button state changes to "thanks, logged" after click
- No login required; rate-limited per session

**5.7 Admin resolution tooling.** Extend `app/admin/router.py`:
- New tab: Contested Fields
- List of active contested + pending_admin rows with old value, new value, confirmations, disputes, age, source
- One-tap approve / reject / edit-before-approve
- Batch actions for bulk approval of same-field patterns

**5.8 Tests.** 15 correction scenarios: low-stakes (hours, cost, schedule), high-stakes (phone, address, age), sanity failures, rate-limit hits, confirmation/dispute flow, auto-resolution, admin override.

**Exit criterion:**
- 15 test scenarios pass.
- Rate limits block abusive patterns without blocking legitimate contributors.
- Dual-answer template renders correctly for contested fields in chat responses.
- Admin panel shows contested queue and resolution works end-to-end.
- Auto-resolution background task runs and processes correctly.

---

### Phase 6 — Voice, Feedback, and Onboarding (1–2 weeks, 15–25 hours)

**Goal:** Polish. The phase that turns "working" into "good."

**Sub-phases:**

**6.1 Voice audit.** Create `prompts/voice_audit.txt` from the existing master file's voice audit prompt. Run the full Tier 1 template library through it. Run 30 sampled Tier 3 responses through it. Generate a report. **Fixing flagged items is owner task** (Claude Code can draft fixes, owner approves — per 2.7).

**6.2 Feedback signals.** Add thumbs up/down to Tier 3 recommendations in `app/static/index.html`. Posts to new endpoint `POST /chat/feedback` (reuse from 5.6). Writes to `chat_logs.feedback_signal`. Admin panel gets a new analytics view: feedback ratio per mode/sub-intent/over time.

**6.3 Onboarding first-turn.** On first session visit, chat greets and asks two quick-tap questions:
- "Visiting or local?" → `local` / `visiting`
- "Kids with you?" → `yes` / `no`

Stored in session state. Fed into context builder as user context for subsequent queries. If skipped, chat operates without that signal.

**6.4 Session memory.** Extend session state to capture:
- Age hints volunteered during conversation ("my 6-year-old")
- Location hints ("we're near the island bridge")
- Prior entities asked about (for natural follow-ups like "what time does it open" after asking about a place)

Context builder reads session state and injects into LLM context. Scope: within-session only, cleared after 30 min idle. No cross-session memory (per 1.4).

**6.5 Local-voice content. OWNER TASK.** Flag this in the phase completion note. Owner writes 20–30 pieces of editorial knowledge (favorite sunset spot, which market is better, when the BMX race is actually worth it, etc.). Content structure: each piece is a tagged blurb with keywords for retrieval. Stored in `app/data/local_voice.py` as a list of dicts with `keywords`, `text`, `category`. Context builder matches on keywords and injects relevant blurbs into Tier 3 context.

**Exit criterion:**
- Voice audit completed, all flagged items addressed or explicitly accepted by owner.
- Feedback thumbs live on Tier 3 responses, data flowing to `chat_logs`.
- Onboarding works for first-time visitors.
- Session memory improves context on multi-turn conversations (tested manually).
- Owner has drafted initial local_voice content (or flagged that they will do so before launch).

---

### Phase 7 — Tier 2 Handlers (1–2 weeks, 15–25 hours)

**Goal:** Pull common patterns out of Tier 3 into deterministic handlers. Reduces LLM cost and latency.

**Sub-phases:**

**7.1 Handler implementations.** Create `app/chat/tier2_handlers.py` with each handler from section 3.4. Each returns `HandlerResult(success, response)`. Pull only from DB. No LLM calls.

**7.2 Handler selection logic.** Update unified router's ask handler: try Tier 1, then iterate Tier 2 handlers based on sub-intent and query shape, then fall through to Tier 3.

**7.3 Tests.** 40 Tier 2 fixture queries asserting handler success and correct response shape.

**7.4 Distribution verification.** Run the 120-query regression battery + 75 Phase 3 queries + 40 new Tier 2 queries = 235 queries total. Measure tier distribution. Target: 55/25/20 ±10%.

**Exit criterion:**
- 40 new tests pass.
- Tier distribution within ±10% of target across the 235-query battery.
- Tier 3 cost/latency metrics show improvement vs. Phase 3 baseline.

---

### Phase 8 — Pre-Launch Hardening (1–2 weeks, 15–30 hours)

**Goal:** Ship-ready.

**Sub-phases:**

**8.1 Seed data verification. OWNER TASK.** Owner calls the 25 businesses to confirm hours, prices, addresses. Updates via admin panel or direct DB edits. Flag any unverifiable businesses as `draft = true`. Do not attempt this in code.

**8.2 Load testing.** Script or tool of choice. Target: `/chat` endpoint handles 50 concurrent requests at <3s p95 latency. If not, investigate.

**8.3 Error path testing.** Kill OpenAI API (mock), kill Anthropic API (mock), slow DB, entity matcher returns empty, intent classifier ambiguous. Every path returns something graceful per section 3.11.

**8.4 Admin runbook.** Draft `docs/admin_runbook.md` covering: what to do when submissions spike, contested fields pile up, spam patterns emerge, API outages happen. Claude Code can draft; owner reviews.

**8.5 Terms of service and takedown policy. OWNER TASK.** Owner drafts (Claude Code may produce a first draft if asked) and links in the app footer. Owner owns final text and should run past a lawyer if they are serious about this going public.

**8.6 Regression pass.** Full test suite runs clean. 120-query battery + new test suites all pass. Deploy to Railway staging (or main if no staging exists), spot-check live.

**8.7 Privacy review.** Confirm what's logged, for how long, under what key. Document in `docs/privacy.md`. Query text is hashed in `chat_logs` — do not log PII plaintext.

**Exit criterion:**
- Owner would be comfortable if 500 people used it tomorrow.
- All tests green.
- Admin runbook exists.
- ToS linked in app.
- Seed data verified.

---

## 6. File Structure (target end state)

```
havasu-chat/
├── app/
│   ├── main.py                         (extend: mount new chat endpoint)
│   ├── bootstrap_env.py                (existing, no change)
│   ├── admin/
│   │   ├── auth.py                     (existing, no change)
│   │   └── router.py                   (extend: providers/programs/contested tabs)
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── normalizer.py               (existing, no change — Phase 1 of original plan, done)
│   │   ├── entity_matcher.py           (extend: add provider+program match, not just event) [Phase 2]
│   │   ├── intent_classifier.py        NEW — Phase 2
│   │   ├── unified_router.py           NEW — Phase 2
│   │   ├── tier1_templates.py          (existing partial, complete in Phase 3)
│   │   ├── tier3_llm.py                NEW — Phase 3
│   │   ├── context_builder.py          NEW — Phase 3
│   │   ├── intake.py                   NEW — Phase 4
│   │   ├── correction.py               NEW — Phase 5
│   │   ├── tier2_handlers.py           NEW — Phase 7
│   │   ├── router.py                   (Track A legacy — keep, do not delete; extract retrieval helpers)
│   │   └── voice_rules.py              NEW — Phase 3, shared constants for templates
│   ├── api/
│   │   └── routes/
│   │       └── chat.py                 NEW — Phase 2, endpoint for POST /chat
│   ├── core/
│   │   ├── conversation_copy.py        (existing — extend with new templates as needed)
│   │   ├── dedupe.py                   (existing — extend in Phase 4)
│   │   ├── event_quality.py            (existing, no change)
│   │   ├── extraction.py               (existing — extend in Phase 4 for program+business extraction)
│   │   ├── intent.py                   (Track A legacy — keep; unified_router may call through)
│   │   ├── rate_limit.py               (existing — extend in Phase 5 for correction limits)
│   │   ├── search.py                   (existing — context_builder wraps this in Phase 3)
│   │   ├── search_log.py               (existing, no change)
│   │   ├── session.py                  (existing — extend in Phase 4 and Phase 6)
│   │   ├── slots.py                    (existing, no change)
│   │   └── venues.py                   (existing, no change)
│   ├── data/
│   │   └── local_voice.py              NEW — Phase 6, owner-authored content blurbs
│   ├── db/
│   │   ├── chat_logging.py             (existing — extend schema in Phase 2 and 6)
│   │   ├── database.py                 (existing, no change)
│   │   ├── models.py                   (extend: Provider, Program, FieldHistory in Phase 1)
│   │   ├── seed.py                     (existing — keep)
│   │   └── seed_providers.py           NEW — Phase 1
│   ├── schemas/
│   │   ├── chat.py                     (extend for new ChatResponse fields in Phase 2)
│   │   ├── event.py                    (existing, no change)
│   │   ├── program.py                  NEW — Phase 1
│   │   ├── provider.py                 NEW — Phase 1
│   │   └── feedback.py                 NEW — Phase 5/6
│   └── static/
│       └── index.html                  (extend in Phase 5 and 6 — no rewrite)
├── alembic/versions/
│   ├── <existing migrations>           (keep)
│   ├── <new: providers_programs_field_history>  — Phase 1
│   ├── <new: chat_logs_mode_sub_intent>         — Phase 2
│   └── <new: chat_logs_feedback_signal>         — Phase 6
├── prompts/
│   ├── system_prompt.txt               NEW — Phase 3
│   └── voice_audit.txt                 NEW — Phase 6
├── tests/
│   ├── <existing Track A tests>        (keep, must pass throughout)
│   ├── test_intent_classifier.py       NEW — Phase 2
│   ├── test_unified_router.py          NEW — Phase 2
│   ├── test_ask_mode.py                NEW — Phase 3
│   ├── test_intake.py                  NEW — Phase 4
│   ├── test_correction.py              NEW — Phase 5
│   └── test_tier2_handlers.py          NEW — Phase 7
├── docs/
│   ├── <existing docs>                 (keep)
│   ├── admin_runbook.md                NEW — Phase 8
│   └── privacy.md                      NEW — Phase 8
├── scripts/
│   ├── <existing scripts>              (keep)
│   └── battery_results.json            (update as regression battery evolves)
├── HAVASU_CHAT_CONCIERGE_HANDOFF.md    (this file — source of truth)
├── requirements.txt                    (add anthropic in Phase 3)
└── .env                                (add ANTHROPIC_API_KEY — owner task)
```

---

## 7. What to Reuse (Do Not Rewrite)

**Fully reusable:**
- `app/db/database.py`, `app/db/models.py` base (extend, don't replace)
- `app/admin/auth.py` and admin router framework
- `app/core/extraction.py` (extend for programs/businesses; keep gpt-4.1-mini)
- `app/core/dedupe.py` (extend for programs/businesses)
- `app/core/rate_limit.py`
- `app/chat/normalizer.py`
- `app/chat/entity_matcher.py` (extend entity scope; keep the rapidfuzz pattern)
- Alembic migration infrastructure
- Test infrastructure (pytest, 172 existing tests must pass)
- `scripts/run_query_battery.py` (quality gate)
- Deployment pipeline (Railway, Nixpacks, Procfile)

**Partially reusable — wrap, don't replace:**
- `app/chat/router.py` (Track A's router — extract `_run_search_core` as a retrieval service; new unified router calls into it)
- `app/core/intent.py` (Track A's intent — new classifier may wrap or supersede)
- `app/core/slots.py` (date range parsing, QUERY_SYNONYMS — feed these into context builder)
- `app/core/search.py` (context_builder in Phase 3 wraps this)
- `app/static/index.html` (extend only)

**Do not rewrite any of these unless the new feature genuinely cannot be built on top.** If you find yourself rewriting, stop and ask.

---

## 8. Voice Specification (locked)

Read this before writing any template, prompt, or LLM message.

### 8.1 Identity

The concierge is a knowledgeable local friend in Lake Havasu City. It knows the town, has opinions, is direct, and credits the community openly when its knowledge comes from them.

### 8.2 Hard rules

- **1–3 sentences.** No exceptions except multi-option lists (which should still be tight).
- **Contractions always.** "It's," "they're," "what's," "there's."
- **No filler.** Never start with "Certainly," "Absolutely," "Great question," "I'd be happy to," "Let me help you," "Sure thing."
- **No self-reference to being an AI.** Never say "as an AI," "I'm a chatbot," "I don't have access to," etc.
- **No follow-up questions** unless in intake or correction flow (where the next question is the explicit point).
- **No "I don't know — here's what I have anyway."** If the chat doesn't know, say so and stop.

### 8.3 Community-credit patterns

Use these naturally when the answer involves community-authored data, stale data, or missing data:

- *"A local told me [X]..."*
- *"Confirmed last week by a local..."*
- *"Haven't heard about this one in a while — my info might be old..."*
- *"Nobody's added a price yet — know what it costs? I'll add it."*
- *"We were recently told it moved from [X] to [Y] — let me know if that's wrong."*

Don't use them when the answer is trivially true or stable (e.g., saying "a local told me the BMX track is at Sara Park" feels weird for a fact that doesn't change). Use judgment.

### 8.4 Recommendation voice

**Default (Option 2):** list a few options, flag the standout.
> *"Saturday has a few options — the BMX race at 6 is usually the liveliest. Farmers market in the morning if you want something chill, or Altitude's open till 9."*

**When explicitly asked for a rec (Option 3):** pick, say why, can tell user what to skip.
> *"Go to the BMX race Saturday at 6 — it's the one thing locals actually show up for. Skip the farmers market; Thursday's is better."*

Explicit-rec triggers: "what should I do," "pick one," "which is best," "worth it," "your favorite," "what would you do."

### 8.5 Contested-state voice

**Low-stakes, newer leads:**
> *"Opens at 7 — someone recently reported it moved from 6. Let me know if that's wrong."*

**High-stakes, established leads (pending admin):**
> *"My info says the phone is (928) 555-0100. Someone recently reported a different number — I'll get it confirmed before updating."*

### 8.6 Not-in-catalog voice

> *"I don't have that one yet — know anything about it? I'll get it added."*

### 8.7 Out-of-scope voice

For restaurants, real estate, weather, etc.:
> *"That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?"*

### 8.8 Intake voice

Acknowledge, ask for the most important missing thing, stay brief.

> User: "there's a car show at the channel saturday"
> App: "nice — got a time, and who's running it?"

On commit:
> *"got it, added to the pile. Casey reviews new events before they go live — usually within a day or two."*

### 8.9 Correction voice

On a low-stakes correction:
> *"got it, noted — I'll flag it and watch for more confirmations."*

On a high-stakes correction:
> *"got it — that one needs to go through review before I update it. Thanks for the heads up."*

---

## 9. Cost Targets (as designed)

At 1,000 queries/day:
- Tier 1 + Tier 2: $0
- Tier 3 (20%): 200 queries × ~800 input + 100 output tokens × Haiku pricing = ~$0.26/day, **~$8/month**
- Intake extraction: ~20 submissions/day × gpt-4.1-mini = trivial, <$1/month
- Correction field detection: minimal, <$1/month

Total API cost at launch scale: **~$10/month**. If Tier 3 creeps to 40%, ~$16/month. If traffic grows 10x, ~$100/month. Budget accordingly.

---

## 10. Testing Strategy

- **Unit tests** for every new module (intent_classifier, unified_router, intake, correction, context_builder, tier1_templates, tier2_handlers, tier3_llm).
- **Fixture-based classification tests**: 80 queries for intent classifier (Phase 2), 75 for ask mode (Phase 3), 20 for intake (Phase 4), 15 for correction (Phase 5), 40 for tier 2 (Phase 7). Target: 90%+ pass rate per fixture suite.
- **Regression battery**: the existing 120-query battery must keep passing throughout. New router may re-route some queries; acceptable if answers are equivalent or better.
- **Voice consistency checks**: assertion helpers check length, contractions, filler words.
- **End-to-end smoke tests** against staging/production after each phase.

Do not ship a phase with failing tests. Do not commit with failing tests.

### Test isolation

Pytest uses **`tests/conftest.py`**: `pytest_configure` assigns **`DATABASE_URL`** to a **fresh temp SQLite file** for the whole session, and a session-scoped autouse fixture runs **`init_db()`** once so the schema matches migrations. The repo-root **`events.db`** used for local development is **not** the test database; tests must not assume or write to it. For rare local debugging only, **`HAVASU_USE_DEV_DB_FOR_TESTS=1`** skips that override and uses the developer DB instead — **never** set this in CI or production.

---

## 11. Deployment and Environment

- Push to `main` → Railway auto-deploys
- Deploy takes 2–5 minutes
- Env vars on Railway:
  - `OPENAI_API_KEY` (existing, Track A)
  - `ANTHROPIC_API_KEY` (add in Phase 3 — **owner task**, flag it)
  - `ADMIN_PASSWORD` (existing)
  - `DATABASE_URL` (existing, Railway-managed)
  - `RAILWAY_ENVIRONMENT` (existing)
- Local dev uses `.env` + SQLite. `python -m venv .venv` + `pip install -r requirements.txt` + `uvicorn app.main:app --reload --port 8000`.
- Before any phase-completion push to main: run full test suite locally.

---

## 12. Known Risks (Named So We Don't Ignore Them)

- **Seed data staleness.** 29 events hardcoded May–July 2026; programs with ⚠️ VERIFY flags from 2018–2020 sources. Phase 8's seed verification (owner task) is the mitigation.
- **Voice drift across tiers.** Ongoing tuning required. Phase 6 does a pass; owner re-audits periodically post-launch.
- **Cold start on contributions.** App is only great when it has contributors. First-month contribution goals are owner's to set and cultivate.
- **Sabotage and spam.** Moderation queue is the backstop. Rate limits are the first line. High-stakes fields never auto-update.
- **Power-contributor dependency.** 5–15 people will drive most corrections. Losing any of them affects quality. Owner's community management matters here.
- **Seed data document drift.** `HAVASU_CHAT_MASTER.md` and `docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md` are not fully in sync. As of Phase 1.5 there are ~7 title mismatches and 1 program that exists in seed-instructions but not master. Phase 8 seed-data verification includes reconciling these two documents to a single source of truth. Until then, `populate_program_concierge_fields` will report these as no-matches (~6% of programs); this is expected and tracked.

---

## 13. Phase Completion Checklist (use at end of each phase)

- [ ] All sub-phase deliverables shipped
- [ ] Exit criterion met and verified
- [ ] Existing tests still pass (172+ growing)
- [ ] New tests added and passing
- [ ] Deploys cleanly to Railway
- [ ] No dead code / commented-out blocks
- [ ] No hardcoded values that should be config
- [ ] No secrets in code
- [ ] Voice rules (Section 8) honored in every user-facing string
- [ ] Owner tasks flagged clearly, not simulated
- [ ] This handoff doc updated if any assumption changed (rare — flag if so)

---

## 14. If You Get Stuck

- Re-read the relevant section of this doc.
- Check the locked decisions in Section 2 — most ambiguity resolves there.
- Prefer matching patterns in existing Track A code over inventing new ones.
- If the blocker is a decision not covered in this doc: **stop and ask the owner**. Do not invent. Do not silently choose. The owner signed off on one set of decisions; anything else needs approval.

---

## END OF HANDOFF

This document is the source of truth for the Havasu Chat concierge build. If anything in another document contradicts this one, this one wins unless the owner explicitly says otherwise.

**Last updated:** Compiled from owner decisions on seven locked questions.
**Total scope:** 8 phases, ~3–5 months at ~20 hours/week, ship-ready concierge with community-authored data model and deferred monetization primitives in place.
