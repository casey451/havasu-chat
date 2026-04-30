> **Status:** pre-H2 read-only investigation; embedded code excerpts predate the LLM-call helper consolidation.
> **H2 stack:** `b47ada6..f7b28df`
> **Current truth:** `app/core/llm_messages.py` and `docs/maintainability/h2_consolidation_decision.md`

# READ-ONLY CODE SPELUNK — Tier 2, gap_template, and explicit-rec patterns

No code changes. No DB queries. No commits. No pushes.

## Q1. What Tier 2 does for OPEN_ENDED calendar queries

### Q1.a Filter set for OPEN_ENDED date-ish queries

Tier 2 flow is parser -> DB query -> formatter (`app/chat/tier2_handler.py`).

- If parser returns valid `Tier2Filters`, confidence >= `0.7`, and `fallback_to_tier3 == False`, Tier 2 runs (`app/chat/tier2_handler.py`).
- Event SQL in `_query_events`:
  - `Event.status == "live"`
  - `Event.date >= lower` where `lower` comes from `_resolve_time_window(...)`
  - optional `Event.date <= win_end` when time window has an end
  - optional text filters on `title/description` (`entity_name`, `category`)
  - optional location filter on `location_name`
  - optional day-of-week post-filter in Python
  - ordered by `Event.date ASC, Event.start_time ASC`
  - SQL `limit(80)`, then output truncated to `MAX_ROWS = 8`
  - **No `provider_id` filter** in Tier 2 event query.
- Programs/providers may also be queried unless `_only_time_window(filters)` is true (time-only asks become events-only).

Relevant code:

```293:327:app/chat/tier2_db_query.py
def _query_events(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    today = _today()
    win_start, win_end = _resolve_time_window(filters.time_window, today)
    lower = win_start if win_start is not None else today
    q = select(Event).where(Event.status == "live", Event.date >= lower)
    if win_end is not None:
        q = q.where(Event.date <= win_end)
    # ... optional entity/location/category filters ...
    rows = list(
        db.scalars(q.order_by(Event.date.asc(), Event.start_time.asc()).limit(80)).all()
    )
    # ... optional category/day_of_week post-filters ...
    return [_event_dict(e) for e in rows[:MAX_ROWS]]
```

### Q1.b If parser gives no concrete date constraint

If parser leaves `time_window` as `None`, Tier 2 still sets window start to `today` and no upper bound (`_resolve_time_window(None, ref) -> (ref, None)`), so it behaves as "upcoming from today" rather than empty.

```114:147:app/chat/tier2_db_query.py
def _resolve_time_window(
    tw: str | None, ref: date
) -> tuple[date | None, date | None]:
    if tw is None:
        return ref, None
    # ...
    if tw == "upcoming":
        return ref, None
```

If parser returns no usable filters at all (`_has_query_dimensions == False`), Tier 2 uses browse-mode mixed sampling (`_sample_mixed`) and still returns rows (future events first, then programs, then providers), capped to 8.

```453:458:app/chat/tier2_db_query.py
def query(filters: Tier2Filters) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        if not _has_query_dimensions(filters):
            return _sample_mixed(db, MAX_ROWS)
```

### Q1.c How formatter presents rows

Formatter is **LLM-based natural-language text**, not deterministic template rendering.

- It JSON-serializes rows and sends them to Anthropic with a formatter system prompt.
- Returns plain text string from model output.

```49:91:app/chat/tier2_formatter.py
def format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]:
    # ...
    system_prompt = _load_formatter_system_prompt()
    system_blocks = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    user_text = (
        f"Query: {query.strip()}\n\n"
        f"Catalog rows:\n{rows_json}\n\n"
        "Respond:"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        system=system_blocks,
        messages=[{"role": "user", "content": user_text}],
    )
```

### Q1.d Formatter prompt template (verbatim)

System prompt file (`prompts/tier2_formatter.txt`):

```text
Role:
You are Hava — the AI local of Lake Havasu. You answer from firsthand local voice at the level of the town: how places here divide, what’s worth knowing, and how the catalog hangs together. You are not a generic assistant and you do not speak as a community database interface.

In this Tier, you format the reply using ONLY the JSON catalog rows provided. Do not invent facts. If the rows don't contain enough to answer what they asked, say so briefly and stop.

**§6.7 (Tier 2 — formatter, not full synthesis):** You are rephrasing data from rows, not inventing visits. At landscape level, one short line of how this kind of place fits Havasu is fine. At the per-row level, stay factual and descriptive from the JSON only — do not add manufactured "I'd sit at the bar" color unless a row actually supplies that kind of operator-grounded detail. For a single business or place, you may start with one framing line, then the specifics from the row(s). Do not use any `source` field or provenance tag to pick voice; work from what the text actually says, not a column label. Never mention a `source` field for how you write.

**Phrases and patterns you never use (persona brief §8.1, verbatim):**
- "Certainly"
- "Absolutely"
- "I'd be happy to help"
- "Here are several options"
- "You may want to consider"
- "As an AI language model…"
- Any customer-service register

**Formatting and length (Tier 2):**
Use ONLY the JSON catalog rows provided. About 80 words for a simple answer, ~120 when comparing a few rows (but Option 3 is usually one pick, not a compare). Contractions OK. No filler. No follow-ups unless they asked one. No conditional prompts ("If you tell me X…").

If the question is outside what the rows support, acknowledge the gap briefly; you may suggest one official site or a tight web search only for that gap — not as filler.

Format:
Plain text only. No markdown (no asterisks, bold, italics, or headers) unless they explicitly wanted a list.

Authoritative spec: `docs/persona-brief.md` + `HAVA_CONCIERGE_HANDOFF.md` §3 + §8.
```

Formatter user payload template:

```text
Query: <original query>

Catalog rows:
<compact JSON rows>

Respond:
```

## Q2. What `_catalog_gap_response` returns

### Q2.a Function body / DATE_LOOKUP branch

```71:82:app/chat/unified_router.py
def _catalog_gap_response(intent_result: IntentResult) -> str | None:
    sub = intent_result.sub_intent
    if sub not in ("DATE_LOOKUP", "LOCATION_LOOKUP", "HOURS_LOOKUP"):
        return None
    if (intent_result.entity or "").strip():
        return None
    if sub == "HOURS_LOOKUP":
        return f"I don't have those business hours in the catalog yet. {_GAP_TAIL}"
    if sub == "LOCATION_LOOKUP":
        return f"I don't have that place in the catalog yet. {_GAP_TAIL}"
    return f"I don't have that event or program in the catalog yet. {_GAP_TAIL}"
```

`_GAP_TAIL` is:

```66:68:app/chat/unified_router.py
_GAP_TAIL = (
    "Add it at /contribute or share the name and a link (Google Business page or official site) — either works."
)
```

### Q2.b Verbatim response text (DATE_LOOKUP)

For `sub_intent == "DATE_LOOKUP"` and no entity:

`I don't have that event or program in the catalog yet. Add it at /contribute or share the name and a link (Google Business page or official site) — either works.`

### Q2.c Conditions for `gap_template` vs Tier 2

In `route(...)`, gap handling executes before `_handle_ask`:

```347:357:app/chat/unified_router.py
if intent_result.mode == "ask":
    gap_text = _catalog_gap_response(intent_result)
    if gap_text is not None:
        return _finish(
            gap_text,
            "ask",
            intent_result.sub_intent,
            intent_result.entity,
            "gap_template",
            None,
        )
```

So `gap_template` fires when:

- `intent_result.mode == "ask"`
- `sub_intent` in `{"DATE_LOOKUP","LOCATION_LOOKUP","HOURS_LOOKUP"}`
- `entity` is blank/None after enrichment

Tier 2 is only attempted when `_catalog_gap_response(...)` returns `None`.

## Q3. Full explicit-rec signal

### Q3.a Full pattern list (verbatim)

```44:52:app/chat/unified_router.py
_EXPLICIT_REC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat should i do\b", re.IGNORECASE),
    re.compile(r"\bpick one\b", re.IGNORECASE),
    re.compile(r"\bwhich is best\b", re.IGNORECASE),
    re.compile(r"\bbest\b", re.IGNORECASE),
    re.compile(r"\bworth it\b", re.IGNORECASE),
    re.compile(r"\byour favorite\b", re.IGNORECASE),
    re.compile(r"\bwhat would you do\b", re.IGNORECASE),
)
```

Matcher:

```111:115:app/chat/unified_router.py
def _is_explicit_rec(query: str) -> bool:
    if not query:
        return False
    return any(p.search(query) for p in _EXPLICIT_REC_PATTERNS)
```

### Q3.b Examples that would match vs not match

Would match (contains one of the regex phrases):

1. "What should I do Saturday?"
2. "Pick one event for me this weekend."
3. "Which is best for date night?"
4. "Is the July 4 show worth it?"
5. "What would you do in Havasu tomorrow?"

Would not match:

1. "What's happening in Havasu this summer?"
2. "What events are happening on July 4?"
3. "When is the 4th of July show in Havasu?"
4. "I'm looking for fireworks on the 4th of July in Lake Havasu."
5. "Any events this weekend?"

### Q3.c Any other Tier 3-forcing mechanism in `_handle_ask`

Yes, two ways Tier 3 runs in `_handle_ask`:

1. `_is_explicit_rec(query)` is true -> immediate Tier 3.
2. Tier 2 attempt returns `None` (`try_tier2_with_usage`) -> fallback Tier 3.

```126:140:app/chat/unified_router.py
tier1 = try_tier1(query, intent_result, db)
if tier1 is not None:
    return tier1, "1", None, None, None
if _is_explicit_rec(query):
    # Tier 3
    ...
t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(query)
if t2_text is not None:
    return t2_text, "2", t2_total, t2_in, t2_out
# Tier 3 fallback when Tier 2 returns None
...
```

There is no additional explicit "force Tier 3" switch in `_handle_ask` beyond those.
