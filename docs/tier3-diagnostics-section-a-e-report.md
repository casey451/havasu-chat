# Tier 3 unlinked-events — prod diagnostics report (Sections A–E)

**Date:** 2026-04-24 (run on prod via `railway run` with project venv)  
**Code reference:** Option B / `88556bb` context builder; optional tightenings from `docs/tier3-diagnostics-prompt-v2-and-readiness.md` preamble.

**Environment note:** `railway run python` failed on Windows (Store `python` stub). Diagnostics used **`railway run .venv\Scripts\python.exe`** with **`PYTHONPATH`** = repo root. A one-off runner was used for the batch query, then removed from the tree.

---

## Section A — Environment

| Check | Result |
|--------|--------|
| Venv / Python | Used `c:\Users\casey\projects\havasu-chat\.venv\Scripts\python.exe` (required; bare `python` on PATH is the Store stub and `railway run python` failed with “Python was not found…”). Set `PYTHONPATH` to the repo root for `app` imports. |
| Railway CLI | 4.40.0; `railway run` succeeded with the venv interpreter. |
| `railway run` failure? | Initial failure with default `python`; resolved by using `.venv\Scripts\python.exe`. No manual fallback needed. |
| Preamble (optional tightenings) | (1) D2b with `mode IS NOT NULL` returned the same 8 rows as D2. (2) D5 uses literal `2026-07-04` as specified. (3) Branch 2 logging: `docs/tier3-unlinked-events-readonly-investigation.md` §5. |

---

## Section B — Raw diagnostics (D1–D7)

### D1 — `ChatLog` / `chat_logs`

- **`__tablename__`:** `chat_logs`
- **Columns (declaration order):** `id`, `session_id`, `message`, `role`, `intent`, `created_at`, `query_text_hashed`, `normalized_query`, `mode`, `sub_intent`, `entity_matched`, `tier_used`, `latency_ms`, `llm_tokens_used`, `llm_input_tokens`, `llm_output_tokens`, `feedback_signal`
- **User query text:** `normalized_query`
- **Assistant reply (truncated in log):** `message`

### D2 — Recent `chat_logs` (patterns on `normalized_query`, last 15, `created_at` DESC)

**8 rows** (all matching; fewer than 15).

| `tier_used` | `sub_intent` | `normalized_query` (abridged) | Note |
|-------------|--------------|--------------------------------|------|
| `2` | OPEN_ENDED | `i am looking for fireworks on the 4th of july in lake havasu` | `entity_matched`: Lake Havasu City BMX |
| `2` | OPEN_ENDED | `what events are happening on july 4` |  |
| `gap_template` | DATE_LOOKUP | `when is the 4th of july show in havasu` | Not tier 1/2/3 LLM with full context |
| `2` | OPEN_ENDED | `what is happening in havasu this summer` |  |
| `2` | OPEN_ENDED | `what events are happening on july 4` | earlier duplicate |
| `gap_template` | DATE_LOOKUP | `when is the 4th of july show in havasu` | duplicate time |
| `2` | OPEN_ENDED | `what is happening in havasu this summer` |  |
| `2` | OPEN_ENDED | `what is happening in havasu this summer` |  |

**D2b** (`mode IS NOT NULL` added): **8 rows** — same set.

### D3 — Per validation query (from D2)

| Intent (paraphrase) | Rows | `tier_used` values |
|---------------------|------|--------------------|
| Summer (“what is happening in havasu this summer”) | 3 | **2**, **2**, **2** |
| “When is the 4th of July show…” | 2 | **gap_template**, **gap_template** (both `DATE_LOOKUP`) |
| “What events on July 4” | 2 | **2**, **2** |
| Fireworks on the 4th (full phrasing) | 1 | **2** |

**None of these rows have `tier_used = '3'`.** Not in the “all four missing from `chat_logs`” failure mode for this slice.

### D4 — `events` title match (`%july%`, `%4th%`, `%fourth%`, `%firework%`, `%independence%`)

| `id` (prefix) | `title` | `date` | `status` | `is_unlinked` |
|---------------|---------|--------|----------|----------------|
| `1ef18616-…` | 4th of July Fireworks in Lake Havasu City | 2026-07-04 | `live` | **True** |
| `cf620aa3-…` | July 4th Fireworks & Celebration | 2026-07-04 | `live` | **True** |

(Only 2 rows; both unlinked.)

### D5 — Option B unlinked-future set (no `LIMIT`), `rn` = order `date ASC`, `start_time ASC`

- **`today`:** 2026-04-24  
- **Window end:** 2027-04-24  
- **Total rows in window:** **28**  
- **Count with `date < 2026-07-04`:** **16** (≥ 10; first 10 slots are all before 2026-07-04).  
- **First 10 titles (rn 1–10):** Safety Orange, Country Divas at Havasu Landing Casino, … through Motor Madness Cruise-In.  
- July 4 fireworks appear at **rn 18 and 19** (same calendar day as other July 4 rows at 17+).

**Mechanical conclusion:** With `LIMIT 10` as in `88556bb`, neither July 4 fireworks row appears in the General calendar unlinked block.

### D6 — `%taste%` / `%balloon%`

| `title` | `provider_id` | `is_unlinked` |
|---------|---------------|---------------|
| 2026 Taste of Havasu | `NULL` | **True** |
| Havasu Balloon Festival… | `NULL` | **True** |

### D7 — Container date / TZ (`railway run`)

- `date.today`: **2026-04-24**  
- `datetime.now`: **2026-04-24** (naive, ~20:03 from run)  
- `TZ`: **unset**

---

## Section C — Interpretation

1. **“What is happening in Havasu this summer”** — **Tier `2`** every time. Tier 3 / Option B did not run. Answer = Tier 2 parser → DB → formatter.

2. **“When is the 4th of July show in Havasu”** — **`gap_template`**, not 2/3. `sub_intent` = `DATE_LOOKUP`; `_catalog_gap_response` returns fixed copy without Tier 2 or Tier 3. Option B did not run.

3. **“What events are happening on July 4”** — **Tier `2`**. Assistant `message` reflects Tier 2’s row sample / formatter, not Tier 3 context. Option B did not run.

4. **“Fireworks on the 4th of July…”** — **Tier `2`**, `entity_matched` = Lake Havasu City BMX. Reply text is Tier 2 + model behavior, not Option B. Option B did not run.

**Oct/Jan vs July (D4–D6):** Taste and Balloon are **unlinked** in prod — not explained by `provider_id IS NOT NULL` for those titles. In D5 ordering they sit at rn 26–28, also **outside** the first 10 unlinked rows (same structural pressure as July 4 for any Tier 3 unlinked block).

**Did Option B run for these failing queries?** **No** — `tier_used` is **`2`** or **`gap_template`**, never **`3`**.

**If Tier 3 had run:** D5 shows **16** unlinked events before 2026-07-04 and `LIMIT 10`, so July 4 unlinked rows **cannot** appear in the General calendar block as implemented.

---

## Section D — Branching plan

| Branch | Fit |
|--------|-----|
| **1 — Tier 2 (and gap) masking** | **Primary.** Validation traffic did not hit Tier 3. |
| **2 — Tier 3, block/LLM** | Not supported by `chat_logs` for this set (no `tier_used='3'`). D5 is the right secondary story if Tier 3 is forced: `LIMIT 10` + `ORDER BY date` excludes July 4 fireworks today. |
| **3 — Mixed** | **Actual shape:** Tier 2 for most + `gap_template` for DATE_LOOKUP “when is the show” phrasing. |

**Position:** **Branch 1 (dominant)**, with D5 documenting a **parallel structural limit** on Option B if/when Tier 3 runs for calendar questions.

### Branch 1 — Next work (planning only)

- **Relevant files:** `unified_router` (`_handle_ask`, `_catalog_gap_response`), `tier2_handler`, `tier2_db_query`, `tier2_formatter`.
- **Risks:** Skipping T2 for some intents increases Tier 3 cost; gap-template changes hit all `DATE_LOOKUP` with no entity.
- **Spec vs PR:** Tier routing is a product decision — may need a short addendum, not only a small PR.
- **pytest:** Run from real venv on Windows (same as `railway run` success path).

### Branch 2 — If Tier 3 proof is needed later

- **`logger.info`:** See `docs/tier3-unlinked-events-readonly-investigation.md` §5.
- **Optional addition:** log count of unlinked rows returned (e.g. in `build_context_for_tier3` / `_unlinked_future_events`).

### Branch 3

- N/A for “all four missing” — logs exist for the pattern set. Broader phrasings: widen D2 patterns and re-run.

---

## Section E — Adjacent observations

- “When is the 4th …” as `DATE_LOOKUP` + **gap** bypasses T2 and T3 — a different failure mode from “T2 won.”
- Entity matcher → **BMX** on the fireworks question may bias Tier 2.
- D6 **falsifies** “Taste / Balloon must be provider-linked” for those two titles.
- **Ops gap:** `tier_used` is in API/DB, not proven on default stdout access logs.

---

*Read-only diagnosis; no application code or schema changes in this report.*
