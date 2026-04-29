# Deletion ship: legacy `/chat` router (H1)

Paste this entire prompt into a **fresh Cursor thread** to execute the ship. Do not merge planning context from other chats.

---

You are executing a pre-planned deletion. The investigation is complete; the plan below is locked. **Do not redesign it.** **Halt and report between commits.**

## Context

Production has shown zero `track_a` traffic over 30 days (486 chat rows total, none on legacy `/chat`). The legacy `app/chat/router.py` is being deleted. The unified concierge router at `POST /api/chat` remains the sole chat entry point.

Reachable-set analysis is done. No dynamic imports under `app/`. No string-based module references. No entry-point declarations. The orphan list below is verified.

## Discipline

- **Halt and report after each commit.** Wait for **"proceed"** before the next.
- Run `python -m pytest -q` after every commit. Suite must be green.
- After commit 7, run `python -m pytest --collect-only -q` then `python -m pytest -q` as final pre-push checks.
- **Do not push** until explicitly told to push.
- If anything deviates from the plan — unexpected import, failing test, ambiguous edit — **stop and report.** Do not improvise.

## Commit sequence

### Commit 1 — Delete `tests/test_phase4.py`

Full file delete. Every test in it hits `/chat` for duplicate detection.

```bash
git rm tests/test_phase4.py
```

Run pytest. Report.

### Commit 2 — Surgical edits to mixed test files

One commit, themed **"remove /chat tests from mixed files."** Edits per file:

#### `tests/test_api_chat.py`

- Delete `test_track_a_post_chat_unchanged`
- Delete `test_track_a_chat_logs_tier_used_sentinel`
- Delete import `from app.db.chat_logging import TRACK_A_TIER_USED`
- Keep all `/api/chat` concierge tests

#### `tests/test_calendar_intent.py`

- Delete `test_chat_endpoint_flags_open_calendar`
- Delete `test_month_look_like_phrase_also_triggers`
- Delete `test_unrelated_message_does_not_trigger`
- Keep `test_calendar_phrases_detected`, `test_non_calendar_phrases_not_detected`, `test_detect_intent_returns_calendar_view`
- Trim `setUp`: drop the `cal-open` / `cal-month` / `cal-neg` `clear_session_state` calls and the `SessionLocal`/`Event` cleanup block — none of the kept tests need them
- Drop now-unused imports: `TestClient`, `app.main.app`, `app.db.database.SessionLocal`, `app.db.models.Event`

#### `tests/test_phase2.py`

- Delete `Phase2ChatTests` class entirely
- Keep `ExtractDateRangeTests` class
- Drop now-unused imports: `TestClient`, `FIELD_PROMPTS`, `clear_session_state`, `get_session`, `SessionLocal`, `Event`, `app.main.app`
- Keep: `monthrange`, `date`, `extract_date_range`

#### `tests/test_phase3.py`

- Delete `test_weekend_search_asks_activity_then_returns_grouped_results`
- Delete `test_empty_search_returns_required_empty_message`
- Delete `test_missing_date_asks_date_first_then_activity`
- Keep `test_rain_triggers_out_of_scope`, `test_restaurant_week_not_dining_redirect`, `test_weather_station_tour_not_weather_redirect`
- Drop now-unused: `TestClient`, `EventCreate`, `Event`, `SessionLocal`, `clear_session_state`, `get_session`, `_next_weekday`, `setUpClass`/`tearDownClass`/`setUp`, `app.main.app`
- Leave the `unittest.TestCase` shell even if thin — refactoring it is out of scope

#### `tests/test_phase6.py`

- Delete only `test_chat_review_offer_after_two_bad_replies`
- Drop the `clear_session_state("phase6-review-flow")` line from `setUp`
- Before finalizing the commit, grep the file for `FIELD_PROMPTS`, `REVIEW_OFFER_MESSAGE`, `SUBMITTED_REVIEW_MESSAGE` — if no surviving test references a name, drop that import
- Keep everything else

#### `tests/test_phase8.py`

- Delete `test_stale_session_returns_warm_message`
- Delete `test_chat_logs_written_for_turn`
- Keep everything else

Run pytest. Report.

### Commit 3 — Unwire `/chat` from `main.py`

In `app/main.py`:

- Delete line `from app.chat.router import router as chat_router` (currently line 31)
- Delete line `app.include_router(chat_router)` (currently line 330)
- In `_is_chat_post_request_url` (currently lines 48–55): simplify the return to match `/api/chat` only. Change  
  `return path.endswith("/api/chat") or path.endswith("/chat")`  
  to  
  `return path.endswith("/api/chat")`.

After this commit, `app/chat/router.py` exists on disk but nothing imports it. This is intentional — the file is removed in commit 4.

Run pytest. Confirm `POST /chat` would now return 404 (route is gone, but file is still in tree). Report.

### Commit 4 — Delete `app/chat/router.py`

```bash
git rm app/chat/router.py
```

Verify nothing else imports `app.chat.router`:

```bash
grep -rn "app.chat.router" app/ tests/ --include='*.py'
```

Should return empty. Run pytest. Report.

### Commit 5 — Delete `app/core/venues.py`

`detect_venue` was the only export and `router.py` was the only consumer. Verify before deleting:

```bash
grep -rn "from app.core.venues\|import app.core.venues\|detect_venue" app/ tests/ --include='*.py'
```

Should return empty (`router.py` is gone in commit 4). If there's any stray reference, halt and report.

```bash
git rm app/core/venues.py
```

Run pytest. Report.

### Commit 6 — Trim `app/db/chat_logging.py`

In `app/db/chat_logging.py`:

- Delete the `TRACK_A_TIER_USED = "track_a"` constant
- Delete the entire `log_chat_turn` function definition
- Keep `log_unified_route` and all imports (`logging`, `Session`, `ChatLog`)

Verify nothing imports the deleted symbols:

```bash
grep -rn "TRACK_A_TIER_USED\|log_chat_turn" app/ tests/ --include='*.py'
```

Should return empty. Run pytest. Report.

### Commit 7 — Trim `app/schemas/chat.py`

In `app/schemas/chat.py`:

- Delete the `ChatRequest` class
- Delete the legacy `ChatResponse` class (the BaseModel one — leave `ConciergeChatRequest` and `ConciergeChatResponse` alone)

Verify nothing imports the deleted classes:

```bash
grep -rn "from app.schemas.chat import.*ChatRequest\|from app.schemas.chat import.*ChatResponse" app/ tests/ --include='*.py'
```

Hits should reference only `ConciergeChatRequest` / `ConciergeChatResponse`. If anything references the bare `ChatRequest` or `ChatResponse`, halt and report.

Run pytest. Report.

## Pre-push verification

After commit 7 reports green:

```bash
python -m pytest --collect-only -q
python -m pytest -q
```

Both must pass clean. The `--collect-only` run is the runtime backstop for decorator-time references that static grep misses.

Report results. Wait for push instruction.

## Post-deploy verification (after push and Railway deploy)

- `GET /health` → 200 with expected body
- `POST /chat` with any payload → 404 (route is gone)
- `POST /api/chat` with valid concierge payload → 200 (unified route still works)

Report all three. Then update `STATE.md` and `BACKLOG.md` per `POST_SHIP_CHECKLIST`.

## Out of scope — do not touch

- `app/core/event_quality.py` symbol cleanup (router-only exports remain in the file as orphan symbols; flagged for a separate follow-up ship)
- `app/chat/unified_router.py:96` comment update (cosmetic; can ride a future commit)
- Any DB migration on `chat_logs.tier_used` (column is VARCHAR(32), not an enum; historical `'track_a'` rows persist as data)
- Refactoring thin test classes in `test_phase3.py` after trim

If you find yourself wanting to change anything not explicitly listed above, halt and report.

---

**Standing by for what Cursor returns after commit 1.**
