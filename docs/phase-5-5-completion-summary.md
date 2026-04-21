# Phase 5.5 — Completion summary

Phase 5.5 is implemented and verified. Per the agreed workflow, **nothing was committed** until owner approval — say **`approved`** when you want the verbatim commit and push.

## Pre-flight checks

| Check | Result |
|--------|--------|
| **1 — Phase 5.4 in last 20 commits** | **PASS** — `5c58f52 Phase 5.4: Public user contribution form` is on `main`. |
| **2 — Tier 3 + `chat_log` flow** | **PASS** — `POST /api/chat` → `app/api/routes/chat.py` → `unified_router.route()` → `_finish()` → `log_unified_route()` in `app/db/chat_logging.py` (returns `chat_logs.id`). `tier_used == "3"` comes from `_handle_ask` → `answer_with_tier3`. Response is the `ChatResponse` returned from `route()`. **Before 5.5:** `BackgroundTasks` was not used on `/api/chat`; **now** it is injected on `post_concierge_chat` and schedules `scan_and_save_mentions` when `tier_used == "3"` and `chat_log_id` is set. |
| **3 — BackgroundTasks (5.2 pattern)** | **PASS** — `admin_contributions.py` uses `BackgroundTasks` + `add_task(enrich_contribution, row.id, SessionLocal)`; promote paths reuse the same `enrich_contribution` + `SessionLocal` pattern. |

## Verification

| Step | Result |
|------|--------|
| **`pytest` full suite** | **644 passed** (~12.7s) |
| **`scripts/run_query_battery.py` (production)** | **116 / 120** matches (meets ≥116 Track A bar) |

## What was built

- **Model + migration:** `LlmMentionedEntity` in `app/db/models.py`; `alembic/versions/c6d7e8f9a012_add_llm_mentioned_entities.py`.
- **Scanner + background save:** `app/contrib/mention_scanner.py` — `MentionCandidate`, `scan_tier3_response`, `STOP_PHRASES` / `STOP_PHRASES_LC`, URL strip, regex 2–5 title-case words, min length 6, dedupe, snippets; `scan_and_save_mentions` (try/except, new session, `IntegrityError` → `None` from store).
- **Store:** `app/db/llm_mention_store.py` (create/get/list/dismiss/promote/count + optional `detected_from` / `detected_to`).
- **API schema:** `app/schemas/llm_mention.py` (`LlmMentionResponse` with `from_attributes=True`).
- **Chat:** `app/api/routes/chat.py` — `BackgroundTasks`, optional `chat_log_id` on response; `app/schemas/chat.py` — `chat_log_id` on `ConciergeChatResponse`.
- **Router logging:** `app/db/chat_logging.py` returns `str | None`; `app/chat/unified_router.py` — `ChatResponse.chat_log_id`.
- **Admin HTML:** `app/admin/mentions_html.py` + `register_mentions_html_routes` from `app/admin/router.py` — list (status + date range, pagination, catalog hint via `Provider.provider_name` / program & event titles), detail, promote, dismiss; HTML escaped with `_esc`.
- **Admin JSON:** `app/api/routes/admin_mentions.py` + `app/main.py` `include_router`.
- **Tests:** `tests/test_mention_scanner.py`, `test_llm_mention_store.py`, `test_admin_mentions_html.py`, `test_admin_mentions_api.py`, `test_tier3_mention_scan.py`; updates to `test_api_chat.py`, `test_api_chat_e2e_ask_mode.py`, `test_phase2_integration.py`.

## Scan scheduling (Check 2)

After `unified.route()` returns, `post_concierge_chat` adds:

`scan_and_save_mentions(chat_log_id, response_text, SessionLocal)` **only if** `tier_used == "3"` and `chat_log_id` is non-null.

## Sample scanner output (family-style line)

**Input:**

*For family fun try Rotary Community Park, London Bridge Beach, or Splash Bash Saturdays at Aquatic Center.*

**Candidates (names only):** Rotary Community Park, London Bridge Beach, Splash Bash Saturdays, Aquatic Center.

## `STOP_PHRASES` (module content)

Same strings as in `app/contrib/mention_scanner.py` `STOP_PHRASES` frozenset: Lake Havasu, Lake Havasu City, Havasu, Havasu Chat, Arizona, United States, USA, North America, West Coast, weekdays (Monday–Sunday), months January–December, Google / Google Search / YouTube, Lake Havasu CVB, Convention Visitors Bureau.

## STOP-and-ask

None — no auto-promotion from scanner, no NLP deps, no Tier 3 prompt edits, no `Contribution` schema changes.

## Commit workflow (owner)

When satisfied, reply **`approved`** for a single commit with message:

```text
Phase 5.5: LLM-inferred facts logging
```

and one push to `main` (no amend, no hook bypass, leave `Made-with: Cursor` trailer as-is).
