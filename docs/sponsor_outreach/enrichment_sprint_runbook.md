# Enrichment sprint runbook

**Operator-facing workflow for the Hava sponsor enrichment sprint.** This runbook synthesizes the outreach flow from `docs/sponsor_outreach/cold_email_templates.md`, `docs/sponsor_outreach/cold_email_variants_2026-05-09.md`, `docs/sponsor_outreach/reply_handlers.md`, and `docs/sponsor_outreach/post_launch_comms.md`, along with the enrichment CSV workflow from `templates/enrichment/README.md`. You are the operator in this document. The workflow below is sequenced intentionally so you can move a business from first research to live Spotlight placement without jumping between multiple docs.

**Estimated time per business:** ~30 minutes from research to ingest, plus reply-handling latency over the following weeks.

---

## Section 1 — Sprint goals and target list

The goal of this sprint is simple: get 50 verified businesses into the Hava catalog across the highest-value local categories.

Priority categories for this batch:

- Restaurants
- Plumbers
- HVAC
- Pool service
- Boat repair
- Urgent care
- Auto repair

These categories were selected because they match the highest-intent search behavior inside the Hava concept. People searching these categories are usually trying to make a decision quickly, which makes Spotlight placement valuable and measurable.

The bottleneck in this sprint is not data quality. The bottleneck is outreach response rate. Do not over-optimize formatting or spend an hour researching one business. Move steadily.

Use Google Maps plus your own Lake Havasu knowledge to build candidate lists. The target intake is roughly 15 businesses per category. That gives you a reasonable 2× outreach buffer assuming about half will never respond.

Prioritize businesses with strong review volume, clear owner-operated signals, updated websites, good Google Business Profile maintenance, strong local reputation, and distinct positioning you can personalize against. Avoid obvious dead listings, permanently closed businesses, businesses with broken websites, or businesses that already look abandoned.

The sprint only works if volume stays consistent. Keep moving category by category instead of obsessing over individual sends.

---

## Section 2 — Pre-outreach research per business

Before you send a cold email, collect the minimum viable information needed to personalize the outreach and onboard them later if they say yes.

For each business, collect:

- Canonical business name capitalization
- Correct category slug from `templates/enrichment/README.md`
- Owner or manager email address
- One personalization hook for the `[BRACKETS]` placeholder

The personalization hook matters more than the rest of the email. It is the signal that the outreach is local and specific instead of mass-blasted.

Good sources for personalization: Google reviews, Yelp reviews, business About pages, BBB listings, ASE certification references, outdoor patio mentions, family-owned positioning, weekend-hours positioning, emergency-response mentions, manufacturer-authorized repair badges.

Do not invent anything. If you cannot find a clean personalization angle in 5–10 minutes, move on to another business.

The owner email usually comes from: website Contact page, footer contact section, Google Business Profile, or Facebook page About section.

Track all research in the same spreadsheet you use for outreach tracking. Do not leave businesses half-researched in browser tabs.

---

## Section 3 — Cold email send

Once the research is done, open `docs/sponsor_outreach/cold_email_variants_2026-05-09.md` and pick the category-specific variant that matches the business.

Replace:

- `[Business Name]` (appears 3–4 times per email — double-check all replacements before sending)
- The personalization bracket line
- Any category-specific details needed for flow consistency

Pick one subject suggestion from the variant and send the email from your personal account, not a generic company inbox. The whole tone of the sprint depends on the outreach feeling like a local operator sending a direct note.

Do not modify the structure heavily while the sprint is running. You need clean response-rate feedback by category. If you freestyle every email, you lose the ability to tell whether the variant itself is working.

Track each send in a spreadsheet with at minimum:

- `business_name`
- `category`
- `owner_email`
- `sent_date`
- `status`

Every new send starts with status `SENT`. The spreadsheet is the source of truth for sprint state.

---

## Section 4 — Reply handling

Once replies start coming in, map them directly into the handlers from `docs/sponsor_outreach/reply_handlers.md`. Do not improvise unless something unusual happens.

### (a) Clear yes

If the business replies with "yes," "sounds good," "interested," "send details," "let's do it," or similar — use Section 1 of `reply_handlers.md`.

Status flow: `SENT → YES → AWAITING DETAILS`

Your immediate goal becomes collecting the onboarding data cleanly.

### (b) Decline

If they say no, not interested, maybe later, or similar — use Section 2 of `reply_handlers.md`.

Do not try to overcome objections. Do not turn the thread into a debate.

Status flow: `SENT → NO → RECONTACT 6MO`

The sprint depends on preserving goodwill with local businesses. A clean no is fine.

### (c) Questions

If they ask operational questions, pricing questions, or "how does this work" questions — use the Q&A bank in Section 3 of `reply_handlers.md`. Copy only the relevant answers instead of pasting the entire section.

Status remains `SENT` until they either commit or decline.

Do not invent analytics details, sponsor counts, dashboard functionality, or traffic numbers. Use the `[CASEY: confirm]` placeholders in `reply_handlers.md` Section 3 as your reminder of which facts need product-reality confirmation before sending.

### (d) Silence at week 1

If no reply after one week — use the Week-1 follow-up from Section 4 of `reply_handlers.md`.

Status flow: `SENT → FOLLOW-UP 1`

Do not apologize for following up.

### (e) Silence at week 4

If still no reply after four weeks — use the Week-4 follow-up.

Status flow: `FOLLOW-UP 1 → FOLLOW-UP 2 → CLOSED`

At that point, stop touching the business during this sprint cycle.

The outreach works because it stays calm and low-pressure. The moment it starts feeling persistent or sales-heavy, response quality drops.

---

## Section 5 — Onboarding after a yes

Once a business replies yes and sends the requested onboarding details, move into enrichment ingest preparation.

Open `templates/enrichment/business_enrichment_template.csv`. Use the rules from `templates/enrichment/README.md` to fill out a single row correctly.

Typical onboarding data collected: phone number, street address, hours, website, preferred contact email, signature positioning line.

Important details:

- `provider_name` should use proper capitalization (e.g., `"Havasu Pool Pros"`, not `"HAVASU POOL PROS"`).
- Use the exact category slug from the README's allowed list.
- `last_verified_at` must be ISO-8601 with `-07:00` offset (Lake Havasu has no DST year-round).
- `verification_method` is usually `email_confirmation` when the operator confirmed details by email reply.
- `hava_voice_description` should be 80–400 characters.

The `hava_voice_description` matters. Write it the way Hava would naturally describe the business based on what they told you about themselves.

Do not write generic filler like "trusted local business," "serving the community," or "quality service." Use specifics instead — "same-day outboard repair," "family-owned Mexican restaurant with patio seating," "ASE-certified domestic truck specialist," "after-hours emergency plumbing."

Status flow: `YES → AWAITING DETAILS → READY TO INGEST`

Only move to `READY TO INGEST` once the CSV row is fully valid and complete.

---

## Section 6 — Validate and ingest

Once the CSV row is complete, validate it before ingest.

From the repo root, run:

```
python scripts/ingest/validate_enrichment_csv.py path/to/your_filled.csv
```

The validator prints PASS/FAIL results per row.

If validation fails: fix the row, rerun the validator, repeat until clean. Do not bypass validator failures manually.

Once validation passes, preview the ingest first:

```
python scripts/ingest/ingest_enrichment_csv.py path/to/your_filled.csv --dry-run
```

If the dry run looks correct:

```
python scripts/ingest/ingest_enrichment_csv.py path/to/your_filled.csv
```

The ingest is idempotent. Running the same file twice is safe.

Status flow: `READY TO INGEST → LIVE`

---

## Section 7 — Launch and post-launch sequence

The day the ingest completes becomes the sponsor launch date.

Immediately send Section 1 of `docs/sponsor_outreach/post_launch_comms.md` (the launch email). Fill in `[LAUNCH DATE]` and `[LAUNCH URL or BUSINESS LISTING URL]`.

Status becomes `LIVE`.

The launch email confirms the placement is active and gives the sponsor a chance to correct any listing details immediately.

Right after sending the launch email, calendar a reminder for day 25.

At day 25, send Section 2 of `post_launch_comms.md` (the check-in). This email matters because it respects the money-back guarantee honestly instead of hiding behind billing timing. If a sponsor is unhappy, this is where you find out.

Track whether the sponsor reports any of: calls, mentions, walk-ins, messages, or "nothing yet."

At day 31, decide between continuation (Section 3a) and pause (Section 3b). Do not auto-renew emotionally checked-out sponsors just because they did not explicitly cancel.

---

## Section 8 — Tracking and metrics

Minimum spreadsheet columns:

- `business_name`
- `category`
- `owner_email`
- `sent_date`
- `last_status`
- `last_status_date`
- `hava_voice_description` (once written)
- `launch_date` (once live)
- `notes`

Keep the sheet clean. Do not use vague statuses like "maybe" or "working on it."

The main sprint KPI is response rate by category variant.

Sanity thresholds:

- Under 5% response after 20 sends in a category → rewrite the variant.
- Over 15% response → scale that category harder.

Do not assume all categories behave equally. Restaurants may respond differently than HVAC or boat repair. You are testing local operator language quality as much as you are testing sponsor appetite. The spreadsheet should make weak categories obvious quickly.

---

## Section 9 — Escalation triggers

Pause the sprint and reassess if any of the following happen:

- A sponsor reports a Hava-driven complaint or refund dispute.
- Multiple sponsors across categories report zero traction at day 25.
- Validator failures start happening on rows that should pass cleanly (signal of a schema drift).
- Ingest behavior drifts from README expectations.
- Sponsors consistently misunderstand the product positioning (signal that the cold-email variants need a structural rewrite, not just a per-category subject swap).

Otherwise, keep the sprint moving steadily without overreacting to isolated no replies.

---

## When the sprint completes

Once the 50-business verified batch is live, Phase 2.5 / `P2.PREM.1` becomes unblocked because there is enough real sponsor inventory to justify structured Spotlight rotation and premium placement behavior. The HALT 3 close criteria also becomes runnable because the catalog stops being hypothetical and starts reflecting real local supply. At that point, optimization work matters more than outreach volume, and the sprint shifts from enrichment into retention and search-quality tuning.
