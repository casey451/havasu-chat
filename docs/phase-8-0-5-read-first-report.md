# Phase 8.0.5 — Analytics cleanup (read-first report)

**Date:** 2026-04-22  
**Scope:** Read-only inspection for Issues A (`tier_used` NULL / `placeholder` vs documented rates) and B (`response_text` vs `message` doc–code drift). **No code changes, no commits, no production writes.**

---

## Pre-flight

| Check | Result |
|--------|--------|
| `git log --oneline -1` | `a4beb5a` Phase 8.0.4 (HEAD matches spec when read-first started; repo clean afterward) |
| `git status` | Only untracked `docs/phase-9-scoping-notes-2026-04-22.md` before this file was added |
| `pytest -q` | **753 passed**, 3 subtests passed |

---

## 1. NULL `tier_used` — distribution (dev vs production)

### 1.1 Queries run

```sql
SELECT tier_used, COUNT(*) AS c
FROM chat_logs
GROUP BY tier_used
ORDER BY c DESC;

SELECT COUNT(*) FROM chat_logs;
```

Timestamp clustering (note: ORM column is **`created_at`**, not `timestamp` — see §4):

```sql
SELECT MIN(created_at), MAX(created_at) FROM chat_logs WHERE tier_used IS NULL;
SELECT MIN(created_at), MAX(created_at) FROM chat_logs WHERE tier_used IS NOT NULL;
```

**Production** queries executed via `railway run` with repo on `PYTHONPATH` (read-only).

### 1.2 Dev (local SQLite, workspace `SessionLocal()` default DB)

| `tier_used` | Count | % of 343 total |
|---------------|------:|---------------:|
| `3` | 140 | 40.8% |
| **NULL** | **78** | **22.7%** |
| `2` | 55 | 16.0% |
| `1` | 24 | 7.0% |
| `gap_template` | 23 | 6.7% |
| `chat` | 23 | 6.7% |
| `placeholder` | 0 | 0% |

**NULL rows by role:** `user` 39, `assistant` 39 (perfect 1:1 pairing).

**NULL rows + `normalized_query`:** All 78 NULL rows have `normalized_query IS NULL` (unified-router analytics columns unused on these rows).

**NULL `created_at` range:** `2026-04-18 22:12:09` → `2026-04-18 22:12:11` (~2 seconds of wall clock).

**Non-NULL `created_at` range:** `2026-04-20 18:39:28` → `2026-04-22 17:05:08`.

**Interpretation:** Dev NULLs are a **compact legacy burst** (likely automated or manual **`POST /chat`** Track A traffic + tests), **not** an ongoing steady-state failure of `/api/chat` unified logging. They do **not** overlap in time with the bulk of tier-populated rows.

### 1.3 Production (Railway Postgres via `railway run`)

| `tier_used` | Count | % of 376 total |
|---------------|------:|---------------:|
| `3` | 180 | 47.9% |
| `2` | 94 | 25.0% |
| `chat` | 35 | 9.3% |
| `1` | 33 | 8.8% |
| `gap_template` | 26 | 6.9% |
| **NULL** | **6** | **1.6%** |
| `placeholder` | 2 | 0.5% |

**NULL + `placeholder` combined:** 8 rows → **2.13%** of all `chat_logs` rows — aligns with handoff **§5 tech-debt** line “**2.4%**” (`placeholder` + `null`) within sampling noise.

**NULL rows by role:** `user` 3, `assistant` 3 (again paired turns).

**NULL `created_at` range:** `2026-04-19 23:23:48` → `2026-04-20 02:02:03`.

**Non-NULL `created_at` range:** `2026-04-19 23:23:46` → `2026-04-22 01:50:26` (NULL window sits at the **start** of production logging, then tiered rows continue).

**Sample NULL messages (prod):** Short natural-language turns (“what’s happening this weekend”, Tier-1-style assistant replies, “phone number for altitude”, etc.) consistent with **early Track A `POST /chat`** behavior, not Tier 2/3 unified rows.

### 1.4 Dev vs prod comparison

| Dimension | Dev | Prod |
|-----------|-----|------|
| NULL % | **~23%** | **~1.6%** |
| `placeholder` string | 0 | 2 |
| NULL clustering | Single **2s** burst on 2026-04-18 | **~2.5h** window on 2026-04-19–20 |
| Paired user/assistant NULL | Yes (39+39) | Yes (3+3) |

**Conclusion:** **Prod matches the handoff’s ~2.4% “NULL + placeholder” story.** **Dev does not** — dev is dominated by **Track A `log_chat_turn` rows** (and/or local test runs) that **never set** unified-router columns. **Do not** extrapolate dev NULL rate to production.

---

## 2. NULL `tier_used` — write-path inventory

Every **`chat_logs` insert** in application code goes through **`app/db/chat_logging.py`**. There are **two** insert helpers:

### 2.1 `log_unified_route(...)` — `app/db/chat_logging.py`

- **Called from:** `app/chat/unified_router.py`, inner `_finish()` inside **`route()`** (only path for **`POST /api/chat`** concierge).
- **Inserts:** One **assistant** row per unified turn with `query_text_hashed`, `normalized_query`, `mode`, `sub_intent`, `entity_matched`, **`tier_used`**, token + latency fields.
- **`tier_used`:** Always passed explicitly from `_finish`. Observed values include `"1"`, `"2"`, `"3"`, `"gap_template"`, `"chat"`, `"placeholder"` (graceful / classify failures use **`"placeholder"`**; catalog gap early return uses **`"gap_template"`**). **No intentional NULL** from this path unless `tier_used` were ever passed as empty string (`log_unified_route` maps falsy to `None` — current callers pass non-empty strings).
- **User utterances:** **Not** logged here (concierge API does not call `log_chat_turn` for the query text).

### 2.2 `log_chat_turn(session_id, text, role, intent)` — `app/db/chat_logging.py`

- **Called from:** `app/chat/router.py` → **`POST /chat`** handler **`chat()`** — **`log_chat_turn`** for **user** then **assistant** (`lines ~408–411`).
- **Inserts:** `ChatLog` with **`session_id`, `message`, `role`, `intent` only** for unified analytics fields — **all NULL** (`tier_used`, `mode`, `normalized_query`, etc.).
- **`tier_used`:** **Always NULL** for these rows by design.

### 2.3 Other `chat_logs` **mutations** (not inserts)

| Location | Behavior |
|----------|----------|
| `app/api/routes/chat.py` `post_chat_feedback` | **UPDATE** `feedback_signal` on existing row |
| `app/contrib/mention_scanner.py` | Reads / writes **`llm_mentioned_entities`** — not `chat_logs` inserts |

### 2.4 Tests / fixtures

Multiple tests construct **`ChatLog(...)`** directly (e.g. feedback, mentions, phase8). Affects **test DBs only**, not prod.

### 2.5 Root cause summary (Issue A)

- **`tier_used IS NULL`** = **rows created by `log_chat_turn` (Track A `/chat`)**, not by unified **`log_unified_route`**.
- **`tier_used = 'placeholder'`** = **real unified-router enum** for failure / contribute / correct branches (see `unified_router.py`); **not** the same as SQL NULL.
- Handoff aggregates **NULL + placeholder** into one tech-debt bucket (~2.4%); production data supports that **combined** rate, with **NULL** mostly **legacy Track A** volume.

---

## 3. NULL `tier_used` — timestamp clustering (“legacy data?”)

Already covered in §1:

- **Dev:** NULL rows are **100%** confined to a **two-second** window; all tiered rows are **newer** → strong evidence of **one-off / test burst**, not a broken writer today.
- **Prod:** Six NULLs sit in an **early** window when tiered rows already existed seconds apart → **early Track A** or pre–full-migration traffic, **not** proof of a current high-volume NULL writer.

**No schema change** was required to diagnose.

---

## 4. `response_text` vs `message` — grep / handoff / code

### 4.1 Handoff `HAVASU_CHAT_CONCIERGE_HANDOFF.md`

- **§3.10 Analytics schema** lists: `timestamp`, `user_hash`, **`response_text`**, etc. (`lines ~503–519` in current file).
- **`response_text`:** Appears in **§3.10** as the logged body column name.
- **`message`:** **Not** used in §3.10 for the assistant body field name.
- **Elsewhere:** §4.5 `chat_logs` extension lists `mode`, `sub_intent`, `feedback_signal` — **does not** rename the legacy `message` column.
- **§5 tech-debt (line ~699):** Documents **`placeholder` + NULL `tier_used`** — consistent with prod counts.

### 4.2 ORM / migrations

- **`app/db/models.py` — `ChatLog`:** Body text column is **`message: Mapped[str]`** (`Text`, NOT NULL).
- **Initial migration** `b2f8c1a9d0e1_add_chat_logs_table.py`: column **`message`**.
- **There is no `response_text` column** in the database or ORM.

### 4.3 Codebase grep for `response_text` as a **column**

- **`app/db/chat_logging.py`:** Parameter name **`response_text`** on `log_unified_route` — **mapped into** `ChatLog.message=` (same string).
- **`app/chat/unified_router.py`:** Passes `response_text=response` into `log_unified_route`.
- **Other `.py` uses:** Variable names in **`tier2_handler`**, **`mention_scanner`**, **`scripts/diagnose_search.py`**, tests — all **Python identifiers** or JSON keys, **not** SQL column names.
- **No** `SELECT response_text` or ORM attribute `.response_text` on `ChatLog`.

**Conclusion (Issue B):** Pure **documentation / naming** drift. **No** second column, **no** rename migration in history for `response_text`. Risk is **future scripts** written from §3.10 alone.

---

## 5. Proposed fix shapes (implement **not** in this pass)

### 5.1 Issue A — NULL / `placeholder` `tier_used`

| Layer | Recommendation |
|--------|----------------|
| **Understanding** | Treat **NULL** as **Track A `log_chat_turn` rows**; treat **`placeholder`** as an **explicit unified-router sentinel** (not SQL NULL). |
| **Docs / handoff** | Clarify in **§3.10** + **§5 tech-debt** that **`tier_used` NULL** = **legacy `/chat`** rows without unified analytics; list **`placeholder`** separately with semantic meaning (failure / contribute / correct per code). |
| **Analytics scripts** | `scripts/analyze_chat_costs.py` (and any SQL dashboards): default filter **`tier_used IS NOT NULL`** and/or **`normalized_query IS NOT NULL`** for **tier-mix / cost** metrics; optionally report **`(null)`** as **“Track A / unknown tier”** bucket. |
| **Code fix?** | **Not required** to stop NULL production churn if **`POST /chat`** is deprecated or unused in prod. If Track A must stay, consider **`tier_used='track_a'`** (or similar) **on insert** for observability — **small** change, but touches product/analytics semantics → owner approval. |
| **Data fix / backfill** | **Do not** invent tiers for NULL rows. Optional **one-time annotation** (e.g. `tier_used='legacy_uninstrumented'`) for the **six** prod NULL pairs — **low value**; leaving them as historical noise is reasonable. |
| **Tests** | If new sentinel or filters: add **unit tests** for `log_chat_turn` / analytics filter; no need for migration if only docs + script filters. |
| **Risk** | Mis-backfilling NULL → `"1"`/`"3"` would **corrupt cost analytics**; avoid. |

**STOP flag:** None — diagnosis did **not** require schema changes. Scope stays **doc + analytics filtering + optional sentinel** unless owner wants Track A fully unified.

### 5.2 Issue B — `response_text` vs `message`

| Option | Disruption | Recommendation |
|--------|------------|----------------|
| **Rename DB column** `message` → `response_text` | **High** — migration + every ORM/query/admin path | **Reject** — no functional gain. |
| **Update handoff §3.10 (and cross-links)** | **Low** — align spec with **`message`**, **`created_at`**, **`session_id`** (vs abstract `timestamp` / `user_hash` if those were conceptual) | **Preferred** — handoff is spec; code + DB are canonical since Phase 2. |
| **Code comment** in `chat_logging.py` | Optional one-line: “`response_text` param persists to `ChatLog.message` per legacy column name.” | Nice-to-have for implement. |

**STOP flag:** None — mismatch is **simple naming**, not dual columns.

---

## 6. STOP triggers encountered

- **Production DB access:** **Available** via `railway run` (Railway CLI 4.40.0, project linked, read-only SELECTs).
- **Schema surprise:** None — **`created_at`** used instead of handoff **`timestamp`** name (same drift class as Issue B; note in handoff update).

---

## 7. Files touched by this read-first

- **Created (uncommitted):** `docs/phase-8-0-5-read-first-report.md` (this file).
- **No** modifications to tracked files.

---

## 8. Summary for owner (implementation gate)

1. **Prod NULL rate (~1.6%) + placeholder (~0.5%) ≈ handoff 2.4%.** **Dev NULL rate (~23%)** is **environment-specific** (Track A + tests), **not** a prod regression signal.
2. **NULL `tier_used`** is **explained fully** by **`log_chat_turn`** — **inventory complete**.
3. **Timestamp clustering** supports **legacy / alternate endpoint** interpretation, **not** “broken `log_unified_route` today.”
4. **`response_text`** is **handoff-only**; persistence is **`message`** — **doc fix primary**, **no migration**.

Ready for **Phase 8.0.5-implement** scoping after your review.
