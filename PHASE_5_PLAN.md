# Havasu Chat — Phase 5 Plan: Contribute mode

**Date:** 2026-04-20
**Status:** Draft for owner review
**Predecessors:** `PHASE_4_REPLAN.md` (phase reordering rationale), `PHASE_4_PLAN.md` + close report (Tier 2 architecture now in production).

This document scopes Phase 5 at the design level. It breaks the 60–120 hour estimate into six sub-phases, specifies the contribution data model and lifecycle, outlines URL validation and Google Places integration, and flags open decisions the owner needs to make before Phase 5.1 fires.

---

## 1. Goal

Transform Havasu Chat from a statically-seeded concierge (25 providers, 98 programs, 43 events) into a **community-grown knowledge base** per the §1a architectural vision. Users contribute local knowledge (businesses, events, tips) with URL backing; the operator reviews and approves submissions; the catalog grows from real community input rather than from manual seeding.

Phase 5 is the largest sub-phase of the app by hours. It's also the phase where the product's growth story becomes plausible. Before Phase 5, adding a new business to the catalog requires the operator editing seed files. After Phase 5, any user can submit a URL-backed contribution and it flows into the catalog after operator review.

---

## 2. Context — what Phase 5 unlocks

The Phase 3.7 diagnostic and Phase 4.4–4.7 voice batteries both surfaced the same core finding: **50% of organic Tier 3 traffic is catalog-gap responses.** Users ask about farmers markets, sushi, hiking trails, skate parks, Rotary Park programs, live music — and the catalog has none of them. Tier 2 can't help queries where the data doesn't exist. Tier 3's gap-template response is honest but costs a query opportunity.

Phase 5 closes that loop. When a user hits a gap, the response invites contribution. Contributions flow into the operator queue. Approved contributions become catalog rows. Tier 2 now answers those queries next time. The app improves with use.

Three feedback mechanisms contribute data:

1. **Explicit user submissions** — the primary flow. User fills out a form with a URL and a short description.
2. **LLM-inferred facts** (§1a addendum) — when Tier 3 responses name specific entities, those mentions can feed the review queue for operator research. Phase 5 starts with a lightweight logging approach; full automation is Phase 6+.
3. **Operator backfill** — the operator adds contributions directly, e.g., after spotting a gap in their own testing.

All three flow through the same review queue and go live only after operator approval.

---

## 3. Architecture decisions (locked)

### Single-operator review, for now

All contributions require operator approval before going live. Phase 5 assumes a single operator (you) with access via the existing admin password. Multi-operator workflows (multiple reviewers, assignment, voting) are deferred to a later phase if the contribution volume warrants it.

### Anonymous submissions with soft rate limiting

Phase 5 does not require user accounts. Contributions are anonymous, with optional email for receipt confirmation. Rate limiting: one submission per IP per hour (hash the IP, don't store raw). Email validation is minimal — presence check only, no verification.

If spam becomes a problem, Phase 6 or later adds reCAPTCHA or similar. For now, anonymous submission is the friction-lightest path.

### URL-required for businesses, URL-preferred for events, unverified tag for tips

Per §1a:

- **Businesses / organizations:** URL is required. No URL, no submission.
- **Events:** URL preferred. Submissions without URLs are accepted but flagged.
- **Tips / corrections without URLs:** Accepted and stored with an "unverified" tag that surfaces in catalog display.

### Emergent categories, not fixed taxonomy

Per §1a: the catalog's category space grows from contributions, not from a pre-defined list. User submits a category hint as free text; operator normalizes during review. Over time, a common category vocabulary emerges. Phase 5 tooling: surface frequently-submitted category strings to the operator so they can be formalized.

Provider vs. program category split (`providers.category` vs. `programs.activity_category`) is a known tech-debt item. Phase 5 category discovery should either unify at intake or formally document the split. Decision deferred to Phase 5.6.

### Google Places integration for entity resolution

When a contribution includes a URL or a recognizable name, the system looks up Google Places to:

- Validate the entity exists
- Fetch canonical address, phone, hours
- Link to a stable Google Place ID for future deduplication

Google Places is a paid API (free tier: 200 requests/day for the Place Details endpoint). Phase 5 assumes the operator sets up an API key and accepts the cost. Estimated usage at Phase 5 scale: <10 requests per day (one per new contribution). Free tier is plenty.

---

## 4. Contribution data model

New SQLAlchemy model and Alembic migration in Phase 5.1.

**Implementation note:** Catalog tables today use **string UUID primary keys** (`providers.id`, `programs.id`, `events.id`, `chat_logs.id`). Foreign keys on `contributions` must use `String` columns referencing those keys — not integers.

```python
class Contribution(Base):
    __tablename__ = "contributions"

    id: int = Column(Integer, primary_key=True)  # or String UUID — pick one style in 5.1
    submitted_at: datetime = Column(DateTime, server_default=func.now())

    # Submitter identity
    submitter_email: Optional[str] = Column(String, nullable=True)
    submitter_ip_hash: str = Column(String(64), nullable=False)  # sha256 hash

    # Submission content
    entity_type: str = Column(String)  # "provider" | "program" | "event" | "tip"
    submission_name: str = Column(String)
    submission_url: Optional[str] = Column(String)
    submission_category_hint: Optional[str] = Column(String)
    submission_notes: str = Column(Text)

    # Event-specific
    event_date: Optional[date] = Column(Date)
    event_time_start: Optional[time] = Column(Time)
    event_time_end: Optional[time] = Column(Time)

    # URL fetch metadata
    url_title: Optional[str] = Column(String)
    url_description: Optional[str] = Column(Text)
    url_fetch_status: Optional[str] = Column(String)  # "success" | "error" | "timeout" | "not_attempted"
    url_fetched_at: Optional[datetime] = Column(DateTime)

    # Google Places enrichment
    google_place_id: Optional[str] = Column(String)
    google_enriched_data: Optional[dict] = Column(JSON)

    # Review state
    status: str = Column(String, default="pending")
    # "pending" | "approved" | "rejected" | "needs_info"
    review_notes: Optional[str] = Column(Text)
    reviewed_at: Optional[datetime] = Column(DateTime)
    rejection_reason: Optional[str] = Column(String)
    # "duplicate" | "out_of_area" | "spam" | "incomplete" | "unverifiable" | "other"

    # Created entity references (set on approval) — match String PKs on catalog tables
    created_provider_id: Optional[str] = Column(String, ForeignKey("providers.id"))
    created_program_id: Optional[str] = Column(String, ForeignKey("programs.id"))
    created_event_id: Optional[str] = Column(String, ForeignKey("events.id"))

    # Source tagging
    source: str = Column(String, default="user_submission")
    # "user_submission" | "llm_inferred" | "operator_backfill"
    llm_source_chat_log_id: Optional[str] = Column(String, ForeignKey("chat_logs.id"))

    # Unverified tag (for tips/events without URLs)
    unverified: bool = Column(Boolean, default=False)
```

Fields are tentative — refined during Phase 5.1 schema design. The shape is what matters: one table covers user submissions, LLM-inferred facts, and operator backfills. Lifecycle is uniform.

---

## 5. Contribution lifecycle

```
[USER submits] or [LLM infers] or [OPERATOR backfills]
         ↓
    status: "pending"
    (URL fetched async if present)
    (Google Places lookup if applicable)
         ↓
OPERATOR reviews in admin UI
         ↓
    ┌─────────────┬──────────────┬───────────────┐
    ↓             ↓              ↓               ↓
 approve       reject        needs_info    (edit then decide)
    ↓             ↓              ↓
creates row   status:       status:
in catalog    rejected     needs_info
+ sets       + reason      + note to
created_*_id  logged       submitter (if email)
    ↓                           ↓
status:                    (wait for resubmit
approved                    or operator followup)
```

State transitions are one-way for `approved` and `rejected`. `needs_info` can go back to `pending` (resubmitted) or `rejected` (timed out / abandoned). Status history is not tracked in Phase 5 — only current state + review_notes. If audit trails matter later, add a state_transitions table.

---

## 6. URL validation + metadata extraction

### URL validation (Phase 5.2)

For any submission with a URL:

1. **HTTP GET** the URL with a 10-second timeout.
2. Follow redirects (up to 3).
3. Check response status (2xx required; 3xx redirects followed; 4xx / 5xx / timeout → `url_fetch_status="error"`).
4. Parse HTML for:
   - `<title>` tag
   - `<meta name="description">` or OpenGraph `og:description`
   - OpenGraph `og:title` as fallback for title
5. Store results. Sanitize aggressively — no raw HTML in `url_title` or `url_description`.

Failures are non-blocking: the submission is still accepted with `url_fetch_status="error"`. The operator sees the failure during review and decides whether to approve anyway.

### Google Places integration (Phase 5.2)

For submissions where the `entity_type` is `"provider"` and a URL is present (or the name matches a recognizable Lake Havasu business):

1. Query Google Places Text Search with the submission name + "Lake Havasu City, AZ" as the search string.
2. If a high-confidence match returns, fetch Place Details:
   - `place_id` (store for stable reference)
   - Formatted address
   - Phone number
   - Opening hours (structured!)
   - Website URL (cross-check with submitted URL)
3. Store the full Places response in `google_enriched_data`.

Google Places is the **structured hours gold mine**. For providers backfilled via GP, hours come in structured form (open/close times per day) rather than free text. This unlocks `open_now` filtering in Tier 2 for GP-backed providers.

For non-provider submissions (programs, events, tips), Google Places lookup is skipped — these entity types aren't business-registered.

---

## 7. Operator review UX (Phase 5.3)

### Admin page layout

A simple authenticated admin page at `/admin/contributions` (authentication via existing admin password). Shows pending contributions in a list with:

- Submission date, entity type, submission name
- URL (linked, opens in new tab)
- Category hint
- Notes from submitter
- URL fetch status and metadata (title, description)
- Google Places match (if found) with address, hours, phone
- Action buttons: Approve, Reject, Needs Info, Edit

### Approve flow

Clicking Approve opens a form pre-populated with:

- The submission's fields (name, URL, category, notes)
- URL-fetch metadata (description)
- Google Places data (address, hours, phone) — editable
- Category selection: operator can pick from existing categories or enter a new one

Operator confirms or edits, clicks "Approve and Create". System creates the appropriate catalog row (provider / program / event), sets `created_*_id` on the contribution, sets status to `approved`.

### Reject flow

Clicking Reject prompts for:

- Reason (enum dropdown): duplicate, out_of_area, spam, incomplete, unverifiable, other
- Review notes (optional free text)

Saves status as `rejected` and locks further action.

### Needs Info flow

If email was provided, operator can send a short note back. Phase 5 implementation: operator writes the note, system stores it in `review_notes`. Outbound email to submitter is deferred to Phase 6 (email infrastructure).

### Edit flow

Any field editable before approval. Aggressive normalization expected:

- Clean up submission_name (title case, strip marketing fluff)
- Normalize category_hint into existing taxonomy
- Shorten notes / description to operator's preferred style
- Fix URL formatting (ensure https://, trailing slash conventions)

### Filter and search

List view filters by: status, entity_type, source, date range. Search by submission_name substring. Pagination if volume warrants (Phase 5 can start without pagination).

---

## 8. User contribution UX (Phase 5.4)

### Entry point

Tier 3 gap-template responses and Phase 3.8 gap_template responses already say "share the name and a link and I'll add it." Phase 5 makes this link actionable by pointing to `/contribute` — a public-facing contribution form.

Alternative future UX: inline chat-based contribution (user can submit via chat message like "add [name] [url]"). Phase 5 does not include this — too complex for first version. Sticks to a dedicated form page.

### Contribution form

Mobile-first, simple. Single page with:

- Entity type radio buttons (business, program, event, tip)
- Name (text input, required)
- URL (text input, required for business/program, optional for event/tip — UI adjusts required state based on entity type)
- Category hint (text input, optional)
- Description / notes (textarea, optional)
- Event date / time fields (shown only when entity_type=event)
- Email (text input, optional, "we'll send a confirmation")
- Submit button

After submit: brief confirmation page ("Thanks! We'll review your contribution and it'll appear in the catalog once approved.") with a link back to the chat.

### Rate limiting

IP-hash-based rate limit: one submission per IP per hour. Exceeded → polite error page ("Whoa, slow down — you've submitted recently. Please try again in an hour.").

### Validation and feedback

Minimal client-side validation (required fields, URL format). Server validates more thoroughly: URL accessibility, minimum description length, duplicate detection (same URL already submitted → "we already have this in review").

---

## 9. LLM-inferred facts pipeline (Phase 5.5)

The §1a addendum: when Tier 3 responses confidently mention a specific entity that isn't in the catalog, that mention can feed the review queue.

Phase 5 approach is conservative: **log mentioned entities, don't auto-queue them.**

### Implementation

1. A post-processing step on Tier 3 responses scans output for patterns that look like entity mentions ("at [Name]", "the [Name] [category]", etc.).
2. Matches are logged to a new table `llm_mentioned_entities` with fields: chat_log_id, mentioned_name, context_snippet, detected_at.
3. Operator periodically reviews the log via a new admin page `/admin/mentioned-entities`.
4. Operator promotes interesting entries to `contributions` (with source=llm_inferred) for full review + research.

**What Phase 5 does NOT do:**

- Does not auto-create contributions from LLM mentions (too noisy; Phase 4.7 added the anti-hallucination rule for good reason).
- Does not attempt NLP entity extraction (pattern-matching is enough).
- Does not cross-check mentions against the catalog (operator does that during promotion).

### Rationale for conservative approach

Phase 4.7's anti-hallucination rule is meant to prevent exactly the "LLM confidently describes a thing that doesn't exist" failure mode. Auto-queueing LLM mentions as contributions would partially re-open that failure mode by treating hallucinations as legitimate data sources. The conservative approach: log everything for operator awareness, but require human judgment before anything enters the review queue.

Phase 6+ can revisit with a more sophisticated pipeline if the manual approach proves useful.

---

## 10. Category discovery (Phase 5.6)

When contributions are approved, their normalized categories are written to the catalog. Phase 5.6 adds tooling:

- **Category frequency dashboard** in admin UI: shows existing categories with counts (both from original seed data and from approved contributions).
- **New-category surfacing:** when the operator approves a contribution with a category hint that doesn't match any existing category, it's flagged as "new category" for operator confirmation.
- **Category normalization helper:** fuzzy-match incoming category hints against existing categories to suggest alignment (e.g., "BMX" → existing "bmx"; "martial arts gym" → existing "martial arts").
- **Provider vs. program category unification decision** made here: operator decides whether to merge the two category columns, keep them separate with documented rationale, or migrate over time.

This is lightweight tooling — not a full taxonomy management system. It supports the emergent-category approach without over-engineering.

---

## 11. Sub-phase breakdown

### Phase 5.1 — Contribution data model + admin backend (10–15 hours)

**In scope:**

- `Contribution` SQLAlchemy model (per §4 data model).
- Alembic migration.
- CRUD helpers (create, get, list with filters, update status).
- Admin authentication wrapper (reuse existing admin_password mechanism).
- Minimal admin route scaffolding (GET /admin/contributions returns JSON list; individual GET/POST for status changes).
- Unit tests for model + helpers.

**Out of scope:** URL fetching, Google Places, user-facing form, UI polish.

**Acceptance:** operator can insert, list, and update contribution status via backend routes. Tests pass.

### Phase 5.2 — URL validation + Google Places integration (15–20 hours)

**In scope:**

- URL fetcher with timeout, redirect handling, metadata extraction.
- Google Places client (set up API key, Text Search + Place Details).
- Background processing: when a contribution is created, kick off URL fetch + Google Places lookup. Update the contribution row with results.
- Handle failures gracefully (errors don't block the contribution).
- Operator note for API setup: Google Places key in env vars, free tier is sufficient at expected volume.
- Unit tests with mocked HTTP + Google Places responses.

**Out of scope:** UI for displaying enrichment results (that's 5.3).

**Acceptance:** a contribution submitted via API includes URL metadata and (if applicable) Google Places data within a few seconds.

### Phase 5.3 — Operator review UI (15–25 hours)

**In scope:**

- Admin list view for pending contributions with filters.
- Individual contribution view with full enrichment data.
- Approve / Reject / Needs Info / Edit action flows.
- On approve: create catalog row (provider / program / event), set `created_*_id`.
- Category selection during approval (existing categories + new category entry).
- Basic UI styling (match existing admin aesthetic if any; otherwise minimal clean HTML).

**Out of scope:** user-facing form, LLM-inferred facts pipeline, category discovery dashboard.

**Acceptance:** operator can approve a contribution and see it appear as a live catalog row, queryable by Tier 2.

### Phase 5.4 — User contribution form (10–15 hours)

**In scope:**

- Public `/contribute` page with the form described in §8.
- Client-side validation.
- Server-side validation (rate limiting, duplicate URL check, minimum content).
- Confirmation page after submission.
- Chat responses (Tier 3 gap-template, Phase 3.8 gap_template) updated to link to `/contribute`.

**Out of scope:** email sending (deferred to Phase 6), inline chat contribution, reCAPTCHA.

**Acceptance:** a new user can submit a URL-backed contribution from a mobile browser and the submission appears in the operator queue.

### Phase 5.5 — LLM-inferred facts logging (10–15 hours)

**In scope:**

- `llm_mentioned_entities` table + migration.
- Post-processing step in Tier 3 handler (and Tier 2 formatter?) that scans responses for entity-mention patterns and logs matches.
- Admin list view for mentioned entities.
- "Promote to contribution" action that creates a new contribution row with source=llm_inferred.

**Out of scope:** automated promotion, NLP-heavy extraction, cross-catalog checking.

**Acceptance:** operator sees a list of entities the LLM has mentioned, can promote interesting ones to the review queue for research.

### Phase 5.6 — Category discovery + catalog integration polish (10–20 hours)

**In scope:**

- Category frequency dashboard.
- New-category flagging during contribution approval.
- Fuzzy-match suggestion during approval ("did you mean the existing category 'bmx'?").
- Provider vs. program category decision + implementation (unify, document, or migrate).
- Hours normalization at intake: when a provider is approved with Google Places data, store hours in structured form (not free text). Update the provider model / schema as needed.
- `open_now` filter in Tier 2 DB query layer becomes operational for GP-backed providers.

**Out of scope:** full taxonomy management UI, bulk category migration for existing seed data.

**Acceptance:** new categories surface to operator; approvals with GP data store hours structurally; Tier 2 `open_now` filter works for new providers.

### Total estimate

- 5.1: 10–15 hours
- 5.2: 15–20 hours
- 5.3: 15–25 hours
- 5.4: 10–15 hours
- 5.5: 10–15 hours
- 5.6: 10–20 hours
- **Total: 70–110 hours** (within the 60–120 estimate from the re-plan)

---

## 12. Open decisions — owner needs to answer before 5.1 fires

1. **Admin authentication:** Phase 5 assumes the existing `ADMIN_PASSWORD` env var covers admin routes. Is that right, or is a separate login flow needed? My recommendation: existing password is fine for Phase 5.

2. **Google Places API key setup:** Will you set up a Google Cloud project and API key before Phase 5.2? (Required for that sub-phase.) This is owner-operational work, not Cursor work.

3. **Email sending deferral:** Phase 5 does not send emails (no receipt confirmations, no approval notifications). Email comes in Phase 6+ with proper infrastructure (SES? Mailgun? Something else?). OK to defer?

4. **Contribution spam risk assessment:** Phase 5 ships without reCAPTCHA or similar. Anonymous submissions + IP-hash rate limit. If spam becomes real, we add it. Accept?

5. **LLM-inferred facts scope:** Phase 5.5 is the conservative "log, don't queue" approach. Does that match your intent, or do you want more automation sooner?

6. **Operator approval workflow:** Phase 5 assumes you personally review every contribution. At what volume do you want to consider delegation / multi-operator? (Phase 5 doesn't need to answer this — just flagging for future.)

---

## 13. Out of scope for Phase 5

- Multi-operator workflows, reviewer assignment, approval voting.
- Email sending (receipts, confirmations, needs-info notes to submitters).
- Inline chat-based contribution ("add [name] [url]" in a chat message).
- reCAPTCHA / bot protection beyond IP rate limiting.
- Contributor accounts, profiles, leaderboards, gamification.
- Contributor reputation scoring.
- Bulk category migration for existing seed data.
- Automated LLM-inferred facts pipeline (beyond the logging approach in 5.5).
- User-facing edit/flag flows (correction flow is Phase 6).
- Automated hours normalization for existing seed-data providers.

---

## 14. Tech debt

### Resolved by Phase 5 close

- Free-text `providers.hours` → structured (for new GP-backed providers at least; migration of seed data deferred).
- `open_now` filter becomes operational in Tier 2 (for GP-backed providers).
- Provider vs. program category split decision (unify / document / migrate).

### Not resolved by Phase 5 close (rolls forward)

- Seed-data placeholder schedule rows (Phase 8).
- Seed title mismatches (Phase 8).
- `placeholder` and `null` tier_used values in chat_logs (Phase 8).
- Q17 chat-mode nuance.
- Older hardcoded GOOD example in system_prompt.txt (Phase 7 voice iteration).
- Parser prompt token size (Phase 7 if cost pressure returns).

---

## 15. Risk assessment

### Highest-risk sub-phase: 5.3 (Operator review UI)

15–25 hours is a wide range because admin UI work is hard to estimate. The risk: scope creep into "making it polished" vs. "making it work." Mitigation: ship minimal functional UI in 5.3, revisit polish in a later voice/UX pass.

### Second-highest-risk: 5.5 (LLM-inferred facts)

Pattern-matching for entity mentions is fuzzy. Risk: either the regex misses most mentions (low signal) or catches too much (noise). Mitigation: start simple, iterate based on operator feedback.

### Lowest-risk: 5.1 (data model)

Schema work is well-understood at this point. Contribution fields are tentative but the shape is solid.

---

## 16. Immediate next step

Owner review of this plan. Specifically:

- Answer the six open decisions in §12.
- Confirm sub-phase ordering. 5.1 → 5.2 → 5.3 → 5.4 → 5.5 → 5.6 is my recommended order. Alternative: do 5.4 (user form) before 5.3 (operator UI) to validate the user flow with a JSON-only operator backend. Either works.
- Raise any "this whole thing is wrong" concerns while the plan is still cheap to revise.

After owner review, next output is the Phase 5.1 Cursor prompt (data model + admin backend). Scope will be narrow, following the Phase 4 pattern: pre-flight checks, scope fence, review-before-commit.

Phase 5 will run across multiple weeks at your ~20 hour cadence. Each sub-phase is 1–2 weeks. By Phase 5 close, the app has a functioning contribution flow, growing catalog, and the core community-growth story is live.
