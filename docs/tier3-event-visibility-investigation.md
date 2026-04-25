# Read-only investigation — why newly approved events may not surface in Hava chat

**Date:** 2026-04-24  
**Scope:** Code review only (no DB access).  
**Context:** Five `river_scene_import` events approved via `/admin/contributions/{id}/approve`; re-embed run; user chat still does not surface them like seed-adjacent behavior. This document traces **retrieval** paths for `POST /api/chat` (unified router) vs legacy search.

---

## 1. User-facing retrieval: SQL and filters

**Product path:** `POST /api/chat` → `unified.router.route` → `app/chat/unified_router.py` — `_handle_ask` → **Tier 1** → **Tier 2** → **Tier 3** (`unified_router.py` ~118–140). This path does **not** call `app/core/search.search_events`. The legacy static UI uses `POST /chat` → `app/chat/router._run_search_core` → `search_events` (`router.py` ~353–362).

### A. `search_events` (e.g. Track A / `POST /chat` with `SEARCH_EVENTS`)

**File:** `app/core/search.py`

- **Base set:** `_base_future_events_query` (416–421): `Event.date >= today` and, if `date_context` is set, `Event.date` in `[start, end]`. **No** `source`, `verified`, `status`, or `created_by` on `Event` in the base query.
- `search_events` (556+): same candidates; may shrink via `activity_type` terms, literal-match filtering, then embedding vs “without embedding” branches. **No** `Event.source` filter in this module for those filters.

### B. Tier 2 (structured DB)

**File:** `app/chat/tier2_db_query.py`

- **`_query_events` (293–327):** `Event.status == "live"`, date window, optional `ilike` on title/description/location/category, weekday filter. **No** `source`, **no** `provider_id` requirement, **no** `embedding` filter.
- **Browse with no parse dimensions (454–457):** `query` → `_sample_mixed(db, MAX_ROWS)` with **`MAX_ROWS = 8`:** up to 8 **earliest** future `Event` rows (423–429), merged with programs and providers, total capped.

### C. Tier 3 context (feeds the LLM in `answer_with_tier3`)

**File:** `app/chat/context_builder.py`

- **`_events_future_for` (75–85):** `Event.provider_id == provider_id`, `Event.status == "live"`, `Event.date >= today`, `limit(8)`.
- **Effect:** only events **linked to a `Provider` row** appear as “Upcoming event” under that provider. Events with **`provider_id IS NULL`** (typical for seed and contribution-approved rows in current code) are **not** listed in this block, regardless of `source` or `embedding`.
- **Tier 1** `DATE_LOOKUP` with an entity: `_next_event` in `tier1_handler.py` (108–118) — same requirement: `Event.provider_id == provider.id`.

**There is no single “retrieval query” in `/api/chat` that is `search_events` on all events;** the important split is **Tier 2** (ORM on `Event` without `provider_id`) vs **Tier 3** `build_context_for_tier3` (events **scoped to `provider_id`**).

---

## 2. Side-by-side row shape (code-derived, not live DB)

| Column | `run_seed` (`app/db/seed.py` ~518–556) | `approve_contribution_as_event` + `Event.from_create` (`approval_service.py` ~192–211; `models.py` ~114–143) |
|--------|----------------------------------------|-----------------------------------------------------------------------------|
| `source` / `created_by` | `EventCreate` with `created_by="seed"`, `status="live"`, etc. | `source` can be `river_scene_import` when contribution matches; `created_by` `"admin"` for non-`user_submission` |
| `status` | `"live"` | `"live"` |
| `verified` | via `Event.from_create` rules | `ev.verified` set from enrichment (209) |
| `provider_id` | **Not** set in seed path → **NULL** | **Not** set → **NULL** |
| `admin_review_by` | `None` in payload | default **None** |
| `embedding` | set via `generate_query_embedding` (536–550) | **Omitted** at create; not set in approval before commit. After `POST /admin/reembed-all`, can match others if OpenAI path succeeds. |
| `is_recurring` | from payload / `from_create` | from `EventCreate` / recurrence heuristic |

**Takeaway:** Seed and import paths **both** leave `provider_id` unset in code. They differ on **`source` / `created_by` / `verified`** and on **whether `embedding` is set at insert** (seed yes; approval no until re-embed).

---

## 3. `approve_contribution_as_event` — what it sets

**File:** `app/contrib/approval_service.py` ~192–211.

Only `Event` fields from `EventCreate` / `Event.from_create` plus **`ev.verified`**. It does **not** set `provider_id`, `embedding`, or `admin_review_by` (unless defaults). `EventCreate` does not pass `embedding` (default `None`).

`run_seed` explicitly sets **embedding** on the `EventCreate` (536–550).

**Gap vs seed at insert:** no `embedding` on approval; no `provider_id` in **either** path in code.

---

## 4. Embedding model and shape

- **Re-embed (admin):** `app/admin/router.py` 793–812 — `generate_embedding` + `_embedding_input` from `app/core/extraction.py`. `generate_embedding` (272–281) uses **`text-embedding-3-small`**, 1536-dim on success. On failure or missing key, **`_deterministic_embedding`** — **32 dimensions** (`extraction.py` ~295).
- **Seed:** `app/db/seed.py` 536–537 — **`generate_query_embedding`** from `app/core/search.py` — 1536 OpenAI or **`_deterministic_embedding_1536`** on fallback — **not** the 32-dim path.
- **`search_events` (583–585):** uses `event.embedding` in the semantic branch only if **`len(emb) == dim`** (query length, usually 1536). A **32-dim** event vector would not match; row goes to **`without_emb`**.

`Event.embedding` is **JSON** in the ORM — no `pgvector` column type in the reviewed model.

**Relevant mismatch:** re-embed **failure** → 32-dim on event vs 1536-dim query in `search_events` can **degrade** semantic use; it does **not** implement a `source` whitelist.

---

## 5. `source` whitelist

In `app/core/search.py` and `app/chat/tier2_db_query.py`, **`Event.source` is not used in the `WHERE` clauses** reviewed. No evidence of a `source IN (...)` gate excluding `river_scene_import`.

---

## 6. Chat: are embeddings required?

**`search_events`** (`app/core/search.py` ~580–666): events without a 1536-dim embedding that matches the query length land in **`without_emb`**; with `strict_relevance` they can still be merged via the **keyword** path. Not universally dropped for NULL/short embedding in that function.

**`POST /api/chat` Tier 3** does **not** use `search_events` for the catalog block; it uses **`build_context_for_tier3`**, which **does not inject** unlinked `Event` rows (see §1C).

---

## 7. Synthesis — ranked causes

| Option | Verdict |
|--------|--------|
| **(a) `verified` / column filter** | `status == "live"` appears in tier2; not a global `Event.verified` filter in the engines reviewed. |
| **(b) Embedding model/dim mismatch** | Plausible for **degraded** semantic path in `search_events` and admin badges; a weaker story for “April/Oct/Jan only” on **`/api/chat`** Tier 3, which is **not** `search_events`-driven. |
| **(c) `source` excludes `river_scene_import`** | **Not** supported in reviewed code. |
| **(d) Date / slice limits** | Plausible: **`_base_future_events_query` uses `date.today()`**; **`MAX_ROWS = 8`** in browse can omit later-dated future events. |
| **(e) Tier 3 `provider_id` gating** | **Strong for `/api/chat` Tier 3:** `context_builder._events_future_for` (75–85) requires **`Event.provider_id == provider_id`**. Freestanding `live` events (often **NULL** `provider_id` for both seed- and contribution-created rows) **do not** appear in “Upcoming event” lines. Month mentions in answers may be programs, provider text, training prior, or Tier 2 **limited** sample — not a clean “seed table row vs import table row” split. |

### Single most likely cause (Hava on `/api/chat` Tier 3)

**(e) —** Standalone catalog events (including most seed- and import-style rows with **`provider_id IS NULL`**) **never** appear in Tier 3’s **per-provider event** context because of **`app/chat/context_builder.py` lines 75–85 (and 132–136).**

**To confirm in prod:** `SELECT id, title, source, created_by, provider_id, embedding IS NOT NULL` for one seed and one `river_scene_import` event — expect **`provider_id` NULL** for both if the schema matches these code paths.

**Recommendation (out of scope here):** Optionally link events to a `provider` where correct; or extend Tier 3 context to include a bounded set of **unlinked** future `Event` rows; or ensure **Tier 2** fire with structured filters for event questions. If the product still leans on **`search_events`**, keep **re-embed** on the **1536** path to avoid 32/1536 drift (`extraction.generate_embedding` failure vs `search.generate_query_embedding`).

---

*Generated from a read-only Cursor investigation; no code changes.*
