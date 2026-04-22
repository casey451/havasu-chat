# Phase 8.0.1 — Bug-fix track triage (read-only)

**Date:** 2026-04-22  
**Environment:** Windows, repo `c:\Users\casey\projects\havasu-chat`, `.\.venv\Scripts\python.exe`

---

## Pre-flight checks (prompt § Pre-flight checks)

### 1. `git log --oneline -5`

```text
7a12022 docs: Phase 6 close — all sub-phases shipped, Phase 8 next
35194af Phase 6.5-lite: local voice plumbing (empty, ready to grow)
a9dca4d docs: Phase 6.5 deferral plan and correct-and-grow workflow
3b6315e Phase 6.4.1: recommended-entity capture for prior_entity
9f8abb0 test: fix environment-dependent assertions in embedding and router latency tests
```

**Check against prompt:** HEAD is **`7a12022`**, not **`35194af`** alone. `35194af` is **parent** of HEAD (docs-only commit on top of Phase 6.5-lite).

### 2. `git status -sb`

```text
## main...origin/main
?? docs/phase-6-1-3-close-status-response-2026-04-21.md
?? docs/phase-6-1-3-cursor-prompt-commit-close.md
?? docs/phase-6-1-4-commit-response-2026-04-21.md
?? docs/phase-6-1-4-cursor-prompt-voice-fixes-2026-04-21.md
?? docs/phase-6-1-4-cursor-prompt-voice-fixes.md
?? docs/phase-6-3-implementation-summary.md
?? docs/phase-6-3-preflight-report.md
?? docs/phase-6-4-1-cursor-prompt-chat-export.md
?? docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md
?? docs/phase-6-4-1-deploy-and-production-smoke-2026-04-22.md
?? docs/phase-6-4-1-gates-response-2026-04-22.md
?? docs/phase-6-4-1-implementation-summary.md
?? docs/phase-6-4-post-deploy-report-2026-04-21.md
?? docs/phase-6-5-docs-commit-confirmation-2026-04-22.md
?? docs/phase-6-5-lite-post-deploy-2026-04-22.md
?? docs/t3-24-voice-audit-sample.md
```

**Check against prompt:** **Not** a clean working tree — **untracked** files under `docs/` only; **no modified tracked files** before this report.

### 3. `.\.venv\Scripts\python.exe -m pytest -q`

**Before items 1–8:**

```text
742 passed in 403.89s (0:06:43)
```

**After report write (acceptance re-check):**

```text
742 passed in 412.15s (0:06:52)
```

---

## Execution note (HTTP vs TestClient)

Items **1–3**, **6**, and **item 8 (t3-01)** used **`fastapi.testclient.TestClient` against `app.main:app`**, which performs real HTTP to `http://testserver/api/chat` (and admin routes) with the same stack as local uvicorn. **No code in `app/` was modified** for this triage.

---

## Item 1 — Mountain-bike retrieval miss

### Command

`.\.venv\Scripts\python.exe C:\Users\casey\AppData\Local\Temp\phase_8_0_1_triage_run.py`  
*(stdout excerpt: `=== COMMAND: TestClient POST /api/chat (item 1) ===` …)*

### Raw — POST `/api/chat` — `"mountain biking trails in Havasu"`

```json
{
  "response": "I don't have mountain biking trails in the catalog — try the Lake Havasu CVB at https://www.golakehavasu.com/ or search \"mountain biking trails Lake Havasu\" for current conditions and local favorites.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": null,
  "tier_used": "3",
  "latency_ms": 4876,
  "llm_tokens_used": 3448,
  "chat_log_id": "2450c402-2231-45a3-b95b-50df3965161d"
}
```

### Raw — POST `/api/chat` — `"Havasu Mountain Bike Association"`

```json
{
  "response": "The Lake Havasu Mountain Bike Club runs free practices at Sara Park and Rotary Park — Sunday 9–10:30am and Monday & Wednesday 4:30–6pm, open to ages 4 and up through May (summer schedule TBD). Call (619) 823-5088 for details.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": "Lake Havasu Mountain Bike Club",
  "tier_used": "3",
  "latency_ms": 3904,
  "llm_tokens_used": 4370,
  "chat_log_id": "ff532d36-ac3f-4e03-a12b-3e7c4ae58d2d"
}
```

### Raw — POST `/api/chat` — `"where can I mountain bike"`

```json
{
  "response": "I don't have that place in the catalog yet. Add it at /contribute or share the name and a link (Google Business page or official site) — either works.",
  "mode": "ask",
  "sub_intent": "LOCATION_LOOKUP",
  "entity": null,
  "tier_used": "gap_template",
  "latency_ms": 1363,
  "llm_tokens_used": null,
  "chat_log_id": "92e93032-a2aa-45f5-96ad-802e9686f68d"
}
```

### Raw — SQL (SQLAlchemy `text()`, local SQLite)

**Command (conceptual):** `SELECT id, provider_name FROM providers WHERE provider_name LIKE '%mountain%bike%' COLLATE NOCASE`

```text
providers LIKE %mountain%bike%: [('a30c2e60-311c-4c1b-9e7a-7eb0ab5d91d0', 'Lake Havasu Mountain Bike Club')]
```

**Command:** `SELECT id, title, provider_name FROM programs WHERE (title LIKE '%mountain%bike%' OR provider_name LIKE '%mountain%bike%') COLLATE NOCASE`

```text
programs mountain bike: [('fec7772c-58d7-47ee-b0e3-1b7a975fe0d4', 'Mountain Bike Practice — Sara Park (Sunday)', 'Lake Havasu Mountain Bike Club'), ('a8113c7e-dfba-4807-ab63-dcbce3916905', 'Mountain Bike Practice — Sara Park (Monday)', 'Lake Havasu Mountain Bike Club'), ('2c61f512-a7ce-477c-958e-0f17a84fb02c', 'Mountain Bike Practice — Rotary Park (Wednesday)', 'Lake Havasu Mountain Bike Club')]
```

**Command:** `SELECT id, provider_name FROM providers WHERE provider_name LIKE '%bike%' COLLATE NOCASE`

```text
providers LIKE %bike%: [('a30c2e60-311c-4c1b-9e7a-7eb0ab5d91d0', 'Lake Havasu Mountain Bike Club')]
```

### One-sentence assessment

Catalog **does** contain **Lake Havasu Mountain Bike Club** and mountain-bike **programs**; **entity-named query surfaces them**, while **generic “trails” / LOCATION_LOOKUP phrasing** still yields **Tier 3 CVB pointer** or **gap_template** without the club string in the assistant reply.

---

## Item 2 — Tier 2 explicit-rec routing (closes t3-24)

### Command

Same script, section `=== COMMAND: TestClient POST /api/chat (item 2) ===`.

### Raw — `"What should I do Saturday?"`

```json
{
  "response": "Head to Havasu Lanes for Rock & Bowl Saturday night — it's cosmic bowling with black lights and party lights from 6pm to close, and it's a blast. Way more fun than a regular lane, and perfect for a Saturday night out. If you want something earlier in the day, the trampoline park opens at 9am for open jump sessions.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": null,
  "tier_used": "2",
  "latency_ms": 9730,
  "llm_tokens_used": 2652,
  "chat_log_id": "ec693f9f-383a-48ff-9db4-9702e277534e"
}
```

### Raw — `"What's the best thing to do this weekend?"`

```json
{
  "response": "Hit Altitude Trampoline Park on Saturday — they're open 9am–9pm and a 90-minute open jump session is just $19 if you want something active and fun. Otherwise, there's nothing else on the calendar for this specific weekend, so you might check https://www.golakehavasu.com/events for what's happening locally.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": null,
  "tier_used": "3",
  "latency_ms": 4263,
  "llm_tokens_used": 3477,
  "chat_log_id": "3a6022a8-34a9-4768-8a78-e66706f029a5"
}
```

### Raw — `"Pick one thing for Saturday night"`

```json
{
  "response": "Go to Havasu Lanes for Rock & Bowl Saturday night. Black lights, party lights, and music from 6pm to close — it's the perfect Saturday vibe. Skip the trampoline park; that's more of a daytime thing.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": null,
  "tier_used": "2",
  "latency_ms": 3605,
  "llm_tokens_used": 2628,
  "chat_log_id": "4cabe2a0-dc11-4464-88af-6470294c26e9"
}
```

### One-sentence assessment

**Two of three** explicit-rec-shaped queries returned **`tier_used`: `"2"`** with a **primary pick plus extra venue** (still **not** the old three-way menu + “What sounds good?”), matching **Tier 2 still owning** some explicit-rec traffic.

---

## Item 3 — Q17 re-check (`"Boat rentals on the lake?"`)

### Raw

```json
{
  "response": "That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?",
  "mode": "chat",
  "sub_intent": "OUT_OF_SCOPE",
  "entity": null,
  "tier_used": "chat",
  "latency_ms": 973,
  "llm_tokens_used": null,
  "chat_log_id": "58beb943-0d0e-4698-90be-9bb8a777b748"
}
```

### One-sentence assessment

Still **`tier_used`: `"chat"`** / **`OUT_OF_SCOPE`** with **trailing user-directed question** (`Want me to…`), i.e. **unchanged class of behavior** for owner **fix-or-ship** review.

---

## Item 4 — `chat_logs` placeholder `tier_used`

### Raw — `SELECT tier_used, COUNT(*) AS c FROM chat_logs GROUP BY tier_used ORDER BY c DESC`

```text
GROUP BY tier_used: [('3', 107), (None, 78), ('2', 43), ('1', 18), ('gap_template', 17), ('chat', 17)]
```

### Raw — sample rows (`tier_used` NULL or `'placeholder'`)

**Note:** Prompt requested column **`response_text`**; **`chat_logs` has no `response_text` column** (see `app/db/models.py` — logged content is in **`message`**). Query used:

`SELECT id, created_at, query_text_hashed, mode, sub_intent, message FROM chat_logs WHERE tier_used IS NULL OR tier_used = 'placeholder' LIMIT 5`

```text
sample NULL or placeholder (note: schema has no response_text column): [('eff16c6d-c04e-48b0-8665-4757c864be28', '2026-04-18 22:12:09.408985', None, None, None, 'yes'), ('bbfb5c70-580f-4869-99e7-75c33bfbea3a', '2026-04-18 22:12:09.412618', None, None, None, "It's been a few minutes, so I cleared where we left off. What would you like to do next?"), ('934ea8a9-0256-45ec-bc22-9113411ca165', '2026-04-18 22:12:10.081547', None, None, None, 'add an event'), ('6a486d68-a38a-499a-8aed-3f29c255a37f', '2026-04-18 22:12:10.084562', None, None, None, "Give me a quick blurb — ~20 characters or more so folks know what they're getting."), ('3e5ecb2b-71b1-42c0-bd44-53de31227e16', '2026-04-18 22:12:10.135687', None, None, None, 'cheap boat rental')]
```

### One-sentence assessment

**No rows** in this DB with **`tier_used = 'placeholder'`** in the distribution; **`NULL` tier_used = 78`** (~**29%** of 280 total rows in this snapshot), sample rows look **non-concierge / Track A** style messages.

---

## Item 5 — London Bridge example in `prompts/system_prompt.txt`

### Command

Read file `prompts/system_prompt.txt` (lines 14–32).

### Raw excerpt (5 lines context each side of GOOD example)

```text
  14|  GOOD: "I don't have tonight's live music schedule locked in — try https://www.golakehavasu.com/events or search 'live music Lake Havasu tonight'."
  15|  One move when you can't answer from Context (§8.2): do not stack "I don't have / can't tell you" with both a redirect and a follow-up question or second ask ("let me know the date…", "tell me what you're into…"). Pick one path — either one concrete pointer or one narrow clarification — then stop.
  16|  BAD: "I don't have this weekend's date locked in, so I can't tell you what's on yet. Check https://www.golakehavasu.com/events or let me know the specific date and I'll pull what's happening."
  17|  GOOD: "I don't have this weekend's events locked in — try https://www.golakehavasu.com/events for what's posted."
  18|  Anti-hallucination (catalog truth): never name specific businesses, events, vendors, venues, days, times, addresses, or give a "worth it" verdict on something that is not backed by the Context rows you were given. You may still point to real external resources you did not invent (CVB at https://www.golakehavasu.com/, a tight web search) per the catalog-gap rule above — use those instead of filling in local specifics from general knowledge.
  19|  BAD: "Yeah, the Saturday farmers market at London Bridge is worth it — it's the main weekend draw." (invents a vendor, day, and place not in Context)
  20|  GOOD: "I don't have a farmers market in the catalog — try https://www.golakehavasu.com/ or local listings to see what's running this season."
  21|  Contribution invitations for things not in the catalog (the Phase 3.2.2 gap-handling pattern that asks for a URL-backed name and link) are allowed — those ask for shareable data, not open-ended user preferences.
  22|- Lead with the useful answer, then stop.
  23|- If the context block does not contain enough information, say so plainly and stop — do not invent venues, times, or prices.
  24|- If you cannot answer what they asked (e.g. you don't have that date, or the catalog has no row), say that once and stop. Do not pivot to listing other events, months, or venues they didn't ask for.
  25|  BAD: "I don't have tomorrow's date, so I can't tell you what's happening tomorrow. The catalog shows upcoming events in May and June 2026 (dance showcases, recitals, and theater), but nothing closer than that."
  26|  GOOD: "I don't have tomorrow's date locked in — I can't tell you what's on yet."
  27|- Explicit recommendation triggers (Option 3 — pick and commit): when the user says things like "what should I do," "pick one," "which is best," "worth it," "your favorite," or "what would you do," choose one concrete option from the Context and stand behind it. Do not open with "that depends," do not list unprompted alternatives, and do not ask what they want.
  28|  BAD: "That depends what you're into! You could check out Altitude, or a dance studio. What kind of activity interests you?"
  29|  GOOD: "Hit the Saturday farmers market at London Bridge — it's the main weekend draw if you want something local and low-key."
  30|
  31|Response style:
  32|- Respond in plain text only. Do not use markdown formatting — no asterisks, bold, italics, or headers.
```

### One-sentence assessment

The **Option 3 GOOD example** on **line 29** still reads **`Hit the Saturday farmers market at London Bridge`** immediately after **lines 19–20** forbid **London Bridge farmers market** as **uncontextualized fact**.

---

## Item 6 — Generic 422 on malformed `/api/chat` body

### Raw

```text
http_status: 422
content_type: application/json
body: {"message":"Some event details are not valid. Please check and try again."}
```

### One-sentence assessment

**422** with a **single generic `message` string** that reads **event-specific**, not field-level validation detail for a missing **`query`**.

---

## Item 7 — Admin nav consistency

### Command

`TestClient.get` with `cookies={"admin_session": <sign_admin_cookie()>}` for each path.

### Raw — `href` lines containing `admin` (first 40 matches per page)

**`/admin/contributions`**

```json
[
  "      <a href=\"/admin?tab=queue\">Admin home</a>",
  "      <a href=\"/admin/contributions\">Contributions</a>"
]
```

**`/admin/mentioned-entities`**

```json
[
  "      <a href=\"/admin?tab=queue\">Admin home</a>",
  "      <a href=\"/admin/contributions\">Contributions</a>",
  "      <a href=\"/admin/mentioned-entities\">Mentioned entities</a>",
  "<table>...(rows include /admin/mentioned-entities/{id}...)..."
]
```

**`/admin/categories`**

```json
[
  "      <a href=\"/admin?tab=queue\">Admin home</a>",
  "      <a href=\"/admin/contributions\">Contributions</a>",
  "      <a href=\"/admin/mentioned-entities\">Mentioned entities</a>",
  "      <a href=\"/admin/categories\">Categories</a>"
]
```

### One-sentence assessment

**`/admin/contributions`** exposes **only Admin home + Contributions**; **`/admin/mentioned-entities`** and **`/admin/categories`** include **Contributions + Mentioned entities (+ Categories on categories page)** — **nav link set differs by page**.

---

## Item 8 — `docs/known-issues.md` full read + open-entry status

### Open entries (titles only, file unchanged)

1. `2026-04-21 — Mountain-bike retrieval miss`  
2. `2026-04-21 — Tier 3 date hedging on open-ended temporal queries (Phase 6.1 voice audit)`  
3. `2026-04-21 — Tier 2 handling of explicit-recommendation queries (Phase 6.1 voice audit)`

### Item 8b — Owner flag: `t3-01` / Tier 3 date hedging “stale”

### Command

`.\.venv\Scripts\python.exe C:\Users\casey\AppData\Local\Temp\phase_8_0_1_triage_run.py t301`

### Raw — POST `/api/chat` — `"What's happening this weekend?"`

```text
http_status: 200
body: {"response":"The catalog has no events posted for this weekend (April 25–26). Altitude's open Saturday 9am–9pm with 90-minute jump sessions at $19 if you need something active — try https://www.golakehavasu.com/events for what else might be happening locally.","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"3","latency_ms":4976,"llm_tokens_used":3460,"chat_log_id":"b4cb3cc1-d461-4ba9-a510-e2f47c44498a"}
```

### Per-entry one-line status (open items)

| Entry title | Status |
|-------------|--------|
| Mountain-bike retrieval miss | **NEEDS-RE-CHECK** — partial match to known-issues (generic query still misses club; name query hits). |
| Tier 3 date hedging (`t3-01`) | **STALE** for “no date locked in” hedge — **Now line + resolved weekend window** appear in Tier 3 context; response cites **April 25–26** and catalog gap, **not** “can't lock this weekend's date.” |
| Tier 2 explicit-rec | **CONFIRMED-STILL-BROKEN** — **Item 2** shows **`tier_used` `"2"`** on **“What should I do Saturday?”** and **“Pick one thing for Saturday night”**. |

---

## STOP-and-ask triggers

**None** (no off-list bugs filed; no code edits required to inspect).

---

## Out-of-band notes for owner

- **Pre-flight:** Prompt asked HEAD **`35194af`**; actual **HEAD `7a12022`** (docs). **Working tree** had **untracked docs only**. Triage proceeded; document if you want strict re-run on a clean clone at **`35194af`** only.
- **Temp script:** `C:\Users\casey\AppData\Local\Temp\phase_8_0_1_triage_run.py` — **not committed**; safe to delete locally.
