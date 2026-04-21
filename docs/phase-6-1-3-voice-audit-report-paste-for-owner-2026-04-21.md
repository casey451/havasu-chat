# Phase 6.1.3 — Voice audit report (full paste for owner review)

**Purpose:** Single file containing the narrative report text plus supplements from the assistant thread (full `t3-24` body, `route_meta` note, short interpretation). **Source of truth for verdicts:** `scripts/voice_audit_results_2026-04-21.json`.

---

## Full narrative report (`docs/phase-6-1-3-voice-audit-report.md`)

# Phase 6.1.3 — Voice audit report

**Date:** 2026-04-21  
**Model (auditor):** `claude-haiku-4-5-20251001` (`prompts/voice_audit.txt`)  
**Results JSON:** `scripts/voice_audit_results_2026-04-21.json`  
**Execution transcript:** `docs/phase-6-1-3-execution-transcript-2026-04-21.txt` (stdout + post-run summary)  
**Catalog (pre-run):** 25 providers / 98 programs / 16 events (unchanged from 6.1.2 dry-run assumptions)

**Commits:** None — this report and artifacts are **uncommitted** pending owner review (per 6.1.3 workflow).

---

## Section 1 — Summary (skim)

| Bucket | PASS | MINOR | FAIL | ERROR | Total |
|--------|------|-------|------|-------|-------|
| Tier 1 (rendered) | 23 | 1 | 0 | 0 | **24** |
| Tier 3 (generated) | 22 | 0 | 3 | 0 | **25** |
| Reference (golden) | 6 | 0 | 0 | 0 | **6** |
| **Total** | **51** | **1** | **3** | **0** | **55** |

**ERROR rate:** 0 / 55 = 0% (below 10% STOP threshold).

**Duration (approx.):** ~3 minutes wall time (`--execute` run in agent shell ~178s).

**Cost (actual tokens where measured):**

- **Tier 3 generation (Anthropic usage from `route_meta` sums in JSON):** 52,721 input-side + 1,817 output tokens → at list pricing $1/M input and $5/M output for Haiku 4.5, **~US$0.062** for Tier 3 alone.
- **Voice audits (55× Haiku):** per-call usage is **not** persisted in the current runner JSON. A conservative order-of-magnitude using the same rates as the 6.1.2 dry-run assumptions (~900 in + 280 out per audit) yields **~US$0.11–0.14** for audits.
- **Combined rough actual:** **~US$0.17–0.22** (well under the **US$1.00** caution threshold and the **US$2.00** hard ceiling).

---

## Section 2 — Per-sample detail

### 2a — PASS (compact)

All **51** samples below received **PASS** (no `voice_rules_cited`; auditor one-liners omitted for space).

**IDs:**  
`t1-HOURS-01`, `t1-HOURS-02`, `t1-TIME-hours`, `t1-TIME-program`, `t1-PHONE-01`, `t1-PHONE-02`, `t1-PHONE-03`, `t1-LOCATION-iron-wolf`, `t1-LOCATION-altitude`, `t1-WEBSITE-altitude`, `t1-COST-01`, `t1-COST-02`, `t1-AGE-iron-wolf-golf-country-club`, `t1-AGE-lake-havasu-city-aquatic-center`, `t1-AGE-lake-havasu-city-bmx`, `t1-DATE`, `t1-NEXT`, `t1-DATE-p2`, `t1-NEXT-p2`, `t1-OPEN_NOW-altitude-trampoline-park-lake-havasu-city`, `t1-OPEN_NOW-havasu-lanes`, `t1-OPEN_NOW-havasu-shao-lin-kempo`, `t1-OPEN_NOW-iron-wolf-golf-country-club`, `t3-02`, `t3-03`, `t3-04`, `t3-05`, `t3-06`, `t3-07`, `t3-08`, `t3-09`, `t3-10`, `t3-11`, `t3-12`, `t3-13`, `t3-14`, `t3-15`, `t3-16`, `t3-17`, `t3-18`, `t3-19`, `t3-20`, `t3-21`, `t3-22`, `t3-23`, `ref-8.5-low`, `ref-8.5-high`, `ref-8.8-intake`, `ref-8.8-commit`, `ref-8.9-correction-low`, `ref-8.9-high`.

Full `user_query` / `assistant_text` for each PASS row: **`scripts/voice_audit_results_2026-04-21.json`** → `samples[]` joined with `verdicts[]` on `sample_id`.

---

### 2b — MINOR (full)

#### `t1-HOURS-03` — MINOR

| Field | Value |
|--------|--------|
| **tier** | tier1 |
| **intent_or_mode** | HOURS_LOOKUP |
| **tags** | `tier1_matrix` |
| **user_query** | What are Iron Wolf Golf & Country Club hours on Monday? |
| **assistant_text** | Iron Wolf Golf & Country Club's open 9am–9pm on Monday. |
| **verdict** | MINOR |
| **voice_rules_cited** | §8.2 |
| **summary** | Missing contraction ('is' instead of ''s') and minor grammar slip; otherwise compliant. |
| **suggested_rewrite** | Iron Wolf Golf & Country Club's open 9am–9pm on Monday. |
| **notes** | The phrase "Iron Wolf Golf & Country Club's open" is grammatically awkward; should be "Iron Wolf Golf & Country Club is open" or restructured. §8.2 requires natural, direct speech without filler—this reads slightly stilted. One-word fix resolves it. |

**Drafted fix (owner: ACCEPT / REJECT / MODIFY):** `[ ]` `[ ]` `[ ]`

- **Where:** `app/chat/tier1_templates.py` — **HOURS_LOOKUP** render strings / weekday variant that produces the Iron Wolf (and similar) hours line.
- **What:** Prefer a template shape that reads naturally in English, e.g. **"{entity} is open …"** or **"{entity}: …"**, avoiding **"{entity}'s open"** unless product voice intentionally uses that contraction pattern everywhere.

---

### 2c — FAIL (full)

#### `t3-01` — FAIL

| Field | Value |
|--------|--------|
| **tier** | tier3 |
| **intent_or_mode** | ask/OPEN_ENDED |
| **tags** | happy_path |
| **user_query** | What's happening this weekend? |
| **assistant_text** | I don't have this weekend's date locked in, so I can't tell you what's on yet. Check https://www.golakehavasu.com/events or let me know the specific date and I'll pull what's happening. |
| **verdict** | FAIL |
| **voice_rules_cited** | §8.2 |
| **summary** | Violates §8.2 hard rule: 'don't know + keep going' pattern (admits lack of info, then offers follow-up). |
| **suggested_rewrite** | Check https://www.golakehavasu.com/events for this weekend's lineup. |
| **notes** | §8.2 forbids "I don't have X, but ask me Y" structure. Assistant should either redirect to the source or stay silent on the follow-up offer. |

**Drafted fix:** `[ ]` `[ ]` `[ ]`

- **Where:** `prompts/system_prompt.txt` (Tier 3 system voice).
- **What:** Add an explicit few-shot or rule: **never** pair "I don't have / can't" with "or tell me / let me know" in the same breath; either give a **single** external redirect, or **one** clarifying question—not both. Optionally tighten `app/chat/context_builder.py` only if date-range extraction should pre-fill "this weekend" so the model is not tempted to hedge.

---

#### `t3-24` — FAIL

| Field | Value |
|--------|--------|
| **tier** | tier3 |
| **intent_or_mode** | ask/OPEN_ENDED |
| **tags** | explicit_rec_query |
| **user_query** | What should I do Saturday? |
| **assistant_text** | (long; multi-paragraph menu of Altitude, Havasu Lanes, Tap Room Jiu Jitsu, ending with "What sounds good to you?") — full text in JSON. |
| **verdict** | FAIL |
| **voice_rules_cited** | §8.4 |
| **summary** | Sample is tagged explicit_rec_query but uses Option 2 (multiple suggestions + open question) instead of Option 3 (single strong recommendation with rationale). |
| **suggested_rewrite** | (Auditor proposed a Lanes-forward single pick; still ends with "Does that work for you?" — **review in 6.1.4**: trailing questions may conflict with §8.2; MODIFY likely.) |
| **notes** | §8.4 Option 3 requires a single, confident recommendation when explicit_rec_query is true. |

**Drafted fix:** `[ ]` `[ ]` `[ ]`

- **Where:** Primarily **`prompts/system_prompt.txt`**; if the model never sees the `explicit_rec_query` hint, consider **`app/chat/context_builder.py`** to inject a one-line classifier hint ("User asked for a single pick / explicit recommendation").
- **What:** When tags include **explicit_rec_query**, require **Option 3**: one primary recommendation, short **because** rationale, **no** menu of three venues, **no** closing "what sounds good?" unless handoff explicitly allows (it does not for generic ask).

---

#### `t3-25` — FAIL

| Field | Value |
|--------|--------|
| **tier** | tier3 |
| **intent_or_mode** | ask/OPEN_ENDED |
| **tags** | explicit_rec_query |
| **user_query** | Pick one thing to do with kids this weekend |
| **assistant_text** | Take the kids to Altitude Trampoline Park on Saturday — they're open 9am–9pm and a 90-minute open jump session is $19. It's the quickest way to burn energy this weekend. |
| **verdict** | FAIL |
| **voice_rules_cited** | §8.4 |
| **summary** | explicit_rec_query tag requires Option 3 (full recommendation with reasoning), but assistant used Option 2 (bare recommendation with logistics). |
| **suggested_rewrite** | Take the kids to Altitude Trampoline Park on Saturday — they're open 9am–9pm and a 90-minute open jump session is $19. I'd recommend this because it's the quickest way to burn energy this weekend, and the long hours mean you can go whenever fits your schedule. |
| **notes** | Option 3 demands explicit reasoning ("I'd recommend…because…"). Current text has logistics + benefit but not the framed curation the auditor expected. |

**Drafted fix:** `[ ]` `[ ]` `[ ]`

- **Where:** **`prompts/system_prompt.txt`** (same Option 3 block as `t3-24`).
- **What:** Add a **template line** auditors can score: e.g. **"I'd pick … because …"** when `explicit_rec_query` is signaled (via tags in audit payload / future context line in Tier 3).

---

### 2d — ERROR

**None.** Raw auditor bodies for failures are in JSON under `verdicts[*]._raw_auditor_response` if needed.

---

## Section 3 — Data & side-signal findings

*(Voice-adjacent or catalog issues surfaced by the audit matrix — not necessarily auditor-flagged.)*

1. **DATE_LOOKUP vs NEXT_OCCURRENCE** share **`render("DATE_LOOKUP", …)`** in `tier1_templates.py`. Pairs like `t1-DATE` / `t1-NEXT` (same provider) produce **identical `assistant_text`**. When interpreting MINOR/FAIL, **do not double-count** the same underlying string twice.

2. **OPEN_NOW** uses a **single invariant template** across providers ("They're open right now — hours say they're in window for today."). Four matrix rows test the **same** surface string. Useful for regression, weak for sampling phrasing variety; if §8.1 "knowledgeable local friend" should vary by venue/time, that is a **6.1.4 / product** decision.

3. **Seed / catalog gaps** (from matrix + `meta`):
   - **Flips for Fun:** no **active** age-bearing programs surfaced for AGE_LOOKUP (runner walked to other providers — same as production `try_tier1`).
   - **Universal Gymnastics … Sonics:** programs **`is_active=False`** in this seed for AGE traversal.
   - **`meta.future_live_events_null_provider_count`:** **0** for this run.
   - **`branch_present_not_auditable`:** **WEBSITE_LOOKUP** for **Bridge City Combat** (empty `website`) — see `meta.tier1_not_auditable` in JSON.

**Follow-up (owner):** Consider logging seed/catalog items in **`docs/known-issues.md`** after review. **Out of scope for 6.1.3 commit** per kickoff fence.

---

## Section 4 — Phase 6.1.4 handoff (owner checklist)

Mark each **ACCEPT / REJECT / MODIFY** after review. Only **ACCEPT** items should drive 6.1.4 implementation.

| # | sample_id | Verdict | Target file(s) | Drafted change (one line) | ACCEPT | REJECT | MODIFY |
|---|-----------|---------|----------------|---------------------------|--------|--------|--------|
| 1 | `t1-HOURS-03` | MINOR | `tier1_templates.py` | Fix HOURS line grammar ("is open" / avoid awkward possessive + "open"). | `[ ]` | `[ ]` | `[ ]` |
| 2 | `t3-01` | FAIL | `system_prompt.txt` (+ optional `context_builder.py`) | Ban "can't + or tell me" double move; single redirect or single clarify. | `[ ]` | `[ ]` | `[ ]` |
| 3 | `t3-24` | FAIL | `system_prompt.txt` (+ optional `context_builder.py`) | Force Option 3 for explicit_rec_query; no multi-venue menu; no trailing open question. | `[ ]` | `[ ]` | `[ ]` |
| 4 | `t3-25` | FAIL | `system_prompt.txt` | Add explicit "I'd pick … because …" framing for explicit_rec_query. | `[ ]` | `[ ]` | `[ ]` |

---

## Surprising / notable

- **Classifier vs tags:** Both failing explicit-rec samples show **`ask/OPEN_ENDED`** in `intent_or_mode` while audit tags carry **`explicit_rec_query`** — the auditor correctly used tags; 6.1.4 may want the **router or context builder** to surface "explicit rec" to the model, not only the audit JSON.
- **`t3-25`:** Single-venue answer still scored **FAIL** for "Option 2 vs 3" framing — tightening **Option 3** rubric in the prompt may be enough.
- **Cost / errors:** Under **US$1** and **zero ERROR** verdicts — run healthy.

---

## Supplement — `t3-24` full `assistant_text` (from JSON)

Saturday's got some solid options depending what you're in the mood for.

If you want to bounce around, Altitude Trampoline Park opens at 9am with 90-minute or 120-minute jump sessions ($19–$24). It's a huge 22,000+ sq ft park with trampolines, dodgeball, and more.

For something more chill, Havasu Lanes does open bowling from noon to 9pm, and then switches to Rock & Bowl (cosmic bowling with black lights and party vibes) from 6pm to close. That's a fun Saturday night move.

If you've got kids 6+, The Tap Room Jiu Jitsu runs youth wrestling at 9am.

What sounds good to you?

---

## Supplement — routing correction for `t3-24`

In `scripts/voice_audit_results_2026-04-21.json`, sample **`t3-24`** has `route_meta.tier_used` **`"2"`** (Tier 2), not Tier 3. A 6.1.4 fix may need **`prompts/tier2_formatter.txt`** (and/or Tier 2 orchestration), not only `prompts/system_prompt.txt`. The checklist row for `t3-24` in Section 4 above is still directionally right for voice (Option 3 / §8.4) but the **file split** should account for Tier 2 producing this body.

**Note:** `t3-01` used `tier_used: "3"` in the same JSON run.

---

## Short owner read (from thread)

- **`t1-HOURS-03`:** Auditor flagged awkward **“Club's open”** possessive + “open”; notes suggest **“is open”** or restructure (§8.2 MINOR).
- **`t3-01`:** §8.2 **don’t-know + keep going** (redirect + “let me know…”).
- **`t3-24` / `t3-25`:** §8.4 **Option 2 vs Option 3** under audit tag `explicit_rec_query`; **`t3-25`** is single-venue but missing explicit **“I’d pick / because”** framing per auditor.

When **ACCEPT / REJECT / MODIFY** is decided, that drives 6.1.4. Optionally update `docs/phase-6-1-3-voice-audit-report.md` Section 4 row 3 to cite Tier 2 + `tier2_formatter.txt` for `t3-24` so the canonical report matches JSON.
