# Confidence-Tier Formatter Integration — Phase 1 Keystone Spec (Lane CT2)

**Status:** OPEN — implementation not started
**Source of truth for:** wiring the Lane CT1 confidence-tier classifier into the formatter call chain so factual answers register at the freshness of the underlying record
**Audience:** any agent (Cowork / Claude Code / Cursor) executing the CT2 sub-slices
**Companion docs:** `ui_data_correctness_spec.md` §1.2 (the canonical confidence-band policy table), `disclosure_renderer_spec.md` (feature-flag pattern, X2 file-conflict precondition), `persona-brief.md` §4.3 / §6.7 / §8.1 (voice rules), `HAVA_CONCIERGE_HANDOFF.md` §3 (tiered routing)

**Lessons learned (parallel-agent coordination):** the `ui_data_correctness_spec.md` lead-in documented the chaos that follows when multiple agents `Write` the same file. CT2 inherits that convention: anchored `Edit` only on shared files (`tier2_formatter.py`, `tier3_handler.py`, `prompts/tier2_formatter.txt`); reports come back as text for the primary to integrate into `BACKLOG.md` / `STATE.md`. `Write` is reserved for the new test files (`tests/test_confidence_tier_integration_tier2.py`, `tests/test_confidence_tier_integration_tier3.py`) which are net-new and own no shared surface.

---

## 0. Why this spec exists

The Lane CT1 classifier (`app/chat/confidence_tier.py`, shipped 2026-05-08) turns a duck-typed record into a `ConfidenceAssessment` carrying tier (`HIGH` / `MEDIUM` / `LOW`), age in days, verification method, and a one-line rationale. It also exposes `hedge_phrase(tier)` returning the canonical fragment per tier (`""` / `"as of last week"` / `"recommend calling to confirm"`). CT1 owns the policy. **It is shipped and frozen.** CT2 does not propose changes to it.

What CT1 does not do: surface the assessment in the chat output. The formatter still produces the same prose regardless of whether the underlying row was owner-confirmed yesterday or scraped a year ago. Two failure modes follow:

1. **Confident voice on stale data.** Hava says *"they're open until 6"* when the row's `last_verified_at` is six months old and the verification method is `scraper`. The user drives across town to a closed business. Trust degrades on the first mismatch and rarely recovers.
2. **Hedged voice on fresh data.** Hava says *"recommend calling to confirm"* on an owner-confirmed-yesterday row. The user reads the hedge as FUD, the recommendation feels weak, and the bot's value as a local concierge erodes from the opposite direction — too much hedging is as bad as too little.

CT1 solved the policy. CT2 surfaces it at the formatter boundary so the bot's register matches the data's freshness. Concretely: the LLM-formatter prompt receives a per-row `confidence_hint` field; the prompt instructs the LLM to inline the canonical fragment near any fact drawn from that row; the deterministic event renderer is unchanged; Tier 3 picks up the same threading after Lane X2 lands.

---

## 1. Two integration sites

The classifier wires into two LLM-driven formatter paths. The deterministic event renderer (`tier2_catalog_render.py::render_tier2_events`) is **out of scope** because it does not currently surface verification status — adding that would change its contract (see §5).

The two sites are split into independent sub-slices:

| Sub-slice | Surface | File | Precondition |
|---|---|---|---|
| **CT2.A** | Tier 2 LLM-formatter path (mixed / non-event rows) | `app/chat/tier2_formatter.py`, `prompts/tier2_formatter.txt` | None — Lane CT1 shipped; no other lane edits these files |
| **CT2.B** | Tier 3 handler synthesis path | `app/chat/tier3_handler.py` (or `app/chat/context_builder.py`, see §3) | Lane X2 must close first to avoid file-write conflict on `tier3_handler.py` |

CT2.A ships first and is independent. CT2.B opens only after Lane X2 closes (the disclosure-renderer Tier 3 integration that already touches `tier3_handler.py`).

---

## 2. CT2.A — Tier 2 LLM-formatter integration

### 2.1 Current behavior

`app/chat/tier2_formatter.py::format()` (lines 129–158) does three things in order:

1. Strip legacy fallback prefixes from each row's `description` (`_strip_legacy_fallback`).
2. If `rows` is empty, return `EMPTY_CATALOG_MESSAGE`.
3. Dispatch:
   - All rows are `type == "event"` → call `tier2_catalog_render.render_tier2_events(query, rows)` (deterministic, zero formatter tokens).
   - Otherwise → call `_format_via_llm(query, rows)` which serializes rows as JSON, prepends the system prompt at `prompts/tier2_formatter.txt`, and calls the OpenAI chat-completions wrapper. The returned text is post-processed by `_inject_event_url_links` to guarantee event-URL link emission.

The LLM path is the integration site. Today, no row carries verification metadata into the prompt; the LLM has no way to choose register based on freshness even if the persona brief instructed it to.

### 2.2 Target behavior

**Per-row classification, then per-row hint annotation, then unchanged dispatch.** The classifier is called once per row before the LLM serializer runs; each row dict gains a single string field; the prompt is updated to instruct the LLM how to read it.

**(a) Classification step.** Inside `format()`, immediately after the `_strip_legacy_fallback` pass and before the empty/all-event dispatch checks, compute the assessment per row and store the canonical hedge fragment under a new `confidence_hint` key. The classifier accepts duck-typed records, but `format()` receives row *dicts* (not ORM objects); the spec accommodates both:

- Pass each row dict directly to `classify_confidence(row, now=now_lake_havasu())`. The classifier reads `last_verified_at` and `verification_method` via `getattr`, which on a dict returns `None` (defensive, classifier branches to LOW with `rationale="no verification record"`). For rows that don't carry these keys (legacy callers, hand-built fixtures), the assessment is LOW with no age and the hedge fragment is `"recommend calling to confirm"`. **This is the wrong default** for a row that was never expected to carry verification metadata, so the integration adds a small adapter (§2.3.b) that distinguishes "row carries metadata explicitly" from "row never had the field".
- Compute `confidence_hint = hedge_phrase(assessment.tier)`. HIGH → `""`, MEDIUM → `"as of last week"`, LOW → `"recommend calling to confirm"`.

**(b) Threading into the prompt.** The row dict gains `confidence_hint`. Two design options were considered:

- **Option 1 — per-row annotation (RECOMMENDED).** Each row dict the formatter passes to the LLM gains a `confidence_hint: str` field. The LLM is instructed (via prompt update) to inline the hint when it surfaces a fact from that specific row. HIGH rows have empty hints and need no hedge; mixed rows produce mixed register without forcing the whole response into the worst tier.
- **Option 2 — aggregate band on the prompt.** Compute the worst tier across all rows and prepend one hedge to the system prompt context. Simpler to reason about, but loses per-row resolution: a single LOW row collapses an otherwise-HIGH response into a hedged one, which is exactly the "hedged voice on fresh data" failure mode in reverse.

**Recommended: Option 1.** Per-row resolution preserves voice: a fresh row reads plainly while a stale row carries the appropriate hedge. The LLM prompt update is a single-line EXCEPTION clause analogous to the event-URL markdown exception (Backlog #5 close). The cost is one extra string per row in the JSON payload — a few bytes — and one extra prompt instruction. The benefit is that mixed responses register correctly per fact rather than at the lowest common denominator.

**(c) Prompt update.** `prompts/tier2_formatter.txt` gains a single instruction in the "Grounding guardrails" or "Format" block. Suggested wording (the precise edit anchor is the formatter agent's call, but the contract is the same):

> When a row carries `confidence_hint` and the hint is non-empty, inline the hint near any fact you surface from that row — once is enough; do not repeat it across multiple sentences about the same row. HIGH rows have an empty hint and need no hedge; speak plainly. The hint is a fixed fragment — use it verbatim, do not rephrase or expand it.

The instruction is structural, not voice-bearing. The persona brief (§4.3, §6.5, §8.1) governs whether a hedge gets used in any given response; the formatter's only job is to make the canonical fragment available to the LLM as a verbatim string.

**(d) Defensive read.** If a row dict doesn't carry `confidence_hint` (legacy callers, future row producers that don't know about CT2), the LLM-side prompt instruction is a no-op: there's nothing to inline. The formatter's classification step itself is wrapped in a feature-flag check (§2.3.c) so the legacy behavior is byte-identical when the flag is off. Mirrors the X1 / CT1 / S3 defensive pattern: orthogonal signals add fields, never mutate or remove.

**(e) Feature flag.** New env var `FEATURE_FLAG_CONFIDENCE_TIER` (default unset). Scoped exactly like `FEATURE_FLAG_DISCLOSURE_RENDERER` (`app/chat/disclosure_render.py::FEATURE_FLAG_ENV_VAR`):

- When unset or anything other than `"true"` (case-insensitive) → classification is skipped, no `confidence_hint` field is added, the prompt instruction (which references a possibly-absent field) is a no-op. Tier 2 output is byte-for-byte identical to today.
- When `=true` → classification runs per row, the field is added, the prompt instruction takes effect, the LLM has the data it needs to register correctly.

The check lives in a small helper (`is_confidence_tier_enabled() -> bool`) defined in `app/chat/confidence_tier.py` (CT1 module) so other call sites in CT2.B can reuse it without re-importing the env-var name. **This is the only addition CT2 makes to the CT1 module — a single helper that reads the env var. CT1's policy and dataclass surface are not touched.**

### 2.3 File-level changes

| File | Change |
|---|---|
| `app/chat/confidence_tier.py` | Add `FEATURE_FLAG_ENV_VAR = "FEATURE_FLAG_CONFIDENCE_TIER"` constant and `is_confidence_tier_enabled()` helper. Pure additive; mirrors `disclosure_render.py:50,177–179`. |
| `app/chat/tier2_formatter.py` | In `format()`, between the `_strip_legacy_fallback` pass (lines 134–139) and the empty-rows check (line 141), insert a feature-flagged classification loop that annotates each row with `confidence_hint`. The all-event deterministic path is unchanged (§5 explains why). The LLM path serializes the annotated rows as before — the annotation rides along inside the existing JSON payload at no structural cost. |
| `prompts/tier2_formatter.txt` | Add a single EXCEPTION-style clause per §2.2.c. Anchor near the existing event-URL exception or the grounding guardrails block. |
| `tests/test_confidence_tier_integration_tier2.py` | New test file per §6. |

**No changes to `tier2_catalog_render.py`.** The all-event renderer doesn't surface verification status and is out of scope (§5).

**No changes to `tier2_handler.py`.** The handler calls `tier2_formatter.format(q, rows)` and is agnostic to whether rows carry annotations.

### 2.4 Worked example

Before CT2.A:

```
Query: "Who's a good plumber?"
Rows: [
  { "type": "provider", "name": "Acme Plumbing", "phone": "(928) 855-1234",
    "last_verified_at": "2026-05-07", "verification_method": "owner_confirmed" },
  { "type": "provider", "name": "Bayview Plumbing", "phone": "(928) 855-5678",
    "last_verified_at": "2025-09-14", "verification_method": "scraper" }
]
LLM output (illustrative):
"Two solid bets: Acme Plumbing at (928) 855-1234 or Bayview Plumbing at (928) 855-5678."
```

After CT2.A (flag on):

```
Rows passed to LLM (annotated):
[
  { "type": "provider", "name": "Acme Plumbing", ..., "confidence_hint": "" },
  { "type": "provider", "name": "Bayview Plumbing", ..., "confidence_hint": "recommend calling to confirm" }
]
LLM output (illustrative; persona brief governs the surrounding prose):
"Two solid bets: Acme Plumbing at (928) 855-1234, or Bayview Plumbing at (928) 855-5678 — recommend calling to confirm."
```

The hedge attaches to Bayview, not to Acme, because the LLM read the per-row hint. Voice continuity is preserved by the persona brief; the formatter's job is only to make the canonical fragment available verbatim.

---

## 3. CT2.B — Tier 3 handler integration

### 3.1 Current behavior

`app/chat/tier3_handler.py::answer_with_tier3()` (lines 184–319) builds context via `app.chat.context_builder.build_context_for_tier3(query, intent_result, db)` (line 248), prepends a classifier block + `now_line` + audience-bias-derived user-context line + local-voice blurbs, calls the LLM, post-processes via `strip_soft_suggest`, writes to the cache, and returns. Lane X2 has additionally landed a disclosure-renderer hook (lines 211–218, 244–245) that runs before the cache lookup and injects a sponsored block on cache hits and at the end of the LLM path.

### 3.2 Target behavior

The same composition as CT2.A: per-row classification → hint annotation → context-block inclusion. Three notable differences from CT2.A:

**(a) The annotation site is `context_builder.py`, not `tier3_handler.py`.** The handler does not see catalog rows directly — it receives an `IntentResult` and asks `build_context_for_tier3` to produce a plain-text context block from `Provider`, `Program`, and `Event` ORM rows. That's where each row's `last_verified_at` and `verification_method` are available. Two cleaner-site options:

- **Option B1 (RECOMMENDED): annotate in `context_builder.py`.** Inside the existing per-provider / per-event rendering, after fetching the row, classify it and append the hedge fragment to the row's textual rendering — e.g., for a provider line, append `" (recommend calling to confirm)"` when LOW, `" (as of last week)"` when MEDIUM, nothing when HIGH. The annotation is a textual suffix on the context line, not a JSON field, because Tier 3's context block is plain prose.
- **Option B2: annotate in the handler after the context block is built.** Re-derive the assessments by re-querying the DB. Wasteful — duplicates the work `context_builder` already did and reintroduces the timing-skew risk that CT1's `now` parameter was designed to prevent.

**Recommend B1.** The classification lives next to the row read; the hint appears in the context block as a parenthetical suffix; the LLM reads the suffix as part of the catalog context and inlines it (or doesn't) per the system-prompt instruction. The `tier3_handler.py` edit is then minimal — a feature-flag check and (optionally) an instruction line in the system prompt that mirrors the Tier 2 prompt's EXCEPTION clause.

**(b) Composition with audience signal and disclosure block.** Three orthogonal request-boundary signals already run in this path:

1. **Audience signal** (Lane S3) — computed in the unified router, persisted on the chat log, currently does not feed into the Tier 3 context. Threading this into Tier 3 is *Backlog #39* (deferred to Phase 2). CT2.B does not depend on it.
2. **Disclosure block** (Lane X2) — computed before the cache lookup, conditionally injected after the cache write or onto the cache hit. CT2.B's confidence hint is on the *organic* part of the response (the catalog facts the LLM is paraphrasing) and does not duplicate, override, or compete with the sponsored block. Ordering is independent: the sponsored block is a separate string concatenated onto the response; the hedge fragment is inlined within the LLM's organic prose.
3. **Confidence-tier hint** (CT2.B, this slice) — computed inside `context_builder.py` per row, surfaces as a suffix on each row's text in the context block.

The contract: each signal annotates orthogonally and never mutates the others. Specifically:

- Audience signal does not influence which hedge fragment is selected. CT1's policy is purely freshness × method.
- Disclosure block formatting (the sponsored line itself) is not subject to confidence-tier hedging. The sponsored block is rendered deterministically by `disclosure_render.py`; its body is constrained by the tone allowlist and never carries a freshness hedge. Hedging applies to organic catalog rows only.
- The final response composition order is: organic LLM text (with inlined hedges) → sponsored block injection (per `_inject_sponsored_block` regime rules). No re-ordering needed.

**(c) Precondition — Lane X2 must close first.** Lane X2 is currently editing `tier3_handler.py` to wire the disclosure renderer into the call chain. CT2.B's edits to the same file would conflict with X2's in-flight `Edit` operations. CT2.B does not open until X2's ship lands. This is a **hard sequencing constraint**, not a soft one — the lessons-learned banner at the top of `ui_data_correctness_spec.md` documents what happens when concurrent agents touch the same file.

The CT2.B agent must, as the first step, verify that `tier3_handler.py`'s X2 surface is stable (the `disclosure_render` import, `_format_sponsored_block`, `_inject_sponsored_block`, `_maybe_render_sponsored_block`, and the `is_renderer_enabled()` gate are all present and unchanged from the X2 ship-log description). Only then may the CT2.B agent open its anchored `Edit` on `context_builder.py` and (if needed) `tier3_handler.py`.

### 3.3 File-level changes (CT2.B)

| File | Change |
|---|---|
| `app/chat/context_builder.py` | Inside the per-row provider / event / program rendering, classify each row via `classify_confidence(row, now=now_lake_havasu())`, gate on `is_confidence_tier_enabled()`, and append `f" ({hint})"` where `hint = hedge_phrase(assessment.tier)` and `hint != ""`. The append happens once per row, on the row's primary line, not on every detail line. The classifier import is the only new import. |
| `app/chat/tier3_handler.py` | (Optional, single line) — if the system prompt is rewritten to instruct the LLM on the hedge-fragment shape, anchor that update here or in `prompts/system_prompt.txt`. The cleaner site is the prompt file; the handler edit is then zero. |
| `prompts/system_prompt.txt` | (Optional) — single EXCEPTION-style clause analogous to Tier 2's: "When a context line ends with a parenthetical hedge fragment (e.g., `(recommend calling to confirm)`), inline that fragment near the fact you surface from that row, verbatim. HIGH rows carry no parenthetical; speak plainly." |
| `tests/test_confidence_tier_integration_tier3.py` | New test file per §6. |

**No changes to `audience_signal.py` or `disclosure_render.py`.** Those modules own their own surfaces; CT2.B composes alongside them, not into them.

---

## 4. Voice rules and persona-brief alignment

CT1's `hedge_phrase()` returns deliberately short, non-evaluative fragments (see `tests/test_confidence_tier.py::test_hedge_phrase_medium_short_and_factual` — assertions exclude `best`, `amazing`, `perfect`, `incredible`, `favorite`). The CT2 contract is: **the formatter inlines the canonical fragment verbatim. It does not generate new prose around the hedge, and the LLM is instructed not to rephrase or expand it.**

**Specific persona-brief alignment:**

- **§4.3 (Delivery):** Hava speaks in contractions, short sentences, no filler. The MEDIUM hedge `"as of last week"` and the LOW hedge `"recommend calling to confirm"` are both four words or fewer and carry no filler. They drop into a sentence without re-shaping it.
- **§6.5 (Stale-data hedge):** the existing example phrasing — *"Been a while since I was by — check their hours before you drive out."* — is a Tier 3 voice illustration, not the canonical fragment shape CT1 ships. CT1's `"recommend calling to confirm"` is **more compact** and **less first-person**; it composes into either Tier 2 (no Hava-voice framing) or Tier 3 (Hava-voice framing supplied by the surrounding LLM prose). The LOW hedge does not replace §6.5's voice example; it is the deterministic fragment the LLM has access to when the prompt instructs it to inline a hedge.
- **§6.7 (Voice across curated and bulk-imported providers):** the framing-vs-specifics split applies. Confidence hedges attach to the *specifics* layer (factual claim drawn from the row), not the framing layer. A landscape framing line is never hedged.
- **§8.1 (Hard language blocklist):** the canonical fragments do not contain any blocklist phrase, and the LLM is forbidden from rephrasing them — this means the blocklist cannot leak in via a confidence hedge.

**Hard rule — LOW hedge requires phone, when one exists.** When the formatter inlines `"recommend calling to confirm"` for a LOW row, it must inline a phone number from the row in the same sentence (or in an immediately adjacent sentence) when the row carries one. A LOW hedge without a phone reads as deflection — *"recommend calling to confirm"* with no number to call is the worst of both worlds. The LLM's prompt instruction calls this out explicitly:

> When inlining the LOW hedge fragment ("recommend calling to confirm"), ensure the row's phone number appears in the same sentence or the immediately adjacent sentence. If the row has no phone, fall back to the row's website URL or to "no phone on file" — never leave the hedge as a bare directive.

The persona brief governs whether this is composed as one sentence or two; the formatter's job is to make the data available so the persona brief's voice can carry it.

**Dispatcher's note on the existing §6.5 example.** The §6.5 voice example *"Been a while since I was by — check their hours before you drive out."* remains the persona brief's canonical Hava-voice rendering of a stale-data response. CT1's `"recommend calling to confirm"` is the **deterministic fragment** the LLM has access to inside the response prose; the persona brief's framing wraps it. These are not in competition — they operate at different layers.

---

## 5. Out of scope (do not expand)

- **Per-record age-aware hedge variance.** CT1's `ConfidenceAssessment` carries `age_days`; CT2 does not vary the hedge fragment based on it. The MEDIUM hedge is `"as of last week"` regardless of whether the row is 8 days or 28 days old. Future spec may introduce age-aware variance ("verified yesterday", "verified two weeks ago"); that is a separate ship.
- **Confidence-tier annotation on `tier2_catalog_render.py` (the deterministic event renderer).** The renderer currently produces sentences like *"Boat Race on May 9, 2026 from 6:00 AM to 9:00 AM at London Bridge."* — entirely fact-shaped, no verification surface. Adding a hedge would change the renderer's output contract; that is a separate ship and not part of CT2. (Events also have a different freshness profile — most are date-bound; once the date is past, the row is filtered out by the tier-2 query, not hedged. The renderer's failure modes are different from the LLM-formatter's.)
- **Aware/naive datetime mismatch fix on `Provider.last_verified_at` and `Event.last_verified_at`.** CT1 currently catches the `TypeError` from subtracting a naive DB column from a timezone-aware `now_lake_havasu()` and falls through to LOW with `rationale="no verification record"` — defensive but lossy. Fixing the schema (adding `timezone=True` to the DateTime columns in `app/db/models.py` and a small Lane S1.1 migration to convert existing rows) is a tracked dependency for CT2's full effectiveness, but it is **not** in CT2's scope. Cross-reference: BACKLOG follow-up filed under the CT1 ship-log (item 1 of CT1's open questions).
- **LLM rephrasing of hedge fragments.** Disallowed. The canonical fragment is the contract: prompt instructions explicitly forbid rephrasing or expansion. If the LLM substitutes "you might want to give them a ring" for "recommend calling to confirm", the customer-service-blocklist phrase (`prompts/tier2_formatter.txt` §35–43) catches it — but the prompt-side defense is the spec; the blocklist is the safety net.
- **Threading audience signal into hedge selection.** Audience signal does not influence which hedge applies (a stale row is stale regardless of who's asking). Audience-driven adjustments to placement-regime selection are *Backlog #39* (Phase 2).
- **Surfacing CT1's `rationale` field to end users.** `rationale` is debug-grade prose for admin audit trails (see `tests/test_confidence_tier.py::test_assessment_rationale_is_short_string`). It is not surfaced in chat. Out of scope.

---

## 6. Eval harness extension

Two new test files. The unit tests in `tests/test_confidence_tier.py` (256 lines, 22 cases — all green per CT1 ship-log) cover the classifier in isolation. The integration tests below cover the formatter wiring and must not duplicate that coverage.

### 6.1 CT2.A integration tests — `tests/test_confidence_tier_integration_tier2.py`

| Test | Setup | Expected |
|---|---|---|
| `test_high_row_passes_through_unchanged` | Single provider row, `last_verified_at` = today, `method` = `owner_confirmed`. Flag on. | Formatter output contains the row's name, phone, no hedge fragment. `confidence_hint == ""` on the row dict the LLM saw. |
| `test_low_row_surfaces_recommend_calling_fragment` | Single provider row, `last_verified_at` 200 days ago, `method` = `manual`. Flag on. | Formatter output contains `"recommend calling to confirm"` and the row's phone. |
| `test_medium_row_surfaces_as_of_last_week_fragment` | Single provider row, `last_verified_at` 14 days ago, `method` = `scraper`. Flag on. | Formatter output contains `"as of last week"`. |
| `test_low_row_with_missing_phone_falls_back_to_url` | LOW row, no phone, has website. Flag on. | Formatter output contains the LOW hedge **and** the website URL in the same response — never a bare hedge with no actionable target. |
| `test_low_row_with_no_phone_or_url_emits_no_phone_on_file` | LOW row, no phone, no website. Flag on. | Formatter output contains the LOW hedge and either "no phone on file" or omits the call-to-action entirely (per the hard rule in §4). |
| `test_mixed_rows_register_per_row` | Two rows: one HIGH (Acme), one LOW (Bayview). Flag on. | Acme is mentioned without hedge; Bayview is mentioned with the LOW fragment. |
| `test_flag_off_byte_identical_to_today` | Same mixed input as above. Flag off (env var unset). | Formatter output is byte-for-byte identical to the pre-CT2 path. Locks the regression. |
| `test_legacy_row_dict_without_verification_fields` | Row dict missing `last_verified_at` and `verification_method` keys. Flag on. | Classifier defaults to LOW; row gains a LOW hint. (Documents the behavior — see §2.2.a discussion of duck-typed reads on dicts.) |
| `test_all_event_rows_use_deterministic_path_unchanged` | All rows are `type=event`. Flag on. | Output equals `tier2_catalog_render.render_tier2_events(query, rows).strip()` exactly. The classification step ran (rows have `confidence_hint`) but the deterministic renderer ignores it. |
| `test_classifier_called_once_per_row_with_now_lake_havasu` | Mock `classify_confidence`. Flag on. | Called once per row, with `now=` kwarg passed (verified via call args). No accidental clock skew across rows in a single response. |

### 6.2 CT2.B integration tests — `tests/test_confidence_tier_integration_tier3.py`

| Test | Setup | Expected |
|---|---|---|
| `test_high_provider_context_line_unchanged` | Provider with HIGH assessment. Flag on. | Context block line for that provider has no parenthetical hedge appended. |
| `test_low_provider_context_line_carries_hedge` | Provider with LOW assessment. Flag on. | Context block line ends with ` (recommend calling to confirm)`. |
| `test_medium_provider_context_line_carries_hedge` | Provider with MEDIUM assessment. Flag on. | Context block line ends with ` (as of last week)`. |
| `test_flag_off_context_block_byte_identical` | Mixed assessments. Flag off. | Context block is byte-for-byte identical to the pre-CT2.B output. |
| `test_compose_with_audience_signal_does_not_override_hedge` | Onboarding hints set `visitor_status=visiting`; row is LOW. Flag on. | Context block carries the LOW hedge; the user-context bias line is also present; neither is dropped or duplicated. |
| `test_compose_with_disclosure_block_does_not_override_hedge` | `FEATURE_FLAG_DISCLOSURE_RENDERER=true`; eligible sponsor; rows are LOW. Both flags on. | Final response carries the sponsored block (per X2 logic) AND the LOW hedge inline in the organic body. The sponsored block body itself does not carry a freshness hedge. |
| `test_event_rows_in_tier3_context_carry_hedge_when_low` | Event with LOW assessment in the context block. Flag on. | Event context line carries the hedge suffix. |

### 6.3 Prompt regression — golden file

A golden-file test pinned in `tests/fixtures/confidence_tier_prompt_golden.txt` (or similar) captures the exact bytes of the rendered Tier 2 prompt for a canned row set. Confirms no drift in how the hint reaches the LLM. Re-runs of the test that produce different bytes either reflect intentional spec changes (in which case the golden file is updated atomically with the spec edit) or unintentional drift (in which case the test fails and the agent investigates).

The golden file should include at minimum:

- A canned row set with one HIGH, one MEDIUM, one LOW row.
- The full assembled prompt string (system prompt + user text) the LLM would receive when the flag is on.
- The full assembled prompt string when the flag is off (must equal the pre-CT2 behavior exactly).

### 6.4 Close criteria

```
pytest tests/test_confidence_tier.py \
       tests/test_confidence_tier_integration_tier2.py \
       tests/test_confidence_tier_integration_tier3.py -v --tb=short
```

All tests pass. CT1's 22 unchanged. CT2.A adds at least 10. CT2.B adds at least 7. Golden-file test included. No skips, no xfails.

A sub-batch run of just CT2.A (without CT2.B's tests) must pass independently — sub-slices ship independently and CT2.A cannot be blocked by CT2.B's pre-X2 wait.

---

## 7. Migration path

The integration ships behind a feature flag in three phases, mirroring the disclosure-renderer rollout (`disclosure_renderer_spec.md` §7).

### 7.1 Phase 1 — ship CT2.A module wiring + tests behind feature flag (default off)

**Deliverable:**
- `app/chat/confidence_tier.py` — additive: `FEATURE_FLAG_ENV_VAR` constant + `is_confidence_tier_enabled()` helper.
- `app/chat/tier2_formatter.py` — anchored `Edit` adds the per-row classification + hint annotation between lines 139 and 141 (post-`_strip_legacy_fallback`, pre–empty-rows check).
- `prompts/tier2_formatter.txt` — anchored `Edit` adds the EXCEPTION clause per §2.2.c.
- `tests/test_confidence_tier_integration_tier2.py` — new file, ≥10 tests.

**Default:** `FEATURE_FLAG_CONFIDENCE_TIER` env var unset → classification is skipped; Tier 2 output identical to today.

**Close criterion:** all tests in §6.1 + §6.3 pass; the flag-off regression test confirms zero drift; the agent's report comes back text-only for the primary to integrate into `BACKLOG.md`.

### 7.2 Phase 2 — enable the feature flag for Tier 2 in production

**Lever:** Set `FEATURE_FLAG_CONFIDENCE_TIER=true` in the production environment (Railway env var).

**Scope:** Tier 2 LLM-formatter path (CT2.A) only. Tier 3 (CT2.B) does not light up because it has not shipped yet.

**Prerequisite:** observability data on the flag-on path confirms zero hedge-leakage on HIGH rows (no LLM-emitted hedges on rows where `confidence_hint == ""`). Sample at least 50 production responses; manually inspect 20 mixed-row responses.

**Rollback:** flip the flag to `false` (or unset). Behavior reverts to today's exactly.

### 7.3 Phase 3 — ship CT2.B (after Lane X2 closes and CT2.A has run for 4–6 weeks)

**Preconditions:**
1. Lane X2 has closed — `tier3_handler.py` is no longer being concurrently edited.
2. Phase 2 has been live for 4–6 weeks; observed hedge-leakage rate is below 1% on HIGH rows; no user complaints traced to confidence-tier behavior.

**Deliverable:**
- `app/chat/context_builder.py` — anchored `Edit` adds per-row classification + hedge-suffix appending behind `is_confidence_tier_enabled()`.
- (Optional) `prompts/system_prompt.txt` or `app/chat/tier3_handler.py` — single instruction on inlining parenthetical hedges from the context block.
- `tests/test_confidence_tier_integration_tier3.py` — new file, ≥7 tests.

**Default:** flag stays `=true` from Phase 2; CT2.B inherits the flag and lights up immediately on ship. (No separate Tier-3-only flag — flag scope is "is the integration live" not "which tier".)

**Rollback at each phase:** feature flag flip to `false`. Both Tier 2 and Tier 3 revert to pre-CT2 behavior atomically. No DB migrations to roll back, no prompt-file rollback (the EXCEPTION clauses are no-ops when the flag is off because the field they reference is never written).

---

## 8. Lane Map (parallelism guide)

CT2 is two slices, sequenced.

| Lane | Slice | Primary files | Dependencies |
|---|---|---|---|
| **CT2.A** | Tier 2 LLM-formatter integration | `app/chat/confidence_tier.py` (additive), `app/chat/tier2_formatter.py`, `prompts/tier2_formatter.txt`, `tests/test_confidence_tier_integration_tier2.py` | None — Lane CT1 has shipped; nobody else is editing these files |
| **CT2.B** | Tier 3 handler integration | `app/chat/context_builder.py`, optional one-line touch on `app/chat/tier3_handler.py` or `prompts/system_prompt.txt`, `tests/test_confidence_tier_integration_tier3.py` | Lane X2 must close first (file conflict on `tier3_handler.py`); Phase 2 of CT2.A should run for 4–6 weeks first |

**One agent owns each slice.** CT2.A is one agent's anchored-`Edit` work on the Tier 2 surface plus a `Write` of the new test file. CT2.B is a separate agent's anchored-`Edit` on the Tier 3 surface plus a `Write` of the new test file.

**Conflict surface:**
- CT2.A and CT2.B both touch `app/chat/confidence_tier.py` (CT2.A adds the helper; CT2.B reads it). Mitigation: CT2.A lands the helper first; CT2.B imports it without modification.
- No other lane currently touches `tier2_formatter.py` or `context_builder.py`. CT2.A's edits to `tier2_formatter.py` are isolated. CT2.B's edits to `context_builder.py` are isolated.
- `tier3_handler.py` is the conflict-prone file because Lane X2 owns it through its ship. The CT2.B agent's first action before opening any `Edit` is to confirm X2's ship-log entry exists in `BACKLOG.md` and that `tier3_handler.py`'s X2 surface (the disclosure-render hook) is present and stable.

**Convention (inherited from `ui_data_correctness_spec.md`):**
- Anchored `Edit` operations only on shared files. No `Write` on `tier2_formatter.py`, `tier3_handler.py`, `context_builder.py`, `confidence_tier.py`, `prompts/tier2_formatter.txt`, or `prompts/system_prompt.txt`.
- `Write` only on the new test files (which are net-new and own no shared surface).
- Agents report **text-only** to the primary. Primary integrates `BACKLOG.md` ship-log entries and `STATE.md` narrative updates. Agents do **not** edit those files directly.

---

## 9. Doc/PR hygiene (per WORKING_AGREEMENT)

For each sub-slice's PR:

- **Commit message:** references the lane and sub-slice — e.g., `confidence-tier CT2.A: per-row hint annotation in tier2_formatter (Phase 1)` or `confidence-tier CT2.B: context-block hedge suffix in context_builder (Phase 3)`.
- **BACKLOG.md ship-log entry:** appended by the primary, not the agent; entry text proposed in the agent's text-only report. One entry per sub-slice (CT2.A separate from CT2.B). Include close criteria (which tests pass), feature-flag default, and which prompt files were updated.
- **STATE.md narrative:** updated by the primary on each sub-slice close. Notes that the integration is live behind the feature flag (Phase 1 — flag default off) or that the flag has been flipped on (Phase 2) or that CT2.B has shipped (Phase 3).
- **`docs/maintainability/project_index.md`:** add a row for this spec when creating it. Spec name, status, owner-of-policy module (`app/chat/confidence_tier.py`), companion docs.
- **This spec:** mark status `RESOLVED` once Phase 3 ships and CT2.B's tests are green.

---

## 10. Decisions resolved (2026-05-08)

The following decisions are resolved in this spec draft and do not require user input:

- **Per-row annotation over aggregate band.** §2.2.b — Option 1 chosen on voice-quality grounds.
- **`context_builder.py` over `tier3_handler.py` as the CT2.B integration site.** §3.2.a — Option B1 chosen on data-locality grounds.
- **Hard sequencing on Lane X2.** §3.2.c — CT2.B does not open until X2 closes.
- **Single feature flag (`FEATURE_FLAG_CONFIDENCE_TIER`) for both sub-slices.** §7.3 — no separate Tier-2-only / Tier-3-only flags.
- **Pass `now=now_lake_havasu()` explicitly at every CT2 call site.** §2.3 / §3.3 — keeps the boundary clean per Backlog #38's nit and avoids the audience-signal-style naming-vs-implementation drift.

**Open decisions surfaced during draft (require primary's call):**

1. **System-prompt edit ownership for CT2.B.** §3.3 lists `prompts/system_prompt.txt` as an optional touch point. The cleaner site is the prompt file; the alternative is to leave the prompt untouched and rely on the LLM reading the parenthetical context-block suffix without explicit instruction. The first option is more robust; the second is less invasive. **Primary should decide whether CT2.B's deliverable includes the prompt edit.**
2. **Hard rule on LOW-hedge phone composition (§4).** The rule says "the LLM must inline a phone number when one exists alongside the LOW hedge." This is a prompt-side instruction; the formatter cannot enforce it deterministically. If the LLM ignores the instruction in production, the hedge appears bare. **Primary should decide whether the eval harness needs a stronger gate** — e.g., a post-process check that detects bare LOW hedges and adds the phone or downgrades the response — or whether the prompt-side defense is sufficient for Phase 1.
3. **Behavior on rows that are dicts without `last_verified_at` / `verification_method` keys.** §2.2.a notes that CT1's defensive `getattr` returns `None`, which classifies as LOW. For *legacy* row producers that never carried verification data, this is the wrong default — the row isn't stale, the data was never tracked. Two options: (a) accept the LOW default and rely on Lane S1's schema additions to populate the field on every row going forward (eventual consistency); (b) add an explicit "skip annotation" sentinel on rows that opt out (e.g., `confidence_hint = None` rather than missing). **Primary should decide which is simpler to operate.** The spec recommends (a) on grounds of fewer moving parts, but the user may have a stronger view.

If during implementation any further decisions surface, the implementing agent files them as text-only items in its closing report; the primary integrates them into `BACKLOG.md` as either resolved or follow-up items.

---

**Spec complete.** Ready for Phase 1 implementation (CT2.A). CT2.B opens after Lane X2 closes per the sequencing constraint in §3.2.c.
