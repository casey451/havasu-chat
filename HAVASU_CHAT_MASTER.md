# HAVASU CHAT — MASTER PROJECT FILE

**Hyperlocal chat app for Lake Havasu City, AZ.**
**Single source of truth for architecture, implementation, and seed data.**

*Compiled April 2026. Drop this file in the project root and feed it to Cursor/Claude Code.*

---

## TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Quickstart for Claude Code / Cursor](#2-quickstart)
3. [Architecture — 3-Tier Response System](#3-architecture)
4. [Build Plan — Implementation Order](#4-build-plan)
5. [Tier 3 System Prompt + Few-Shot Examples](#5-tier-3-system-prompt)
6. [Test Query Suite](#6-test-query-suite)
7. [Voice Audit Prompt](#7-voice-audit-prompt)
8. [Tier 1 Template Library Notes](#8-tier-1-template-library)
9. [Seed Data — 25 Businesses, Programs, Events](#9-seed-data)
10. [Admin Follow-Up Queue](#10-admin-follow-up)

---

# 1. PROJECT OVERVIEW

Havasu Chat is a mobile-first, hyperlocal chat app answering questions about Lake Havasu City businesses, classes, youth programs, and events. It feels like a full LLM chat but only routes ~20% of queries to the LLM — the rest are answered instantly from regex templates and structured handlers.

**Cost target:** <$10/month LLM spend at 1,000 queries/day.
**Latency target:** <100ms for 80% of queries, <3s for 95%.
**Voice:** local friend, not customer service.

**Stack:**
- Backend: Python (existing Havasu Chat repo on Railway)
- DB: PostgreSQL
- LLM: Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Chat frontend: already exists

---

# 2. QUICKSTART

When given this file, Claude Code / Cursor should:

1. Read this entire file top to bottom
2. Verify the 4 prerequisite ChatGPT artifact files exist in the repo:
   - `template_library.py` (from ChatGPT export — Tier 1 templates)
   - `havasu_prompt.txt` (embedded in section 5 below)
   - `havasu_chat_test_queries.txt` (embedded in section 6)
   - `havasu_chat_voice_audit.txt` (embedded in section 7)
3. Confirm the seed data from section 9 is ingested into the database (check `/admin?tab=programs` for ~99 rows)
4. Begin the Build Plan (section 4) starting with Step 1
5. After each step, run tests to confirm nothing broke
6. Commit a working Tier-1-only version after Step 4
7. Commit the full 3-tier version after Step 6

**Ask the user before adding dependencies beyond:** `rapidfuzz`, `anthropic`, existing deps.

---

# 3. ARCHITECTURE

**Purpose:** Feel like a full LLM chat while only routing ~20% of queries to the LLM. Keeps costs low, response times fast, and behavior predictable.

**Core principle:** The user never knows which tier answered. Every response sounds like the same local friend.

## 3.1 Tier Distribution Targets

| Tier | Target % | Method | Cost | Latency |
|------|----------|--------|------|---------|
| Tier 1 | ~55% | Regex + templates | Free | <50ms |
| Tier 2 | ~25% | Structured handlers | Free | <100ms |
| Tier 3 | ~20% | LLM (Claude Haiku) | Paid | 1–3s |

If Tier 3 rate creeps above 25%, add Tier 2 handlers. If Tier 1 drops below 50%, add templates.

## 3.2 Query Flow

```
User query
    ↓
Normalize (lowercase, strip punctuation, expand contractions)
    ↓
Tier 1 attempt — regex intent + entity match + slot fill
    ↓ (fail)
Tier 2 attempt — structured handler (date math, filtering, multi-intent)
    ↓ (fail)
Tier 3 — LLM with trimmed context block
    ↓
Response returned
```

Every response logs `tier_used`, `intent`, `entity`, `latency_ms` to database for analytics.

## 3.3 Tier 1 — Template Responses

**File:** `app/chat/tier1_templates.py` (from ChatGPT export, `template_library.py`)

**Handles:** single-intent, single-entity queries with direct data lookup.

**Intents:**
- `DATE_LOOKUP` — "when is desert storm"
- `TIME_LOOKUP` — "what time does altitude open"
- `LOCATION_LOOKUP` — "where is ballet havasu"
- `COST_LOOKUP` — "how much is bmx"
- `PHONE_LOOKUP` — "havasu lanes phone"
- `HOURS_LOOKUP` — "sonics hours"
- `WEBSITE_LOOKUP` — "iron wolf website"
- `AGE_LOOKUP` — "what ages is little league"

**Tier 1 succeeds ONLY when ALL are true:**
1. Regex intent classifier returns one intent with confidence
2. Entity is extracted and matches a provider/program in seed data
3. The slot for that intent is populated (not null, not `CONTACT_FOR_PRICING` for cost queries)

If any criterion fails → **escalate to Tier 2**.

**Cost lookup special case:** If `cost` is `CONTACT_FOR_PRICING`, do NOT return "unknown" — return the "call for pricing" template variant with the business phone number.

## 3.4 Tier 2 — Structured Fallback

**File:** `app/chat/tier2_handlers.py`

**Handles:** queries that need data + logic but not reasoning. Still deterministic, no LLM call.

**Handlers:**

- `handle_next_occurrence(entity)` — for "when's the next bmx race". Scan events, find earliest future date.
- `handle_list_by_category(category, filters)` — for "what soccer leagues". Filter providers, return top 3–5.
- `handle_multi_intent(intents, entity)` — for "when and where is bmx". Run each intent, combine outputs.
- `handle_open_now(entity)` — for "is altitude open right now". Compare current time to hours.
- `handle_age_scan(age)` — for "do any gyms take 3 year olds". Scan programs by age range.
- `handle_disambiguation(candidates)` — for "swim lessons". If 2+ providers match, list them briefly.

**Success:** handler exists AND required data is present. Otherwise **escalate to Tier 3**.

## 3.5 Tier 3 — LLM Fallback

**File:** `app/chat/tier3_llm.py`

**Handles:** true open-ended, comparison, recommendation, edge cases.

**Examples:**
- "what should I do with my kids this weekend"
- "whats better sonics or flips for fun"
- "martial arts or gymnastics for shy kid"
- "gymnastics near me open now cheap"

**Configuration:**
- **Model:** `claude-haiku-4-5-20251001`
- **System prompt:** loaded from `prompts/system_prompt.txt` (content in section 5)
- **Max tokens:** 150 (enforces 1–3 sentence rule)
- **Temperature:** 0.3
- **Context block:** trimmed seed data (not the full database)

**Context trimming rules:**
- Start with 0 providers
- Match query keywords to provider categories → include those providers
- Match query keywords to provider names → include those providers
- Maximum 10 providers in context, 2000 tokens
- Include each provider's: name, category, address, phone, hours, 2–3 relevant programs

## 3.6 Routing Logic (pseudocode)

```python
def route(query: str) -> ChatResponse:
    normalized = normalize(query)
    start = time.perf_counter()
    
    # Tier 1
    intent, intent_conf = classify_intent(normalized)
    entity = match_entity(normalized)
    if intent and entity and intent_conf > 0.8:
        template_out = render_template(intent, entity)
        if template_out:
            return log(tier=1, response=template_out, ...)
    
    # Tier 2
    handler_result = try_tier2_handlers(normalized, intent, entity)
    if handler_result.success:
        return log(tier=2, response=handler_result.response, ...)
    
    # Tier 3
    context = build_context_block(normalized)
    llm_out = call_llm(normalized, context)
    return log(tier=3, response=llm_out, ...)
```

## 3.7 Voice Consistency

Run voice audit (section 7) against Tier 1 templates and sampled Tier 3 outputs. All three tiers must produce responses that are:

- 1–3 sentences
- Contractions always ("it's", "they're")
- No filler ("Certainly", "Absolutely", "I'd be happy to")
- No follow-up questions
- Direct answer, then stop

Users must not be able to tell which tier answered.

## 3.8 Analytics Schema

Log every response to a `chat_logs` table:

```
- id (uuid)
- timestamp
- user_id (nullable)
- query_text_hashed
- normalized_query
- tier_used (1, 2, 3)
- intent_classified (nullable)
- entity_matched (nullable)
- latency_ms
- response_text
- llm_tokens_used (nullable, Tier 3 only)
```

**Admin dashboard target metrics:**
- Tier 1 rate (target: >50%)
- Tier 3 rate (target: <25%)
- Unanswered rate (target: <3%)
- Median latency per tier
- Top 20 queries that escalated to Tier 3 (candidates for new Tier 1/2 coverage)

## 3.9 Failure Handling

- **Tier 1 fails silently:** fall through to Tier 2. No "I didn't understand" message.
- **Tier 2 fails silently:** fall through to Tier 3.
- **Tier 3 fails loudly:** on LLM error, return: *"I'm having trouble pulling that right now. Try again in a sec or call the business directly."*  Log error, alert admin if rate exceeds threshold.

---

# 4. BUILD PLAN

## 4.1 Prerequisite Checks

- [ ] Providers, Programs, and Events tables seeded (see section 9)
- [ ] `ANTHROPIC_API_KEY` exists as env var on Railway
- [ ] Four ChatGPT artifact files present:
  - `template_library.py` → will become `app/chat/tier1_templates.py`
  - `havasu_prompt.txt` → loaded by `tier3_llm.py`
  - `havasu_chat_test_queries.txt` → used in `tests/test_chat_router.py`
  - `havasu_chat_voice_audit.txt` → used for Tier 1 QA

## 4.2 File Structure

```
app/
  chat/
    __init__.py
    router.py               # main entry point
    normalizer.py           # query normalization
    intent_classifier.py    # regex intent matching
    entity_matcher.py       # fuzzy match to provider/program
    tier1_templates.py      # from ChatGPT template_library.py
    tier2_handlers.py       # structured fallback logic
    tier3_llm.py            # Anthropic API call
    context_builder.py      # trims seed data for LLM
    voice_rules.py          # shared tone constants
    analytics.py            # logging and metrics
  api/
    routes/
      chat.py               # POST /chat endpoint
tests/
  test_chat_router.py
  test_tier2_handlers.py
  test_entity_matcher.py
prompts/
  system_prompt.txt
  voice_audit.txt
```

## 4.3 Step-by-Step

### Step 1 — Normalizer (`normalizer.py`)
Build `normalize(query: str) -> str`:
- Lowercase
- Strip leading/trailing whitespace and punctuation
- Expand contractions ("whens" → "when is", "whats" → "what is")
- Collapse multi-space
- Keep meaningful apostrophes and hyphens

### Step 2 — Entity Matcher (`entity_matcher.py`)
Build `match_entity(query: str) -> tuple[provider_id, confidence] | None`:
- Load all provider names + aliases at startup
- Add nicknames:
  - "sonics" → Universal Gymnastics and All Star Cheer
  - "altitude" → Altitude Trampoline Park
  - "bmx" → Lake Havasu City BMX
  - "bowling alley" → Havasu Lanes
  - "aquatic center" → Lake Havasu City Aquatic Center
  - "tap room" → The Tap Room Jiu Jitsu
  - "bridge city" → Bridge City Combat
  - "little league" → Lake Havasu Little League
  - "iron wolf" → Iron Wolf Golf & Country Club
  - "lions" → Havasu Lions FC
- Use rapidfuzz with token_set_ratio
- Return only if confidence > 75

### Step 3 — Intent Classifier (`intent_classifier.py`)
Build `classify_intent(query: str) -> tuple[intent, confidence]`:
- Use regex patterns from `template_library.py`
- Return the first matching intent, or None
- If multiple match, return `MULTI_INTENT` with a list

### Step 4 — Tier 1 Wiring (`tier1_templates.py`)
- Drop in ChatGPT `template_library.py` contents
- Expose `render(intent, entity, data) -> str | None`
- Return None if any required slot is null

### Step 5 — Tier 2 Handlers (`tier2_handlers.py`)
Implement each handler returning `HandlerResult(success: bool, response: str | None)`:

```python
def handle_next_occurrence(entity_id) -> HandlerResult: ...
def handle_list_by_category(category, filters) -> HandlerResult: ...
def handle_multi_intent(intents, entity_id) -> HandlerResult: ...
def handle_open_now(entity_id) -> HandlerResult: ...
def handle_age_scan(age) -> HandlerResult: ...
def handle_disambiguation(candidates) -> HandlerResult: ...
```

Pull only from seed data. Return `success=False` if the handler can't confidently answer.

### Step 6 — Tier 3 LLM (`tier3_llm.py`)
Build `call_llm(query: str, context: str) -> str`:
- Load system prompt from `prompts/system_prompt.txt`
- Call Anthropic API:
  - model: `claude-haiku-4-5-20251001`
  - max_tokens: 150
  - temperature: 0.3
  - system: loaded prompt
  - messages: `[{"role": "user", "content": f"Local info:\n{context}\n\nUser: {query}"}]`
- Wrap in try/except with graceful fallback message

### Step 7 — Context Builder (`context_builder.py`)
Build `build_context(query: str) -> str`:
- Extract keywords
- Score each provider: category match +3, name match +5, program match +2
- Select top 10 providers
- Format each as:
  ```
  PROVIDER: [name]
  CATEGORY: [category]
  ADDRESS: [address]
  PHONE: [phone]
  HOURS: [hours]
  KEY PROGRAMS: [up to 3 with age range and schedule]
  ```
- Ensure total < 2000 tokens

### Step 8 — Router (`router.py`)
Main orchestrator wiring Tier 1 → 2 → 3 sequentially.

### Step 9 — Endpoint (`api/routes/chat.py`)
```
POST /chat
Body: { "query": string, "user_id": string? }
Response: { "response": string, "tier": int, "latency_ms": int }
```

### Step 10 — Analytics (`analytics.py`)
- Create `chat_logs` table migration
- Insert one row per response
- Build `/admin/chat-analytics` endpoint showing tier distribution, top-20 Tier-3 queries, median latency, unanswered rate

### Step 11 — Test Suite (`tests/test_chat_router.py`)
- Parse `havasu_chat_test_queries.txt` (section 6)
- For each query, assert correct intent, correct tier, non-empty response
- Target: 95%+ pass rate

### Step 12 — Voice Audit
- Run all Tier 1 templates through voice audit prompt (section 7)
- Generate 20 sample Tier 3 responses, audit those too
- Fix anything flagged before production

## 4.4 Implementation Order (minimize blockers)

1. Normalizer → Entity Matcher → Intent Classifier (parallel-safe)
2. Tier 1 wiring
3. Router skeleton (Tiers 2 and 3 return placeholders)
4. Endpoint + analytics (enables real-world testing)
5. Tier 3 LLM (activate escalation path)
6. Tier 2 handlers (add one at a time, measure Tier 3 reduction)
7. Test suite
8. Voice audit
9. Admin dashboard

**You have a working end-to-end chat by step 5.** Then you optimize costs by moving queries from Tier 3 down to Tier 2 in step 6.

## 4.5 Cost Estimation

Assume 1,000 queries/day to start.

- Tier 1 (55%): $0
- Tier 2 (25%): $0
- Tier 3 (20%): 200 queries × ~800 input tokens + 100 output tokens
  - Haiku: ~$1/M input, ~$5/M output
  - Daily: (200 × 800 × $1/M) + (200 × 100 × $5/M) = **~$0.26/day**
  - Monthly: **~$8/month**

If Tier 3 creeps to 40%: ~$16/month.

## 4.6 Validation Checklist

- [ ] All test queries produce responses within expected tier
- [ ] Voice audit passes on 100% of Tier 1 templates
- [ ] Tier 3 responses sampled and audited
- [ ] `/chat` endpoint responds <3s for 95% of queries
- [ ] Tier distribution matches target (±10%) on 200 real queries
- [ ] Analytics dashboard renders correctly
- [ ] Error handling tested (LLM timeout, missing entity, malformed query)

---

# 5. TIER 3 SYSTEM PROMPT

**File destination:** `prompts/system_prompt.txt`

## 5.1 Few-Shot Examples

**Example 1**
User: What time does the Aquatic Center open?
Assistant: It opens at 10am today.

**Example 2**
User: Are there swim lessons for kids?
Assistant: The Aquatic Center offers swim lessons for kids. You can check their schedule or call to see current availability.

**Example 3**
User: How much are swim lessons?
Assistant: I'm not seeing pricing in the info here. You can call them to get the current rates.

**Example 4**
User: What should I do with my kids this weekend?
Assistant: I'm not seeing specific events listed here for this weekend. You can check with local programs or businesses to see what's scheduled.

**Example 5**
User: Where is the trampoline park?
Assistant: It's at [location if in data]. You can call them at (928) 555-1234 for details.

## 5.2 System Prompt

```
You're a Lake Havasu local helping people quickly find things to do,
classes, and events.

Rules: Answer briefly. 1–3 sentences max unless the question truly
requires more. Sound like a real person, not customer service.
Contractions are good. "Yeah" and "yep" are fine when they fit.

Only use facts from the provided data. If it's not there, say you don't
know and suggest calling the business. Never invent prices, phone
numbers, dates, or details.

Be specific when data is available—name the place and give the detail.
Avoid generic phrases.

Do not ask follow-up questions. Answer and stop. Do not say "I'd be
happy to" or "Let me help you with that."

Do not suggest businesses, categories, or activities that are not
present in the provided data.

For open-ended questions:
- Use only the relevant data provided
- If nothing useful is available, say you're not seeing anything
  specific and suggest contacting local businesses directly

When data is missing:
- Say you're not seeing it in the info
- Suggest calling the business or checking their website

Never characterize businesses with opinions (good, great, worth it,
popular, packed) unless that description is directly present in the
provided data.

Format phone numbers as tappable: (928) 555-1234
Format websites as links.

The user just asked: {user_query}

Here's the relevant local info: {context_block}
```

---

# 6. TEST QUERY SUITE

**File destination:** `tests/fixtures/havasu_chat_test_queries.txt`

**Format:** `query | expected_intent | expected_entity_or_category`

## 6.1 DATE_LOOKUP Tests
```
1. when is desert storm poker run | DATE_LOOKUP | Desert Storm Poker Run
2. whens desert storm this year | DATE_LOOKUP | Desert Storm Poker Run
3. desert storm dates? | DATE_LOOKUP | Desert Storm Poker Run
4. when does little league season start | OPEN_ENDED | Schedule/season info
5. when is next bmx race | DATE_LOOKUP | Lake Havasu BMX
6. ballet havasu recital date | DATE_LOOKUP | Ballet Havasu
7. when does sonics season start | OPEN_ENDED | Schedule/season info
8. havasu lions season start date | OPEN_ENDED | Schedule/season info
9. when are swim lessons starting | OPEN_ENDED | Schedule/season info
10. flips for fun schedule start date | OPEN_ENDED | Schedule/season info
```

## 6.2 TIME_LOOKUP Tests
```
11. what time does desert storm start | TIME_LOOKUP | Desert Storm Poker Run
12. what time is the bmx race tonight | TIME_LOOKUP | Lake Havasu BMX
13. altitude hours today what time open | TIME_LOOKUP | Altitude Trampoline Park
14. what time is gymnastics class at sonics | OPEN_ENDED | Class schedule info
15. when does jiu jitsu class start tonight | TIME_LOOKUP | Tap Room Jiu Jitsu
16. havasu lanes closing time | TIME_LOOKUP | Havasu Lanes
17. what time is dance class ballet havasu | OPEN_ENDED | Class schedule info
18. aquatic center open time | TIME_LOOKUP | Havasu Aquatic Center
19. what time are mma classes bridge city | OPEN_ENDED | Class schedule info
20. tkd class time black belt academy | OPEN_ENDED | Class schedule info
```

## 6.3 LOCATION_LOOKUP Tests
```
21. where is altitude trampoline park | LOCATION_LOOKUP | Altitude Trampoline Park
22. where is the bowling alley | LOCATION_LOOKUP | Havasu Lanes
23. where is that gymnastics place on kiowa | LOCATION_LOOKUP | Sonics
24. where is bmx track | LOCATION_LOOKUP | Lake Havasu BMX
25. where is ballet havasu located | LOCATION_LOOKUP | Ballet Havasu
26. havasu aquatic center address | LOCATION_LOOKUP | Havasu Aquatic Center
27. where is tap room bjj | LOCATION_LOOKUP | Tap Room Jiu Jitsu
28. iron wolf golf location | LOCATION_LOOKUP | Iron Wolf Golf
29. where is flips for fun | LOCATION_LOOKUP | Flips for Fun Gymnastics
30. where are swim lessons aqua beginnings | LOCATION_LOOKUP | Aqua Beginnings
```

## 6.4 COST_LOOKUP Tests
```
31. how much is altitude trampoline park | COST_LOOKUP | Altitude Trampoline Park
32. trampoline price havasu | COST_LOOKUP | Altitude Trampoline Park
33. how much does bmx cost | COST_LOOKUP | Lake Havasu BMX
34. swim lessons price aqua beginnings | COST_LOOKUP | Aqua Beginnings
35. bowling cost per game havasu lanes | COST_LOOKUP | Havasu Lanes
36. sonics gymnastics cost | COST_LOOKUP | Sonics
37. how much is ballet classes havasu | COST_LOOKUP | Ballet Havasu
38. tkd classes cost black belt academy | COST_LOOKUP | Black Belt Academy
39. mma classes price bridge city | COST_LOOKUP | Bridge City Combat
40. golf membership iron wolf cost | COST_LOOKUP | Iron Wolf Golf
```

## 6.5 PHONE_LOOKUP Tests
```
41. phone number altitude havasu | PHONE_LOOKUP | Altitude Trampoline Park
42. havasu lanes phone | PHONE_LOOKUP | Havasu Lanes
43. call the bmx track number | PHONE_LOOKUP | Lake Havasu BMX
44. whats the phone for sonics | PHONE_LOOKUP | Sonics
45. aqua beginnings contact number | PHONE_LOOKUP | Aqua Beginnings
46. ballet havasu phone number | PHONE_LOOKUP | Ballet Havasu
47. tap room bjj phone | PHONE_LOOKUP | Tap Room Jiu Jitsu
48. flips for fun number | PHONE_LOOKUP | Flips for Fun Gymnastics
49. black belt academy phone number | PHONE_LOOKUP | Black Belt Academy
50. iron wolf golf phone | PHONE_LOOKUP | Iron Wolf Golf
```

## 6.6 HOURS_LOOKUP Tests
```
51. what are altitude hours | HOURS_LOOKUP | Altitude Trampoline Park
52. havasu lanes hours today | HOURS_LOOKUP | Havasu Lanes
53. bmx track hours | HOURS_LOOKUP | Lake Havasu BMX
54. sonics open hours | HOURS_LOOKUP | Sonics
55. aquatic center hours | HOURS_LOOKUP | Havasu Aquatic Center
56. ballet havasu hours | HOURS_LOOKUP | Ballet Havasu
57. flips for fun open times | HOURS_LOOKUP | Flips for Fun Gymnastics
58. tap room jiu jitsu hours | HOURS_LOOKUP | Tap Room Jiu Jitsu
59. bridge city mma hours | HOURS_LOOKUP | Bridge City Combat
60. iron wolf golf hours | HOURS_LOOKUP | Iron Wolf Golf
```

## 6.7 WEBSITE_LOOKUP Tests
```
61. altitude trampoline website | WEBSITE_LOOKUP | Altitude Trampoline Park
62. havasu lanes website | WEBSITE_LOOKUP | Havasu Lanes
63. bmx havasu website | WEBSITE_LOOKUP | Lake Havasu BMX
64. sonics gymnastics website | WEBSITE_LOOKUP | Sonics
65. aqua beginnings website | WEBSITE_LOOKUP | Aqua Beginnings
66. ballet havasu site | WEBSITE_LOOKUP | Ballet Havasu
67. flips for fun website | WEBSITE_LOOKUP | Flips for Fun Gymnastics
68. tap room bjj site | WEBSITE_LOOKUP | Tap Room Jiu Jitsu
69. black belt academy website | WEBSITE_LOOKUP | Black Belt Academy
70. iron wolf golf website | WEBSITE_LOOKUP | Iron Wolf Golf
```

## 6.8 AGE_LOOKUP Tests
```
71. what age is bmx for | AGE_LOOKUP | Lake Havasu BMX
72. age for sonics gymnastics | AGE_LOOKUP | Sonics
73. ballet havasu age requirements | AGE_LOOKUP | Ballet Havasu
74. swim lessons ages aqua beginnings | AGE_LOOKUP | Aqua Beginnings
75. what ages little league | AGE_LOOKUP | Lake Havasu Little League
76. havasu lions age groups | AGE_LOOKUP | Havasu Lions FC
77. tkd age black belt academy | AGE_LOOKUP | Black Belt Academy
78. mma classes age bridge city | AGE_LOOKUP | Bridge City Combat
79. gymnastics for toddlers havasu | AGE_LOOKUP | Gymnastics options
80. youngest age for dance havasu | AGE_LOOKUP | Dance options
```

## 6.9 LIST_BY_CATEGORY Tests
```
81. what soccer leagues are in havasu | LIST_BY_CATEGORY | Soccer programs
82. kids gymnastics places havasu | LIST_BY_CATEGORY | Gymnastics
83. martial arts for kids havasu | LIST_BY_CATEGORY | Martial arts
84. swim lessons options havasu | LIST_BY_CATEGORY | Swim
85. bowling places havasu | LIST_BY_CATEGORY | Bowling
86. golf courses havasu | LIST_BY_CATEGORY | Golf
87. dance classes for kids havasu | LIST_BY_CATEGORY | Dance
88. trampoline parks near me havasu | LIST_BY_CATEGORY | Trampoline
89. youth sports havasu | LIST_BY_CATEGORY | Youth sports
90. mma gyms havasu | LIST_BY_CATEGORY | MMA
```

## 6.10 OPEN_NOW / NEXT_OCCURRENCE Tests
```
101. is altitude open right now | HOURS_LOOKUP | open_now
102. is havasu lanes open | HOURS_LOOKUP | open_now
103. when's the next bmx race | NEXT_OCCURRENCE | BMX
104. next bmx | NEXT_OCCURRENCE | BMX
```

## 6.11 Edge Cases (expected: Tier 3)
```
1. when and where is the bmx race
2. desert stomr times and location
3. how much and what ages is altitude
4. where is that place kids jump around
5. gymnastics near me open now cheap
6. is there soccer or baseball right now for kids
7. bmx tonight time and cost
8. whats better sonics or flips for fun
9. havasu lanes or another bowling place
10. swimming lessons for babies like 1 year old
11. do any gyms take 3 year olds
12. iron wolf vs other golf course which better
13. desert storm free to watch or not
14. martial arts or gymnastics for shy kid
15. trampoline place hours and price
```

---

# 7. VOICE AUDIT PROMPT

**File destination:** `prompts/voice_audit.txt`

Use this prompt to audit Tier 1 templates and sampled Tier 3 responses. Paste the templates to audit at the bottom where indicated.

```
PROMPT 4 — VOICE AUDIT

I'm building a hyperlocal chat app for Lake Havasu City, Arizona.
The app answers questions about local businesses, events, youth sports,
classes, and activities.

I've written a set of response templates for common user questions.

The voice should sound like a helpful local friend — not a chatbot,
not customer service.

OBJECTIVE

Audit the templates and flag anything that sounds:
- Robotic or templated
- Corporate or customer-service-like
- Overly formal or stiff
- Forced casual (trying too hard)
- Wordy or longer than needed
- Vague when it should be specific
- Awkward when variables/slots are filled
- Inconsistent with the rest

If it wouldn't sound normal said out loud, it's wrong.

VOICE STANDARDS (NON-NEGOTIABLE)

- 1–2 sentences for most responses
- Contractions always ("it's", "they're")
- No filler phrases ("Certainly", "Absolutely", "I'd be happy to help")
- No follow-up questions
- No fluff or padding
- Answer directly, then stop
- Sounds like a local, not a brand
- Confident, not hesitant

OUTPUT FORMAT

Group results by intent category:
DATE_LOOKUP | TIME_LOOKUP | LOCATION_LOOKUP | COST_LOOKUP
PHONE_LOOKUP | HOURS_LOOKUP | WEBSITE_LOOKUP | AGE_LOOKUP
LIST_BY_CATEGORY | OPEN_ENDED

For each category, separate into:

PASS (no changes needed) — list templates that already feel natural

NEEDS FIX — for each template:
  Original: [template]
  Issue: [1 blunt sentence]
  Rewrite: [clean natural version]

CUT — templates that should be deleted entirely because they:
  - Add no value
  - Are redundant
  - Will never sound natural even if rewritten

REWRITE RULES
- Keep it shorter than the original whenever possible
- Replace generic phrasing with specific phrasing
- Remove any "helper tone" or politeness padding
- Make it sound like something you'd actually say out loud

FINAL CHECK
- Voice Score (1–10): [score]
- Diagnosis: [one sentence on what still feels off overall]

TEMPLATES TO AUDIT:

[PASTE TEMPLATES HERE]
```

---

# 8. TIER 1 TEMPLATE LIBRARY

The Python template library (`template_library.py`) is maintained as a separate file in the ChatGPT export. It contains:

- A `TEMPLATES` dict keyed by intent
- A `render(intent, variant, **slots)` function
- Tier 1 intents with multiple response variants each
- Regex patterns for intent classification

**Destination in app:** `app/chat/tier1_templates.py`

**Refinements already applied in the ChatGPT version:**
- Removed broken TIME_LOOKUP variation
- Fixed PHONE_LOOKUP tone
- Removed duplicate UNKNOWN_ENTITY section
- Improved HOURS_LOOKUP closed-state responses
- Added NEXT_OCCURRENCE intent
- Added COST_LOOKUP safety rule (CONTACT_FOR_PRICING fallback)
- Fixed WEBSITE_LOOKUP bare response

**If `template_library.py` isn't in your repo yet:** retrieve it from the ChatGPT conversation where it was generated, or have Cursor re-derive it from the intent list in section 3.3 and voice rules in section 7.

---

# 9. SEED DATA

**Purpose:** verified real-world programs, classes, and events for Lake Havasu City, AZ. Seed into the Havasu Chat database.

## 9.1 Seeding Instructions for Claude Code

### SEED ALL BUSINESSES
Parse each business header block and upsert a Provider record: provider_name, category, address, phone, email, website, facebook, hours.

### SEED ALL PROGRAMS
For each YAML program block, create a Program record with:
- title, activity_category (map to your ActivityCategory enum)
- age_min / age_max (null where not specified)
- schedule_days (array of day strings)
- schedule_start_time / schedule_end_time (24h format, null if unknown)
- schedule_note (plain text)
- location_name / location_address
- cost (numeric; 0.0 for free)
- cost_description (plain text pricing detail)
- provider_name (use to link)
- contact_phone / contact_email / contact_url
- description

Where cost is `CONTACT_FOR_PRICING`, set cost to null and `show_pricing_cta = true` so the app displays "Contact for pricing" with a tap-to-call button.

### SEED ALL EVENTS
For each event block, create an Event record with: title, description, date, time, location, cost, provider. Where date is a range, create separate rows for each date.

### SKIP THESE — DO NOT SEED PUBLIC
- Elite Cheer Athletics — Havasu (no address confirmed)

Mark with `draft = true` so they appear in admin dashboard but not public app.

### FLAG FOR ADMIN REVIEW
Any program or business with a ⚠️ VERIFY note should be seeded but tagged `needs_verification = true`.

### ACTIVITY CATEGORY MAPPING
File uses these strings — map to your enum:
golf, fitness, sports, swim, martial_arts, gymnastics, cheer, dance, theatre, art, summer_camp

### AFTER SEEDING, PRINT SUMMARY
Businesses created | Programs created | Events created | Items flagged needs_verification | Items skipped (draft)

## 9.2 Notes
- `CONTACT_FOR_PRICING` = no public pricing; display "Contact for pricing" in app
- `⚠️ VERIFY` = confirmed but may need a quick check before going live
- `null` = genuinely unknown; leave blank
- `schedule_days` uses: MON, TUE, WED, THU, FRI, SAT, SUN
- Times in 24h format
- Ages in years (0.5 = 6 months, 1.5 = 18 months)
- All addresses in Lake Havasu City, AZ unless noted

---

## BUSINESS 1 — IRON WOLF GOLF & COUNTRY CLUB

```
provider_name:    Iron Wolf Golf & Country Club
category:         golf
address:          3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
phone:            (928) 764-1404
email:            thegolfshop@ironwolfgcc.com
website:          ironwolfgcc.com
facebook:         facebook.com/ironwolfgcc
hours:            Mon 9am–9pm | Tue CLOSED | Wed–Sun 9am–9pm
```

### Programs

```yaml
- title:              Junior Golf Clinic — Session 1
  activity_category:  golf
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "09:30"
  schedule_note:      "2-week session starting June 30, 2026"
  location_name:      Iron Wolf Golf & Country Club
  location_address:   3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
  cost:               250.00
  cost_description:   "$250 per 2-week session. Includes clubs and swag bag."
  provider_name:      Iron Wolf Golf & Country Club
  contact_phone:      (928) 764-1404 ext. 2
  contact_email:      thegolfshop@ironwolfgcc.com
  contact_url:        ironwolfgcc.com
  description:        Small-group junior golf clinic ages 7–17. Includes clubs and swag bag.

- title:              Junior Golf Clinic — Session 2
  activity_category:  golf
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "09:30"
  schedule_note:      "2-week session starting July 14, 2026"
  location_name:      Iron Wolf Golf & Country Club
  location_address:   3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
  cost:               250.00
  cost_description:   "$250 per 2-week session. Includes clubs and swag bag."
  provider_name:      Iron Wolf Golf & Country Club
  contact_phone:      (928) 764-1404 ext. 2
  contact_email:      thegolfshop@ironwolfgcc.com
  contact_url:        ironwolfgcc.com
  description:        Small-group junior golf clinic ages 7–17.
```

---

## BUSINESS 2 — ALTITUDE TRAMPOLINE PARK

```
provider_name:    Altitude Trampoline Park — Lake Havasu City
category:         fitness
address:          5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
phone:            (928) 436-8316
email:            null
website:          altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/
facebook:         facebook.com/altitudelakehavasu
hours:            Sun 11am–7pm | Mon 11am–7pm | Tue 10am–7pm | Wed 11am–7pm
                  Thu 10am–7pm | Fri 11am–8pm | Sat 9am–9pm
notes:            Children 12 & under must have adult present.
```

### Programs

```yaml
- title:              Open Jump — 90 Minutes
  activity_category:  fitness
  age_min:            null
  age_max:            null
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  schedule_note:      "Any open session during business hours"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               19.00
  cost_description:   "$19.00 per person / 90 minutes"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  description:        22,000+ sq ft indoor trampoline park. Trampolines, dodgeball, battle beam, ninja course, arcade. Socks required ($3.50 if needed).

- title:              Open Jump — 120 Minutes
  activity_category:  fitness
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               24.00
  cost_description:   "$24.00 per person / 120 minutes"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  description:        120-minute jump session at 22,000+ sq ft indoor trampoline park.

- title:              Monthly Membership — Standard
  activity_category:  fitness
  schedule_days:      [MON, TUE, WED, THU, FRI, SAT, SUN]
  schedule_note:      "5 days/week, 90 minutes/day"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               15.00
  cost_description:   "$15/month — 5 days/week, 90 min/day"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  description:        Monthly unlimited jumping membership. 5 days/week, 90 min per visit.

- title:              Monthly Membership — Unlimited
  activity_category:  fitness
  schedule_days:      [MON, TUE, WED, THU, FRI, SAT, SUN]
  schedule_note:      "7 days/week, 120 minutes/day"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               25.00
  cost_description:   "$25/month — 7 days/week, 120 min/day"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  description:        Unlimited 7 day/week membership. 120 min per visit.
```

---

## BUSINESS 3 — HAVASU LANES

```
provider_name:    Havasu Lanes
category:         sports
address:          2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
phone:            (928) 855-2695
website:          havasulanesaz.com
facebook:         facebook.com/HavasuLanesAZ
hours:            Mon–Thu 12pm–9pm | Fri–Sat 12pm–11pm | Sun 12pm–7pm
notes:            32 lanes. Sports bar, pool tables, arcade.
```

### Programs

```yaml
- title:              Open Bowling
  activity_category:  sports
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  schedule_start_time: "12:00"
  schedule_end_time:   "21:00"
  schedule_note:      "Fri–Sat open until 11pm. Fri–Sat after 5:30pm switches to Rock & Bowl."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$5.75/person per game + $5.25 shoe rental + $28/hr lane rental"
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  description:        32-lane bowling center with automatic scoring. Bumper bowling available. Arcade on-site.

- title:              Rock & Bowl (Cosmic Bowling)
  activity_category:  sports
  schedule_days:      [FRI, SAT]
  schedule_start_time: "18:00"
  schedule_end_time:   "23:00"
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$18/person (1hr) | $22 (2hrs) | $26 (3hrs) — all include shoes"
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  description:        Friday & Saturday nights. Black lights, party lights, music. All-inclusive pricing.

- title:              Youth Bowling Leagues (USBC Certified)
  activity_category:  sports
  age_max:            17
  schedule_note:      "⚠️ VERIFY — schedule set each season. Contact league."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  description:        USBC-certified youth leagues. Tournament eligibility. Scholarships available.

- title:              Adult Bowling Leagues
  activity_category:  sports
  age_min:            18
  schedule_note:      "⚠️ VERIFY — Senior/Men's/Women's/Mixed leagues. Contact for schedule."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  description:        Multiple adult league options. Contact for current season schedules.
```

---

## BUSINESS 4 — BRIDGE CITY COMBAT

```
provider_name:    Bridge City Combat
category:         martial_arts
address:          2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
phone:            (928) 716-3009
email:            bridgecitycombat@gmail.com
instagram:        instagram.com/bridgecitycombat
hours:            Closes 9pm. Full weekly hours not confirmed.
notes:            In-person booking only. Founder: Christian Beyers.
```

### Programs

```yaml
- title:              Youth Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            5
  age_max:            18
  schedule_days:      [MON, WED]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:00"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  description:        Gi Brazilian Jiu-Jitsu for youth K–12. Submissions, drills, rolling.

- title:              Youth NOGI Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            5
  age_max:            18
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:00"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  description:        No-gi Brazilian Jiu-Jitsu for youth K–12.

- title:              Adult Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [MON, WED]
  schedule_start_time: "18:00"
  schedule_end_time:   "19:00"
  schedule_note:      "Also Tue 6–7am"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  description:        Traditional gi Jiu-Jitsu for adults. All levels.

- title:              Adult NOGI Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [MON, WED, THU]
  schedule_start_time: "19:15"
  schedule_end_time:   "20:15"
  schedule_note:      "Mon & Wed 7:15–8:15pm. Also Wed 6–7am."
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  description:        No-gi adult Jiu-Jitsu. Thursday 6–7pm session also available.

- title:              Adult MMA
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [TUE, THU]
  schedule_start_time: "19:15"
  schedule_end_time:   "20:15"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  description:        MMA combining boxing, wrestling, Jiu-Jitsu, kickboxing. Team competes in amateur MMA.

- title:              Open Mat
  activity_category:  martial_arts
  schedule_days:      [FRI]
  schedule_start_time: "18:00"
  schedule_note:      "Fri 6pm to close. Weekend open mats on Instagram."
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  description:        Open mat rolling session. All levels welcome.
```

---

## BUSINESS 5 — LAKE HAVASU CITY BMX

```
provider_name:    Lake Havasu City BMX
category:         sports
address:          7260 Sara Park Lane, Lake Havasu City, AZ 86406
phone:            (928) 208-5388
website:          usabmx.com/tracks/1292
facebook:         facebook.com/LakeHavasuCityBMX
hours:            Tue 5–6:30pm (practice) | Wed 5–6:15pm (training) | Thu 6–7pm + 7pm racing
organization:     USA BMX sanctioned non-profit
```

### Programs

```yaml
- title:              BMX Racing — Race Night
  activity_category:  sports
  age_min:            5
  schedule_days:      [THU]
  schedule_start_time: "18:00"
  schedule_end_time:   "21:00"
  schedule_note:      "Registration 6–7pm. Racing starts 7pm. Oct–Jun."
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               10.00
  cost_description:   "$10/race. USA BMX annual membership required: $80/year."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  description:        USA BMX-sanctioned race night. Quarter-mile dirt track. Loaner bikes for first-timers.

- title:              BMX Practice — Tuesday
  activity_category:  sports
  age_min:            5
  schedule_days:      [TUE]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:30"
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5/practice. Striders free."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  description:        Open practice night. All skill levels.

- title:              BMX Training — Wednesday
  activity_category:  sports
  age_min:            5
  schedule_days:      [WED]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:15"
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5. Coaching-focused."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  description:        Coached training session for skills development.

- title:              Strider/Balance Bike Track
  activity_category:  sports
  age_min:            1
  age_max:            5
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:00"
  schedule_end_time:   "21:00"
  location_name:      SARA Park BMX Track — Strider Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5/race. Annual membership $30/year."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  description:        Smaller track for youngest riders (1–5) on balance bikes. Separate gate from main track.
```

### Events (weekly recurring pattern)

```yaml
- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race. Registration 6–7pm. $10 to race.
  date:        2026-04-14
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  date:        2026-04-16
  time:        "18:00"
  location:    SARA Park BMX Track
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  date:        2026-04-21
  time:        "18:00"
  location:    SARA Park BMX Track
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  date:        2026-04-23
  time:        "18:00"
  location:    SARA Park BMX Track
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  date:        2026-04-28
  time:        "18:00"
  location:    SARA Park BMX Track
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  date:        2026-04-30
  time:        "18:00"
  location:    SARA Park BMX Track
  cost:        10.00
  provider:    Lake Havasu City BMX
```

---

## BUSINESS 6 — LAKE HAVASU MOUNTAIN BIKE CLUB

```
provider_name:    Lake Havasu Mountain Bike Club
category:         sports
address:          null — practices at Sara Park & Rotary Park
phone:            (619) 823-5088
email:            leaderunlimited@gmail.com
facebook:         facebook.com/groups/LakeHavasuMountainBikeTeam
organization:     501(c)3 nonprofit
notes:            NO membership fees. Loaner bikes for first few practices. Race season Jan–May.
```

### Programs

```yaml
- title:              Mountain Bike Practice — Sara Park (Sunday)
  activity_category:  sports
  age_min:            4
  schedule_days:      [SUN]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:30"
  location_name:      Sara Park
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               0.00
  cost_description:   "Free — no membership fees."
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  description:        Dirt trail riding at Sara Park. Safety-focused crawl/walk/run progression.

- title:              Mountain Bike Practice — Sara Park (Monday)
  activity_category:  sports
  age_min:            4
  schedule_days:      [MON]
  schedule_start_time: "16:30"
  schedule_end_time:   "18:00"
  schedule_note:      "Race practices run through May 2026. Summer TBD."
  location_name:      Sara Park
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               0.00
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  description:        Race practice session at Sara Park dirt trails.

- title:              Mountain Bike Practice — Rotary Park (Wednesday)
  activity_category:  sports
  age_min:            4
  schedule_days:      [WED]
  schedule_start_time: "16:30"
  schedule_end_time:   "18:00"
  location_name:      Rotary Park
  location_address:   Rotary Park, Lake Havasu City, AZ
  cost:               0.00
  cost_description:   "Free — best session for newcomers."
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  description:        Non-technical road/path ride. Great intro for new riders.
```

---

## BUSINESS 7 — UNIVERSAL GYMNASTICS AND ALL STAR CHEER (SONICS)

```
provider_name:    Universal Gymnastics and All Star Cheer — Sonics
category:         gymnastics
address:          2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
phone:            (928) 453-1313
email:            havasusonics@gmail.com
website:          universalgymnasticslakehavasu.com
facebook:         facebook.com/universalsonics
hours:            Mon–Thu 3–9pm | Fri 3–6:30pm | Sat–Sun Closed
notes:            40+ years. USA Gymnastics & USASF Certified. All Star Cheer 2026–27 registration open.
```

### Programs

```yaml
- title:              Gym Tots
  activity_category:  gymnastics
  age_min:            0.5
  age_max:            3
  schedule_days:      [THU]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:00"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  description:        Parent-participation class for babies and toddlers 6 months–3 years.

- title:              Tiny Tumblers
  activity_category:  gymnastics
  age_min:            3
  age_max:            4
  schedule_days:      [TUE, WED, THU]
  schedule_note:      "Tue 4:30–5:15pm & 5:30–6:15pm | Wed 5:30–6:15pm | Thu 6:00–6:45pm"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Beginning gymnastics and tumbling for ages 3–4.

- title:              Recreational Gymnastics (Ages 5–9)
  activity_category:  gymnastics
  age_min:            5
  age_max:            9
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Mon 4–5pm | Tue 4:30–5:30pm | Wed 4–5pm | Thu 4:30–5:30pm"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Recreational gymnastics for school-age kids.

- title:              Recreational Tumbling (Level 1/2/3)
  activity_category:  gymnastics
  age_min:            8
  schedule_days:      [TUE]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Tumbling ages 8+. Three levels.

- title:              Recreational Cheer
  activity_category:  cheer
  age_min:            5
  schedule_days:      [THU]
  schedule_start_time: "15:30"
  schedule_end_time:   "16:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Recreational cheerleading for ages 5+.

- title:              Boys Athletics (Ages 5–10)
  activity_category:  sports
  age_min:            5
  age_max:            10
  schedule_days:      [TUE]
  schedule_start_time: "15:30"
  schedule_end_time:   "16:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Athletic conditioning and gymnastics-based training for boys 5–10.

- title:              Sonics Competitive Gymnastics
  activity_category:  gymnastics
  schedule_days:      [MON, WED, THU, FRI]
  schedule_note:      "Mon & Wed 4–8pm | Thu 5–7pm | Fri 3:15–6:15pm. Invite/tryout required."
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        High-level competitive gymnastics. Invite or tryout required.

- title:              Sonics All Star Cheer (2026–2027 Season)
  activity_category:  cheer
  age_min:            4
  age_max:            18
  schedule_note:      "Multiple teams. Full schedule at universalgymnasticslakehavasu.com. Placements begin May 17, 2026."
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  description:        Competitive All Star Cheer ages 4–18. Regional and national competitions.
```

### Events

```yaml
- title:       Sonics All Star Cheer 2026–2027 — Team Placements
  description: Team placement tryouts. No experience needed. Ages 4–18.
  date:        2026-05-17
  time:        "TBD"
  location:    Universal Gymnastics and All Star Cheer, 2245 N. Kiowa Blvd #102
  cost:        CONTACT_FOR_PRICING
  provider:    Universal Gymnastics and All Star Cheer
```

---

## BUSINESS 8 — ARIZONA COAST PERFORMING ARTS (ACPA)

```
provider_name:    Arizona Coast Performing Arts (ACPA)
category:         dance
address:          3476 McCulloch Blvd, Lake Havasu City, AZ 86404
phone:            (928) 208-2273
email:            arizonacoastperformingarts@gmail.com
website:          arizonacoastperformingarts.com
season:           August–May
notes:            31 years. Female-owned. Max 16 students/class. Full Tue–Thu schedule on website.
```

### Programs

```yaml
- title:              Fine Arts Club (Ages 3–5)
  activity_category:  dance
  age_min:            3
  age_max:            5
  schedule_days:      [MON, TUE, WED]
  schedule_start_time: "12:00"
  schedule_end_time:   "14:00"
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        All-inclusive performing arts for young children.

- title:              Ballet (Levels 1–6)
  activity_category:  dance
  age_min:            5
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Mon 3:30–4:30pm confirmed. Full schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Classical ballet. Levels 1–6. Level 6 by invitation.

- title:              Jazz (Levels 1–6)
  activity_category:  dance
  age_min:            5
  schedule_note:      "Mon 4:30–5:30pm confirmed. Full schedule online."
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Jazz dance. Multiple levels.

- title:              Tap (Levels 1–6)
  activity_category:  dance
  age_min:            5
  schedule_note:      "Tue/Thu schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Tap dance. Levels 1–6.

- title:              Contemporary Dance
  activity_category:  dance
  schedule_note:      "Mon 5:30–6:30pm (Int.) confirmed. Full schedule online."
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Contemporary dance. Ballet prerequisite.

- title:              Hip Hop
  activity_category:  dance
  schedule_note:      "Mon 6:30–7:30pm (Adv.) confirmed. See website."
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Hip hop. Multiple levels.

- title:              Musical Theatre
  activity_category:  dance
  schedule_note:      "Wed 3:30–4:30pm (Beg/Int) confirmed."
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Musical theatre combining acting, singing, movement.

- title:              Pointe
  activity_category:  dance
  schedule_note:      "Advanced students only."
  location_name:      Arizona Coast Performing Arts
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  description:        Classical pointe work for advanced ballet students.
```

### Events

```yaml
- title:       ACPA Annual Dance Showcase 2026
  description: Year-end student showcase featuring Ballet, Jazz, Tap, Contemporary, Pointe, Musical Theatre.
  date:        "2026-05-15 through 2026-05-17"
  time:        "TBD"
  location:    ⚠️ VERIFY venue
  cost:        CONTACT_FOR_PRICING
  provider:    Arizona Coast Performing Arts
```

---

## BUSINESS 9 — GRACE ARTS LIVE

```
provider_name:    Grace Arts Live
category:         theatre
address:          2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
website:          graceartslive.com
established:      2006
notes:            Nonprofit. Affiliated with ACPA.
```

### Programs

```yaml
- title:              Storybook Theatre Youth Workshop
  activity_category:  theatre
  age_min:            5
  age_max:            14
  schedule_note:      "Annual summer workshop. 2026: Alice in Wonderland Jr."
  location_name:      Grace Arts Live
  location_address:   2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Grace Arts Live
  description:        Annual summer youth theatre. Grades K–8. Full musical production.
```

### Events

```yaml
- title:       Alice in Wonderland Jr. — Storybook Theatre 2026
  date:        2026-06-26
  time:        "19:30"
  location:    Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live

- title:       Alice in Wonderland Jr. — Storybook Theatre 2026
  date:        2026-06-27
  time:        "19:30"
  location:    Grace Arts Live
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live

- title:       Alice in Wonderland Jr. — Storybook Theatre 2026 (Matinee)
  date:        2026-06-28
  time:        "14:00"
  location:    Grace Arts Live
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live
```

---

## BUSINESS 10 — FOOTLITE SCHOOL OF DANCE

```
provider_name:    Footlite School of Dance
category:         dance
address:          2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
phone:            (928) 854-4328
email:            footliteschool@gmail.com
website:          footliteschoolofdance.com
hours:            Mon–Thu 3–7pm during dance year
```

### Programs

```yaml
- title:              Pre-K Dance (Ages 3–4)
  activity_category:  dance
  age_min:            3
  age_max:            4
  schedule_note:      "See footliteschoolofdance.com"
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Intro to dance for preschoolers. Ballet and tap foundations.

- title:              Combo Ballet/Tap (Ages 4–5)
  activity_category:  dance
  age_min:            4
  age_max:            5
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Ballet and tap combo. Foundational positions, coordination.

- title:              Mini Groovers (Ages 5–7)
  activity_category:  dance
  age_min:            5
  age_max:            7
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Tap-based class sampling hip-hop, musical theatre, movement.

- title:              Ballet (Levels 1–4+)
  activity_category:  dance
  age_min:            6
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Classical ballet. Multiple levels.

- title:              Jazz (Levels 1–3)
  activity_category:  dance
  age_min:            6
  schedule_note:      "Level 3 advanced: ages 13+"
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Upbeat jazz technique. Three progressive levels.

- title:              Hip Hop
  activity_category:  dance
  age_min:            6
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Street dance. Age-appropriate music.

- title:              Active Seniors Dance & Fitness
  activity_category:  fitness
  age_min:            55
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  description:        Low-impact fitness combining dance, weight work, balance/coordination.
```

### Events

```yaml
- title:       Footlite Annual Recital — "Dance Party in the USA!"
  date:        2026-05-30
  time:        "TBD"
  location:    Lake Havasu High School Performing Arts Center, 2675 Palo Verde Blvd S
  cost:        25.00
  cost_description: "$25 center section."
  provider:    Footlite School of Dance

- title:       Footlite Annual Recital — "Dance Party in the USA!"
  date:        2026-06-01
  time:        "TBD"
  location:    Lake Havasu High School Performing Arts Center
  cost:        25.00
  provider:    Footlite School of Dance
```

---

## BUSINESS 11 — FLIPS FOR FUN GYMNASTICS

```
provider_name:    Flips for Fun Gymnastics
category:         gymnastics
address:          955 Kiowa Ave, Lake Havasu City, AZ 86404
phone:            (928) 566-8862
email:            Flips4fungymnastics@gmail.com
website:          fffhavasu.com
hours:            Opens 3pm, closes 8pm (Mon–Fri)
organization:     Non-profit
notes:            Classes 6 months to adult. Recreational and competitive.
```

### Programs

```yaml
- title:              Recreational Gymnastics (All Ages)
  activity_category:  gymnastics
  age_min:            0.5
  schedule_note:      "Full schedule at fffhavasu.com"
  location_name:      Flips for Fun Gymnastics
  location_address:   955 Kiowa Ave, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Flips for Fun Gymnastics
  contact_phone:      (928) 566-8862
  description:        Recreational gymnastics from 6 months to adult. Annual registration fee applies.

- title:              Competitive Gymnastics
  activity_category:  gymnastics
  schedule_note:      "Schedule at fffhavasu.com"
  location_name:      Flips for Fun Gymnastics
  location_address:   955 Kiowa Ave, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Flips for Fun Gymnastics
  contact_phone:      (928) 566-8862
  description:        Competitive program. Contact for tryout info.
```

---

## BUSINESS 12 — LAKE HAVASU CITY AQUATIC CENTER

```
provider_name:    Lake Havasu City Aquatic Center
category:         swim
address:          100 Park Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-8686
website:          lhcaz.gov/parks-recreation/aquatic-center
notes:            Indoor facility. Olympic pool, wave pool, water slide, hot tubs, splash pad.
```

### Programs

```yaml
- title:              Lap Swim
  activity_category:  swim
  schedule_note:      "See lhcaz.gov for monthly schedule."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               5.00
  cost_description:   "$5 drop-in. Monthly passes available."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  description:        6-lane 25-meter heated indoor pool.

- title:              Open Swim
  activity_category:  swim
  schedule_note:      "Saturdays year-round + more days June–July."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$6 adults | $3 seniors & children | Free under 3"
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  description:        Wave pool, water slide, kiddie lagoon, splash pad, hot tubs.

- title:              Children's Swim Lessons
  activity_category:  swim
  age_min:            0.5
  age_max:            9
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Summer. 2-week blocks June 2–July 31."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               37.00
  cost_description:   "$37 per child per 2-week session. ⚠️ Confirm 2026 pricing."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  description:        Certified instructors. Skill-level classes in 2-week blocks.

- title:              Aqua Aerobics / Water Fitness
  activity_category:  fitness
  age_min:            18
  schedule_note:      "Multiple classes. See monthly schedule."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               5.00
  cost_description:   "$5 drop-in per class."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  description:        Year-round adult water fitness. Aqua Aerobics, Ai-Chi, Arthritis Exercise, Cardio Challenge, Aqua Motion.
```

---

## BUSINESS 13 — BLESS THIS NEST LHC

```
provider_name:    Bless This Nest LHC
category:         art
address:          2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
phone:            (928) 412-3718
email:            amber@blessthisnestlhc.com
website:          blessthisnestlhc.com
owner:            Amber Kramer Lohrman
```

### Programs

```yaml
- title:              Open Studio / Drop-In Crafts
  activity_category:  art
  schedule_note:      "See blessthisnestlhc.com"
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  cost_description:   "Price varies by project."
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  description:        Pick-your-project drop-in. Wood signs, painting, resin, seasonal crafts.

- title:              Kids Art Club
  activity_category:  art
  age_max:            17
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  description:        Guided art club for kids.

- title:              Toddler Time
  activity_category:  art
  age_min:            1.5
  age_max:            5
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  description:        Art and craft sessions for toddlers.

- title:              Summer Camps — Art
  activity_category:  summer_camp
  age_max:            17
  schedule_note:      "Summer only. Dates and pricing at blessthisnestlhc.com."
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  description:        Summer art camps for youth.
```

---

## BUSINESS 14 — HAVASU LIONS FC

```
provider_name:    Havasu Lions FC
category:         sports
address:          P.O. Box 1749, Lake Havasu City, AZ 86405
email:            bkistler@havasulions.com
website:          havasulions.com
organization:     501(c)3 nonprofit
notes:            1,000+ rec players. Scholarship program.
```

### Programs

```yaml
- title:              Recreational Soccer — Spring
  activity_category:  sports
  age_min:            4
  age_max:            17
  schedule_note:      "Spring 2026 open. Saturday games. Weeknight practices by coach."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  description:        Youth rec soccer 4–17. Scholarships available.

- title:              Recreational Soccer — Fall
  activity_category:  sports
  age_min:            4
  age_max:            17
  schedule_note:      "Practices begin ~Sept 22. Saturday games Oct–Dec."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  description:        Youth rec soccer fall season. Playoffs, All-Star game, Coach Cup in Dec.

- title:              Travel / Club League (Competitive)
  activity_category:  sports
  age_min:            8
  age_max:            17
  schedule_note:      "Travel to Phoenix, Flagstaff, Las Vegas, SoCal. Tryout required."
  location_name:      Various locations
  location_address:   Lake Havasu City, AZ (home base)
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  description:        Competitive travel soccer 8–17. Higher commitment level.
```

---

## BUSINESS 15 — HAVASU STINGRAYS SWIM TEAM

```
provider_name:    Havasu Stingrays Swim Team
category:         swim
address:          P.O. Box 3802, Lake Havasu City, AZ 86405
email:            membership@havasustingrays.com ⚠️ VERIFY
website:          gomotionapp.com/team/azhsaz
organization:     USA Swimming sanctioned nonprofit. Est. 1990.
tryout:           Required. Must swim 25m independently.
```

### Programs

```yaml
- title:              Competitive Swim Team
  activity_category:  swim
  age_min:            5
  age_max:            18
  schedule_note:      "Year-round. Schedule after placement."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Stingrays Swim Team
  contact_email:      membership@havasustingrays.com
  description:        USA Swimming competitive team. Ages 5–18. Tryout required.
```

---

## BUSINESS 16 — AQUA BEGINNINGS

```
provider_name:    Aqua Beginnings
category:         swim
address:          Private heated outdoor pool (address at booking)
website:          aquabeginnings.com
coach:            Coach Rick (Swim America® certified)
notes:            Max 3 swimmers per group. Free initial assessment.
```

### Programs

```yaml
- title:              Private & Small-Group Swim Lessons
  activity_category:  swim
  schedule_days:      [TUE, WED, FRI]
  schedule_start_time: "08:00"
  schedule_end_time:   "14:00"
  schedule_note:      "Assessment hours Tue/Wed/Fri 8am–2pm."
  location_name:      Aqua Beginnings
  location_address:   Lake Havasu City, AZ (address at booking)
  cost:               CONTACT_FOR_PRICING
  provider_name:      Aqua Beginnings
  description:        One-on-one and small-group (max 3) lessons in heated outdoor pool. Modified Swim America® progression. Free assessment.
```

---

## BUSINESS 17 — LAKE HAVASU LITTLE LEAGUE

```
provider_name:    Lake Havasu Little League
category:         sports
address:          1990 McCulloch Blvd N, Ste 373, Lake Havasu City, AZ 86403
email:            info@lakehavasulittleleague.net
website:          lakehavasulittleleague.net
season:           Spring only. Registration Nov–Jan. Games Mar–May.
notes:            2026 Opening Day: Feb 28. Various fields.
```

### Programs

```yaml
- title:              Tee Ball
  activity_category:  sports
  age_min:            4
  age_max:            5
  schedule_note:      "Spring. Games Mar–May."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Hits off tee. Safety ball. 50-foot bases.

- title:              A Minor (Machine Pitch)
  activity_category:  sports
  age_min:            5
  age_max:            6
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Pitching machine. Safety ball. 50-foot bases. 7 pitches per at-bat.

- title:              AA Minor (Machine & Player Pitch)
  activity_category:  sports
  age_min:            7
  age_max:            8
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Regulation baseball. 60-foot bases. Machine then player pitch.

- title:              AAA Minor
  activity_category:  sports
  age_min:            9
  age_max:            10
  schedule_note:      "8-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Player pitch. Full regulation baseball.

- title:              Majors Division
  activity_category:  sports
  age_min:            11
  age_max:            12
  schedule_note:      "10-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Classic Little League experience.

- title:              Senior Division
  activity_category:  sports
  age_min:            13
  age_max:            16
  schedule_note:      "12-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  description:        Full diamond dimensions.
```

---

## BUSINESS 18 — HAVASU SHAO-LIN KEMPO

```
provider_name:    Havasu Shao-Lin Kempo
category:         martial_arts
address:          2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
phone:            (928) 680-4121
website:          shao-linkempo.com
hours:            Mon–Thu 10am–8pm | Sat 8am–2pm | Fri & Sun closed
notes:            ⚠️ Class schedule from 2018 data — verify with (928) 680-4121.
```

### Programs

```yaml
- title:              Peewee's Group Class (Ages 3–9)
  activity_category:  martial_arts
  age_min:            3
  age_max:            9
  schedule_days:      [TUE, WED, FRI, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Wed/Fri 5:30–6:15pm | Sat 12–12:45pm (2018)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  description:        Traditional Kempo for young children.

- title:              Kid's Group Class (Ages 10–17)
  activity_category:  martial_arts
  age_min:            10
  age_max:            17
  schedule_days:      [TUE, WED, FRI, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Wed/Fri 4–5pm | Sat 10:30–11:30am (2018)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  description:        Kempo for kids and teens.

- title:              Adult Group Class
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [TUE, WED, THU, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Thu 6:30–7:30pm | Wed 11am–12pm | Sat 9–10am (2018)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  description:        Adult Kempo/Karate, Kung Fu, Tai Chi.
```

### Events

```yaml
- title:       Shao-Lin Kempo Tournament
  date:        2026-05-18
  time:        "TBD"
  location:    ⚠️ VERIFY
  cost:        CONTACT_FOR_PRICING
  provider:    Havasu Shao-Lin Kempo

- title:       GrandMaster Pearl Clinic
  date:        "August 2026 — exact date TBD"
  time:        TBD
  location:    ⚠️ VERIFY
  cost:        CONTACT_FOR_PRICING
  provider:    Havasu Shao-Lin Kempo
```

---

## BUSINESS 19 — BALLET HAVASU

```
provider_name:    Ballet Havasu
category:         dance
address:          2735 Maricopa Ave (inside The Dance Center), Lake Havasu City, AZ 86406
phone:            (928) 412-8208
website:          ballethavasu.org
notes:            First class FREE. Open enrollment. ESA accepted.
```

### Programs

```yaml
- title:              Tiny Toes & Twirls (Ages 1.5–3)
  activity_category:  dance
  age_min:            1.5
  age_max:            3
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  description:        Playful intro for toddlers. Movement, music, coordination. Parents encouraged.

- title:              Ballet Beginnings (Ages 3–5)
  activity_category:  dance
  age_min:            3
  age_max:            5
  schedule_note:      "First class free."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  description:        First ballet class. Foundational steps. No parents in class.

- title:              Elementary Ballet (Levels A & B)
  activity_category:  dance
  age_min:            5
  schedule_note:      "Placement by readiness."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  description:        Formal ballet training. Posture, alignment, basic vocabulary.

- title:              Intermediate Ballet (Levels A & B)
  activity_category:  dance
  schedule_note:      "Placement by technique."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  description:        Refined technique and musicality.

- title:              Advanced Ballet (Levels A & B)
  activity_category:  dance
  schedule_note:      "Placement by demonstrated technique."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  description:        Highest level. Advanced combinations, artistry, classical performance.
```

---

## BUSINESS 20 — LHC PARKS & RECREATION

```
provider_name:    Lake Havasu City Parks & Recreation
category:         sports
address:          100 Park Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-8686 (main) | (928) 854-0892 (youth athletics)
website:          lhcaz.gov/parks-recreation
registration:     register.lhcaz.gov
contact:          Brook DuBay — dubayb@lhcaz.gov
```

### Programs

```yaml
- title:              NFL Flag Football League
  activity_category:  sports
  age_min:            6
  age_max:            15
  schedule_note:      "Jan 12–Mar 30, 2026. Co-ed, non-contact."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 854-0892
  contact_email:      dubayb@lhcaz.gov
  description:        NFL-sanctioned co-ed flag football 6–15. Non-contact.

- title:              Jr. Suns Basketball League
  activity_category:  sports
  schedule_note:      "Summer 2026. Registration coming soon. Phoenix Suns partnership."
  location_name:      TBD
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 854-0892
  contact_email:      dubayb@lhcaz.gov
  description:        Youth basketball with Phoenix Suns Jr. Suns/Jr. Mercury. Players get official jersey.

- title:              Tennis Lessons (Youth)
  activity_category:  sports
  age_min:            9
  age_max:            14
  schedule_days:      [MON, WED]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:30"
  schedule_note:      "3 fall sessions. ⚠️ Confirm 2026 dates."
  location_name:      Lake Havasu High School Tennis Courts
  location_address:   2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403
  cost:               80.00
  cost_description:   "$80 per 8-class session. Private: $35/hr. Semi-private: $40/hr/group."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 855-4744
  description:        Tennis fundamentals grades 4–8. Bring own racket and tennis shoes.

- title:              Sunshine Kids Summer Camp
  activity_category:  summer_camp
  age_min:            6
  age_max:            12
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "17:30"
  schedule_note:      "June–mid July. ⚠️ Confirm 2026 dates. Grades K–4."
  location_name:      Havasupai Elementary / Oro Grande Classical Academy
  location_address:   Lake Havasu City, AZ
  cost:               305.00
  cost_description:   "$305 first child | $246 additional. Lunch provided. Scholarships available."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  description:        Full-day summer camp K–4. Games, crafts, field trips. USDA lunch free.

- title:              Adventure Academy Summer Camp
  activity_category:  summer_camp
  age_min:            11
  age_max:            13
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "17:30"
  schedule_note:      "June–mid July. ⚠️ Confirm dates. Grades 5–7."
  location_name:      TBD
  location_address:   Lake Havasu City, AZ
  cost:               305.00
  cost_description:   "$305 first child | $246 additional."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  description:        Full-day summer camp 5–7. Swimming, crafts, movies, bowling, cooking, fitness, photography.

- title:              Adventure Camp (Archery, Kayaking)
  activity_category:  summer_camp
  age_min:            9
  age_max:            14
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "09:00"
  schedule_end_time:   "13:00"
  schedule_note:      "Three 2-week sessions in June. ⚠️ Confirm dates."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  description:        Half-day adventure camp. Archery, kayaking, snorkeling, fishing.

- title:              Fairway Friends (Youth Golf Intro)
  activity_category:  golf
  age_min:            3
  age_max:            8
  schedule_days:      [WED]
  schedule_note:      "June Wednesdays. Ages 3–5 at 5:15pm | Ages 6–8 at 6:15pm."
  location_name:      Lake Havasu City Aquatic Center / Iron Wolf Golf
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               24.00
  cost_description:   "$24 per child per session."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  description:        Beginner golf with plastic clubs. One session at Iron Wolf GCC.
```

---

## BUSINESS 21 — THE TAP ROOM JIU JITSU

```
provider_name:    The Tap Room Jiu Jitsu
category:         martial_arts
address:          2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
phone:            (928) 889-5487
email:            thetaproomjj@gmail.com
website:          thetaproomjiujitsu.com
established:      2025
pricing:          $109/month + $39.99 sign-up (all memberships)
notes:            3-day free trial for locals.
```

### Programs

```yaml
- title:              Littles Gi Jiu-Jitsu (Ages 3–6)
  activity_category:  martial_arts
  age_min:            3
  age_max:            6
  schedule_days:      [MON, WED]
  schedule_start_time: "16:30"
  schedule_end_time:   "17:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up. 3-day free trial."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  description:        Gi Jiu-Jitsu for youngest students 3–6.

- title:              Littles NoGi Jiu-Jitsu (Ages 3–6)
  activity_category:  martial_arts
  age_min:            3
  age_max:            6
  schedule_days:      [TUE, THU]
  schedule_start_time: "16:30"
  schedule_end_time:   "17:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        No-gi Jiu-Jitsu for youngest students 3–6.

- title:              Youth Gi Jiu-Jitsu (All Levels)
  activity_category:  martial_arts
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED]
  schedule_start_time: "17:15"
  schedule_end_time:   "18:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Gi Jiu-Jitsu for youth all levels.

- title:              Youth NoGi Jiu-Jitsu (All Levels)
  activity_category:  martial_arts
  age_min:            7
  age_max:            17
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:15"
  schedule_end_time:   "18:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        No-gi Jiu-Jitsu for youth all levels.

- title:              Youth Wrestling (Ages 6+)
  activity_category:  martial_arts
  age_min:            6
  age_max:            17
  schedule_days:      [SAT]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:00"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Youth wrestling for ages 6+.

- title:              Adult Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [MON, WED]
  schedule_start_time: "18:15"
  schedule_end_time:   "19:45"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Adult gi Brazilian Jiu-Jitsu. All levels.

- title:              Adult NoGi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [TUE, THU]
  schedule_start_time: "18:15"
  schedule_end_time:   "19:45"
  schedule_note:      "Also Fri 5:15–6:15pm (Leg Locks)."
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Adult no-gi Jiu-Jitsu. All levels.

- title:              MMA
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [WED, FRI]
  schedule_note:      "Wed 7:30–8:30pm (sparring) | Fri 6:15–7:15pm"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        MMA training and sparring.

- title:              Women's Only NoGi
  activity_category:  martial_arts
  age_min:            18
  schedule_days:      [MON]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:00"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Women-only no-gi Jiu-Jitsu. All levels.

- title:              Open Mat (All Welcome)
  activity_category:  martial_arts
  schedule_days:      [SUN]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:30"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "Included in membership."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  description:        Open mat — all levels and styles welcome.
```

---

## BUSINESS 22 — AREVALO ACADEMY

```
provider_name:    Arevalo Academy
category:         martial_arts
address:          3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
phone:            (928) 855-0505
website:          arevaloacademy.com
notes:            ⚠️ Schedule data from 2018 — VERIFY before going live.
```

### Programs

```yaml
- title:              Little Ninjas (Ages ~3–5)
  activity_category:  martial_arts
  age_min:            3
  age_max:            5
  schedule_note:      "⚠️ VERIFY"
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  description:        Intro martial arts for youngest students. No contact between students.

- title:              Kids MMA (Ages 6–12)
  activity_category:  martial_arts
  age_min:            6
  age_max:            12
  schedule_note:      "⚠️ VERIFY current schedule."
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  description:        Children's MMA. Multiple levels.

- title:              Adult MMA
  activity_category:  martial_arts
  age_min:            18
  schedule_note:      "⚠️ VERIFY. Morning and evening sessions."
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  description:        "Adult MMA: Muay Thai, Boxing, Kickboxing, BJJ, Wrestling."
```

---

## BUSINESS 23 — LAKE HAVASU BLACK BELT ACADEMY

```
provider_name:    Lake Havasu Black Belt Academy
category:         martial_arts
address:          597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-0515
email:            info@lhcbba.com
website:          lakehavasublackbeltacademy.com
hours:            Mon–Fri ~4:00–7:30pm | Sat–Sun Closed
notes:            ATA affiliated. Ages 3–103. Free first class.
```

### Programs

```yaml
- title:              ATA Tigers / Tiny Tigers (Ages 3–7)
  activity_category:  martial_arts
  age_min:            3
  age_max:            7
  schedule_note:      "Mon–Fri afternoons. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  description:        ATA Taekwondo for young children. Free first class.

- title:              Karate for Kids (Ages ~7–12)
  activity_category:  martial_arts
  age_min:            7
  age_max:            12
  schedule_note:      "Mon–Fri afternoons. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  description:        ATA Songham Taekwondo for school-age kids.

- title:              Teen & Adult Taekwondo
  activity_category:  martial_arts
  age_min:            13
  schedule_note:      "Mon–Fri evenings. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  description:        "ATA Taekwondo teens/adults. All levels through black belt. Advanced: Black Belt Club, Masters, Leadership, Legacy. Krav Maga and Tai Chi special sessions."
```

---

## BUSINESS 24 — ELITE CHEER ATHLETICS — HAVASU

```
provider_name:    Elite Cheer Athletics — Havasu
category:         cheer
address:          ⚠️ NOT CONFIRMED — DO NOT SEED PUBLIC
draft:            true
instagram:        @elite_cheer_athletic_lhc
ages:             3–18
notes:            New business 2024–2025. No address/phone/pricing confirmed. Seed as draft=true.
```

### Programs

```yaml
- title:              Competitive All Star Cheer
  activity_category:  cheer
  age_min:            3
  age_max:            18
  draft:              true
  schedule_note:      "⚠️ ALL DETAILS UNVERIFIED."
  location_name:      ⚠️ UNKNOWN
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Elite Cheer Athletics — Havasu
  description:        Competitive All Star cheerleading ages 3–18.
```

---

## BUSINESS 25 — HAVASU STINGRAYS MASTERS SWIM TEAM

```
provider_name:    Havasu Stingrays Masters Team
category:         swim
address:          Lake Havasu City Aquatic Center, 100 Park Ave, Lake Havasu City, AZ 86403
website:          usms.org/clubs/lake-havasu-masters-team
organization:     U.S. Masters Swimming
```

### Programs

```yaml
- title:              Masters Swim Practice
  activity_category:  swim
  age_min:            18
  schedule_days:      [MON, WED]
  schedule_start_time: "06:00"
  schedule_end_time:   "07:00"
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Stingrays Masters Team
  description:        Adult masters swim under certified coaching. U.S. Masters Swimming sanctioned.
```

---

# 10. ADMIN FOLLOW-UP

## 10.1 Do Not Publish (draft=true)
- Elite Cheer Athletics Havasu — no address confirmed

## 10.2 Needs Verification (seeded with flag)
- Arevalo Academy — schedule from 2018, call (928) 855-0505
- Havasu Shao-Lin Kempo — schedule from 2018, call (928) 680-4121
- Lake Havasu Black Belt Academy — schedule is a posted image, verify at website
- BMX email — partially captured, verify full address
- Aquatic Center swim lesson cost — $37 is a 2020 rate, confirm 2026
- LHC Tennis — 2026 session dates not yet published
- Stingrays membership email — verify domain
- ACPA Showcase venue — verify location

## 10.3 Pricing Gaps (show_pricing_cta=true)
Bridge City Combat | Flips for Fun | Shao-Lin Kempo | Lake Havasu Black Belt Academy | Arevalo Academy | Universal Sonics | Footlite | ACPA | Ballet Havasu | Stingrays | Little League | Havasu Lions Soccer | LHC Flag Football | Bless This Nest | Aqua Beginnings | Grace Arts Live

---

# END OF MASTER FILE

*Pair this file with `template_library.py` from your ChatGPT export. Together they constitute the complete Havasu Chat implementation specification.*

**Total: 25 businesses | ~115 programs | 16 events**
**Compiled April 2026.**
