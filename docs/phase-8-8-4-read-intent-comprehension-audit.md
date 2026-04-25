# READ-ONLY INTENT COMPREHENSION AUDIT — Phase 8.8.4-read

Date: 2026-04-24
Scope: Read-only code audit of intent comprehension chain; no code/prompt changes.

## Section 1 — Component-by-component capability map

### 1.1 API entry: `/api/chat` route

- **Inputs:** `query`, optional `session_id` in `ConciergeChatRequest` (`app/schemas/chat.py` L24-L29), HTTP POST `/api/chat` (`app/api/routes/chat.py` L43-L53).
- **Outputs:** `ConciergeChatResponse` with `response`, `mode`, `sub_intent`, `entity`, `tier_used`, timing/tokens (`app/api/routes/chat.py` L61-L70; `app/schemas/chat.py` L30-L40).
- **Recognized shapes:** Any non-empty query; delegates comprehension to `unified_router.route`.
- **Unrecognized shapes:** N/A at this layer (validation-only).
- **Failure mode:** validation error if `query` missing/empty.
- **Confidence/threshold behavior:** none.
- **LLM-backed vs deterministic:** deterministic wrapper.

### 1.2 Intent classifier (`classify`)

- **Inputs:** raw text query (`app/chat/intent_classifier.py` L213-L217).
- **Outputs:** `IntentResult(mode, sub_intent, confidence, entity, raw_query, normalized_query)` (`app/chat/intent_classifier.py` L203-L210, L243-L250).
- **Recognized shapes (deterministic regex/heuristics):**
  - **Modes:** `ask`, `contribute`, `correct`, `chat` (`app/chat/intent_classifier.py` L117-L151).
  - **Ask sub-intents:** Tier1 regex intents from `INTENT_PATTERNS` + `NEXT_OCCURRENCE` + `LIST_BY_CATEGORY` + `OPEN_NOW` + fallback `OPEN_ENDED` (`app/chat/intent_classifier.py` L153-L170; `app/chat/tier1_templates.py` L43-L61).
  - **Contribute sub-intents:** `NEW_EVENT`, `NEW_PROGRAM`, `NEW_BUSINESS` (`app/chat/intent_classifier.py` L173-L191).
  - **Correct sub-intent:** `CORRECTION` (`app/chat/intent_classifier.py` L226-L227).
  - **Chat sub-intents:** `GREETING`, `SMALL_TALK`, `OUT_OF_SCOPE` (`app/chat/intent_classifier.py` L138-L149, L229-L230).
- **Unrecognized/degraded shapes:**
  - Calendar terms not explicitly modeled in classifier itself (e.g., “summer”, “next month”, “october”) usually fall to `OPEN_ENDED`.
  - False positive entity matches from canonical extras can attach unrelated entities.
- **Failure mode on unrecognized input:** defaults to `ask + OPEN_ENDED` with moderate confidence (`app/chat/intent_classifier.py` L170, L150).
- **Confidence behavior:**
  - Base mode confidence + sub-intent confidence merged (`app/chat/intent_classifier.py` L194-L200).
  - Entity score can raise floor (`>=0.9 -> >=0.95`, `>=0.75 -> >=0.82`) (`app/chat/intent_classifier.py` L196-L199).
  - `OPEN_ENDED` has floor `0.42` (`app/chat/intent_classifier.py` L240-L241).
- **LLM-backed vs deterministic:** deterministic (no LLM call).

### 1.3 Entity matching / enrichment

- **Inputs:** normalized query + canonical names and/or DB-backed rows (`app/chat/entity_matcher.py` L186-L236, L216-L236).
- **Outputs:** best fuzzy match `provider_name` and score, thresholded >75 (`app/chat/entity_matcher.py` L211-L213, L234-L235).
- **Recognized shapes:** aliases in `CANONICAL_EXTRAS` and provider/program names (`app/chat/entity_matcher.py` L17-L84, L107-L118).
- **Unrecognized/degraded shapes:** place/venue nouns not in canonical alias set; ambiguous city-level mentions can map to nearest alias by fuzz score.
- **Failure mode:** returns `None` if best score <=75 (`app/chat/entity_matcher.py` L211-L213, L234-L235).
- **Confidence behavior:** strict score threshold >75.
- **LLM-backed vs deterministic:** deterministic fuzzy match (RapidFuzz).

### 1.4 Router (`unified_router.route`)

- **Inputs:** query/session/db (`app/chat/unified_router.py` L236-L240).
- **Outputs:** `ChatResponse` and persisted `chat_logs` row (`app/chat/unified_router.py` L245-L287, L417-L426).
- **Recognized shapes:** all modes from classifier, plus ask-path tier orchestration.
- **Unrecognized/degraded shapes:** malformed/exceptions in normalize/classify/mode handler return graceful fallback (`app/chat/unified_router.py` L290-L294, L310-L312, L396-L407).
- **Failure mode:** returns `_GRACEFUL` placeholder answer on internal exceptions.
- **Confidence/threshold behavior:** none directly; uses classifier outputs and Tier2 threshold indirectly.
- **LLM-backed vs deterministic:** deterministic orchestration; calls LLM-backed Tier2 parser/formatter and Tier3 handler.

### 1.5 Tier 1 direct handler (`try_tier1`)

- **Inputs:** `IntentResult` (must include `entity`) + DB (`app/chat/tier1_handler.py` L164-L174).
- **Outputs:** direct template text or `None` fall-through (`app/chat/tier1_handler.py` L164-L171, L311).
- **Recognized shapes:** entity-specific lookups: `TIME_LOOKUP`, `HOURS_LOOKUP`, `PHONE_LOOKUP`, `LOCATION_LOOKUP`, `WEBSITE_LOOKUP`, `COST_LOOKUP`, `AGE_LOOKUP`, `DATE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW` (`app/chat/tier1_handler.py` L21-L34).
- **Unrecognized/degraded shapes:** no entity, missing provider field, missing program/event data -> returns `None`.
- **Failure mode:** silent fall-through (`None`) to downstream tiers.
- **Confidence behavior:** none in this module.
- **LLM-backed vs deterministic:** deterministic DB + templates.

### 1.6 Tier 1 templates (`render`)

- **Inputs:** intent + entity/data slots (`app/chat/tier1_templates.py` L249-L254).
- **Outputs:** formatted string or `None` if required slots missing (`app/chat/tier1_templates.py` L255-L263, L281-L283).
- **Recognized shapes:** fixed regex and slot-driven responses for Tier1 intents (`app/chat/tier1_templates.py` L43-L61, L64-L139).
- **Unrecognized/degraded shapes:** missing slots, unsupported intent keys.
- **Failure mode:** `None` (forces fall-through).
- **Confidence behavior:** none.
- **LLM-backed vs deterministic:** deterministic.

### 1.7 Tier 2 orchestrator (`try_tier2_with_usage`)

- **Inputs:** query string (`app/chat/tier2_handler.py` L14-L16).
- **Outputs:** `(text, total_tokens, in_tokens, out_tokens)` or all `None` fallback (`app/chat/tier2_handler.py` L17-L21, L53).
- **Recognized shapes:** parser-valid, confidence >=0.7, `fallback_to_tier3=False`, DB rows non-empty, formatter non-empty (`app/chat/tier2_handler.py` L27-L46).
- **Unrecognized/degraded shapes:** parser errors, parser low confidence, parser fallback flag, empty rows, formatter failure.
- **Failure mode:** returns `None` to caller for Tier3 fallback (or gap path in current router when gap-eligible + no Tier2 rows).
- **Confidence behavior:** hard threshold `TIER2_CONFIDENCE_THRESHOLD = 0.7` (`app/chat/tier2_handler.py` L10-L11, L34-L36).
- **LLM-backed vs deterministic:** hybrid (LLM parser + deterministic DB + LLM formatter).

### 1.8 Tier 2 parser (`tier2_parser.parse`)

- **Inputs:** raw user query (`app/chat/tier2_parser.py` L75-L81, L105).
- **Outputs:** validated `Tier2Filters` or `None` (`app/chat/tier2_parser.py` L75-L80, L129-L135).
- **Recognized shapes:** `entity_name`, `category`, `age_min/max`, `location`, `day_of_week`, `time_window` in `{today,tomorrow,this_week,this_weekend,this_month,upcoming}`, `open_now`, `parser_confidence`, `fallback_to_tier3` (`prompts/tier2_parser.txt` L3-L21).
- **Unrecognized/degraded shapes:** non-JSON output, schema-invalid JSON, low-confidence ambiguous outputs.
- **Failure mode:** returns `None` (parser error path).
- **Confidence behavior:** parser emits confidence; Tier2 handler enforces >=0.7.
- **LLM-backed vs deterministic:** LLM-backed extraction.
- **Prompt (verbatim):**

```text
You extract structured filters from user queries for Hava, a Lake Havasu City concierge. Return JSON matching the schema exactly. No prose, no markdown, no code fences, and no explanation — output a single JSON object only.

Schema (all keys optional except parser_confidence, which is required on every response):

- entity_name (string or null): A specific named business, program, venue, or organization when the query clearly names it (e.g. a proper name). Prefer this over category when the user is asking about that entity by name.

- category (string or null): A topic or activity type the catalog might match on (e.g. bmx, gymnastics, dance, family). Use for thematic queries, not for a single clearly named entity.

- age_min / age_max (integer or null): Inferred ages from phrases like "6-year-old" (min and max both 6) or "ages 5–12" (min 5, max 12).

- location (string or null): A named place or area in the city (parks, neighborhoods, "downtown", etc.).

- day_of_week (array of strings or null): Lowercase English weekday names from "monday" through "sunday". For "weekend", use ["saturday", "sunday"].

- time_window (string or null): Exactly one of: "today", "tomorrow", "this_week", "this_weekend", "this_month", "upcoming". Use "this_weekend" for the next Saturday–Sunday pair. Use "upcoming" for general future events when no fixed end window fits.

- open_now (boolean or null): True when the user clearly wants currently open options.

- parser_confidence (number, required): 0.0 through 1.0. Use about 0.7 or higher when filters are meaningful and fairly clear; below 0.7 when the query is extractable but ambiguous.

- fallback_to_tier3 (boolean): Default false. Set true when the query is not Tier 2-shaped (too vague, open-ended, opinion-heavy, or small talk). When true, other fields may be null and confidence may be low.

Few-shot examples:

Query: what should I do saturday
Output: {"day_of_week": ["saturday"], "time_window": "this_weekend", "parser_confidence": 0.85, "fallback_to_tier3": false}

Query: tell me about bridge city
Output: {"entity_name": "Bridge City", "parser_confidence": 0.9, "fallback_to_tier3": false}

Query: what is a good place for my 6-year-old to burn off some energy
Output: {"age_min": 6, "age_max": 6, "category": "active", "parser_confidence": 0.8, "fallback_to_tier3": false}

Query: stuff happening at sara park
Output: {"location": "Sara Park", "parser_confidence": 0.9, "fallback_to_tier3": false}

Query: family activities this month
Output: {"category": "family", "time_window": "this_month", "parser_confidence": 0.75, "fallback_to_tier3": false}

Query: events tomorrow
Output: {"time_window": "tomorrow", "parser_confidence": 0.85, "fallback_to_tier3": false}

Query: your favorite event coming up
Output: {"time_window": "upcoming", "parser_confidence": 0.8, "fallback_to_tier3": false}

Query: Where can I grab dinner right now?
Output: {"category": "restaurant", "open_now": true, "parser_confidence": 0.82, "fallback_to_tier3": false}

Query: Anywhere open for a workout this late?
Output: {"category": "gym", "open_now": true, "parser_confidence": 0.8, "fallback_to_tier3": false}

Query: tell me something cool about this town
Output: {"parser_confidence": 0.15, "fallback_to_tier3": true}
```

### 1.9 Tier 2 DB query (`tier2_db_query.query`)

- **Inputs:** `Tier2Filters` (`app/chat/tier2_db_query.py` L453-L455).
- **Outputs:** up to 8 mixed row dicts for formatter (`app/chat/tier2_db_query.py` L34, L453-L476).
- **Recognized shapes:**
  - Event filtering by live status/date window/location/category/day-of-week/entity text (`app/chat/tier2_db_query.py` L293-L327).
  - Program/provider filters for category/location/entity/age/day constraints (`app/chat/tier2_db_query.py` L330-L417).
  - Browse fallback sample when no dimensions (`app/chat/tier2_db_query.py` L456-L458, L420-L450).
- **Unrecognized/degraded shapes:**
  - No explicit support for month names like “october” or seasonal words like “summer” (depends on parser emitting `time_window`; DB layer only understands normalized window token inputs).
  - Time-only query shape suppresses programs/providers (`_only_time_window`) (`app/chat/tier2_db_query.py` L56-L69, L331-L333, L376-L377).
- **Failure mode:** empty list (upstream falls through).
- **Confidence behavior:** none; upstream controls threshold.
- **LLM-backed vs deterministic:** deterministic SQL/Python filtering.

### 1.10 Tier 2 formatter (`tier2_formatter.format`)

- **Inputs:** raw query + list of row dicts (`app/chat/tier2_formatter.py` L49-L50, L75-L80).
- **Outputs:** natural-language text from Anthropic or `None` (`app/chat/tier2_formatter.py` L49-L55, L96-L107).
- **Recognized shapes:** any row JSON payload; prompt-guided formatting + grounding rules.
- **Unrecognized/degraded shapes:** if rows sparse/missing detail, should acknowledge missing info; still model-dependent.
- **Failure mode:** SDK error/empty text -> `None` causing Tier2 fallback.
- **Confidence behavior:** none in formatter.
- **LLM-backed vs deterministic:** LLM-backed.
- **Prompt (verbatim):**

```text
Role:
You are Hava — the AI local of Lake Havasu. You answer from firsthand local voice at the level of the town: how places here divide, what’s worth knowing, and how the catalog hangs together. You are not a generic assistant and you do not speak as a community database interface.

In this Tier, you format the reply using ONLY the JSON catalog rows provided. Do not invent facts. If the rows don't contain enough to answer what they asked, say so briefly and stop.

**§6.7 (Tier 2 — formatter, not full synthesis):** You are rephrasing data from rows, not inventing visits. At landscape level, one short line of how this kind of place fits Havasu is fine. At the per-row level, stay factual and descriptive from the JSON only — do not add manufactured "I'd sit at the bar" color unless a row actually supplies that kind of operator-grounded detail. For a single business or place, you may start with one framing line, then the specifics from the row(s). Do not use any `source` field or provenance tag to pick voice; work from what the text actually says, not a column label. Never mention a `source` field for how you write.

**Grounding guardrails (additive to §6.7):**
- Keep the §6.7 framing beat: one short landscape line is allowed.
- After that framing line, every concrete detail must be directly row-backed.
- If a row does not contain a detail, do not infer it and do not state it.
- Never invent venue, address, event time window, duration, organizer, or pricing details.
- If the user asks for a missing detail (for example "where" with no location field), say briefly that the provided rows do not include it.
- When in doubt, be sparse and factual rather than interpolating.

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

### 1.11 Tier 3 handler (`answer_with_tier3`)

- **Inputs:** query + `IntentResult` + DB + optional onboarding hints (`app/chat/tier3_handler.py` L105-L112).
- **Outputs:** model answer + token counts (`app/chat/tier3_handler.py` L113-L188).
- **Recognized shapes:** open-ended synthesis with context string from `context_builder`.
- **Unrecognized/degraded shapes:** context gaps can produce conservative fallback answers; still model-dependent.
- **Failure mode:** fallback message when key/import/API errors or empty model output (`app/chat/tier3_handler.py` L115-L123, L175-L181).
- **Confidence behavior:** none in module.
- **LLM-backed vs deterministic:** LLM-backed synthesis.
- **Prompt:** `prompts/system_prompt.txt` loaded verbatim (`app/chat/tier3_handler.py` L32-L37). Long prompt includes anti-hallucination, option-3 recommendation rules, context discipline, `Now:` semantics, and plain-text constraints (`prompts/system_prompt.txt` L1-L85).

### 1.12 Tier 3 context builder (`build_context_for_tier3`)

- **Inputs:** query, `IntentResult`, DB (`app/chat/context_builder.py` L88-L91).
- **Outputs:** plain-text provider/program/event context capped by word budget (`app/chat/context_builder.py` L139-L141).
- **Recognized shapes:** provider-centric context for up to 10 providers, each with up to 8 linked future events.
- **Unrecognized/degraded shapes:**
  - **No providers:** early return “no catalog rows” string, no event retrieval (`app/chat/context_builder.py` L92-L96).
  - Only linked events (`Event.provider_id == provider_id`) are included (`app/chat/context_builder.py` L75-L85).
- **Failure mode:** returns conservative fallback context string.
- **Confidence behavior:** none.
- **LLM-backed vs deterministic:** deterministic DB + string assembly.

---

## Section 2 — Routing decision tree

1. **HTTP entry** `POST /api/chat` calls `unified.route(query, session_id, db)` (`app/api/routes/chat.py` L52-L53).
2. **Normalize query**; failure => graceful placeholder (`app/chat/unified_router.py` L289-L294).
3. **Classify** into `mode` + `sub_intent` + confidence + seed-entity (`app/chat/unified_router.py` L308-L312; classifier logic in `app/chat/intent_classifier.py`).
4. **Entity enrichment** via DB matcher if entity missing (`app/chat/unified_router.py` L321-L333).
5. Branch by `mode` (`app/chat/unified_router.py` L355-L395):
   - `ask` -> ask pipeline
   - `contribute` -> placeholder contribute copy (`_handle_contribute`)
   - `correct` -> correction prompt (`_handle_correct`)
   - `chat` -> greeting/small-talk/out-of-scope (`_handle_chat`)
   - else -> ask pipeline.
6. **Ask pipeline** (`app/chat/unified_router.py` L355-L382 + `_handle_ask` L118-L143):
   - Compute `gap_text = _catalog_gap_response(intent_result)` (`L356`).
   - If `gap_text` exists (conditions below), call `_handle_ask(... allow_tier3_fallback=False)` first (`L358-L365`):
     - Tier1 attempt (`_handle_ask` L127-L129)
     - explicit-rec gate -> Tier3 (`L130-L134`)
     - Tier2 attempt (`L135-L137`)
     - if Tier2 returns no text and fallback disabled -> return `text=None` (`L138-L139`)
   - If `text is None` after that, return `gap_template` (`L366-L374`).
   - If no `gap_text`, call `_handle_ask(... allow_tier3_fallback=True)`:
     - Tier1 success -> tier `1`
     - else explicit-rec success -> tier `3`
     - else Tier2 success -> tier `2`
     - else Tier3 fallback -> tier `3`.
7. **Gap-template conditions** (`_catalog_gap_response`):
   - `sub_intent in {DATE_LOOKUP, LOCATION_LOOKUP, HOURS_LOOKUP}`
   - AND entity missing/blank (`app/chat/unified_router.py` L71-L82).
8. **Tier3 entry conditions (complete):**
   - In `_handle_ask` when `_is_explicit_rec(query)` true (`app/chat/unified_router.py` L130-L134).
   - In `_handle_ask` when Tier2 returns `None` and `allow_tier3_fallback=True` (`L138-L143`).
9. **Log + return** with `tier_used` persisted to `chat_logs` (`app/chat/unified_router.py` L245-L287, L417-L426).

### Sub-intent/mode handled set

- **Modes:** `ask`, `contribute`, `correct`, `chat` (`app/chat/intent_classifier.py` L203-L206).
- **Ask sub-intents:** `NEXT_OCCURRENCE`, all Tier1 regex intents (`WEBSITE_LOOKUP`, `PHONE_LOOKUP`, `AGE_LOOKUP`, `COST_LOOKUP`, `TIME_LOOKUP`, `HOURS_LOOKUP`, `LOCATION_LOOKUP`, `DATE_LOOKUP`), plus `LIST_BY_CATEGORY`, `OPEN_NOW`, `OPEN_ENDED` (`app/chat/intent_classifier.py` L153-L170; `app/chat/tier1_templates.py` L43-L61).
- **Contribute sub-intents:** `NEW_EVENT`, `NEW_PROGRAM`, `NEW_BUSINESS` (`app/chat/intent_classifier.py` L173-L191).
- **Correct:** `CORRECTION` (`app/chat/intent_classifier.py` L226-L227).
- **Chat:** `GREETING`, `SMALL_TALK`, `OUT_OF_SCOPE` (`app/chat/intent_classifier.py` L138-L149, L229-L230).

---

## Section 3 — Query trace matrix

Classifier outputs below came from read-only local `classify()` execution against current code.

| # | Query | Classifier output | Routing path | Tier2 parser output (if attempted) | Final tier | Predicted correctness |
|---|---|---|---|---|---|---|
| 1 | what's happening this weekend | ask / OPEN_ENDED / entity None / conf 0.7 | Tier1 none -> explicit-rec no -> Tier2 -> maybe Tier3 fallback | Likely `time_window=this_weekend`, `parser_conf~0.8`, `fallback_to_tier3=false` | likely 2 | honest-but-incomplete (capped earliest rows) |
| 2 | what's happening this summer | ask / OPEN_ENDED / None / 0.7 | Tier2 path | Uncertain; parser schema has no `summer` token, may emit `upcoming` or low-confidence/fallback | likely 2 else 3 | honest-but-wrong risk |
| 3 | what events are happening on july 4 | ask / OPEN_ENDED / None / 0.7 | Tier2 path | Uncertain; parser has no explicit month/day field | likely 2 | honest-but-incomplete / brick risk |
| 4 | when is the 4th of july show in havasu | ask / DATE_LOOKUP / None / 0.8 | gap-eligible ask flow: Tier1 none -> explicit-rec no -> Tier2 attempted (fallback disabled) -> gap if Tier2 no rows | likely weak structured filter; uncertain | 2 or gap_template | brick-wall risk if Tier2 no rows |
| 5 | anything to do tomorrow night | ask / OPEN_ENDED / None / 0.7 | Tier2 path | likely `time_window=tomorrow`, no explicit night filter | likely 2 | honest-but-incomplete |
| 6 | events in october | ask / OPEN_ENDED / None / 0.7 | Tier2 path | uncertain; schema has no month-name field | likely 2 | honest-but-wrong risk |
| 7 | what's coming up next month | ask / OPEN_ENDED / None / 0.7 | Tier2 path | uncertain; parser could map to `upcoming` (no `next_month` enum) | likely 2 | honest-but-wrong risk |
| 8 | what time does sara park bmx open | ask / TIME_LOOKUP / entity BMX / 0.95 | Tier1 direct with provider | Tier2 not attempted if Tier1 succeeds | 1 | correct if provider hours present |
| 9 | where is the london bridge | ask / LOCATION_LOOKUP / None / 0.8 | gap-eligible path; Tier1 none; Tier2 attempted; gap if no rows | uncertain | likely gap_template | brick-wall likely |
| 10 | is rotary park open on sundays | ask / OPEN_ENDED / None / 0.7 | Tier2 path | could infer location/day; uncertain | likely 2 | honest-but-incomplete |
| 11 | what should I do friday night | ask / OPEN_ENDED / None / 0.7 | explicit-rec match (`what should i do`) -> Tier3 | Tier2 skipped | 3 | generally correct if Tier3 context sufficient |
| 12 | best place for breakfast in havasu | chat / OUT_OF_SCOPE / None / 0.85 | chat handler out-of-scope reply | none | chat | intentional out-of-scope |
| 13 | where should I take my kids on a hot day | ask / LOCATION_LOOKUP / None / 0.8 | gap-eligible path; Tier2 attempted first, then gap if no rows | uncertain | 2 or gap_template | mixed/high gap risk |
| 14 | is the london bridge worth seeing | ask / OPEN_ENDED / None / 0.7 | no explicit-rec (`worth it` only), so Tier2 path | uncertain | likely 2 | honest-but-wrong risk |
| 15 | what is there to do in lake havasu | ask / OPEN_ENDED / entity BMX / 0.82 | Tier2 path likely entity-biased | uncertain | likely 2 | honest-but-incomplete |
| 16 | tell me about lake havasu | ask / OPEN_ENDED / entity BMX / 0.82 | Tier2 path | uncertain | likely 2 | honest-but-wrong for broad town query |
| 17 | what kind of outdoor stuff is around here | ask / OPEN_ENDED / None / 0.7 | Tier2 path | likely category infer; uncertain | likely 2 | often acceptable but incomplete |
| 18 | I'm visiting next week, what should I plan | ask / OPEN_ENDED / None / 0.7 | Tier2 path | uncertain; parser enum lacks `next_week` | likely 2 | honest-but-wrong risk |
| 19 | fireworks july 4 | ask / OPEN_ENDED / None / 0.7 | Tier2 path | uncertain | likely 2 | honest-but-wrong risk |
| 20 | are there any farmers markets | ask / OPEN_ENDED / None / 0.7 | Tier2 path | likely category-ish inference uncertain | likely 2 | mixed |

Notes:
- Parser outputs are LLM-variable; uncertain cells mark non-deterministic outcomes.
- Non-representable temporal semantics in parser schema are a key uncertainty source.

---

## Section 4 — Failure pattern analysis

### Pattern A — Calendar phrase loss in parser schema

- **Description:** Natural time expressions are not first-class in `Tier2Filters.time_window` enum.
- **Queries:** 2, 3, 6, 7, 18, 19.
- **Responsible components:** `prompts/tier2_parser.txt` schema constraints (`time_window` enum), parser validation.
- **Severity:** High.

### Pattern B — Gap-template branch remains brittle for no-entity DATE/LOCATION/HOURS

- **Description:** Even after reorder, gap path still triggers when Tier2 yields no rows for these sub-intents.
- **Queries:** 4, 9, 13.
- **Responsible components:** `_catalog_gap_response` + ask path with `allow_tier3_fallback=False` (`app/chat/unified_router.py` L71-L82, L356-L367).
- **Severity:** Medium-high.

### Pattern C — Tier2 earliest-date + cap bias

- **Description:** Event ordering `date ASC` and cap `MAX_ROWS=8` can underrepresent user intent in broad queries.
- **Queries:** 1, 2, 6, 7, 15, 17, 20.
- **Responsible components:** `_query_events` + `_merge_simple` caps (`app/chat/tier2_db_query.py` L316-L327, L273-L290, L453-L476).
- **Severity:** High.

### Pattern D — Entity matcher false positives on broad locality terms

- **Description:** Fuzzy alias matching can attach unrelated provider entities to broad queries.
- **Queries:** 15, 16 (observed), potentially 14.
- **Responsible components:** `match_entity_with_rows` thresholded best-match (`app/chat/entity_matcher.py` L216-L236).
- **Severity:** Medium.

### Pattern E — Explicit-rec trigger set narrow

- **Description:** Tier3 forcing depends on specific phrase regexes.
- **Queries:** many recommendation/browse phrasings that don’t include trigger text.
- **Responsible components:** `_EXPLICIT_REC_PATTERNS` (`app/chat/unified_router.py` L44-L52).
- **Severity:** Medium.

### Pattern F — Formatter quality constrained by upstream row selection

- **Description:** Even grounded formatter remains limited by parser extraction + capped rows.
- **Queries:** 1, 2, 6, 7, 15, 17, 20.
- **Responsible components:** `tier2_db_query` + `tier2_formatter`.
- **Severity:** Medium-high.

---

## Section 5 — Architectural assessment

### Q5.1 Parser improvements alone vs topology changes

Parser improvements can fix a substantial subset, but topology-level blind spots remain:

- Parser/schema gaps clearly drive many failures (Pattern A).
- Routing still has special-case gap behavior for DATE/LOCATION/HOURS no-entity asks (`app/chat/unified_router.py` L356-L367).
- No semantic "answerability" check exists when Tier2 returns some rows that may not satisfy intent.

Conclusion: parser improvements are necessary but likely insufficient for full natural-language calendar/discovery robustness.

### Q5.2 Smallest change likely to fix ~80%

1. Expand Tier2 parser temporal expressiveness (`next_week`, `next_month`, explicit month/date literals, season handling guidance).
2. Add parser confidence/fallback rules when temporal intent is detected but structured date extraction is missing.
3. Keep current routing mostly intact initially.

This minimizes risk while addressing the dominant failure pattern.

### Q5.3 Maximalist change likely to fix ~all

- Replace split classifier+Tier2 parser handoff with a unified LLM-backed structured router producing intent, confidence, temporal structure, and tier plan.
- Add semantic answerability checks before finalizing Tier2 outputs.
- Potentially extend schema for richer temporal constructs.

Tradeoffs:
- Better coverage/consistency.
- Higher latency/cost and larger pre-launch regression surface.

---

## Section 6 — Adjacent observations

1. `unified_router.py` top docstring still says ask is Tier1 else Tier3, but code now does Tier1/explicit-rec/Tier2/Tier3 with gap special-case.
2. Intent understanding is split across deterministic classifier and LLM parser, increasing mismatch risk.
3. `_EXPLICIT_REC_PATTERNS` includes broad `\bbest\b` trigger but misses many equivalent recommendation phrasings.
4. `app/core/slots.py` supports richer temporal extraction (`next_month`, weekdays) than Tier2 parser enum currently allows; capability mismatch exists.
5. Tier3 context (post-8.8.3 revert) remains provider-linked events only.
6. Entity model is provider-centric; landmark/location entities are weakly represented.

---

Read-only report only. No code/prompt/DB writes performed.
