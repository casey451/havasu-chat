# Post-enrichment smoke catalog — DISCLOSURE_RENDERER flag-flip validation

**Purpose:** This catalog is the operator-facing validation instrument for the day `FEATURE_FLAG_DISCLOSURE_RENDERER` flips from `false` to `true` in the production Railway environment. It complements (does not replace) `backlog_46_smoke_check_queries.md`, which validates the entity-matcher #46 ship. Where #46's catalog spot-checks the matcher's correctness on adversarial typos, this catalog spot-checks the renderer's behavior across the eligibility, regime-gating, tone, cache, and CT-composition surfaces called out in `disclosure_renderer_spec.md` §1–§5 and `confidence_tier_integration_spec.md` §3. This is **not** the HALT 3 confabulation harness: per `halt3_definition.md` §2, the harness measures the three close-criteria bands across populations, while this catalog spot-checks named queries against named expected behavior. The bands themselves are calibrated during HALT 3 close from baseline measurements and are not pre-stated here.

**When this catalog runs:** the morning of the flag flip, immediately after the Railway env-var change has propagated and the cache is in a known state (per §"Pre-flip preconditions" below). Run all classes top-to-bottom; record pass/fail in §"Pass/fail recording" at the bottom. If any Class A row fails (no sponsored block when one is expected) or any Class B/C/E row fails (sponsored block when one is forbidden), flip the flag back to `false` and investigate before re-attempting.

**Prerequisites (must all be true before this catalog has signal):**

- Operator enrichment sprint complete (per `halt3_definition.md` §6 step 1) — at minimum, **≥1 Sponsor row in `live` status with `active=true`** plus **≥1 matching `Provider` row** keyed by `Sponsor.business_id` exists in the production DB.
- Sponsor row populates the verified-fields the renderer reads (per `disclosure_renderer_spec.md` §2.2 SponsoredBlock body field constraints): `name`, `attribution_text`, `cta_label`, `cta_url`; ideally also `headline`, `pitch`, and a linked Provider's `years_in_business` / `hours` / `service_area` / `certifications`.
- Sponsor row's copy passes the tone allowlist (`disclosure_renderer_spec.md` §3.2). If the operator copy contains any disallowed phrase (`best`, `award-winning`, `highly recommended`, etc.), the renderer will return `None` and the catalog reads as a Class B/E miss even though the flag is on. Operators should pre-screen Sponsor copy against §3.2 before the flip.
- `FEATURE_FLAG_CONFIDENCE_TIER` is **on** (re-enabled 2026-05-09 evening per `halt3_definition.md` §3 footnote). Class G assumes both flags are on.
- Cache is flushed at flip time (or cache key includes the flag state). See Class F.
- Documented rollback plan: a single Railway env-var flip from `true` to `false` returns the renderer to dark and Tier 3 to its pre-flip code path (`disclosure_renderer_spec.md` §7.2 "Rollback").

**Companion docs:**
- `disclosure_renderer_spec.md` — what the renderer does and how eligibility is determined.
- `confidence_tier_integration_spec.md` — CT2.B hedge composition; the renderer and CT operate as independent gates on the same response.
- `halt3_definition.md` — the close-criteria framework that this catalog complements.
- `backlog_46_smoke_check_queries.md` — format reference; that catalog validates the entity-matcher ship.

---

## How to use

PowerShell — `Invoke-RestMethod` avoids the `curl.exe + $body` JSON-mangling bug (per Rule 4 of `dispatch_protocol.md`). The `; charset=utf-8` clause is mandatory; PowerShell's `-Body` defaults to ISO-8859-1 / Windows-1252 without it, which produces invalid UTF-8 bytes that Starlette rejects with HTTP 400 before any app code runs.

```powershell
Invoke-RestMethod -Method Post -Uri "https://havasu-chat-production.up.railway.app/api/chat" `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"query":"<paste query here>","session_id":"smoke-flip-<class>-<n>"}'
```

For each row, paste the `Query` value verbatim into the `<paste query here>` placeholder. Replace `[BUSINESS NAME]`, `[CATEGORY]`, `[SPONSOR_NAME]` placeholders with the actual enriched-catalog values **before** running the query (these placeholders flag rows that depend on enrichment data that won't exist until the sprint completes).

**Reading the response:** the disclosure word `Sponsored` is the canonical signal that the renderer fired. Look for the literal word `Sponsored` (with a capital S, no rephrasing — `Featured`, `Partner`, `Recommended`, `Spotlight` are all violations of `disclosure_renderer_spec.md` §4). The block format is approximately `Sponsored: [attribution]. [body] [CTA].` per §4 output template.

**Telemetry cross-check:** after each query, the row in `chat_logs` should have `disclosure_regime`, `disclosure_sponsor_id`, `disclosure_tone_allowlist_passed`, and `disclosure_eligible` populated per `disclosure_renderer_spec.md` §7.2 P2.OBS.1. A NULL on these columns when a Class A query was just posted indicates the renderer did not fire — investigate before attributing a behavioral pass to the response text alone.

---

## Pre-flip preconditions

Before posting any query in this catalog, confirm:

- `FEATURE_FLAG_DISCLOSURE_RENDERER` Railway env var is set to `true` and a deploy has propagated (check the Railway deploy log for restart timestamp; the var is read at module-load time).
- `FEATURE_FLAG_CONFIDENCE_TIER` is also `true` (Class G depends on this).
- `Sponsor` table has ≥1 row where `status='live' AND active=true` AND the booking window covers `now_lake_havasu()` (`starts_at <= now AND (ends_at IS NULL OR ends_at > now)`).
- That Sponsor's `business_id` resolves to a `Provider` row that exists and is reachable by the catalog query path the intent classifier routes to.
- The Sponsor's `attribution_text`, `headline`, and `pitch` fields contain no allowlist-violating phrases (a quick `grep -iE` against `disclosure_renderer_spec.md` §3.2 DISALLOWED_PHRASES on the operator-supplied copy).
- Cache state: either flush the chat-route cache at flip time or confirm the cache key includes the flag state (see Class F — this is the single most likely source of post-flip false negatives).
- Alembic head: confirm migrations for the four `chat_logs` disclosure-telemetry columns (`disclosure_regime`, `disclosure_sponsor_id`, `disclosure_tone_allowlist_passed`, `disclosure_eligible`) are at head. Without these columns the renderer still works but observability cross-check below is impossible.
- Production HEAD reflects Lane S2 + Lane X2 ship (the renderer module + the Tier 3 integration). Spot-check `app/chat/disclosure_render.py` exists and `app/chat/tier3_handler.py` imports from it.

---

## Class A — Renderer-on basic positive cases

These queries match Sponsor-eligible regimes (`GENERIC_CATEGORY` or `EMERGENCY_URGENT` per `disclosure_renderer_spec.md` §1), have at least one live Sponsor row matching, and have allowlist-clean copy. The renderer should fire and the response should contain the literal word `Sponsored`. If it doesn't, either the flag didn't take effect, the cache is serving a stale pre-flip response, no Sponsor row matches the inferred category, or the tone allowlist tripped on operator copy.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| A1 | `where can i grab coffee` | Sponsored block in response; `disclosure_word == "Sponsored"`; organic providers also listed (Regime B requires organic pairing); `chat_logs.disclosure_regime == "generic_category"` | Renderer is dark despite flag on; Regime B not wired | Canonical worked example from spec §1.2; assumes a `[CATEGORY=coffee]` sponsor exists. If no coffee sponsor, the response is organic-only — that's a no-op-due-to-inventory pass, not a fail. |
| A2 | `recommend a restaurant for dinner` | Sponsored block if a restaurant-category sponsor exists; allowlist-clean attribution | Generic-category dispatch fails to identify restaurant category | Sub-intent should classify as `RECOMMENDATION` per §1.2 triggering conditions. |
| A3 | `where do people go for nightlife` | Sponsored block if nightlife sponsor exists; organic alternatives also listed | DISCOVERY sub-intent not routed to Regime B | DISCOVERY is one of the three §1.2-listed sub-intents that triggers Regime B. |
| A4 | `any free kids activities this weekend` | Sponsored block from EMERGENCY_URGENT regime if a free-program sponsor with overlapping booking window exists; organic free programs also listed; suppression if no organic pair | EMERGENCY_URGENT temporal-overlap or organic-pairing gates broken | Canonical worked example from §1.3. Sponsor's `starts_at`/`ends_at` must overlap the query weekend. |
| A5 | `what gyms are around` | Sponsored block if fitness-category sponsor exists | GENERAL_QUESTION sub-intent + searchable category fails to route | Spec §1.2 lists `fitness` as a worked-example searchable category. |
| A6 | `tell me about [CATEGORY] in lake havasu` | Sponsored block keyed to `[CATEGORY]` if matching sponsor exists | Category extraction broken when query is templated | Replace `[CATEGORY]` with whatever category your Sponsor row covers. Tests that the renderer keys on inferred category, not query keyword match. |
| A7 | `looking for a good place to get tacos` | Sponsored block if a restaurant/Mexican sponsor exists; renderer must reject the LLM's natural inclination to use "good place" framing in the sponsored body itself | Sponsor body inherits user-query evaluative phrasing | The user's query contains "good" but the renderer's body should still be allowlist-clean (the body comes from Sponsor fields, not the query). |
| A8 | `any tours i should know about` | Sponsored block if tours-category sponsor exists | "tours" category mapping not in the §1.2 worked-example list | Spec §1.2 worked examples list `tours` explicitly; tests the inferred-category mapping. |

---

## Class B — Renderer-on but eligibility-blocked cases

These queries hit the renderer but should NOT produce a sponsored block: either the regime is `SPECIFIC_QUALITY` (zero sponsored allowed per §1.1), the tone allowlist trips on the candidate Sponsor's copy, no Provider row matches the Sponsor's `business_id`, or the Regime C organic-pairing requirement is unmet. Expected: response renders WITHOUT a sponsored block (clean fall-through to organic-only or Tier 1 deterministic). The `disclosure_eligible` telemetry column should be `false` for these (renderer ran, decided no).

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| B1 | `what are barley brothers hours` | No sponsored block. Tier 1 deterministic path returns the hours line. | SPECIFIC_QUALITY regime not gating sponsored | Canonical example from §1.1 worked example. HOURS_LOOKUP + entity resolved → SPECIFIC_QUALITY. Even if a coffee sponsor exists, none should appear. |
| B2 | `phone for [BUSINESS NAME]` | No sponsored block. Tier 1 returns the phone. | PHONE_LOOKUP not classified as specific-quality | Replace `[BUSINESS NAME]` with any enriched provider. |
| B3 | `address for [BUSINESS NAME]` | No sponsored block. | LOCATION_LOOKUP not gating sponsored | Same shape as B2; different sub-intent. |
| B4 | `is [BUSINESS NAME] open now` | No sponsored block. | OPEN_NOW not in the SPECIFIC_QUALITY allowlist | OPEN_NOW is one of the §1.1 sub-intents. |
| B5 | `website for [BUSINESS NAME]` | No sponsored block. | WEBSITE_LOOKUP not gating | |
| B6 | `where can i grab coffee` (with a Sponsor whose `attribution_text` contains the word `best`) | No sponsored block — renderer returns `None` per §3.4 because the tone allowlist trips on `best`. Response is organic-only. | Tone allowlist not enforced; LLM-rendered drift would produce a sponsored block anyway | Pre-flip, manually plant a sponsor row with disallowed copy in a non-prod-collision row to verify the gate. Document the row name in §"Open questions" if you don't pre-plant. |
| B7 | `recommend a [CATEGORY] place` where the Sponsor row has `business_id` set but the linked `Provider` is missing or soft-deleted | No sponsored block (renderer suppresses if linked Provider unresolvable). | Renderer doesn't validate the Provider link | Tests the §2.2 "linked `Provider` (if `business_id` is set)" join. |
| B8 | `free workshops next month` (where the only candidate Sponsor's booking window has already ended) | No sponsored block (Regime C temporal overlap fails per §1.3). | Renderer ignores `starts_at`/`ends_at` | Mirrors the spec test `test_regime_emergency_urgent_temporal_check`. |

---

## Class C — Renderer-on cross-category protection

Mirrors Lane 1 #47's cross-category guard but on the disclosure-render side. A Sponsor exists for category X; the user asks about category Y. Expected: no sponsored block. The renderer must key sponsor candidates to the inferred category from intent_result, not surface a category-X sponsor on a category-Y query.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| C1 | `where can i grab coffee` (when only Sponsor in DB is a fitness studio) | No sponsored block. Organic coffee alternatives only. | Renderer surfaces sponsor regardless of category match | The candidate-sponsor query in §5.2 already filters by status/active/booking-window; spec doesn't show category filter explicitly, so this row tests whether the dispatch site or `_pick_sponsor` performs category alignment. |
| C2 | `recommend a plumber` (when only Sponsor is in restaurants) | No sponsored block. | Cross-category leak on RECOMMENDATION sub-intent | High-stakes category (plumber) — leaking a restaurant sponsor here would be the worst-case failure. |
| C3 | `any tours around here` (when only Sponsor is in coffee) | No sponsored block. | Cross-category on DISCOVERY sub-intent | |
| C4 | `looking for boat repair` (when no boat-repair sponsor exists but other-category sponsors do) | No sponsored block. Organic-only. | Renderer fails open instead of returning None | High-stakes / emergency-adjacent category from `halt3_definition.md` §3's enrichment-priority list. |
| C5 | `urgent care nearby` (when no urgent-care sponsor exists, other-category sponsors do) | No sponsored block. | Cross-category leak on emergency-adjacent query | Per `halt3_definition.md` §1: "wrong emergency plumber recommendation at 11pm is not [recoverable]." Cross-category leak on urgent-care queries is the highest-severity failure mode in this catalog. |

---

## Class D — Multi-sponsor rotation

The spec resolves rotation deterministically: per `disclosure_renderer_spec.md` §2.1 `_pick_sponsor`, **highest weight first; ties broken by `created_at` (oldest first, stable sort)**. There is no random rotation, no round-robin, and no scored ranking — the same query will always surface the same sponsor for a fixed candidate set. This is by-design (§2.1 docstring: "Internal randomness is forbidden") to keep the renderer deterministic for the eval harness.

These cases test that the deterministic pick holds. Operators with multiple sponsors in the same category must understand that the lower-weighted / newer sponsor will never surface unless the higher-weighted / older one is taken out (deactivated, expired, or its tone allowlist trips). This is a product-policy issue, not a renderer bug — flag to advertisers ahead of the flip.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| D1 | `where can i grab coffee` (with two coffee sponsors A and B; A has higher weight) | Sponsored block surfaces sponsor A on every call. Sponsor B never appears while A is live. | Non-deterministic rotation; B leaks through | Run the same query 5×; expect identical sponsor across all 5. |
| D2 | `recommend a [CATEGORY] place` (two sponsors in `[CATEGORY]` with **equal weight**) | Sponsored block surfaces the older sponsor (lower `created_at`) on every call. | Tie-break ordering not stable | Per §2.1 "ties broken by `created_at` (oldest first, stable sort)." |
| D3 | `where can i grab coffee` (sponsor A live, deactivate A, query again) | First call surfaces A; second call (post-deactivation) surfaces B if B exists, else organic-only. | Inventory pre-filter (`status=live AND active=true`) not honored in candidate query | Tests the §5.2 candidate-sponsor SQL filter. |
| D4 | `recommend a [CATEGORY] place` (sponsor A's `ends_at` passes during the day) | Calls before `ends_at` surface A; calls after surface B (if any) or organic-only. | Booking-window filter not honored | The `ends_at > now()` clause in §5.2. |

**Open question for operators:** if you want round-robin or rotation, the spec does not provide it. File a follow-up if multi-sponsor inventory becomes the norm. See §"Open questions / spec ambiguities."

---

## Class E — Tone allowlist edge cases

These queries exercise the §3 tone allowlist gate. Most cases here require a planted Sponsor row whose `headline`, `pitch`, or `attribution_text` contains an allowlist-violating phrase. The renderer must return `None` (per §3.4) and the response must fall through to organic-only. The persona-brief blocklist in `prompts/tier2_formatter.txt` is a *separate* safety net on the LLM-organic side; this class tests the *deterministic* allowlist on the renderer side.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| E1 | `where can i grab coffee` (Sponsor `headline = "Best coffee in Lake Havasu!"`) | No sponsored block; renderer returns `None` per §3.4. | Allowlist regex misses `\bbest\b` | Mirrors `test_tone_allowlist_rejects_superlatives` from the spec. |
| E2 | `recommend a [CATEGORY] place` (Sponsor `attribution_text = "award-winning [CATEGORY]"`) | No sponsored block. | `\baward[-\s]?winning\b` regex misses | §3.2 disallowed list. |
| E3 | `where can i grab coffee` (Sponsor `pitch = "Locals' favorite spot"`) | No sponsored block. | `\b(customer\|local\|visitor)\s+favorite\b` regex misses | §3.2 evaluative-marketing class. |
| E4 | `any tours around here` (Sponsor `headline = "Limited time offer — book now!"`) | No sponsored block. | False-scarcity gate misses `\blimited\s+time\b` | §3.2 false-scarcity class. |
| E5 | `recommend a [CATEGORY] place` (Sponsor `pitch = "Better than the rest"`) | No sponsored block. | Comparative-language gate misses `\bbetter\s+than\b` | §3.2 comparative class. |
| E6 | `where can i grab coffee` (Sponsor copy is allowlist-clean BUT the LLM's surrounding organic prose contains "the best" because the user query bait-and-switched the LLM) | Sponsored block PRESENT (renderer's body is clean); organic LLM prose may contain "best" but that's the LLM-side persona-blocklist's responsibility, not the renderer's. | Test author confuses the two gates and fails the row | Documents the boundary: §3 governs the *rendered block's body and attribution*, not the surrounding LLM prose. |

---

## Class F — Cache invalidation across flag-flip

A query that hit cache pre-flip (renderer dark) returned a non-rendered response. Post-flip, the same query MUST return a NEW response with the sponsored block — not the cached pre-flip response. This is the single most likely source of false-negative reports on flip day.

The spec does not explicitly state cache-key composition. Inspect `app/chat/tier3_handler.py` for the cache key shape before the flip. If the cache key does not include the flag state (or a flag-state version stamp), the cache **must** be flushed at flip time.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| F1 | `where can i grab coffee` posted pre-flip (cache miss → cache write of organic-only response), then SAME query posted immediately post-flip | Post-flip response contains the sponsored block. | Cache key doesn't include flag state; pre-flip response served stale | The smoking-gun cache regression. If it fails, flush the cache and re-run; document the flush as a permanent step in the flip runbook. |
| F2 | Any Class A query, run 3× post-flip with the same `session_id` | First call may be cache miss; calls 2 and 3 hit cache; all three responses must contain the sponsored block. | Renderer output is not stable across cache hits (e.g., renderer fires only on miss path) | Per spec §5.2 the renderer runs before the cache lookup AND post-LLM-injection happens after — verify the inject path is also taken on cache hits if Lane X2's cache integration shipped. |
| F3 | `where can i grab coffee` post-flip with the renderer flipped back to OFF (rollback rehearsal) | Sponsored block disappears from the response. | Stale post-flip response served on rollback | Tests the rollback path described in `disclosure_renderer_spec.md` §7.2 — flip should be reversible. |

---

## Class G — CT + renderer interaction

Both `FEATURE_FLAG_CONFIDENCE_TIER` and `FEATURE_FLAG_DISCLOSURE_RENDERER` are independent gates that compose on the same response per `confidence_tier_integration_spec.md` §3.2.b. Specifically:
- Audience signal does not influence which hedge fragment applies (CT1 policy).
- The sponsored block body is constrained by the §3 tone allowlist and **never carries a freshness hedge** — hedges apply only to organic catalog rows.
- Composition order: organic LLM text (with inlined hedges per row) → sponsored block injection per regime rules.

These cases fire BOTH gates on the same response and verify that neither gate clobbers the other.

| # | Query | Expected behavior | Failure mode it tests for | Notes |
|---|---|---|---|---|
| G1 | `recommend a [CATEGORY] place` where the inferred category has (a) one live, allowlist-clean Sponsor with HIGH-confidence linked Provider AND (b) at least one organic Provider with a LOW-confidence row (e.g., `last_verified_at` 200 days ago) | Response contains: sponsored block (no hedge inside it) AND the LOW organic provider's mention with the inlined fragment `recommend calling to confirm` AND that provider's phone in the same or adjacent sentence (per §4 hard rule). | One gate suppresses the other; or the renderer's body inherits a freshness hedge | Mirrors `test_compose_with_disclosure_block_does_not_override_hedge` from the CT2.B spec. |
| G2 | `where can i grab coffee` where Sponsor links to a HIGH-confidence Provider AND organic providers are all HIGH-confidence | Sponsored block present; no `recommend calling to confirm` or `as of last week` fragments anywhere in the response. | Hedge leaks into the sponsored block body or onto HIGH-confidence organic rows | Locks the regression that CT2.A and X2 don't interact. |
| G3 | `recommend a plumber` where Sponsor has MEDIUM-confidence linked Provider (e.g., `last_verified_at` 14 days ago, scraper-method) AND no organic providers in DB | Response contains sponsored block (CT2.B does NOT hedge the sponsored block body). The `chat_logs` row should still record `disclosure_regime` and a CT-tier value separately. | Renderer's body inherits a `(as of last week)` suffix; or sponsored block is suppressed because no organic to pair with under Regime B | Trickier: under §1.2 Regime B "organic alternatives must accompany," a Sponsor with no organic peers MAY produce no sponsored block — verify the spec's intent here vs. spec §1.2 wording in §"Open questions." |
| G4 | `free kids activities this weekend` where Sponsor is a youth program (Regime C) AND organic free programs are LOW-confidence | Sponsored block present per Regime C; LOW hedge attaches to the organic free-program lines, not to the sponsored body. | Hedge attaches to time-sensitive sponsored block (worst-case voice failure) | Time-sensitive responses are exactly where a hedge on a sponsored block reads as broken trust. |

---

## Class H — Audience-signal regime selection (behavior-tracked, not pass-fail)

Per `disclosure_renderer_spec.md` §1 and `confidence_tier_integration_spec.md` §3.2.b.1, the audience-signal classifier (Lane S3, shipped) does NOT currently influence placement-regime selection. Threading audience signal into Regime selection is **deferred to Backlog #39** (Phase 2). For the flip-day catalog, these rows are documented for telemetry-tracking purposes only — they are NOT pass-fail rows.

Run them and record the response and the `chat_logs.audience_*` columns and `disclosure_regime` column for later analysis. If the audience-signal-driven Regime selection ships post-#39, this class becomes pass-fail at that point.

| # | Query | Expected behavior (today) | Failure mode it tests for | Notes |
|---|---|---|---|---|
| H1 | `where should i eat tonight` (visitor-leaning phrasing per audience-signal classifier) | Sponsored block whose selection is NOT influenced by audience-signal classification today; Regime selection is purely intent-driven. | A post-Backlog-#39 ship leaks into prod prematurely | Record `chat_logs.audience_status` + `disclosure_regime` for tracking. |
| H2 | `where do locals eat` (local-leaning phrasing) | Same Regime selection as H1 if the inferred category is the same. | Audience signal accidentally influences the candidate-sponsor pool | Compare H1 vs H2 — same sponsor should surface; if different, file as #39 surface area. |
| H3 | `vacation rentals downtown` (visitor-leaning) | Regime B sponsored block if a vacation-rentals sponsor exists; regime selection independent of audience signal. | | Vacation-rentals is a high-visitor-skew category; useful for Backlog #39 telemetry. |
| H4 | `is there a pharmacy nearby` (audience-neutral) | Regime selection per intent; SPECIFIC_QUALITY-adjacent if the user has a specific pharmacy in mind, else GENERIC_CATEGORY. | Audience-neutral query mistakenly classified as visitor-leaning | Useful audience-signal sanity check on a category that doesn't skew. |

---

## Post-flip verification

After running all classes, confirm:

- `chat_logs` table: rows from this catalog are present; `disclosure_regime`, `disclosure_sponsor_id`, `disclosure_tone_allowlist_passed`, and `disclosure_eligible` columns are populated for queries that hit Tier 3 with the renderer enabled (per `disclosure_renderer_spec.md` §7.2 P2.OBS.1).
- Class A queries' chat_logs rows have `disclosure_eligible=true` AND `disclosure_tone_allowlist_passed=true` AND a non-NULL `disclosure_sponsor_id`.
- Class B/C queries' chat_logs rows have `disclosure_eligible=false` OR a NULL `disclosure_sponsor_id` (renderer ran, decided no).
- Class E queries' chat_logs rows have `disclosure_tone_allowlist_passed=false` for the planted-disallowed-copy cases.
- No HTTP 5xx responses from any catalog query (sample the Railway logs for the catalog session_ids).
- No spike in `app/chat/tier3_handler.py` exception rate on the flip-day Railway log dashboard.
- Cache write-side (whatever store the chat-route cache lives in) has new entries with `Sponsored:` substrings inside cached values for Class A queries.
- The `DISCLOSURE_WORD = "Sponsored"` literal appears in every Class A response — not `Featured`, not `Partner`, not `Recommended`. A grep across all Class A responses for `(?i)(featured|partner|recommended|spotlight)` should return zero hits inside the disclosure-positioned line.
- Tier 1 deterministic path (Class B1–B5) responses do NOT contain `Sponsored` anywhere.
- For Class G rows, manually inspect that the renderer's body is hedge-free and that any LOW hedges attach to organic rows only.

If any of the above fail, flip the flag back to `false`, capture the failing chat_logs rows + raw responses in a Backlog ticket, and re-investigate before re-attempting.

---

## Open questions / spec ambiguities

These are flagged for Casey's call before the flip — the spec does not resolve them, and the catalog rows above make assumptions worth confirming.

1. **Catalog terminology vs. spec terminology.** The dispatch brief referred to placement regimes `LISTING` and `SHORT_ANSWER`. The spec (`disclosure_renderer_spec.md` §2.1 `PlacementRegime` enum) defines exactly three values: `SPECIFIC_QUALITY`, `GENERIC_CATEGORY`, `EMERGENCY_URGENT`. This catalog uses the spec's enum names. If `LISTING`/`SHORT_ANSWER` reflect a newer regime split that has not landed in `disclosure_render.py`, this catalog will need a revision pass once that ship lands.

2. **Category alignment of candidate sponsors (Class C).** §5.2's candidate-sponsor query filters by `status='live'`, `active=true`, and booking window. It does **not** show an explicit category filter. Class C assumes cross-category leakage is gated somewhere (`_pick_sponsor` or the dispatch site), but the spec does not name where. Inspect the implementation before the flip — if there is no category gate, Class C will systematically fail and the flip should be deferred until a category filter is added.

3. **Multi-sponsor rotation policy (Class D).** Spec §2.1 prescribes deterministic pick (weight DESC, created_at ASC). Operators with multiple sponsors per category should understand that lower-weighted / newer sponsors **never** surface unless the leading sponsor is taken down. If this is unintended product behavior, file a follow-up spec for weighted-rotation. Catalog assumes deterministic-pick is the desired behavior.

4. **Regime B "organic required" wording (Class G3).** §1.2 says "organic catalog rows must be returned alongside the sponsored block." It does not specify whether the renderer suppresses the sponsored block when zero organic rows are available, or whether it surfaces the sponsored block regardless and lets the formatter render organic-empty prose alongside. Spec §1.3 explicitly suppresses for Regime C ("If no organic rows exist, sponsored block is suppressed"); §1.2 does not. Resolve before the flip.

5. **Cache key composition (Class F).** Spec does not state whether the chat-route cache key includes flag state. If it does not, the flip-day runbook MUST include a cache flush. Class F1 is the regression-detection row for this; verify before the flip rather than discovering the issue post-flip when responses report stale.

6. **CT2.B ship status as of flip day.** This catalog assumes CT2.B (Tier 3 context-block hedge suffix) has shipped per `confidence_tier_integration_spec.md` §3 and is gated on `FEATURE_FLAG_CONFIDENCE_TIER`. If CT2.B has not shipped at flip time, Class G3/G4 fall through to "no hedge anywhere" rather than "hedge on organic, none on sponsor," and the failure mode they test for is different. Confirm CT2.B status before running Class G.

7. **Audience-signal regime selection ship status (Class H).** Class H is documented as "behavior-tracked, not pass-fail" because Backlog #39 (audience-signal-driven regime selection) is deferred to Phase 2. If #39 ships before this catalog runs, promote Class H to pass-fail and tighten the expected-behavior column.

8. **Tone allowlist case-sensitivity (Class E).** §3.3 uses `re.IGNORECASE` so case should not matter, but operators planting test sponsors with mixed-case copy (`"BEST"`, `"Best"`, `"best"`) should all trip the gate. If any case-variant slips, file as a regex bug in `DISALLOWED_PHRASES`.

---

## Pass/fail recording

After running this catalog, record results as one line per query:

```
A1 where can i grab coffee → PASS (sponsored block: "Sponsored: [SPONSOR_NAME] — local coffee roaster. ...")
A2 recommend a restaurant for dinner → FAIL (no sponsored block; chat_logs.disclosure_regime=NULL — renderer did not fire)
B1 what are barley brothers hours → PASS (Tier 1 path, no sponsored block as expected)
F1 cache regression → FAIL (cache served pre-flip response; cache flushed manually; re-run passed)
```

If any Class A row FAILS (no sponsored block when one is expected) AND the failure is not attributable to "no sponsor in that category exists yet" → flip the flag back to `false` and investigate. Cache regression (Class F) and cross-category leak (Class C, especially C4/C5) are high-severity; file Backlog tickets immediately.

If every Class A passes, every Class B/C/E suppresses, Class D is deterministic, and Class F survives flag toggling → the flip is validated and ready for the 1-week observation window before HALT 3 baseline run (per `halt3_definition.md` §6 step 3).
