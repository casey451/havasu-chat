# READ-ONLY INVESTIGATION — Tier 3 unlinked events diagnosis

**Assumption:** Code matches commit `88556bb` in `app/chat/context_builder.py` and related files as read from the repo.

---

## 1. Tier 3 call chain

### Entry: `app/api/routes/chat.py` → `unified_router.route`

`POST /api/chat` calls `unified.route(payload.query, payload.session_id, db)`:

```43:70:app/api/routes/chat.py
@router.post("/api/chat", response_model=ConciergeChatResponse)
# ...
    result = unified.route(payload.query, payload.session_id, db)
# ...
    return ConciergeChatResponse(
        response=result.response,
        # ...
        tier_used=result.tier_used,
```

### Ask path: `unified_router._handle_ask` decides Tier 1 → (explicit rec?) → Tier 2 try → Tier 3

```118:140:app/chat/unified_router.py
def _handle_ask(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: dict | None = None,
    now_line: str | None = None,
) -> tuple[str, str, int | None, int | None, int | None]:
    tier1 = try_tier1(query, intent_result, db)
    if tier1 is not None:
        return tier1, "1", None, None, None
    if _is_explicit_rec(query):
        text, total, tin, tout = answer_with_tier3(
            query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
        )
        return text, "3", total, tin, tout
    t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(query)
    if t2_text is not None:
        return t2_text, "2", t2_total, t2_in, t2_out
    text, total, tin, tout = answer_with_tier3(
        query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
    )
    return text, "3", total, tin, tout
```

**Tier-selection signal (in code):**

- **`"1"`** — `try_tier1` returned a string.
- **`"3"`** — Either `_is_explicit_rec(query)` is true (Tier 2 is **skipped**), or Tier 2 was tried and returned `None`.
- **`"2"`** — `try_tier2_with_usage` returned non-`None` text (parser + DB + formatter path succeeded).

So **open-ended “what’s this summer / July 4 / fireworks” queries are *not* explicit-rec unless they match `_EXPLICIT_REC_PATTERNS` / `_is_explicit_rec`**. They will **try Tier 2 first**. If Tier 2 returns an answer, **`build_context_for_tier3` and `_unlinked_future_events` are never run** for that request.

### Tier 3: `app/chat/tier3_handler.py` — `answer_with_tier3`

```105:174:app/chat/tier3_handler.py
def answer_with_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: Mapping[str, Any] | None = None,
    now_line: str | None = None,
) -> tuple[str, int | None, int | None, int | None]:
    # ...
    context = build_context_for_tier3(query, intent_result, db)
    # ... mid = classifier, User context, Now, optional Local voice ...
    user_text = f"User query:\n{query.strip()}\n\n{mid}\n\n{context}"
    # ...
    msg = client.messages.create(
        # ...
        messages=[{"role": "user", "content": user_text}],
    )
```

`query` and `intent_result` are passed into `build_context_for_tier3`; the **raw user question does not filter** which events are selected (selection is DB predicates + word budget, not query text).

### Context: `app/chat/context_builder.py` — `build_context_for_tier3`, `_unlinked_future_events`

Unlinked events are only considered **after** providers are loaded, and only if the **no-providers** early return is not taken (see early return at 124–128).

---

## 2. `_trim_to_word_budget` behavior

```35:43:app/chat/context_builder.py
def _word_count(text: str) -> int:
    return len(text.split())

def _trim_to_word_budget(text: str, max_words: int) -> str:
    if _word_count(text) <= max_words:
        return text
    words = text.split()
    return " ".join(words[:max_words])
```

- It keeps the **first** `max_words` whitespace-delimited “words” and **drops the tail**. It does not preserve sections or newlines structurally (join is single-space).

**Reserved-tail path when the General calendar block exists:**

```184:190:app/chat/context_builder.py
    body = "\n\n".join(parts)
    if unlinked_text is not None:
        provider_max = max(1, MAX_CONTEXT_WORDS - RESERVED_UNLINKED_WORDS)
        body = _trim_to_word_budget(body, provider_max) + "\n\n" + unlinked_text
    else:
        body = _trim_to_word_budget(body, MAX_CONTEXT_WORDS)
    return body
```

- The **unlinked block** (`unlinked_text`) is **appended after** trim and is **not** an argument to `_trim_to_word_budget`.
- So **the reserved-tail strategy does reserve space** in the sense that the unlinked block **cannot be cut off** by `_trim_to_word_budget` in this path.
- If the **provider** portion alone is longer than `provider_max` (~**1200** words with `MAX_CONTEXT_WORDS=1500` and `RESERVED_UNLINKED_WORDS=300`), only the **head** of that provider portion is kept; the **unlinked** section still appears in full after it.

**Caveat:** `MAX_CONTEXT_WORDS` and `RESERVED_UNLINKED_WORDS` are not patched in production; the math above is the intended behavior in code.

---

## 3. `_unlinked_future_events` query shape and “Oct/Jan vs summer/July”

**Implemented shape (88556bb):**

```90:108:app/chat/context_builder.py
def _unlinked_future_events(
    db: Session, today: date, exclude_ids: set[str], limit: int = _UNLINKED_EVENTS_LIMIT
) -> list[Event]:
    """Future standalone events (no provider) for the general-calendar block."""
    end = today + timedelta(days=365)
    rows = list(
        db.scalars(
            select(Event)
            .where(
                Event.status == "live",
                Event.date >= today,
                Event.date <= end,
                Event.provider_id.is_(None),
            )
            .order_by(Event.date.asc(), Event.start_time.asc())
            .limit(limit)
        ).all()
    )
    return [e for e in rows if e.id not in exclude_ids]
```

With `_UNLINKED_EVENTS_LIMIT = 10` (line 23).

So for the **unlinked** block: **`ORDER BY date ASC, start_time ASC` + `LIMIT 10` → the 10 *earliest* future standalone events** (subject to `status`, `provider_id IS NULL`, and 365-day end cap).

**Reasoning:**

- If **more than 10** future unlinked `live` events have dates **strictly before** July 4, then **July 4** rows **cannot** appear in the unlinked block, because they are not in the first 10 by `date`.
- **October / January** are **after** July on the calendar. If July is missing from the unlinked list **because of `LIMIT 10`**, then **October and January should also be missing** from that same unlinked list *unless* there are **fewer than 10** rows with dates before October (i.e. the 10th row could still be in October or later). So: **“July missing but Oct/Jan present in the *General calendar* lines”** is **not** explained by a simple “first 10 by date” rule alone **if** July’s rows are unlinked, live, and in-window — **July would appear before Oct/Jan** in sort order.
- Plausible reconciliations to validate in **prod DB** (not runnable in investigation env):
  1. **Oct/Jan names in the assistant answer came from the per-provider `Upcoming event` lines** (`_events_future_for` with `provider_id` set), **not** from the “General calendar (upcoming, not attached…)” block. *Option B only adds unlinked rows; it does not remove linked ones.*
  2. **July 4 rows are not in the unlinked set**: e.g. `provider_id` is **not** `NULL`, or `status` ≠ `live`, or `date` outside `today..today+365` from the app’s `date.today()` in the container, or the row count / dates differ from the “28 unlinked” mental model.
  3. **The response was not from Tier 3** (Tier 2 or Tier 1), so the **Option B** path never ran (see section 1).

**DB checks that would confirm or refute:**

- `SELECT id, title, date, status, provider_id FROM events … ORDER BY date LIMIT 20` for unlinked, live, future, and see whether July 4 rows are `NULL` / `live` and where they rank vs row 10.
- For events you believe are “Taste of Havasu” / “Balloon Festival”: check **`provider_id` IS NULL or not**.

---

## 4. Which tier answered? Logging / stored signal

**HTTP API:** `ConciergeChatResponse` includes **`tier_used`**; clients can log it. (`app/api/routes/chat.py`, `app/schemas/chat.py` lines 30–40.)

**Database:** `log_unified_route` persists **`tier_used`** on `chat_logs` (along with `mode`, `sub_intent`, `entity_matched`, token fields, etc.):

```13:47:app/db/chat_logging.py
def log_unified_route(
    db: Session,
    *,
    # ...
    tier_used: str,
    # ...
) -> str | None:
    # ...
        row = ChatLog(
            # ...
            tier_used=tier_used[:32] if tier_used else None,
```

So for a given `chat_log_id` / session+time, **Postgres (prod) can answer “1 vs 2 vs 3”** if logging succeeded.

**In-repo stdout:** there is **no** `logger.info` that records `tier_used` on every request in `unified_router` (only exception paths in places). `tier2_handler` and `tier3_handler` emit **diagnostic** logs on fallbacks / errors, not a single canonical “answered tier X” line.

**Gap:** Default **Railway** request logs are unlikely to show **`tier_used` unless the app or proxy logs the response body** — the tier is in the **DB** and in the **JSON body**, not proven to be in line-oriented logs. **If `log_unified_route` fails,** `chat_log_id` can be `None` and the row may be missing (see exception handling in `unified_router._finish`).

---

## 5. Railway logs vs code, and a proposed (not added) log line

**With current code, default Railway process logs are likely to show:**

- Uvicorn/Gunicorn access lines (path, status).
- **`logging.info` / `logging.exception`** from Tier 2 / Tier 3 on **fallbacks** (e.g. `tier2_handler: fallback: no matches`, `tier3: ANTHROPIC_API_KEY unset`, `tier2_parser: …`).
- They do **not** by default show **unlinked row counts**, **whether the General calendar substring is in `context`**, or **the full trimmed context** — that is **not** logged in 88556bb.

**They do *not* directly prove** “unlinked block present” unless you add logging or query DB + reproduce.

**One low-risk `logger.info` (for a future change, not applied in this investigation)**

- **File:** `app/chat/tier3_handler.py`
- **After:** the line that assigns `user_text` (e.g. line 162: `user_text = f"User query:...` — insert **after** that line, so `user_text` is complete; `context` is still in scope from the earlier `build_context_for_tier3` call).
- **Statement (example):**

```python
logging.info(
    "tier3: gcal_in_context=%s n_words_context=%d",
    "General calendar" in context,
    len(context.split()),
)
```

This file already uses the `logging` module; alternatively `logging.getLogger(__name__).info(...)` for consistency with other modules.

This answers: **Was the General calendar block present in `context`?** and a rough size — **it does not log the full string** (PII/size safe). A more precise “unlinked count” would need logging inside `context_builder` or returning metadata from `build_context_for_tier3`.

---

## Adjacent observations

1. **Tier 2 can mask Option B** — For non–explicit-rec asks, any successful `try_tier2_with_usage` prevents Tier 3 and all of `context_builder` for that turn. Investigating “Hava’s answer” without `tier_used` (DB or client) can misattribute failures to Option B.
2. **No providers → no unlinked** — `build_context_for_tier3` early-returns with no unlinked block if `_fetch_provider_rows` is empty (`context_builder.py` 124–128), per the v1 spec.
3. **Explicit rec → Tier 3, skip Tier 2** — `unified_router.py` 128–132: `_is_explicit_rec` forces Tier 3, so Tier 2 is never tried on those matches.
4. **Query 4 (fireworks, London Bridge)** — If `tier_used=3` but the July 4 / Rotary events were **not** in `context`, the model is still under pressure to answer; the system prompt asks for **Context-grounded** facts, but that is a **separate** failure mode from “trim dropped unlinked” (trim does not drop the unlinked block when that block is built; see section 2). **Hallucinated venue/times** may be model behavior, not the SQL limit.
5. **`date.today()`** in `build_context_for_tier3` (line 122) uses the **server process** calendar date; timezone of the **host** affects “today” if code ever used aware datetimes; here it is naive `date.today()` (UTC/local of container — worth confirming in Railway).

---

*Read-only report. No code or schema changes in producing this file.*
