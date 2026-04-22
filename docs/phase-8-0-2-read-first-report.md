# Phase 8.0.2 — Router-level explicit-rec bypass (READ-FIRST report)

Date: 2026-04-22  
Repo: `c:\Users\casey\projects\havasu-chat`  
Mode: read-only inspection; no code edits; no commit.

---

## Pre-flight results (raw)

### 1) `git log --oneline -5`

```text
0e7708f Phase 8.0.1.6: gitignore Cursor handback and pre-flight-stop reports
8d48eed Phase 8.0.1.5: archive Phase 6 + 8.0.1 process artifacts, gitignore chat-export prompts
69e1a75 Phase 8.0.1: bug-fix track triage report
7a12022 docs: Phase 6 close — all sub-phases shipped, Phase 8 next
35194af Phase 6.5-lite: local voice plumbing (empty, ready to grow)
```

### 2) `git status`

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

### 3) `.\.venv\Scripts\python.exe -m pytest -q`

```text
........................................................................ [  9%]
........................................................................ [ 19%]
........................................................................ [ 29%]
........................................................................ [ 38%]
........................................................................ [ 48%]
........................................................................ [ 58%]
........................................................................ [ 67%]
........................................................................ [ 77%]
........................................................................ [ 87%]
........................................................................ [ 97%]
......................                                                   [100%]
742 passed in 446.00s (0:07:25)
```

---

## 1) Current routing flow for OPEN_ENDED / explicit-rec queries

### Raw code excerpts

`app/chat/unified_router.py`:

```python
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
    t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(query)
    if t2_text is not None:
        return t2_text, "2", t2_total, t2_in, t2_out
    text, total, tin, tout = answer_with_tier3(
        query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
    )
    return text, "3", total, tin, tout
```

```python
if intent_result.mode == "ask":
    text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
        q_raw, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
    )
```

`app/chat/tier2_handler.py`:

```python
def try_tier2_with_usage(
    query: str,
) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    q = (query or "").strip()
    if not q:
        logging.info("tier2_handler: fallback: empty query")
        return None, None, None, None

    filters, p_in, p_out = tier2_parser.parse(q)
    if filters is None:
        logging.info("tier2_handler: fallback: parser error")
        return None, None, None, None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: parser refused")
        return None, None, None, None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: low confidence")
        return None, None, None, None

    rows = tier2_db_query.query(filters)
    if len(rows) == 0:
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None

    text, f_in, f_out = tier2_formatter.format(q, rows)
    if text is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None, None, None, None
```

`app/chat/intent_classifier.py`:

```python
def _ask_sub_intent(nq: str) -> tuple[str, float]:
    if _NEXT_OCCURRENCE.search(nq):
        return "NEXT_OCCURRENCE", 0.78

    for intent_name, pattern in INTENT_PATTERNS:
        if pattern.search(nq):
            if intent_name == "HOURS_LOOKUP" and _OPEN_NOW_DISAMBIG.search(nq):
                return "OPEN_NOW", 0.82
            return intent_name, 0.88

    if _LIST_BY_CATEGORY.search(nq):
        return "LIST_BY_CATEGORY", 0.75

    if _OPEN_NOW_DISAMBIG.search(nq):
        return "OPEN_NOW", 0.7

    return "OPEN_ENDED", 0.68
```

```python
def classify(query: str) -> IntentResult:
    ...
    if mode == "ask":
        sub, sub_conf = _ask_sub_intent(nq)
    ...
    return IntentResult(...)
```

### Plain-English current flow

- `route()` classifies mode/sub-intent; for `mode == "ask"` it calls `_handle_ask()`.
- `_handle_ask()` is fixed order: Tier 1 first, then Tier 2 (`try_tier2_with_usage`), then Tier 3 if Tier 2 returns `None`.
- There is no router-level explicit-rec detector in `unified_router.py`; routing to Tier 2 vs Tier 3 is currently decided by Tier 2 success/fallback behavior.
- `intent_classifier.py` assigns many ask queries (including recommendation-style) to `OPEN_ENDED`; that label alone does not force Tier 3.

---

## 2) Explicit-rec trigger matches in `app/`, `prompts/`, `scripts/`, `tests/` (raw grep output)

Command intent: search for `what should i do|pick one|which is best|\bbest\b|worth it|your favorite|what would you do` with 3 lines context.

### `app/` raw matches

```text
app\chat\intent_classifier.py
  65-
  66-_SMALL_TALK = re.compile(
  67-    r"^\s*(thanks|thank you|thx|ty|appreciate it|much appreciated|how are you|how is it going|"
  68:    r"you are the best|you rock|bye|goodbye|good night|goodnight)\b[\s,!.]*$",
  69-    re.IGNORECASE,
  70-)
  71-

app\core\intent.py
  108-        (
  109-            "restaurant",
  110-            "where to eat",
  111:            "best place to eat",
  112:            "best places to eat",
  113-            "dinner spot",
  114-            "breakfast spot",
  115-            "lunch spot",
```

### `prompts/` raw matches

```text
prompts\system_prompt.txt
  27:- Explicit recommendation triggers (Option 3 — pick and commit): when the user says things like "what should I do," "pick one," "which is best," "worth it," "your favorite," or "what would you do," choose one concrete option from the Context and stand behind it. Do not open with "that depends," do not list unprompted alternatives, and do not ask what they want.

prompts\tier2_formatter.txt
  7:Explicit recommendation (Option 3 — handoff §8.4): when the user's message matches any of these triggers (case-insensitive, substring OK): "what should I do", "pick one", "which is best", "worth it", "your favorite", "what would you do" — treat it as a request for one committed pick from the rows. ...

prompts\tier2_parser.txt
  25:Query: what should I do saturday
  26-Output: {"day_of_week": ["saturday"], "time_window": "this_weekend", "parser_confidence": 0.85, "fallback_to_tier3": false}
  ...
  43:Query: your favorite event coming up
  44-Output: {"time_window": "upcoming", "parser_confidence": 0.8, "fallback_to_tier3": false}
```

### `scripts/` raw matches

```text
scripts\run_voice_spotcheck.py
  24:    "What should I do Saturday?",
  25:    "Pick one thing to do with kids this weekend",
  26:    "What's the best BMX program in town?",
  27:    "Is the farmers market worth it?",
  28:    "Your favorite event coming up?",
```

### `tests/` raw matches

```text
tests\test_tier2_formatter.py
  39:    assert "pick one" in body
  40:    assert "your favorite" in body or "favorite" in body

tests\test_tier2_parser.py
  48:    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "what should i do saturday")
  61:        json.dumps(payload), "pick one thing to do with kids this weekend"
  107:    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "your favorite event coming up")
  146:        json.dumps(payload), "what is the best bmx program in town"
```

---

## 3) Why `"best"` routes Tier 3 while `"should"` can route Tier 2

### Raw runtime evidence (local)

Direct `/api/chat` comparison:

```text
QUERY: What should I do Saturday?
{"response":"Go bowling at Havasu Lanes ...","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"2","latency_ms":4670,"llm_tokens_used":2656,"chat_log_id":"bdf86618-46d5-4cd0-ad54-6d8623ce8de3"}
---
QUERY: What's the best thing to do this weekend?
{"response":"Hit Altitude Trampoline Park on Saturday ...","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"3","latency_ms":4540,"llm_tokens_used":3449,"chat_log_id":"0865c4d7-93e5-474d-b2b8-e769a2ece0c7"}
---
```

Tier 2 parser output + Tier 2 row counts for the same two queries:

```text
QUERY: What should I do Saturday?
FILTERS: {'entity_name': None, 'category': None, 'age_min': None, 'age_max': None, 'location': None, 'day_of_week': ['saturday'], 'time_window': 'this_weekend', 'open_now': False, 'parser_confidence': 0.85, 'fallback_to_tier3': False}
ROW_COUNT: 7
ROW_TYPES: ['program', 'program', 'program', 'program', 'program', 'program', 'program']
---
QUERY: What's the best thing to do this weekend?
FILTERS: {'entity_name': None, 'category': None, 'age_min': None, 'age_max': None, 'location': None, 'day_of_week': None, 'time_window': 'this_weekend', 'open_now': False, 'parser_confidence': 0.7, 'fallback_to_tier3': False}
ROW_COUNT: 0
ROW_TYPES: []
---
```

### Code path proving mechanism

`app/chat/tier2_db_query.py`:

```python
def _only_time_window(filters: Tier2Filters) -> bool:
    if filters.time_window is None:
        return False
    return not any(
        (
            bool(filters.entity_name and filters.entity_name.strip()),
            bool(filters.category and filters.category.strip()),
            filters.age_min is not None,
            filters.age_max is not None,
            bool(filters.location and filters.location.strip()),
            bool(filters.day_of_week),
        )
    )
```

```python
def _query_programs(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    if _only_time_window(filters):
        return []
```

```python
def _query_providers_orm(db: Session, filters: Tier2Filters) -> list[Provider]:
    if _only_time_window(filters):
        return []
```

```python
rows = tier2_db_query.query(filters)
if len(rows) == 0:
    logging.info("tier2_handler: fallback: no matches")
    return None, None, None, None
```

### Determined mechanism (not guess)

- Both queries classify as `ask/OPEN_ENDED`.
- `"What should I do Saturday?"` yields `day_of_week=['saturday']` + `time_window='this_weekend'`, so Tier 2 can query programs/providers and returns rows; Tier 2 responds.
- `"What's the best thing to do this weekend?"` yields only `time_window='this_weekend'` (no day/category/entity/location), which triggers `_only_time_window=True`; Tier 2 suppresses program/provider sources and effectively relies on events only; local result set is zero; Tier 2 falls back to Tier 3.

---

## 4) Tier 2 fallback conditions (doc vs code)

### Raw code

`app/chat/tier2_handler.py` fallback branches:

```python
if not q:
    logging.info("tier2_handler: fallback: empty query")
    return None, None, None, None

filters, p_in, p_out = tier2_parser.parse(q)
if filters is None:
    logging.info("tier2_handler: fallback: parser error")
    return None, None, None, None
if filters.fallback_to_tier3:
    logging.info("tier2_handler: fallback: parser refused")
    return None, None, None, None
if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
    logging.info("tier2_handler: fallback: low confidence")
    return None, None, None, None

rows = tier2_db_query.query(filters)
if len(rows) == 0:
    logging.info("tier2_handler: fallback: no matches")
    return None, None, None, None

text, f_in, f_out = tier2_formatter.format(q, rows)
if text is None:
    logging.info("tier2_handler: fallback: formatter error")
    return None, None, None, None
```

### Confirmed

- Handoff-listed conditions are present: parser error, low confidence, explicit `fallback_to_tier3`, zero DB results.
- Additional fallback triggers in code (not in the handoff list):
  - empty query
  - formatter error (`text is None`)

---

## 5) Voice battery baseline (`scripts/run_voice_spotcheck.py`) — full output

Command run:

```text
.\.venv\Scripts\python.exe scripts\run_voice_spotcheck.py --base http://127.0.0.1:8000 --skip-smoke
Wrote C:\Users\casey\projects\havasu-chat\scripts\output\voice_spotcheck_2026-04-22T09-22.md
```

Full output file content:

```markdown
# Voice Spot-Check — 2026-04-22T09:22:26Z
# Production URL: http://127.0.0.1:8000
# Battery: 20 queries (Phase 3 voice battery)

**WARNING — row count mismatch:** expected 20 chat_logs rows, got 0 (session_id `voice-spot-2026-04-22T09-22-fe16ff3d23`).

**session_id:** `voice-spot-2026-04-22T09-22-fe16ff3d23`

---

## Query 1
- **Query:** What should I do Saturday?
- **tier_used:** 2
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 5095 (client HTTP elapsed)
- **Response:**

Go to Rock & Bowl at Havasu Lanes Saturday night. Black lights, party lights, and music from 6pm to close — it's the vibe on weekends here. If you want something earlier in the day, hit Altitude Trampoline Park for an open jump session instead.

---

## Query 2
- **Query:** Pick one thing to do with kids this weekend
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 4163 (client HTTP elapsed)
- **Response:**

Take the kids to Altitude Trampoline Park on Saturday morning — they're open 9am–9pm, and a 90-minute open jump session is $19 per person. It's a solid way to burn energy without much planning.

---

## Query 3
- **Query:** What's the best BMX program in town?
- **tier_used:** 2
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 4967 (client HTTP elapsed)
- **Response:**

Go to BMX Training — Wednesday at Lake Havasu City BMX. It's coached skill development from 5–6:15pm, just $5, and you'll get real instruction instead of just showing up to practice. If you want to race instead, their Thursday night race program is USA BMX-sanctioned and runs Oct–Jun. Call (928) 208-5388 to ask about beginner tracks or age groups.

---

## Query 4
- **Query:** Is the farmers market worth it?
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 3606 (client HTTP elapsed)
- **Response:**

I don't have a farmers market in the catalog — try https://www.golakehavasu.com/ or search "farmers market Lake Havasu" to see what's running this season.

---

## Query 5
- **Query:** Your favorite event coming up?
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 3541 (client HTTP elapsed)
- **Response:**

The ACPA Annual Dance Showcase is coming up mid-May — three nights of performances that'll show you what the local dance community's been working on all year.

---

## Query 6
- **Query:** Things to do this weekend
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 4752 (client HTTP elapsed)
- **Response:**

This weekend (Saturday–Sunday, April 25–26), Altitude Trampoline Park is your best bet — they're open 9am–9pm Saturday and 11am–7pm Sunday with 90-minute open jump sessions for $19. If you're looking for something else, I don't have other weekend events locked in for this specific weekend — try https://www.golakehavasu.com/events to see what's posted locally.

---

## Query 7
- **Query:** Family activities this month
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 5108 (client HTTP elapsed)
- **Response:**

For the rest of April, Altitude Trampoline Park's got 90-minute open jump sessions at $19 — it's open Saturday 9am–9pm if you need to burn energy. May picks up with dance showcases (ACPA mid-May) and recitals (Footlite late May), plus Grace Arts Live's Alice in Wonderland Jr. production kicks off in late June.

---

## Query 8
- **Query:** Kids programs at Rotary Park
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 3618 (client HTTP elapsed)
- **Response:**

I don't have kids programs specifically at Rotary Park in the catalog — try the Lake Havasu Parks & Recreation department at https://www.golakehavasu.com/ or call the city directly to ask what's running there this season.

---

## Query 9
- **Query:** Events tomorrow
- **tier_used:** 2
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 5557 (client HTTP elapsed)
- **Response:**

Tomorrow (April 23rd) there's a Local BMX Race at SARA Park BMX Track from 6 to 7 PM. It's a USA BMX-sanctioned weekly race, and admission is $10. If you're into bikes or want to catch some local racing action, it's worth a look.

---

## Query 10
- **Query:** Stuff happening at Sara Park
- **tier_used:** 2
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 5494 (client HTTP elapsed)
- **Response:**

Sara Park's got a solid BMX and mountain bike scene going on.

BMX side: There are weekly USA BMX-sanctioned races on Thursday nights (6–9pm, $10 entry, registration opens at 6). You can also drop in for open practice Tuesday evenings (5–6:30pm, $5) or coached training Wednesday afternoons (5–5:15pm, $5). All skill levels welcome.

Mountain biking: The Lake Havasu Mountain Bike Club runs free dirt trail practice Sunday mornings (9–10:30am, more challenging terrain) and Monday afternoons (4:30–6pm). Both are race-focused sessions through May.

Everything's at 7260 Sara Park Lane. What draws you — racing, practice, or just riding trails?

---

## Query 11
- **Query:** Does Rotary Park have programs for 8-year-olds?
- **tier_used:** 2
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 4129 (client HTTP elapsed)
- **Response:**

Yes. Rotary Park has a Mountain Bike Practice program on Wednesdays from 4:30–6:00 PM run by the Lake Havasu Mountain Bike Club. It's free and designed for new riders starting at age 4, so an 8-year-old would fit right in. It's a non-technical road and path ride—a good way to build fitness and skills before tackling harder terrain.

---

## Query 12
- **Query:** When does the farmers market start on Thursday?
- **tier_used:** gap_template
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 936 (client HTTP elapsed)
- **Response:**

I don't have that event or program in the catalog yet. Add it at /contribute or share the name and a link (Google Business page or official site) — either works.

---

## Query 13
- **Query:** What's at the skate park?
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 3707 (client HTTP elapsed)
- **Response:**

I don't have the skate park in the catalog — try https://www.golakehavasu.com/ or search "skate park Lake Havasu" to find what's there and when it's open.

---

## Query 14
- **Query:** Is Altitude open late on Friday?
- **tier_used:** 1
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 905 (client HTTP elapsed)
- **Response:**

Altitude Trampoline Park is open 11am–8pm on Friday.

---

## Query 15
- **Query:** When's the next BMX race?
- **tier_used:** 1
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 893 (client HTTP elapsed)
- **Response:**

The next Local BMX Race is Thursday, April 23, 2026.

---

## Query 16
- **Query:** Where's the best sushi in town?
- **tier_used:** gap_template
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 1097 (client HTTP elapsed)
- **Response:**

I don't have that place in the catalog yet. Add it at /contribute or share the name and a link (Google Business page or official site) — either works.

---

## Query 17
- **Query:** Boat rentals on the lake?
- **tier_used:** chat
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 949 (client HTTP elapsed)
- **Response:**

That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?

---

## Query 18
- **Query:** Weather this weekend?
- **tier_used:** chat
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 790 (client HTTP elapsed)
- **Response:**

That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?

---

## Query 19
- **Query:** Any good hiking trails?
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 4049 (client HTTP elapsed)
- **Response:**

I don't have hiking trails in the catalog — try the Lake Havasu CVB at https://www.golakehavasu.com/ or search "hiking trails near Lake Havasu" for what's in the area.

---

## Query 20
- **Query:** Is there live music tonight?
- **tier_used:** 3
- **llm_input_tokens:** (unavailable)
- **llm_output_tokens:** (unavailable)
- **Latency (ms):** 3461 (client HTTP elapsed)
- **Response:**

I don't have live music listings in the catalog — try https://www.golakehavasu.com/events or search "live music Lake Havasu tonight" to see what's posted.

---
```

---

## 6) Proposed fix shape (description only; no implementation)

### Where change goes

- Primary: `app/chat/unified_router.py`, function `_handle_ask(...)` (or a helper called from it just before Tier 2 attempt).

### Minimal diff concept

- Add a router-level explicit-rec trigger check on normalized/raw query (case-insensitive substring list matching §8.4 set, plus accepted `"best X"` handling).
- If trigger matches and mode is `ask`, bypass Tier 2 and call Tier 3 directly (`answer_with_tier3(...)`), preserving existing logging and response envelope.
- Keep Tier 1 precedence intact to avoid changing precise factual lookups where Tier 1 already applies.

### Why this is minimal for intended behavior

- Current behavior drift comes from Tier 2 parser + query-shape variability (same intent class, different filter extraction, different Tier 2 row availability).
- Router-level bypass makes explicit-rec deterministic and independent of Tier 2 parser/db shape edge-cases.

### Risk surface

- Queries that include trigger words but were previously better served by Tier 2 could move to Tier 3.
- False positives if trigger matching is too broad (especially bare `"best"` in non-recommendation contexts).
- Tier3 token/cost profile may increase for moved traffic.

### Tests to add/update

- Add router tests asserting `tier_used == "3"` for canonical explicit-rec phrasings:
  - `"What should I do Saturday?"`
  - `"Pick one thing for Saturday night"`
  - `"What's the best thing to do this weekend?"`
  - `"Is the farmers market worth it?"`
  - `"What would you do this weekend?"`
- Add negative controls where Tier 2 should remain eligible (non-explicit-rec OPEN_ENDED).
- Keep existing Tier2 parser/formatter tests unchanged unless trigger list source is centralized.

### Voice-battery risk

- Expected movement: explicit-rec queries currently split between Tier 2 and Tier 3 should converge to Tier 3.
- Most likely affected in spotcheck: queries 1, 2, 3, 4, 5 (and any similar phrasings).
- Direction of movement: Tier 2 -> Tier 3 for trigger matches.

### Downstream data flow impact

- `chat_logs`: `tier_used` distribution shifts toward `"3"` for trigger-matching ask traffic; schema unchanged.
- Analytics/mention scanner: no schema or pipeline changes expected; mention scanner already processes Tier 3 text.

### Coordination needs

- Can be self-contained in router decision point plus trigger list location.
- Optional but recommended follow-up: source-of-truth alignment between router trigger list and prompt text (`prompts/system_prompt.txt`, `prompts/tier2_formatter.txt`) to avoid drift.

### Scope check

- Fix remains within "one router decision point plus trigger list" scope; no schema change, no new module required.

---

## STOP-and-ask trigger status for this read-first pass

- Trigger encountered requiring stop: **none**.
- Notable finding (recorded, not a stop): explicit-rec behavior is currently implemented in prompt-layer instructions, while Tier routing is still parser/result-shape dependent.

