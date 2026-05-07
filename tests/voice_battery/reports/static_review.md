# Voice battery — static review

**Drafted:** 2026-05-06.
**Method:** Hand-traced 200 representative questions (`tests/voice_battery/questions.yaml`) through the unified router, intent classifier, Tier 1 templates, and Tier 2 shortcut by reading code, anchored to the recently-shipped Slice A–D behavior. Zero LLM calls. Empirical run available via `python -m scripts.voice_battery.static_check`.
**Companion:** `docs/voice-rubric.md` (the rubric this scores against).

## §1 Executive summary

Tier 1 + Tier 2 cost discipline is solid for the *covered* shapes — phone/address/website/hours/open-now/rating/review-count, plus the regex-shortcut listing path. The work that's needed is **breadth, not depth**: the regex patterns for intent classification, the gap-response list, and the OOS triggers all date from before the Google business catalog landed and miss many natural phrasings. Plus the OPEN_NOW response itself is sterile and doesn't tell the user when to come back.

**Top eight findings ranked by user-impact.**

1. **OPEN_NOW response is sterile** (already flagged by Casey). "outside today's posted window" doesn't tell the user *when* they're next open. Same for the open variant — doesn't say *until when*. FIX: include the day's window or next-open time in the response. *Affects every open/closed query.*
2. **Restaurant / dining queries blocked by stale OUT_OF_SCOPE rule.** `app/core/intent.py` triggers OOS on "restaurant", "where to eat", "best place to eat", "dinner spot" etc. The 2,266 Google providers include 200+ restaurants — these queries now have real catalog answers and should route to Tier 2 listings, not the chat-mode "outside what I cover" reply. *High-volume regression for visitors.*
3. **Gap response only fires for 3 of 9 Tier 1 intents.** `unified_router._catalog_gap_response` returns the "I don't have that, add at /contribute" template only for DATE / LOCATION / HOURS. PHONE, WEBSITE, RATING, REVIEW_COUNT fall through to Tier 3 LLM synthesis when no entity matches — wastes tokens AND the catch-all Tier 3 reply is less useful than the structured gap template. *Cost discipline + UX.*
4. **PHONE_LOOKUP regex misses "reach" and bare "contact".** "how do I reach havasu lanes" / "contact for the foundry" — natural phrasings — fall through to OPEN_ENDED. *Coverage hole.*
5. **OPEN_NOW disambiguation requires explicit "now / right now / currently".** Bare "is X open" routes to HOURS_LOOKUP (renders the full week's hours) instead of computing current state. *Coverage hole — especially likely on mobile typing.*
6. **HOURS_LOOKUP regex requires plural "hours".** "what hour is X" / "open hour" don't match. Minor. *Edge.*
7. **WEBSITE_LOOKUP regex misses "link".** "link for X" doesn't match. *Edge.*
8. **Tier 2 LLM-parser path still spends tokens on event-shaped listings.** "what events this weekend" routes through `tier2_parser.parse()` (Haiku, ~50–300 in tokens) + `tier2_formatter.format()` (Haiku, ~200–400 out tokens) on every query. Slice D's regex shortcut only covers business listings; event listings still pay full freight. *Cost discipline gap — explicit on the brief but deferred.*

The rest of this doc walks each finding with the exact file/line and recommended fix shape.

## §2 Findings detail

### §2.1 OPEN_NOW response wording (HIGH)

**File:** `app/chat/tier1_handler.py:184–193`

Current:

```python
if state:
    msg = "They're open right now — hours say they're in window for today."
else:
    msg = "They're closed right now — outside today's posted window."
```

Both lines are technically correct but useless — they don't tell the user the actual window. The natural human answer is "Closed now, open tomorrow at 9" or "Open until 9 PM tonight."

**Fix shape.** Read the day's windows from `_provider_hours_text(provider)` (already populated for Google providers), pick the relevant slice, and substitute into a richer template:

- Open + closes-today: `Open until {close_time} today.`
- Open + 24/7: `Open 24/7.`
- Closed but opens later today: `Closed right now — opens at {next_open_time} today.`
- Closed all day, opens later this week: `Closed today — open {next_open_day} {next_open_window}.`
- Closed and unknown next-open: fall back to the existing line.

The `places_hours_to_structured(google_hours)` helper already returns weekday segments. A small helper next to `_provider_open_now` can resolve "next open boundary" deterministically. Casey's voice rubric explicitly calls this out (§4.2 in `docs/voice-rubric.md`).

### §2.2 Stale OOS dining triggers blocking restaurant queries (HIGH)

**File:** `app/core/intent.py:75–93`

The `dining` bucket in `_OUT_OF_SCOPE_TRIGGERS` includes:

```python
("restaurant", "where to eat", "best place to eat", ..., "good food in", "yelp", "breakfast")
```

Pre-Slice-A, Hava had no business catalog so dining was correctly out of scope. Now there are 200+ restaurants in `providers`. Queries like "any good restaurants" / "best place to eat" should route to Tier 2 listings, not to the OOS chat reply.

**Fix shape.** Drop the dining bucket from `_OUT_OF_SCOPE_TRIGGERS` entirely; let Tier 2 handle these. Verify the existing `_LIST_BY_CATEGORY` regex doesn't conflict (it requires "leagues|classes|programs|lessons" which restaurants don't trigger).

A safer staged version: keep "yelp" as OOS (off-platform reference) but drop the rest. "Best place to eat" then matches the Tier 2 listing shortcut after a small predicate addition (see §2.7).

### §2.3 Gap-response template covers only 3 of 9 Tier 1 intents (HIGH)

**File:** `app/chat/unified_router.py:80–88`

```python
def _catalog_gap_response(intent_result: IntentResult) -> str | None:
    sub = intent_result.sub_intent
    if sub not in ("DATE_LOOKUP", "LOCATION_LOOKUP", "HOURS_LOOKUP"):
        return None
    ...
```

If the user asks "phone number for [business not in catalog]" we currently:
1. classify → PHONE_LOOKUP, no entity → enrich → still no entity
2. `_catalog_gap_response` returns None (PHONE not in list)
3. Falls to Tier 2 LLM parser → parser fails or returns junk → falls to Tier 3
4. Tier 3 synthesizes a vague answer or graceful fallback

**Fix shape.** Extend the allowed list to include the full `_TIER1_SUB_INTENTS` set with intent-tailored gap copy:

- PHONE: "I don't have that business's phone in the catalog yet. Add it at /contribute or share the name and a Google Business link."
- WEBSITE: "I don't have a website on file for that one. /contribute or share the link and I'll add it."
- RATING / REVIEW_COUNT: "I don't have Google reviews on file for that. Add it at /contribute with a Google Business link and I'll pull them."
- TIME / OPEN_NOW: same gap as HOURS (already covered).
- AGE / COST / DATE: program-shaped, gap text already friendly.

This makes catalog gaps zero-token AND consistent in voice.

### §2.4 PHONE_LOOKUP regex coverage (MEDIUM)

**File:** `app/chat/tier1_templates.py` (INTENT_PATTERNS, PHONE_LOOKUP)

```python
("PHONE_LOOKUP", re.compile(r"\b(phone number|phone|contact number|call them|number)\b"))
```

Misses common phrasings: "reach", "contact for X" (bare), "get ahold of", "call X" (without "them"). Sample queries that fall through to OPEN_ENDED:

- "how do I reach havasu lanes" — no match
- "contact for sloane's" — only matches if "contact number" not bare "contact"
- "call X" without "them" — no match

**Fix shape.** Widen the regex to:

```
\b(phone number|phone|contact number|contact info|contact|call them|call for|reach (?:them|out)|number)\b
```

Test against existing fixtures (`tests/test_intent_classifier.py`) to confirm no over-matching.

### §2.5 OPEN_NOW disambiguation requires explicit "now" (MEDIUM)

**File:** `app/chat/intent_classifier.py:91–94`

```python
_OPEN_NOW_DISAMBIG = re.compile(
    r"\b(open now|open right now|currently open|open at the moment|are you open now|is it open now)\b",
    re.IGNORECASE,
)
```

When user says "is X open" (no "now"), the classifier matches HOURS_LOOKUP and returns the full week's hours. Better: if the query is a yes/no question about a specific business and the classifier already has an entity match, treat as OPEN_NOW.

**Fix shape.** Loosen disambig:

```
\b(open now|open right now|currently open|open at the moment|are you open(?: now)?|is (?:it|\w+) open|open today|open tonight)\b
```

Pair with the OPEN_NOW response wording fix (§2.1) so the answer is useful.

### §2.6 HOURS_LOOKUP requires plural / WEBSITE_LOOKUP misses "link" (LOW)

**File:** `app/chat/tier1_templates.py` INTENT_PATTERNS.

- HOURS: add `\bhour\b` (singular) to the alternation. "what hour is X" / "open hour".
- WEBSITE: add `\b(link|landing page)\b`. "link for X" is common.

Both are one-line regex tweaks.

### §2.7 Tier 2 listing shortcut predicate gaps (MEDIUM)

**File:** `app/chat/tier2_business_shortcut.py:31–47`

`_LISTING_PREFIX` covers "find me", "show me", "where can I find", "any good", "list of", "are there any" — but misses common shapes:

- "what are some coffee shops" — `what are some` not in alternation
- "what are the good barbers in town" — `what are the good` not in alternation
- "got any taco places" — `got any` not in alternation
- "got a recommendation for X" — opens a soft listing
- "best X" / "good X" without leading verb — bare adjective starts (likely Tier 3 territory, fine to keep there)

**Fix shape.** Extend predicate:

```
what (?:are )?(?:some |the )?(?:good |best )?|
got (?:any |a )?(?:good )?|
recommend (?:a |any )?(?:good )?|
```

Add tests for each new shape in `tests/test_tier2_business_shortcut.py`.

### §2.8 Tier 2 event/program listings still spend tokens (HIGH but explicit deferral)

**File:** `app/chat/tier2_handler.py` + `app/chat/tier2_parser.py`

Slice D's shortcut only fires when the query is *business-shaped* (no event-shape tokens). All event/program listings still go through the Anthropic-powered parser + formatter. Casey's brief decision #6 was explicit: "(a) regex shortcut for business listings". Events/programs were left for a follow-up.

For the voice battery, ~10 event-listing questions and ~10 program-listing questions all spend tokens. That's ~$0.05 per battery run today. Not blocking, but worth surfacing here.

**Fix shape (future slice).** Mirror Slice D for events: regex predicate + extracted time window (today/this weekend/next week — small set) + deterministic event listing renderer. The structured-filter route into `tier2_db_query` already supports this if `Tier2Filters.time_window` is set; the only LLM-side cost is parser + formatter.

## §3 Coverage summary by shape

| Shape | Count | Routing risk | Voice risk |
|---|---|---|---|
| factual_phone | 10 | regex too narrow (§2.4) | low |
| factual_address | 10 | "directions to" → OOS (correct) | low |
| factual_website | 8 | "link" miss (§2.6) | low |
| factual_hours | 8 | "hour" singular miss (§2.6) | low |
| factual_open_now | 8 | bare "is X open" misses (§2.5) | **HIGH (§2.1)** |
| factual_rating | 6 | clean | low |
| factual_review_count | 4 | clean | low |
| factual_age/cost/time/date | 8 | clean | low |
| listing_business | 20 | predicate gaps (§2.7), restaurants blocked by OOS (§2.2) | low |
| listing_events | 10 | spends tokens (§2.8) | low (LLM-graded) |
| synthesis_rec | 30 | clean routing | LLM-graded |
| synthesis_multi | 10 | clean routing | LLM-graded |
| gap_factual | 7 | half not covered by gap template (§2.3) | medium |
| gap_listing | 5 | falls to LLM (correct) | LLM-graded |
| ambiguous_entity | 10 | one-shot match could be wrong | medium |
| oos_* | 5 | clean | low |
| greeting / small_talk | 10 | "yo" miss (minor) | low |
| contribute | 5 | clean placeholder reply | low |
| correction | 5 | clean placeholder reply | low |
| near_miss / typo | 10 | no fuzzy resilience | medium |
| follow-up multi-turn | 5 | session-dependent | not tested standalone |
| day-aware hours | 3 | sunday-open boundary case | medium |

## §4 Recommended next slice (voice tuning campaign — Slice F)

Order by user impact, not by file:

1. **OPEN_NOW response with hours context (§2.1)** — biggest UX win, single template.
2. **Drop OOS dining (§2.2)** — unlocks restaurant catalog for the highest-volume visitor query.
3. **Extend gap-template list (§2.3)** — saves tokens + ships consistent voice on missing data.
4. **Tier 1 regex coverage (§2.4 + §2.5 + §2.6)** — small one-line tweaks, big classification recall gains.
5. **Tier 2 listing predicate widening (§2.7)** — incremental shortcut coverage.
6. **Event/program Tier 2 shortcut (§2.8)** — bigger work, defer one slice.

Each item gets a 5–15 line code change plus 3–5 unit tests. Total: probably one focused engineering session with green tests at each step.

## §5 How to run the empirical battery

The static review above was hand-derived from code reading. The harness automates it:

```
python -m scripts.voice_battery.static_check
```

Output:
- `tests/voice_battery/reports/static_check.md` — markdown table per intent shape
- `tests/voice_battery/reports/static_check.jsonl` — raw rows for follow-up grading

The harness suppresses the Anthropic API key during the run so Tier 3 routes return the graceful fallback message — no token spend. To run with live Tier 3 (costs ~$1–2 in Haiku), set `VOICE_BATTERY_ALLOW_LLM=1`.

For voice-quality grading (the part this static review can't do — judging Tier 3 synthesis text), a separate `scripts/voice_battery/grade.py` would feed the response + rubric to Haiku for PASS/MINOR/FAIL judgment. That's the natural Slice F follow-up after the routing/template fixes land.
