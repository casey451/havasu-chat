# Phase 6.1.2 — Voice audit runner (proposal only, **owner-redlined**)

**Status:** Owner redlines applied (reference set = 6; `ref-8.5-low-b` removed). Implementation: `scripts/run_voice_audit.py` + delivery report `docs/phase-6-1-2-audit-runner-report.md` (6.1.2). Full paid audit execution remains 6.1.3 unless explicitly approved.

**References:** `prompts/voice_audit.txt` (locked), `HAVASU_CHAT_CONCIERGE_HANDOFF.md` §8, `scripts/run_voice_spotcheck.py`, `app/chat/unified_router.py` (`route`), `app/chat/tier1_handler.py` + `tier1_templates.render`, `app/chat/tier3_handler.answer_with_tier3`.

---

## Task 3 — Pre-flight check outputs (1–10)

| # | Check | Output |
|---|--------|--------|
| 1 | `git log --oneline -3` | `7aa49a0 docs: log mountain-bike retrieval miss (post-Phase 6.2.3)` / `b1eb5b4 Phase 6.1.1: establish voice_audit.txt prompt file` / `f09057b docs: session resume doc for next chat` |
| 2 | Voice-related scripts under `scripts/` | **`run_voice_spotcheck.py`** only. |
| 3 | `scripts/run_voice_spotcheck.py` (first ~80 lines) | Stdlib `urllib` POST to `{base}/api/chat`, JSON body `query` + `session_id`, fixed `QUERIES` list; `_ROOT` on `sys.path` — standalone script + argparse pattern. |
| 4 | Tier 1 source files | **`app/chat/tier1_templates.py`**, **`app/chat/tier1_handler.py`**. |
| 5 | `_TIER1_SUB_INTENTS` | `TIME_LOOKUP`, `HOURS_LOOKUP`, `PHONE_LOOKUP`, `LOCATION_LOOKUP`, `WEBSITE_LOOKUP`, `COST_LOOKUP`, `AGE_LOOKUP`, `DATE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW` — all implemented in **`try_tier1`** when `entity` resolves and required fields exist. `DATE_LOOKUP` and `NEXT_OCCURRENCE` share the same **`render("DATE_LOOKUP", ...)`** path in code. |
| 6 | `tier1_templates.py` | Public API **`render(intent, entity, data, variant)`** plus helpers. |
| 7 | `tier3_handler.py` | **`answer_with_tier3(query, intent_result, db)`** — system prompt + Haiku. |
| 8 | Catalog row counts (typical local `events.db`) | **~25 providers / ~98 programs / ~16 events** (re-count at implementation time). |
| 9 | `requirements.txt` | **`anthropic==0.96.0`**. |
| 10 | Prior `run_voice_audit*.py` | **None** found. |

---

## Runner location and name

- **`scripts/run_voice_audit.py`** — diagnostic-only; mirrors `run_voice_spotcheck.py` layout (`argparse`, venv `python.exe`, `sys.path` bootstrap).

---

## Tier 1 — explicit runner spec (owner redline #1)

**Requirement (not optional):** The runner **must** attempt to produce at least one **rendered string per implemented `try_tier1` branch** (all **10** sub-intents below), using **`tier1_templates.render`** with the same `intent` / `entity` / `data` shapes as production. This is an explicit audit of Tier 1 voice surface area.

**Outcomes:**

- If a branch renders: it is fed to the voice auditor (PASS/MINOR/FAIL).
- If **no** seeded row satisfies required columns **after** a DB scan: log **`branch_present_not_auditable`** — *“branch present, not auditable with current seed — possible dead code or data gap.”* That log line is itself a useful audit artifact (either seed is thin, or production rarely hits the branch).

### Matrix — all 10 sub-intents

| `sub_intent` (classifier output) | `render(...)` **intent** key | Entity type passed to `render` | Required fields (from `try_tier1`) | Seeded row to try (re-resolve at run time) | Notes |
|----------------------------------|------------------------------|----------------------------------|--------------------------------------|---------------------------------------------|--------|
| **HOURS_LOOKUP** | `HOURS_LOOKUP` | `Provider` | `provider.hours` non-empty | Footlite School of Dance, Altitude Trampoline Park, Iron Wolf Golf & Country Club | Weekday focus from `normalized_query` in `data`. |
| **TIME_LOOKUP** | `HOURS_LOOKUP` *or* `TIME_LOOKUP` | `Provider` (hours path) **or** `Program` (schedule path) | Hours blob **or** program `schedule_start_time` / `schedule_end_time` | Altitude (hours); Altitude program “Open Jump — 90 Minutes” (schedule window) | Two render paths in code; both must appear in audit matrix as separate rendered rows. |
| **PHONE_LOOKUP** | `PHONE_LOOKUP` | `Provider` | Program or provider phone | Footlite, Bridge City Combat, Flips for Fun | Uses `_phone_for_query`. |
| **LOCATION_LOOKUP** | `LOCATION_LOOKUP` | `Provider` | `provider.address` non-empty | Iron Wolf, Altitude (verify `address` at runtime) | If no provider has address → **not auditable** for LOCATION until seed improves. |
| **WEBSITE_LOOKUP** | `WEBSITE_LOOKUP` | `Provider` | `provider.website` non-empty | Bridge City Combat, Altitude (verify at runtime) | If missing → **not auditable**. |
| **COST_LOOKUP** | `COST_LOOKUP` | `Program` | `cost` or `show_pricing_cta` + phone fallback | Altitude “Open Jump — 90 Minutes”, Iron Wolf “Junior Golf Clinic — Session 1” | |
| **AGE_LOOKUP** | `AGE_LOOKUP` | `Program` | `age_min` / `age_max` | Flips for Fun / Universal Gymnastics programs with ages | |
| **DATE_LOOKUP** | `DATE_LOOKUP` | `Provider` (entity) + event fields in `data` | `_next_event` returns future `Event` for `provider_id` | Any provider with **`Event.provider_id`** set and `date >= today` | If **no** provider-linked future events in DB → **not auditable** (events may be unlinked — flag possible data/model gap). |
| **NEXT_OCCURRENCE** | `DATE_LOOKUP` | Same as **DATE_LOOKUP** | Same | Same | Same row as DATE_LOOKUP in practice; still list separately so classifier label coverage is explicit in audit metadata. |
| **OPEN_NOW** | *(inline template in handler, not `render`)* | `Provider` | `hours` parseable by `_open_now_from_hours` regex | Altitude (if hours string matches `9am-9pm` style pattern) | If parser returns `None` for all providers → **not auditable** without synthetic hours string (optional: one **synthetic** hours blob solely to exercise OPEN_NOW — only if owner allows in 6.1.2 implementation; **default:** log not auditable). |

**Target count:** **~25–40** distinct rendered lines (upper bound over rich seeds: multiple matrix entities per sub-intent where the handoff table names more than one provider, optional second DATE/NEXT provider when two linkage chains exist, and several OPEN_NOW rows for distinct parseable-hours providers). Thin seeds land lower; exact auditable + ``branch_present_not_auditable`` counts print in **`--dry-run`**.

---

## Sample inventory (owner redlines #2–#7)

| Bucket | Count | Notes |
|--------|------:|--------|
| Tier 1 rendered | ~25–40 | Matrix above |
| Tier 3 **generated** (`unified_router.route`) | **25** | Live classifier + tier order + real `assistant_text` |
| **Reference** (frozen golden) | **6** | No LLM generation; `tier: "reference"`; measures §8.5 / §8.8 / §8.9 voice directly (two samples each for §8.8 intake+commit and §8.9 low+high stakes) |
| **Total audit payloads** | **~56–71** | ~25–40 Tier 1 + 25 Tier 3 + 6 reference |

**Tier 3 path (unchanged):** **`unified_router.route`** — not direct `answer_with_tier3` — so the audit sees what users see (classifier, Tier 1 try, then Tier 3).

---

## Tier 3 generated queries (**25**) — redlined list

Tags for auditor hints: `happy_path`, `gap`, `multi_entity`, `disambiguation`, `out_of_scope`, `explicit_rec_query` (plus any `voice_audit.txt` optional tags the runner forwards).

### Happy path (~10)

1. What’s happening this weekend? — **happy_path**
2. **What time does the BMX track open Saturday?** — **happy_path** *(replaces old #2 “family activities this month” — different shape: entity + time, may still land Tier 3 if Tier 1 misses)*
3. When is the farmers market on Thursday? — **happy_path**
4. Is Altitude open late on Friday? — **happy_path**
5. Kids gymnastics programs near me — **happy_path**
6. Tell me about Bridge City Combat — **happy_path**
7. Events at Sara Park — **happy_path**
8. BMX race times — **happy_path**
9. Swimming lessons for beginners — **happy_path**
10. Dance classes for a 7-year-old — **happy_path**

### Gap (~5)

11. My son wants to ride mountain bikes. Any classes available? — **gap**  
    **Scope note (owner redline #5):** This sample measures **§8.6 / gap-template voice compliance** of whatever the app returns — **not** whether retrieval should have found “Lake Havasu Mountain Bike Association.” The retrieval miss is tracked in **`docs/known-issues.md`**. The 6.1.3 report should state explicitly: a **PASS** voice verdict here can coexist with an **incorrect catalog outcome**.

12. Is there a curling club in Havasu? — **gap**  
13. When is the hot air balloon festival? — **gap**  
14. Who teaches violin to adults? — **gap**  
15. Underground techno tonight? — **gap**

### Multi-entity / disambiguation (~5)

16. Sonics or Flips for fun for a shy 5-year-old? — **multi_entity**, **disambiguation**  
17. **Bridge City Combat vs Footlite School of Dance for Saturday morning kids classes?** — **multi_entity**, **disambiguation** *(replaces “Altitude vs Sky Zone” — **both** names exist in typical seed; avoids fake entity / §8.6 vs §8.4 scorer confusion.)*  
18. Which martial arts gym has Saturday morning kids classes? — **multi_entity**, **disambiguation**  
19. Best place for toddler tumbling — **multi_entity**, **explicit_rec_query**  
20. Compare Footlite and Ballet Havasu for preschool dance — **multi_entity**, **disambiguation**

### Out-of-scope (~3)

21. What’s the best sushi in town? — **out_of_scope**  
22. Are home prices going down in Havasu? — **out_of_scope**  
23. Weather this weekend? — **out_of_scope**

### Explicit recommendation (~2)

24. What should I do Saturday? — **explicit_rec_query**  
25. Pick one thing to do with kids this weekend — **explicit_rec_query**

*(Former live “contested-state” slots 24–26 in the old 30-list are now **reference** §8.5 samples — see below. Former intake/correction queries 29–30 are **reference** §8.8 / §8.9 — see below.)*

---

## Reference samples (**6**) — frozen golden strings (owner redlines #2, #3, final)

**Rationale:** Voice audit scores **§8** patterns, not contribute/correct **state machines** (partially aspirational per Phase 5 close). No contested rows in DB for live §8.5 — use handoff text.

Each row: `sample_id`, `tier: "reference"`, synthetic `user_query` (for auditor context), **`assistant_text`** = golden target (handoff verbatim; plain text — no italics), `tags`, `voice_rules_cited` left empty for auditor to fill.

| ID | § | Synthetic `user_query` (short) | `assistant_text` (verbatim from handoff) |
|----|---|--------------------------------|------------------------------------------|
| **ref-8.5-low** | §8.5 low-stakes | *(n/a — contested hours scenario)* | Opens at 7 — someone recently reported it moved from 6. Let me know if that's wrong. |
| **ref-8.5-high** | §8.5 high-stakes | *(n/a — contested phone scenario)* | My info says the phone is (928) 555-0100. Someone recently reported a different number — I'll get it confirmed before updating. |
| **ref-8.8-intake** | §8.8 intake | *there's a car show at the channel saturday* | nice — got a time, and who's running it? |
| **ref-8.8-commit** | §8.8 commit | *Casey I just submitted a car show event* | got it, added to the pile. Casey reviews new events before they go live — usually within a day or two. |
| **ref-8.9-correction-low** | §8.9 low-stakes | *(user corrected a small fact)* | got it, noted — I'll flag it and watch for more confirmations. |
| **ref-8.9-high** | §8.9 high-stakes | *Altitude's phone isn't (928) 555-0100 anymore — it's a different number now* | got it — that one needs to go through review before I update it. Thanks for the heads up. |

**Dropped:** **ref-8.5-low-b** (non-handoff variant; scorer noise risk). Two §8.5 samples (**low** + **high**) cover both sub-patterns.

---

## Sample generation flow

| Stream | Approach |
|--------|----------|
| **Tier 1** | DB → `tier1_templates.render(...)` per matrix row. Deterministic. |
| **Tier 3** | **`unified_router.route(query, session_id, db)`** per generated query; capture final `assistant_text` (+ intent / tier metadata from `ChatResponse`). |
| **Reference** | No router / no LLM — build JSON payload exactly like other samples; `tier: "reference"`. |
| **Audit** | One Haiku call per sample; **`prompts/voice_audit.txt`** system; user JSON = one object; **one retry** on parse failure → `verdict: "ERROR"` + raw body. |

---

## Audit invocation (implementation detail)

- Model: **`claude-haiku-4-5-20251001`**, temp **0.2–0.3**, `max_tokens` ~**300** for JSON verdict.
- **One sample per API call** (unchanged).

---

## Output format

- **`scripts/voice_audit_results_<YYYY-MM-DD>.json`** — top-level `meta`, `summary`, `samples[]`. Include **`git_sha`** (or `null`) in `meta` for reproducibility.

---

## Cost guardrails (owner redline #7)

- **`--dry-run`:** enumerate all samples (Tier 1 + Tier 3 + reference), print counts and **estimated USD** (Haiku list pricing, order-of-magnitude).
- **`--confirm`:** required (or interactive **y/N**) before any paid API call.
- **Band:** rough estimate **~US$0.20–0.55** for ~56–71 audit calls + **25** Tier 3 generations (recompute formula in runner help text).
- **Hard ceiling:** if estimated cost **>** **US$2.00**, the runner **aborts with a clear warning** and does not call the API (defensive against future larger sample sets or mis-configured loops).

---

## Idempotency / reproducibility

- Tier 1 + reference: deterministic for a given DB snapshot.
- Tier 3: non-deterministic; document in docstring; store catalog **`git_sha`** in `meta`.

---

## Explicitly out of scope

- No edits to `tier1_templates.py`, `tier3_handler.py`, `unified_router.py`, or `prompts/` for 6.1.2 runner work.
- No pytest / migrations in this sub-phase.

---

## Next step

6.1.2 implementation: **`scripts/run_voice_audit.py`** + **`docs/phase-6-1-2-audit-runner-report.md`**. Full paid **`--execute`** audit + narrative voice report = **6.1.3** (separate approval). Git commit for 6.1.2 awaits explicit owner sign-off.
