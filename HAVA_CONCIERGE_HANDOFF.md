# Hava — Concierge Build Handoff

**Purpose:** Complete reference document for Claude Code. Read this in full before executing any phase. Every decision below is locked. Do not re-open decisions without explicit owner approval.

**Owner:** Casey
**Location scope:** Lake Havasu City, AZ — single city, no multi-city framework
**Live app (Track A):** `https://havasu-chat-production.up.railway.app`
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

### Role split (Cursor + owner)

Claude drafts Cursor prompts; Cursor executes; Casey reports outcomes. **Review-before-commit:** Cursor completes implementation and verification, then **holds commits pending explicit owner approval** — no unilateral commits (policy stabilized post–Phase 4.3 through Phase 5).

---

## 1. Product Definition

### 1.1 What the app is

Hava is a conversational local concierge for Lake Havasu City, Arizona. One text box. Users ask it anything about what to do, where to go, who to call, what's happening. It answers in a local voice, makes recommendations when asked, and learns from the community — users can also contribute new events, programs, and businesses, or correct existing info, all through the same chat interface.

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

Hava is not a fixed-schema app with a pre-decided scope. It is a **community-grown local knowledge base** where the shape of the database emerges from what residents and visitors actually ask about and contribute.

### Four principles

1. **Seed is a starter kit, not the final shape.** The 25 providers, 98 programs, and 43 events loaded at launch are enough to make the app useful on day one. They are not the intended end state. The database grows from use.

2. **Growth is URL-backed user contributions.** When a user recommends a place, event, or service the app doesn't know about, the app asks for a URL — Google Business page, official website, venue page, or equivalent. That URL is the trust anchor: it's what distinguishes community knowledge from unverified claims. Structured data (name, address, phone, hours, category) is ingested from the URL rather than entered by hand.

3. **Categories emerge from use.** The operator does not pre-decide what Hava is "about." Categories are created when contributions accumulate demand for them. Restaurants, kayak rentals, live music, fishing guides — any of these may become categories if the community brings them with URL-backed evidence. The data model adapts to real demand rather than operator guesswork.

4. **Operator stays in the review loop early; automation grows with trust.** New contributions and new categories pass through operator review until patterns are established. Over time, high-confidence contribution paths (e.g. Google Business page → structured import → auto-admit) can be automated. Lower-confidence paths stay in review indefinitely.

### URL-evidence policy

- **Businesses and organizations:** URL required (Google Business, official website, or equivalent authoritative source).
- **Events:** URL preferred (venue page, ticket link, official announcement). Accepted without URL if contributor provides date, time, and location.
- **Tips, favorite spots, local knowledge without a natural URL:** accepted but flagged as "community tip — unverified" in provenance. Displayed differently from URL-backed entries so users can weigh them appropriately.
- All contributions pass through operator review until automation is trusted for that contribution type.

### What this changes about the rest of this handoff

- **§1.3 "What the app is NOT" list** (restaurants, real estate, weather, etc.) should now be read as **"not pre-seeded"** rather than **"permanently excluded."** Any of these may enter the knowledge base if users bring them with URL-backed evidence and operator approves. The exception is items excluded for architectural reasons (native mobile, SMS, multi-city), which remain out of scope.

- **Contribute / intake (roadmap "Phase 4" below, execution "Phase 5" in build plan)** is reframed: it is not just "let users add providers to existing categories." It is the **primary growth mechanism** for the app, and its design centers on URL-backed ingestion (Google Places API New, URL fetcher) with category discovery and operator review. *(Engineering Tier 2 arc is summarized in **§1b**; shipped phase table in **§1d**; live contribute stack in **§1c** — different numbering from the original roadmap headings in §5.)*

- **Phase 5 (Corrections)** extends naturally: users can correct field values and also challenge entries with counter-URLs. Contested-state (locked decision #3, field-stakes split) applies to URL-backed disputes.

- **Phase 7 (Tier 2 vector FAQ)** becomes more valuable as the knowledge base grows, since it can surface semantically similar community contributions.

- §1a's community-grown architecture operates beneath the voice surface. Users still contribute URL-backed entries, the URL is still the trust anchor ("the receipt"), and operator review still gates new data. The voice stance (§2.1) no longer surfaces provenance in every answer — Hava speaks from firsthand local voice instead — but the architectural commitment to user-contributed data is unchanged.

### What this does NOT change

- Phase 3.2 and 3.2.1 as currently shipped are correct and stay.
- The seven locked decisions stay.
- Phase 3.3 (end-to-end ask-mode tests) proceeds as planned.
- This vision informs Phase 4+ design; it is not a Phase 3 change.

### LLM-inferred facts (Tier 3 → review pipeline)

**Phase 3.6 context.** §1a's original addendum said Tier 3 responses naming catalog-gap entities could feed the review queue. Early implementation (Phase 3.6) added a rule forbidding external-resource pivots after catalog-gap acknowledgments. This made Q20 ("Is there live music tonight?") score PASS with a skeletal response that felt crisp in synthetic testing but insufficient for real users.

**Phase 4.6 reversal.** Removed the anti-pivot rule. Added an external-delegation rule allowing Tier 3 to mention CVB, search, venue sites when appropriate.

**Phase 4.7 guardrail.** Added an anti-hallucination rule preventing Tier 3 from fabricating specific local facts when bridging catalog gaps. End state: gap acknowledgment + concrete external pointer, no fabricated specifics.

**Phase 5.5 implementation.** A post-processing scanner (`app/contrib/mention_scanner.py`) runs as a BackgroundTask after every Tier 3 response. Pattern-matches title-case phrases (2–5 words, 6+ chars), filters against a stop-phrase frozenset (locations, calendar words, common external references), strips URLs before scanning, dedupes within response. Matches are logged to `llm_mentioned_entities` table. Operator reviews at `/admin/mentioned-entities` and manually promotes interesting entries to `contributions` (with source=llm_inferred). No auto-promotion — the anti-hallucination rule from 4.7 makes auto-promotion a re-opening of that failure mode.

## 1b. Four-tier routing architecture

Production query flow as of Phase 5 close:

**1. Classifier** (`app/chat/intent_classifier.py`). Assigns sub_intent and attempts entity matching. Uses gpt-4.1-mini (legacy pick from Phase 2).

**2. Tier 1** (`app/chat/tier1_handler.py` + `tier1_templates.py`) — deterministic templates. Fires when sub_intent is in TIER1_SUB_INTENTS and an entity matched. Zero LLM cost. Currently covers HOURS_LOOKUP (including day-specific per Phase 4.6), PHONE_LOOKUP, NEXT_OCCURRENCE. Other Tier 1 sub-intents defined but not firing in production — re-evaluate with organic traffic data.

**3. gap_template** (`app/chat/unified_router.py`) — catalog-gap acknowledgment. Fires when sub_intent is a fact-lookup and no entity matched. Zero LLM cost. Added Phase 3.8, updated in Phase 5.4 to direct users to `/contribute`.

**4. Tier 2** (`app/chat/tier2_handler.py`) — retrieve-then-generate. Fires for OPEN_ENDED queries where parser extracts usable filters with confidence ≥ 0.7 and the DB query returns at least one row. Cost: parser LLM call (~150 tokens in / ~80 out) + formatter LLM call (~1400 tokens in / ~160 out). Combined mean ~1737 input tokens per Tier 2 query post-Phase 4.5. Tier 2 falls back to Tier 3 on: parser error, low confidence, explicit `fallback_to_tier3`, or zero DB results. Now includes `open_now` filter (Phase 5.6) for GP-backed providers with structured hours.

**5. Tier 3** (`app/chat/tier3_handler.py`) — open-ended synthesis over full catalog. Fires as Tier 2's fallback and for queries that don't pattern-match elsewhere. Cost: single LLM call ~2400 tokens. Catalog-gap responses include external-delegation pointers (Phase 4.6) and are gated against fabrication of unlisted specifics (Phase 4.7).

**6. chat mode** — out-of-scope acknowledgment (boat rentals, weather, etc.). Zero LLM cost. Classifier decides.

All tiers log `tier_used` to `chat_logs`. Per-tier cost analytics via `scripts/analyze_chat_costs.py` (Phase 4.3 migration added input/output split). Tier 3 responses are scanned post-response by the mention scanner (Phase 5.5) for potential contribution candidates.

## 1c. Community-grown catalog implementation

The §1a architectural vision is implemented in production. This section documents the shape.

**Contribution lifecycle.** Three sources feed a unified `contributions` table (Phase 5.1):

- **User submissions** via `/contribute` form (Phase 5.4). Anonymous, IP-hash rate-limited at 1/hour.
- **LLM-inferred mentions** surfaced by the mention scanner (Phase 5.5). Operator promotes manually; never auto-queued.
- **Operator backfill** via admin JSON API or admin UI.

All sources flow through the same queue with identical status states (`pending` / `approved` / `rejected` / `needs_info`).

**Enrichment pipeline** (Phase 5.2). On contribution insert, two background tasks fire:

- **URL fetcher** — GET the submitted URL with 10s timeout, follow redirects (max 3 hops, SSRF-protected against private IP ranges), parse HTML for `<title>` and meta description with OpenGraph fallback. 5 MB body cap. Accepts only `text/html` or `application/xhtml+xml`. Failures are non-blocking.
- **Google Places (New)** — for `entity_type == "provider"` only. Text Search with location bias "Lake Havasu City, AZ". Fuzzy-match on displayName via Levenshtein to distinguish `success` from `low_confidence`. Returns structured `regular_opening_hours`, `formatted_address`, `phone`, `website_uri`, `place_id`, `types`, `location`, `business_status`. Field mask keeps request on the Pro + Contact Data SKU tier (~$17/1000 requests).

Enrichment failures don't block the contribution — operator sees the failure status during review. Manual reprocess endpoint available at `POST /admin/contributions/{id}/enrich`.

**Operator review** (Phase 5.3). Admin HTML pages at `/admin/contributions` show list view with filters, detail view with submission + enrichment side by side, and approve/reject/needs_info/edit action flows. Approval runs through the approval service (`app/contrib/approval_service.py`) which creates the appropriate catalog row (provider / program / event) in a single transaction with rollback on failure. Tip approval is deferred — tips can be submitted and rejected/needs_info'd but not approved (no catalog destination defined yet).

**Category handling.** Provider and program categories remain separate columns by design (see Phase 5.6 category split decision, `docs/phase_5_6_category_split_decision.md`). Category discovery dashboard at `/admin/categories` shows provider / program category frequencies plus pending contribution category hints. No taxonomy management tools beyond autocomplete during approval.

**Hours.** Provider hours stored in two forms for every new approval with GP data: `hours` (free text, backward compatible with Tier 1 HOURS_LOOKUP) and `hours_structured` (JSON, used by Tier 2's `open_now` filter). Existing seed providers have NULL `hours_structured`. Structured-hours editor during approval is deferred to Phase 7+.

**Rate limiting.** Two mechanisms coexist: `slowapi` (`app/core/rate_limit.py`) for `/api/chat` (120/min), and DB-backed per-IP-hash counting on `/contribute` (1/hour). Both honor `RATE_LIMIT_DISABLED` env var. Unified rate limiter is a future refactor candidate.

## 1d. Phase status and close state (through 8.8.1a)

| Phase | Status | Commit | Notes |
| --- | --- | --- | --- |
| 1 | ✅ | — | Project setup, FastAPI, SQLAlchemy, seed data |
| 2.x | ✅ | — | Chat API, classifier, Tier 3, ChatLog, rate limiter |
| 3.1–3.5 | ✅ | — | Tier 1 templates, routing, gap handling |
| 3.6 | ✅ | — | Voice revision (Option B community-credit, anti-delegation — later reversed) |
| 3.7 | ✅ | — | Organic traffic diagnostic, 50% gap finding |
| 3.8 | ✅ | `c9d9fac` | HOURS_LOOKUP variants + gap_template + rate-limit test mode |
| 4.0 Re-plan | ✅ | — | Tier 2 moved ahead of Contribute mode |
| 4.1 Parser | ✅ | `9a30909` | Tier2Filters schema + intent parser |
| 4.2 DB+Formatter | ✅ | — | tier2_db_query, tier2_formatter, tier2_handler |
| 4.3 Routing+Schema | ✅ | `903032c` | Router integration + token split columns |
| 4.4 Voice battery | ✅ | `16038ca` | Reusable voice-battery script + baseline |
| 4.5 Row cleanup | ✅ | `67f5bf4` | ~15% Tier 2 row payload reduction |
| 4.6 Voice cleanup | ✅ | `c2800a8` | Day-aware hours + external-delegation rule |
| 4.7 Anti-hallucination | ✅ | `1c27e21` | Tier 3 fabrication guardrail |
| 5.1 Contribution model | ✅ | `200f545` | `contributions` table + admin JSON API |
| 5.2 URL + Places | ✅ | `f5c4463` | `url_fetcher`, `places_client`, `enrichment`, BackgroundTasks |
| 5.3 Operator review UI | ✅ | `7fa2630` | HTML admin at `/admin/contributions`, approval creates catalog rows |
| 5.4 User form | ✅ | `5c58f52` | Public `/contribute` form, gap_template + system prompt updates |
| 5.5 Mention scanner | ✅ | `ce11e75` | `llm_mentioned_entities` + admin at `/admin/mentioned-entities` |
| 5.6 Categories + hours | ✅ | `b2f3fa9` | `/admin/categories`, `providers.hours_structured`, Tier 2 open_now filter |
| 6 | ✅ | `7a12022` | Voice audit track (6.1.x), feedback 6.2.x, onboarding 6.3, session memory 6.4 / 6.4.1, 6.5-lite plumbing; Phase 6 close doc — Phase 8 next |
| 7 | ⏸️ | — | Roadmap **§5 Phase 7** (deterministic `tier2_handlers.py` sheet) not executed; Tier 2 retrieve-then-generate shipped under Phase 4.x (`tier2_handler` + parser/formatter). Revisit if cost/latency warrant handler extraction. |
| 8 | ✅ | `0d01d40` | Pre-launch hardening (8.0.x bug track, 8.2 load, 8.3 error-path tests, 8.4 `docs/runbook.md`, 8.5 ToS, 8.5/8.7 privacy, 8.6 full regression) |
| 8.8.0 | ✅ | `3d4680b` | Persona design output: `docs/persona-brief.md` (owner + Claude 8.8.0) — committed in same package as 8.8.1a doc pass |
| 8.8.1a | ✅ | `3d4680b` | Handoff rewrite: Hava rename + §2.1 firsthand voice + §8.3 replacement + `docs/persona-brief.md` in tree |

### Phase 4 + Phase 5 close summary

**Phase 4 close.**

- Final voice battery: 19 PASS / 1 MINOR / 0 FAIL (up from Phase 3.6 baseline 17/3/0).
- Remaining MINOR: Q17 "Boat rentals on the lake?" chat-mode classification nuance. Deferred since 3.6.
- Tier 2 retrieve-then-generate live in production, ~30–50% of organic traffic on structured retrieval.
- Tier 2 input tokens ~2023 → ~1737 after 4.5 row cleanup (~14% reduction). Per-query cost ~$0.00268 → ~$0.00257 (~4%). Design target of ~$0.0006 per query not achieved; aggressive cuts rejected per owner direction (quality first, cost second).
- Tech debt resolved: token split, external delegation, anti-hallucination.

**Phase 5 close.**

- All six sub-phases shipped (5.1–5.6).
- 139 new tests added across Phase 5. Total suite: 669 passing.
- Track A regression: 116/120 preserved through every sub-phase.
- Voice battery at Phase 5.4 re-run: 19/1/0 unchanged.
- Community-grown catalog live end-to-end: `/contribute` form → enrichment → operator review at `/admin/contributions` → approval creates catalog row → Tier 2 queryable.
- Two additional feedback channels: LLM-inferred mention scanner (Phase 5.5) and category discovery dashboard (Phase 5.6).
- `open_now` filter in Tier 2 operational for GP-backed providers.
- Tech debt resolved: free-text hours, `open_now` skeleton, provider/program category ambiguity, JSON/HTML admin collision.

### Voice battery history

20-query battery, Q1–Q20 from `scripts/run_voice_spotcheck.py`. Scoring: PASS / MINOR / FAIL.

| Run | Score | Notes |
| --- | --- | --- |
| Phase 3.6 baseline | 17/3/0 | Post voice revision |
| Phase 4.4 | 15/5/0 | Initial Tier 2 deploy regressed some queries |
| Phase 4.5 | 16/4/0 | Q6 upgraded via row cleanup |
| Phase 4.6 | 18/1/1 | Q7, Q14, Q20 improved; Q4 hallucination regression from anti-pivot rule removal |
| Phase 4.7 | 19/1/0 | Q4 fixed via anti-hallucination rule |
| Phase 5.4 | 19/1/0 | Stable across Phase 5 |
| Phase 6.1.3 (55-sample `run_voice_audit`) | 51/1/3/0 | `c899bfb` — `docs/phase-6-1-3-voice-audit-report.md` — 55 samples, not the 20-query `run_voice_spotcheck` matrix |
| Phase 8.6 (55-sample `run_voice_audit`, baseline @ `8de25ce`) | 51/1/3/0 | `docs/phase-8-6-implement-report.md` — `meta.git_sha` `8de25ce` (pre–8.8 persona); same aggregate distribution as 2026-04-21 baseline; canonical `scripts/voice_audit_results_2026-04-22-phase86.json` |

Persistent MINOR: Q17 "Boat rentals on the lake?" chat-mode classification. Not affected by Phase 4 or 5 work.

### Cost state summary

**Model rates (Haiku 4.5 at Phase 5 close):** $1/M input tokens, $5/M output tokens.

**Staleness note (Phase 8.X doc pass):** Per-tier token **means** below were last benchmarked for documentation at **Phase 5.6** (see §1b narrative). Phases 6–8 did not publish a replacement per-tier mean table in-repo. Re-run `scripts/analyze_chat_costs.py` (or equivalent) against current production mix before treating these numbers as current operational truth.

**Per-tier cost (mean):**

- Tier 1: zero LLM cost (deterministic).
- gap_template: zero LLM cost (deterministic).
- Tier 2: ~1737 input tokens + ~240 output tokens ≈ $0.00257 per query.
- Tier 3: ~2400 input tokens + ~100 output tokens ≈ $0.00290 per query.
- chat mode: zero LLM cost.

**Deferred cost reductions (Phase 7 candidates):**

- Parser few-shot reduction (~200 token cut possible, voice risk).
- Formatter row payload further trimming (minor gains).
- Tier 3 context trimming (risk to catalog coverage).

Owner direction: quality first, cost second. Do not revisit unless cost becomes a real operational issue.

### Deferred decisions log

Open product and technical decisions that Phase 5's shipping has surfaced or clarified but not settled:

1. **Email infrastructure** (Phase 6 candidate). Contribution receipts, approval confirmations, needs-info replies. Provider choice (SES / Mailgun / Postmark). Deliverability, unsubscribe, rate limits.

2. **CSRF tokens on public forms** (future security pass). Currently not protected. Low-risk for contribute form because moderator review gates publishing. Admin actions deserve CSRF at some point.

3. **Multi-operator workflows.** When contribution volume warrants multiple reviewers. No trigger yet.

4. **reCAPTCHA / bot protection** on `/contribute`. Adding iff spam becomes real.

5. **Structured-hours editor in approval form UI.** Currently GP data flows through unchanged; operator edits free-text only. Phase 7+ UX polish.

6. **Tip approval destination.** Tips can be submitted + rejected but not approved. Options: new `tips` table, tag on existing provider table, deferred indefinitely.

7. **Backfill `hours_structured` for existing seed providers.** Would unlock `open_now` filter for all providers, not just new GP-backed ones. Migration task, probably simple but not scoped.

8. **Bulk ops on contributions.** Batch approvals, multi-select, bulk category-assign. Only relevant at higher volume.

9. **Public launch criteria.** No single numeric threshold. Pre-launch gate work lives in `docs/pre-launch-checklist.md` (Phase 8+). Roadmap Phase 6 is closed; **email infrastructure (item 1)** and **§5 Phase 7** remain open — launch timing still owner decision.

10. **Revenue model.** Deferred. Sponsored listings / freemium / ad-supported / hobby. No monthly cost ceiling set.

11. **Scale thresholds** (Postgres pooling, batch LLM API, CDN). Deferred until usage warrants.

12. **Provider/program category unification.** Phase 5.6 documented as intentional split. Reconsider if pattern changes.

13. **Mention scanner stop-phrase list tuning.** Grows organically with operator review. No automated surfacing of "frequently dismissed phrases" tool yet.

---

## 2. The Seven Locked Decisions

These shape every template, prompt, and rule downstream. Do not deviate.

### 2.1 Voice stance: Firsthand local voice (revised 2026-04-22, supersedes Option B)

Hava speaks from firsthand local voice. She has opinions, makes recommendations, and describes places as if from personal experience. She does not attribute knowledge to community sources in response text.

**Example:** *"Altitude opens at 10."*

Not: *"A local told me Altitude opens at 10."* (old Option B stance, superseded)

Authoritative source for voice specifics: `docs/persona-brief.md`. See §4 (voice texture) and §6 (voice examples) of the brief.

**What this does NOT change:** the §1a community-grown architecture. Users still contribute URL-backed entries via `/contribute`. Operator review still gates new data. The URL is still the trust anchor. Only the voice surface changes — contributions feed the catalog silently rather than being narrated in every answer.

**Historical note:** Phase 3.6 shipped Option B (community-credit in foreground). Phase 8.8 reopened and revised this decision. The §1d voice battery history preserves the provenance.

### 2.2 Recommendation opinionatedness: Option 2 — Light opinion default, Option 3 when explicitly asked

**Default voice (Option 2):** Lists options, flags the standout.
*"Saturday has a few options — the BMX race at 6 is usually the liveliest. Farmers market in the morning if you want something chill, or Altitude's open till 9."*

**When user explicitly asks for a recommendation** ("what should I do," "pick one," "what's worth it," "best X"): lean into Option 3 energy.
*"Go to the BMX race Saturday at 6 — it's the one thing locals actually show up for."*

System prompt handles the split. Both voices follow the §2.1 firsthand-voice stance per `docs/persona-brief.md`.

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

### 2.5 LLM split: classifier + Tier 2 + Tier 3

**Intent classifier** (`app/chat/intent_classifier.py`): `gpt-4.1-mini` via OpenAI (legacy Phase 2 choice). Structured slot extraction for events (`app/core/extraction.py`) also uses `gpt-4.1-mini`. Do NOT rewrite the classifier to Claude without an explicit owner decision.

**Tier 2 parser and formatter** and **Tier 3 synthesis**: Claude Haiku (`claude-haiku-4-5-20251001`) via Anthropic (`ANTHROPIC_API_KEY`). Tier 2 is retrieve-then-generate (parser + formatter), not deterministic handlers.

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

### 2.8 Administration, intake, and contribute stack (Phase 5 close)

Locked for shipped production:

- **Admin auth** reuses `ADMIN_PASSWORD` with `itsdangerous` cookie sessions.
- **Public contribution form** (`/contribute`) is anonymous with IP-hash rate limiting only (1/hour).
- **Google Places (New)** API used over legacy Places API (`GOOGLE_PLACES_API_KEY`).
- **Background enrichment** via FastAPI `BackgroundTasks`, not Celery/RQ.
- **Inline HTML in Python** for admin pages (no Jinja2 introduced).
- **Contribution `id`** is integer autoincrement (not string UUID like `providers` / `programs` / `events` / `chat_logs`). Foreign keys to those tables use string UUIDs.
- **Provider vs. program categories** remain separate columns by design (`docs/phase_5_6_category_split_decision.md`).

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
- `DATE_LOOKUP`, `TIME_LOOKUP`, `LOCATION_LOOKUP`, `COST_LOOKUP`, `PHONE_LOOKUP`, `HOURS_LOOKUP`, `WEBSITE_LOOKUP`, `AGE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW`

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
- Light opinion default, stronger when asked (section 2.2)

Users must not be able to tell which tier answered.

### 3.10 Analytics schema

Every response logs to `chat_logs` (see ORM `ChatLog` in `app/db/models.py` — column names below match the implementation).

```
id (uuid)
created_at
session_id (device/session bucket; not a separate user_hash column)
role (user | assistant)
message (utterance text for that row — user message or assistant reply)
intent (legacy short label on some rows)
query_text_hashed (unified-router turns only; null on Track A legacy rows)
normalized_query (unified-router turns only; null on Track A legacy rows)
mode (ask / contribute / correct / chat — unified-router turns only)
sub_intent (nullable)
entity_matched (nullable)
tier_used (1 / 2 / 3 / gap_template / chat / placeholder / intake / correction / track_a)
latency_ms
llm_tokens_used (nullable; legacy aggregate — Tier 3 paths also populate llm_input_tokens / llm_output_tokens)
llm_input_tokens (nullable)
llm_output_tokens (nullable)
feedback_signal (nullable: positive / negative / null — set via thumbs UI)
```

**`track_a`:** Rows written by legacy **`POST /chat`** (`app/chat/router.py` → `log_chat_turn`) use `tier_used='track_a'` so they are not confused with unified **`POST /api/chat`** rows that left `tier_used` null before this sentinel existed. Historical pre-sentinel rows may still show `tier_used` null.

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

## Pending tech-debt log (as of Phase 5 close)

**Resolved during Phase 4:**

- `llm_tokens_used` input/output split — Phase 4.3 migration.
- HOURS_LOOKUP classifier miss on "open late/early on [day]" — Phase 3.8.
- External-delegation rule scope — Phase 4.6.
- Hallucination of unlisted specifics — Phase 4.7.

**Resolved during Phase 5:**

- Free-text `providers.hours` blocking `open_now` filter — Phase 5.6 added parallel `hours_structured` column; new approvals with GP data populate it.
- `open_now` filter skeleton in Tier2Filters unused since Phase 4.1 — Phase 5.6 wired parser few-shots, DB query filter, and helper module.
- LLM-inferred facts pipeline undocumented — Phase 5.5 implemented conservative log-only approach.
- Provider vs. program category split as ambiguous tech debt — Phase 5.6 formalized as intentional design choice (documented in `docs/phase_5_6_category_split_decision.md`).
- JSON admin vs HTML admin path collision — Phase 5.3 refactored JSON under `/admin/api` namespace.
- Contribution PK type vs. other table PKs — Phase 5.1 documented `contributions.id` as integer autoincrement while `providers`/`programs`/`events`/`chat_logs` use string UUIDs. FKs to those tables use strings.

**Remaining (rolled forward from Phase 5 close):**

1. `placeholder` + `null` `tier_used` values in `chat_logs` (2.4% of rows, undocumented) — Phase 8.
2. Seed title mismatches (7 known between `master.md` and `instructions.md`) — Phase 8.
3. Placeholder schedule 09:00-10:00 rows on programs — Phase 8.
4. Q17 chat-mode classification nuance ("Boat rentals on the lake?") — deferred since 3.6.
5. Older "Explicit recommendation triggers" GOOD example in `prompts/system_prompt.txt` still references London Bridge farmers market (inconsistent with Phase 4.7 anti-hallucination rule but the newer rule dominates actual behavior) — Phase 7 voice iteration.
6. Parser system prompt at ~795 tokens (grew from 745 in Phase 5.6 via open_now few-shots; Phase 4 target was ~300) — Phase 7 if cost pressure returns.
7. Tip approval destination not defined (tips currently non-approvable) — Phase 5.6 or later decision.
8. CSRF tokens on public `/contribute` form — future security pass.
9. Spam protection beyond IP-hash rate limit on `/contribute` — future security pass.
10. Structured-hours editor in approval UI (drift possible between free-text and structured) — Phase 7+ UX polish.
11. Backfill `hours_structured` for existing seed providers — future migration task.
12. Two rate-limiting mechanisms coexist (slowapi for chat, DB-backed for contribute) — unify in future refactor.
13. Inline HTML admin pages (no Jinja2) — acceptable at current scale; Phase 7+ may migrate to templates.

---

## Phase 5 — Contribute mode (shipped)

**Status:** Closed through 5.6 (see **§1c**, **§1d**, and `PHASE_5_PLAN.md` for historical scope). Production paths: public **`/contribute`**, admin **`/admin/contributions`**, mentions **`/admin/mentioned-entities`**, categories **`/admin/categories`**, JSON under **`/admin/api/`**.

**Still deferred vs. original roadmap:** chat-based contribute/correct intake state machines in §3 remain partially aspirational; the shipped path is the web form + operator queue. Email receipts, CSRF, and bulk ops are in **§1d Deferred decisions**.

---

## Solo-dev workflow playbook (Phases 4–5)

Established patterns from Phases 4 and 5. Apply to all future sub-phase prompts.

### Prompt structure

Every Cursor prompt includes:

1. **Context** — self-contained, no external doc reads required.
2. **Pre-flight checks** — 2–4 verifications using `git log --oneline -20 | grep <subject>` (not HEAD comparisons — Phase 4.3's Check 1 design bug is fixed). Hard gate. Failed checks trigger STOP.
3. **Git scope fence** — trailer-accepted policy: leave `Made-with: Cursor` trailer alone, no amends, no hook bypass, no `core.hooksPath` edits, no `--no-verify`.
4. **STOP-and-ask triggers** — enumerated. For owner-gated decisions, use "STOP-and-ask — do not continue until owner replies" phrasing explicitly. Looser "STOP and report" has been interpreted as "proceed after documenting" (Phase 5.6 Check 2 finding).
5. **Goal** — what the phase delivers.
6. **Scope details** — in-scope / out-of-scope lists, explicit.
7. **Acceptance criteria** — testable conditions.
8. **Completion workflow** — review-before-commit. Cursor holds the commit pending explicit owner approval.

### Owner workflow

1. Review completion report including pre-flight check table.
2. Spot-check any anomalies or reported deviations.
3. Reply with explicit "approved, commit and push" when satisfied.
4. For voice-affecting changes, wait 3 minutes after push for Railway auto-deploy, rerun voice spot-check battery, upload result for scoring.

### When things go wrong

- Failed pre-flight check → STOP, do not proceed. Report and wait.
- Cursor proposes scope expansion → STOP, do not expand. Report and ask.
- Cursor reports "continued past failed check" → process-discipline violation, correct in reply, do not tolerate the pattern.
- Cursor deviates from spec but documents clearly → adjudicate case by case. Phase 5.2 (rate limiter design change) and Phase 5.6 (Check 2 STOP interpretation) were both accepted; future deviations aren't automatic approvals.
- Voice regression on battery → decide: revert, iterate, or accept as tradeoff.

---

## 5. Build Plan

**Implementation note (2026-04):** Tier 2 retrieve-then-generate shipped in production as engineering sub-phases **4.1–4.7** (see **§1b**); Contribute mode shipped as **5.1–5.6** (see **§1c–§1d**). The **Phase 4 — Contribute Mode** and **Phase 7 — Tier 2 Handlers** headings in this section are the **original product roadmap**; execution order was re-planned so Tier 2 preceded Contribute mode.

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
- All existing Track A tests still pass (669+ as of Phase 5 close — run `pytest` for current count).
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

**Goal:** Ship a working concierge for ask mode. Tier 1 for direct lookups, Tier 3 for everything else. *(Original plan: skip Tier 2 until Phase 7 — superseded: Tier 2 shipped in Phase 4 engineering arc per §1b.)*

**Sub-phases:**

**3.1 Tier 1 template library.** Create `app/chat/tier1_templates.py`. Regex patterns per sub-intent. `render(intent, entity, data) -> str | None` returns None if any required slot is null or the field is in a state requiring Tier 3 escalation. Template variants per intent, selected round-robin or by query signal to avoid identical repeats. **All templates honor §2.1 firsthand voice per `docs/persona-brief.md`** and §2.3 contested-state rules.

**3.2 System prompt.** Write `prompts/system_prompt.txt`. Must embody all of section 2.1, 2.2, 3.9. Include explicit instruction: when the user explicitly asks for a recommendation ("what should I do", "pick one", "best X", "worth it"), lean into stronger opinion (Option 3 energy). Otherwise, light opinion default (Option 2). Include a few-shot example block. Cap responses at 1–3 sentences. Firsthand voice per §2.1 and `docs/persona-brief.md`. No source-attribution phrasing in Tier 3 output.

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

**Note (2026-04-22):** Phase 6.5 sequencing changed post-6.4.1. The 20-30 blurb upfront approach was deferred in favor of a correct-and-grow workflow. See `docs/PHASE_6_5_LOCAL_VOICE_HANDOFF.md` for the current plan, data structure, and plumbing options.

**Exit criterion:**
- Voice audit completed (Phase 6.1.3 55-sample run; follow-on 6.1.4 fixes), all flagged items addressed or explicitly accepted by owner.
- Feedback thumbs live on Tier 3 responses, data flowing to `chat_logs`.
- Onboarding works for first-time visitors.
- Session memory improves context on multi-turn conversations (tested manually); recommended-entity capture for `prior_entity` shipped in 6.4.1.
- **6.5 local-voice content:** 20–30 blurb approach deferred post-6.4.1 in favor of **correct-and-grow** (`docs/PHASE_6_5_LOCAL_VOICE_HANDOFF.md`); 6.5-lite plumbing exists (`app/data/local_voice.py` + matcher) for future growth.

**As shipped:** Sub-phases 6.1–6.4.1, 6.2.2, 6.2.3, 6.5-lite as recorded in `7a12022` Phase 6 close.

---

### Phase 7 — Tier 2 Handlers (1–2 weeks, 15–25 hours)

**Goal (roadmap):** Pull common patterns out of Tier 3 into deterministic handlers. Reduces LLM cost and latency.

**As of Phase 8.X:** This roadmap phase has **not** been executed as a named release. Tier 2 **retrieve-then-generate** (parser + DB + formatter) is live from Phase 4.x (`tier2_handler.py` and related modules). The **deterministic** `tier2_handlers.py` sheet (no LLM) described in sub-phases 7.1–7.2 is **not** built — revisit if product needs lower-cost paths for high-volume query shapes.

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

**Goal:** Ship-ready (soft-launch / dogfooding); broader public still gated by `docs/pre-launch-checklist.md`.

**As shipped (roadmap 8.1–8.7 = execution 8.0.x–8.7 + 8.2 + 8.4–8.6, not 1:1 with original sub-numbering):**

**8.0.x Bug-fix / reconciliation track** — read-first triage, router + analytics fixes, known-issues reconciliation, explicit-rec routing (8.0.2), retrieval tuning (8.0.3), prompt hygiene (8.0.4), analytics (8.0.5), small UX (8.0.6/8.0.7). Closes with stable test suite and doc alignment.

**8.2 Load testing** — `scripts/smoke_concurrent_chat.py` and related; production-scoped performance notes in `docs/runbook.md` §3.10.

**8.3 Error-path testing** — automated coverage for §3.11 failure paths (Phase 8.3 deliverable).

**8.4 Operational runbook** — `docs/runbook.md` (not `admin_runbook.md`) — production ops, SQL, Sentry, env vars.

**8.5 + 8.7 Terms of service and privacy** — `docs/tos.md`, `docs/privacy.md` in tree; app footer links; items remain on pre-launch checklist for lawyer review and contact-email swap.

**8.6 Full regression** — `pytest` green; 55-sample `run_voice_audit` + smoke/docs per `docs/phase-8-6-implement-report.md` (see §1d voice history). **8.1 seed verification** remains an **owner task** — not closed in code.

**Exit criterion (as treated at `0d01d40` close):**
- Full automated regression pass and documented spot-checks complete; **GO** for dogfooding with open pre-launch items.
- `docs/runbook.md` exists and is linked from project docs.
- ToS and privacy pages exist; lawyer review and launch gates tracked in pre-launch checklist.
- **8.1** seed-calling verification still outstanding unless owner has completed out-of-band.

---

### Phase 8.8 — Persona, handoff, and code voice alignment (8.8.0 through 8.8.2)

**8.8.0 — Persona design (owner + Claude, no repo work).** Closed. Output is the agreed character, tagline, and voice constraints — captured in `docs/persona-brief.md` (landed in repo in **8.8.1a** as `3d4680b`).

**8.8.1a — Handoff documentation** — **Closed** (`3d4680b`). `HAVA_CONCIERGE_HANDOFF.md` rename, "Havasu Chat" → "Hava" prose, §2.1 / §8.3 rewrites, brief in tree. Follow-up doc-only commits may adjust §1d hashes (e.g. `adfa04c`) and completion report (`eb7b76f`) — see git log; substantive scope remains `3d4680b`.

**8.8.1b — Code implementation (system prompt, templates, known-issues cross-ref)** — **In flight / pending.** Per `docs/persona-brief.md` §10.2. Propagates firsthand-voice and persona rules into prompts and correction templates. Out of scope: Phase 8.9 retrieval work.

**8.8.2 — Voice regression verification** — **Pending.** Re-run voice battery with updated acceptance (persona-brief §9.5) after 8.8.1b lands; zero disallowed community-credit phrasing per known-issues resolution criteria.

**Exit criterion (8.8 track):** Handoff and brief authoritative; code matches brief after 8.8.1b+8.8.2; owner sign-off on voice.

---

### Phase 8.9 — Event ranking (recurring vs one-time) [pre-launch addendum]

**Scope (from `docs/persona-brief.md` §9.6):** Classify events as one-time vs recurring; prefer one-time in time-scoped queries; when no one-time events apply, use evergreen / recommendation fallback per brief voice examples. **Not** in scope for 8.8.1b. Touches retrieval / ranking; coordinate with any dedicated ranking work in `app/core/search.py` / event-quality modules.

**Checklist status:** `docs/persona-brief.md` §9.6 references a pre-launch checklist line item; **as of 2026-04-22** the open-block of `docs/pre-launch-checklist.md` does not yet list 8.9 — treat persona brief as the scope spec until the checklist is amended.

**Exit criterion:** Time-scoped queries return sensible ordering; no silent suppression of one-time events when data exists; documented in handoff or brief.

---

### Phase 8.10 — River Scene Event Pull (pre-launch, ~1 week, 10–15 hours)

**Goal:** Ingest events from River Scene local event calendar into the events catalog. Single source, structured ingestion, operator review pass, dedup against existing seed events.

**Sub-phases:**

**8.10.1 Scraper + parser.** Fetch logic for River Scene event pages, parse into structured event records (title, date, time, location, description, source URL). Respect robots.txt and reasonable rate limits.

**8.10.2 Dedup against seed.** Compare ingested events against existing 43 seeded events. Fuzzy match on title + date. Flag duplicates for operator review rather than auto-dropping.

**8.10.3 Operator review queue.** Ingested events land in existing `/admin/contributions` review queue with `source='river_scene_import'`. Operator approves, rejects, or edits before events go live.

**Exit criterion:** River Scene events visible in `/admin/contributions`, approved events queryable via chat, no test regressions, no voice battery regressions.

### Phase 8.11 — Google Bulk Import (pre-launch, ~3–6 weeks, 40–80 hours)

**Goal:** Enrich all ~4,574 Lake Havasu businesses via the `havasu-enrichment` pipeline and ingest into the chat app's provider catalog. Full scope commitment per scope revision doc — no stage gate.

**Sub-phases:**

**8.11.0 Day 1 setup (owner tasks).** Google Cloud project creation + Places API enablement + billing + budget alerts; Anthropic key; `havasu-enrichment` repo initialization; venv + dependencies; Google Drive folder for layered output; API key smoke tests. Reference: enrichment framework v3.

**8.11.1 Batch 1 execution.** Run enrichment pipeline on 25-provider validation set. Review batch quality report (match confidence distribution, category mapping sanity, narrative sample review). If framework bugs surface, fix in enrichment repo before proceeding.

**8.11.2 Batches 2–N execution.** Run enrichment pipeline on remaining ~4,549 providers in batches per framework checkpoint strategy. Monitor quality reports between batches; address anomalies before proceeding.

**8.11.3 Operator review drain.** Providers with match confidence below auto-admit threshold queue for operator review. Review cadence TBD during this sub-phase scoping. Define "drained enough to launch" threshold.

**8.11.4 Ingestion into chat app Postgres.** Enrichment pipeline writes to chat app's production Postgres. Schema additions (if any) go through standard Alembic migration path. Coordinate with any Tier 2/Tier 3 retrieval logic that may need awareness of bulk-import source.

**Exit criterion:** All ~4,574 providers in Postgres with enrichment data, operator review queue drained to defined threshold, no test regressions, preliminary Tier 3 queries against expanded catalog returning reasonable results.

### Phase 8.12 — Voice Regression v2 (pre-launch, ~1 week, 10–20 hours)

**Goal:** Re-run voice regression battery against expanded catalog (curated + bulk). Revised acceptance criteria account for bulk-imported narrative surface area. Verifies that Hava's firsthand voice (per §2.1 and persona brief) holds across the full catalog.

**Sub-phases:**

**8.12.1 Acceptance criteria update.** Based on §2.3 voice-for-bulk decision (made during 8.8.1b input phase), define updated pass/fail criteria for voice battery.

**8.12.2 Battery re-run.** Execute existing voice battery + any new prompts added to cover bulk-imported content scenarios.

**8.12.3 Remediation.** Any failures addressed via system prompt tuning or template revision. No catalog-data changes (those are Phase 8.11 scope).

**Exit criterion:** Voice battery passes at acceptable threshold against full catalog. Remediation plan in place for any deferred failures.

### Phase 8.13 — Tier 3 Retrieval Tuning (pre-launch, ~1–2 weeks, 15–30 hours)

**Goal:** Tune Tier 3 retrieval and synthesis for the expanded catalog. Current Tier 3 was calibrated against 25 providers; 4,574 providers changes retrieval recall/precision tradeoffs.

**Sub-phases:**

**8.13.1 Retrieval audit.** Run a battery of representative queries against the expanded catalog. Identify where retrieval pulls irrelevant providers, where it misses relevant ones.

**8.13.2 Tuning.** Adjust retrieval parameters (similarity thresholds, top-k, filter logic) based on audit findings. Coordinate with any embedding/narrative work from enrichment pipeline.

**8.13.3 Synthesis verification.** Verify Tier 3 synthesis quality hasn't degraded with expanded context. Re-run representative queries from 8.13.1.

**Exit criterion:** Tier 3 quality on representative queries matches or exceeds pre-expansion baseline. No new failure modes introduced by scale.

---

## 6. File Structure (target end state)

```
havasu-chat/
├── app/
│   ├── main.py
│   ├── bootstrap_env.py
│   ├── admin/
│   │   ├── auth.py
│   │   ├── router.py
│   │   ├── contributions_html.py
│   │   ├── mentions_html.py
│   │   └── categories_html.py
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── normalizer.py
│   │   ├── entity_matcher.py
│   │   ├── intent_classifier.py
│   │   ├── unified_router.py
│   │   ├── tier1_handler.py
│   │   ├── tier1_templates.py
│   │   ├── tier2_schema.py
│   │   ├── tier2_parser.py
│   │   ├── tier2_db_query.py
│   │   ├── tier2_formatter.py
│   │   ├── tier2_handler.py            (Tier 2 retrieve-then-generate — not roadmap §5 Phase 7 deterministic sheet)
│   │   ├── tier3_handler.py
│   │   ├── context_builder.py
│   │   ├── hint_extractor.py
│   │   ├── local_voice_matcher.py
│   │   ├── intake.py
│   │   ├── correction.py
│   │   ├── router.py                   (Track A legacy — keep)
│   │   └── voice_rules.py
│   ├── contrib/                        (Phase 5: url_fetcher, places_client, enrichment, approval_service, mention_scanner, hours_helper, …)
│   ├── api/
│   │   └── routes/
│   │       ├── chat.py                 (/api/chat, feedback)
│   │       ├── contribute.py
│   │       ├── admin_contributions.py
│   │       └── admin_mentions.py
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
│   │   └── local_voice.py              (6.5-lite; grows with correct-and-grow workflow)
│   ├── db/
│   │   ├── chat_logging.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── seed.py
│   │   ├── seed_providers.py
│   │   ├── contribution_store.py
│   │   └── llm_mention_store.py
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
│   ├── conftest.py                     (test DB isolation)
│   ├── test_*.py                       (pytest suite — 794+ as of Phase 8.6; see CI / local run)
│   └── fixtures/
├── docs/
│   ├── runbook.md                      (Phase 8.4 — operational; not admin_runbook.md)
│   ├── privacy.md, tos.md, known-issues.md, pre-launch-checklist.md
│   ├── persona-brief.md                (Phase 8.8.0+ — voice/persona reference)
│   └── START_HERE.md                   (Phase 8.X — onboarding map)
├── scripts/
│   ├── run_query_battery.py, run_voice_spotcheck.py, run_voice_audit.py, smoke_concurrent_chat.py
│   ├── analyze_chat_costs.py, verify_queries.py, …
│   └── battery_results.json, voice_audit_results_*.json (regression artifacts as generated)
├── HAVA_CONCIERGE_HANDOFF.md          (this file — source of truth)
├── requirements.txt
└── .env
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
- Test infrastructure (pytest; full suite 669+ as of Phase 5 close)
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

Hava is a knowledgeable local friend in Lake Havasu City. She knows the town, has opinions, is direct, and speaks from firsthand local voice per `docs/persona-brief.md`.

### 8.2 Hard rules

- **1–3 sentences.** No exceptions except multi-option lists (which should still be tight).
- **Contractions always.** "It's," "they're," "what's," "there's."
- **No filler.** Never start with "Certainly," "Absolutely," "Great question," "I'd be happy to," "Let me help you," "Sure thing."
- **No proactive self-reference to being an AI in Tier 1/2/3 answers.** AI-acknowledgment is reserved for direct questions about Hava's nature, per persona brief §5.3.
- **No follow-up questions** unless in intake or correction flow (where the next question is the explicit point).
- **No "I don't know — here's what I have anyway."** If the chat doesn't know, say so and stop.

### 8.3 Firsthand voice patterns

Hava speaks from firsthand local voice. No source-attribution phrasing.

**Stale-data hedge** (when Hava's info might be outdated):
- *"Been a while since I was by — double-check their hours."*
- *"Haven't been lately, so take that with a grain of salt."*

**Correction acceptance** (launches correction flow per §8.9):
- *"Huh, didn't know — want to update it?"*
- *"Oh, got it. Want to fix that so it's right going forward?"*
- *"Fair. What's the real story?"*

**Contribution invitations** (personal framing):
- *"Know a good one? Send me a link."*
- *"If you spot something I'm missing, let me know."*

**Never use** (superseded Option B patterns):
- *"A local told me..."*
- *"The community says..."*
- *"Confirmed last week by a local..."*
- *"Nobody's added a price yet..."*

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

**As-built mean per-tier costs (Phase 5 close):** see **§1d — Cost state summary** (Tier 2/Tier 3 Haiku token means supersede the rough figures below).

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
- **Railway CLI (Windows):** from repo root, use the project venv interpreter so dependencies match production images, for example:
  - `railway run .\.venv\Scripts\python.exe -m alembic upgrade head` — production migrations
  - `railway run .\.venv\Scripts\python.exe -m alembic current` — verify migration head
  - `railway variables` — list env vars
  - `railway variables --set "KEY=value"` — set env var
- **Env vars on Railway (Phase 5 close):**
  - `ADMIN_PASSWORD`
  - `OPENAI_API_KEY` (intake classifier — gpt-4.1-mini legacy)
  - `SECRET_KEY`
  - `SENTRY_DSN`
  - `DATABASE_URL` (Railway-managed)
  - `ANTHROPIC_API_KEY` (Tier 2 parser, Tier 2 formatter, Tier 3)
  - `GOOGLE_PLACES_API_KEY` (Places API New enabled; API restrictions set; no IP restriction; billing cap alert recommended)
  - `RATE_LIMIT_DISABLED` (test mode; honored by both slowapi and DB-backed rate limits)
- **Local dev:** `.env` + SQLite. `python -m venv .venv` then `.\.venv\Scripts\pip.exe install -r requirements.txt` and `.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000` (on macOS/Linux use `venv/bin/...` instead).
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
- [ ] Existing tests still pass (794+ as of Phase 8.6; run `pytest` for current count)
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

## 15. Implementation appendix (post–Phase 5 production)

Short reference for production architecture after Phase 5 close. Details drift as code evolves — prefer the repo for exact behavior.

### File paths (critical)

**Documentation (repo root):**

- `HAVA_CONCIERGE_HANDOFF.md` — this doc.
- `docs/phase_5_6_category_split_decision.md` — provider/program split rationale.

**Chat pipeline:**

- `app/chat/unified_router.py` — routing orchestrator + gap_template strings.
- `app/chat/intent_classifier.py` — sub_intent + entity matching (gpt-4.1-mini).
- `app/chat/tier1_handler.py`, `tier1_templates.py` — deterministic templates.
- `app/chat/tier2_schema.py` — Tier2Filters Pydantic (includes `open_now` field).
- `app/chat/tier2_parser.py` — LLM parser call.
- `app/chat/tier2_db_query.py` — DB query + `open_now` post-filter.
- `app/chat/tier2_formatter.py` — LLM formatter call.
- `app/chat/tier2_handler.py` — Tier 2 orchestrator.
- `app/chat/tier3_handler.py` — Tier 3 synthesis + anti-hallucination.
- `app/chat/context_builder.py` — Tier 3 context assembly.

**Contribute pipeline (Phase 5):**

- `app/contrib/url_fetcher.py` — HTML fetch + metadata extraction + SSRF protection.
- `app/contrib/places_client.py` — Google Places (New) Text Search client.
- `app/contrib/enrichment.py` — background enrichment orchestrator.
- `app/contrib/approval_service.py` — single-transaction approval → catalog row.
- `app/contrib/mention_scanner.py` — Tier 3 response scanner + stop phrases.
- `app/contrib/hours_helper.py` — Places hours → structured + is_open_at.

**Admin (HTML):**

- `app/admin/auth.py` — cookie session with `itsdangerous`.
- `app/admin/router.py` — HTML route registration.
- `app/admin/contributions_html.py` — review UI for contributions.
- `app/admin/mentions_html.py` — review UI for LLM mentions.
- `app/admin/categories_html.py` — category discovery dashboard.

**Admin (JSON):**

- `app/api/routes/admin_contributions.py` — JSON API at `/admin/api/contributions`.
- `app/api/routes/admin_mentions.py` — JSON API at `/admin/api/mentioned-entities`.

**Public:**

- `app/api/routes/chat.py` — `/api/chat` POST.
- `app/api/routes/contribute.py` — `/contribute` GET/POST.
- `app/static/index.html` — chat frontend.

**Data layer:**

- `app/db/models.py` — all SQLAlchemy models (ChatLog, Provider, Program, Event, Contribution, LlmMentionedEntity).
- `app/db/database.py` — Base + session.
- `app/db/chat_logging.py` — chat_log writes.
- `app/db/contribution_store.py` — contribution CRUD + duplicate URL detection + IP-hash rate count.
- `app/db/llm_mention_store.py` — mention CRUD.

**Schemas:**

- `app/schemas/chat.py`
- `app/schemas/contribution.py` — includes approval field schemas (provider/program/event).
- `app/schemas/llm_mention.py`

**Prompts:**

- `prompts/system_prompt.txt` — Tier 3 voice, external delegation, anti-hallucination, `/contribute` mention.
- `prompts/tier2_parser.txt` — 10+ few-shot examples (includes open_now).
- `prompts/tier2_formatter.txt` — response formatting for Tier 2.

**Scripts:**

- `scripts/run_query_battery.py` — Track A (120 queries).
- `scripts/run_voice_spotcheck.py` — 20-query voice battery.
- `scripts/analyze_chat_costs.py` — cost analytics with input/output split.
- `scripts/smoke_phase52_contributions.py` — production smoke test for Phase 5.2.

**Alembic migrations (production-applied):**

- `7a8b9c0d1e2f_add_llm_input_output_token_columns.py` — Phase 4.3.
- `b5c6d7e8f901_add_contributions_table.py` — Phase 5.1.
- `c6d7e8f9a012_add_llm_mentioned_entities.py` — Phase 5.5.
- `d7e8f9a0b123_add_providers_hours_structured.py` — Phase 5.6.

**Core:**

- `app/core/rate_limit.py` — slowapi Limiter + `RATE_LIMIT_DISABLED` helper.
- `app/main.py` — router registration.

### Data flow: user contribution

1. User GETs `/contribute`.
2. User POSTs form to `/contribute`.
3. Route handler (`app/api/routes/contribute.py`):
   a. DB-backed IP-hash rate check (1/hour).
   b. Pydantic validation via `ContributionCreate`.
   c. Duplicate URL check against pending/approved contributions.
   d. Minimum content check (URL or notes required).
   e. `create_contribution()` inserts row.
   f. `BackgroundTasks.add_task(enrich_contribution, ...)`.
   g. Redirect to `/contribute?submitted=1`.
4. Background: `enrich_contribution` runs URL fetch (if URL present) and Places lookup (if provider) in sequence. Updates contribution row with results. Handles all failures gracefully.
5. Contribution appears in `/admin/contributions` queue with enrichment status.
6. Operator reviews, clicks Approve (or Reject / Needs Info / Edit).
7. Approval service (`app/contrib/approval_service.py`) runs in single transaction:
   a. Creates Provider/Program/Event row with mapped fields including `hours_structured` from Places.
   b. Sets `created_*_id` on contribution, status=approved, reviewed_at=now.
   c. Commits.
8. New catalog row is queryable by Tier 2 immediately.

### Data flow: LLM-inferred mention

1. User POSTs to `/api/chat`, query routes to Tier 3.
2. Tier 3 generates response, chat_log row written, response returned.
3. If `tier_used == "3"`, `/api/chat` route schedules `scan_and_save_mentions` via `BackgroundTasks`.
4. Background: `mention_scanner.scan_tier3_response` extracts title-case candidates, filters stop phrases, dedupes.
5. Each candidate inserted into `llm_mentioned_entities` (unique constraint on chat_log_id + mentioned_name prevents duplicates).
6. Operator reviews at `/admin/mentioned-entities`.
7. If interesting: clicks Promote, fills in entity_type + URL + category, system creates Contribution with source="llm_inferred" and llm_source_chat_log_id set.
8. Promoted mention now flows through standard contribution enrichment + review pipeline.

### Data flow: Tier 2 with open_now

1. User query "what's open right now" POSTs to `/api/chat`.
2. Classifier routes to OPEN_ENDED intent.
3. Tier 2 parser LLM call extracts filters including `open_now=True`.
4. Tier 2 DB query fetches candidate providers per other filters.
5. Post-fetch: query code calls `is_open_at(p.hours_structured, now_lake_havasu)` for each provider, filters to those open.
6. Providers with NULL `hours_structured` are excluded.
7. Tier 2 formatter generates response from filtered rows.
8. Response returned to user.

---

## END OF HANDOFF

This document is the source of truth for the Hava concierge build. If anything in another document contradicts this one, this one wins unless the owner explicitly says otherwise.

**Last updated:** 2026-04-22 — Phase 8.X documentation refresh (§1d Phases 6/7/8/8.8 rows, voice history, §5 Phase 8/8.8/8.9, §6 file map, `docs/START_HERE.md`).
**Total scope:** Phases 1–5.6 (core stack), 6 (voice/onboarding/memory), 8 (pre-launch hardening through 8.6), 8.8.x (persona + handoff + upcoming code voice), 8.9 (pre-launch event ranking) — ship-ready concierge with community-authored data model; public launch gated by checklist.
