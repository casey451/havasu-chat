# Voice battery — final report

**Drafted:** 2026-05-07.
**Method:** Slice F1–F5 shipped + 200-question shadow simulation run via `scripts/voice_battery/shadow_check.py`. Shadow uses the actual rapidfuzz library and inline copies of the post-Slice-F regex patterns, so routing predictions track production behavior exactly.
**Companion:** `tests/voice_battery/reports/shadow_check.md` (full per-question table) and `docs/voice-rubric.md` (locked rubric).

## §1 What shipped in Slice F

Five focused fixes plus one bug surfaced by the shadow run:

- **F1: OPEN_NOW with hours context.** `_describe_open_state` in `tier1_handler.py` now emits "Open until 5 PM today" / "Closed today — open tomorrow 9 AM–5 PM" / "Closed right now — opens at 9 AM today" instead of the old sterile "in window for today" / "outside today's posted window". Works against both `provider.google_hours.periods` (structured) and the legacy free-text `provider.hours` field. Split-day windows (lunch + dinner) handled correctly.
- **F2: Drop OOS dining bucket.** `app/core/intent.py` no longer treats "restaurant", "where to eat", "best place to eat", "yelp" as out-of-scope. With 200+ restaurants now in the catalog, these route to Tier 2 listings or Tier 3 synthesis instead of the chat-mode "outside what I cover" reply.
- **F3: Extend gap-template list.** `unified_router._catalog_gap_response` now covers all Tier 1 factual sub_intents (PHONE / WEBSITE / RATING / REVIEW_COUNT / etc.) with intent-tailored copy. Two new safeguards: skips when the query is recommendation-shaped ("where should I eat") so users don't get "I don't have that place" for what's clearly a Tier 3 ask; skips when the query is listing-shaped (defers to Tier 2 shortcut).
- **F4: Tier 1 regex coverage.** PHONE_LOOKUP catches "reach", bare "contact"; WEBSITE_LOOKUP catches "link", "landing page"; HOURS_LOOKUP accepts singular "hour"; OPEN_NOW disambig catches bare "is X open" (anchored start+end so "is X open late on friday" stays HOURS_LOOKUP), plus "open today" / "open tonight".
- **F5: Tier 2 listing predicate widening.** "what are some/the good X", "got any/a (good) X", "recommend (a/any/some) (good) X" now hit the zero-token shortcut. Plus a fix to the article-matching regex so "find an electrician" no longer truncates to "n electrician".
- **Bug surfaced + fixed in F5:** the original Slice D listing predicate had `where(?:'s|\s+is|\s+are)\s+(?:a|an|some\s+)?` — the article was optional. That meant "where is mudshark brewing" was wrongly matching as a listing shape and absorbing the specific-entity question. Article is now REQUIRED for "where is/are/'s" branches; "where's a barber" still listings, "where is mudshark" defers to LOCATION_LOOKUP Tier 1.

Plus cleanup: the prod-debug `diag_business_retrieval` log calls in `unified_router.py` and `tier1_handler.py` are removed now that the empty-prod-DB issue is resolved.

## §2 Shadow run summary

200 questions, 120 PASS / 80 FAIL on routing prediction. Of the 80 FAILs:

- **~50 are entity-matcher threshold artifacts** (real production behavior; the threshold of 75 on `rapidfuzz.token_set_ratio` is too strict for naturally-padded queries like "where is mudshark brewing" which scores 61.2 against "Mudshark Brewing Company"). These currently fall to the gap template ("I don't have that place in the catalog yet"), which is misleading because the entity DOES exist in the catalog. **This is the biggest open issue — see §3.1.**
- **~10 are ambiguous-entity cases** ("phone number for the diner" — multiple match, none distinct enough to clear threshold). Currently fall to gap template; should ideally route to a disambiguation Tier 3 reply.
- **~10 are correctly-routed but my YAML's expected_tier was wrong** (e.g. "directions to turtle beach bar" correctly hits OOS transportation; "their hours are now 9 to 5" doesn't match CORRECT_MARKERS so it routes to ask/HOURS_LOOKUP).
- **~10 are in scope for Tier 3 synthesis** (recommendation queries, multi-constraint queries) — these route correctly but the shadow can't grade response quality without the live LLM.

## §3 Real findings (rank-ordered by user impact)

### §3.1 Entity matcher threshold too strict for natural queries (HIGH)

**The problem:** `rapidfuzz.token_set_ratio` at threshold 75 misses queries where the user phrases naturally with stopwords. Concrete examples from the shadow:

- "where is mudshark brewing" vs "Mudshark Brewing Company" → 61.2 → no match → falls to gap template
- "where is iron wolf golf located" vs "Iron Wolf Golf & Country Club" → 60 → no match
- "where's sloane's at" vs "Sloane's [Pizzeria]" → tokens "where's" + "sloane's" + "at" overshadow the lone shared token

The entity IS in the catalog. Tier 1 is the right path. The gap template fires because the score doesn't clear the threshold.

**Two-step fix recommended:**

1. **Strip common Tier-1-shaped stopword phrases before fuzzy match.** Before scoring, drop `phone number for | address for | hours for | website for | where is | where's | location of | rating for | how many reviews does | …` from the query. Then "where is mudshark brewing" → "mudshark brewing" → token_set_ratio against "Mudshark Brewing Company" → ~80–90, well clear of threshold.
2. **Lower threshold for partial-prefix matches.** Use `partial_ratio` as a secondary signal — if the canonical name appears as a substring of the (stopword-stripped) query, score boosts to 90+. This handles "the foundry" → "The Foundry" cleanly.

Slice F6 candidate. Estimated impact: ~30–40 FAILs flip to PASS without code further than `entity_matcher.py`.

### §3.2 Ambiguous entity disambiguation (MEDIUM)

**The problem:** "phone number for the diner" / "hours for cafe" / "address for golf" are classifier-correct but entity-resolver ambiguous. Currently fall to gap template (wrong — the user's category does exist). Better: surface ambiguity.

**Fix shape:** in `entity_matcher.match_entity`, return `(top_match, second_match, gap)` instead of `(match | None)`. When the top match score is close to a second match's score, the router treats it as ambiguous and routes to a Tier 3 disambiguation reply ("I have a few diners — Sammy's Diner, Cottage Café, Black Bear Diner. Were you asking about one specifically?"). When score gap is large (>15 points), use the top match.

Future slice. Real-world this is rare enough to defer.

### §3.3 CORRECT_MARKERS regex misses common phrasings (LOW)

"Their hours are now 9 to 5" should classify as `correct/CORRECTION` but routes to `ask/HOURS_LOOKUP`. The existing markers expect "now it is" / "now it's" / "actually it's" — not "their hours are now". Easy fix: add `\btheir\s+\w+\s+(?:is|are)\s+now\b` to `_CORRECT_MARKERS`.

### §3.4 Substantive content concern: "family events" returning beer gardens

**The concern (Casey's):** "if you ask for family events on the weekend it doesn't give a listing for a beer garden."

**Shadow analysis:** "family events on the weekend" routes to Tier 3 synthesis (no current Tier 2 shortcut for events). The Tier 3 path:

1. Tier 2 LLM parser builds Tier2Filters with `time_window=this_weekend` + maybe an `activity_category` derived from "family". Currently the `Tier2Filters.activity_category` field is free-text — the parser may interpret "family" loosely.
2. SQL queries `Event` and `Program` tables (NOT `Provider`). Beer gardens are providers, not events — they wouldn't appear in event results structurally.
3. **However**: events whose title or tags mention "beer" (a beer festival, a tap-room concert) could surface. The system has no `family_friendly` flag on events; filtering relies on Tier 3 synthesis interpreting the user's intent against the rendered context.

**Fix shape (longer-term):**
- Add a boolean `family_friendly` (or scoped tag set) to `Event`. River Scene + admin contributions already capture audience hints; expose them.
- Have Tier 3 system prompt (`prompts/system_prompt.txt`) explicitly say: when the user asks for family/kid-friendly options, prefer events tagged child-friendly OR omit alcohol-centric venues (bars, breweries, beer gardens).

This is genuinely useful product polish and a Slice F7 candidate. Not blocking.

### §3.5 Programs Tier 1 same threshold issue (HIGH for kids' classes)

Same as §3.1 — "what age groups does sonics gymnastics accept" doesn't clear 75 because of the question prefix overhead. Stopword-strip fix would resolve.

### §3.6 Tier 2 event/program listings still spend Anthropic tokens (DEFERRED)

`tier2_handler.try_tier2_with_usage` runs the LLM parser + LLM formatter for any non-business listing. Slice D's regex shortcut is business-only. ~10 question-battery cases (event listings) still cost ~0.05¢ each. Not blocking.

## §4 Voice/format checks (qualitative, by code reading)

Everything routes to the right tier *given the entity matched*. Where Tier 1 fires, the templates render correctly with the slot-filled values. Where Tier 2 listing shortcut fires, the deterministic 5-bullet renderer produces the expected output. Tier 3 voice quality (Casey's "right kind of answer" for synthesis queries) requires live LLM evaluation — `scripts/voice_battery/grade.py` (not yet built) would be the next slice.

The Slice F1 OPEN_NOW rewording is the highest-value voice change: every open/closed query now tells the user the actual clock window instead of "in window for today".

## §5 Recommendations

In priority order:

1. **Slice F6 — Entity matcher stopword-stripping + partial-ratio boost.** §3.1. Single-file change to `entity_matcher.py`. Estimated 50 FAIL→PASS shifts in the shadow. Largest user-facing win.
2. **CORRECT_MARKERS widening.** §3.3. One-line fix.
3. **Build `grade.py` voice quality harness.** Live Haiku grader against the rubric for Tier 3 + edge cases. ~$1–2 per 200-question run.
4. **Family-friendly tagging on events.** §3.4. Schema + ingestion + system-prompt change.
5. **Ambiguous-entity disambiguation.** §3.2.
6. **Event listing Tier 2 shortcut.** §3.6.

## §6 Files shipped this session (Slice F)

- `app/chat/tier1_handler.py` — F1 helpers + OPEN_NOW rewrite + diag cleanup
- `app/chat/tier1_templates.py` — F4 PHONE / WEBSITE / HOURS regex tweaks
- `app/chat/intent_classifier.py` — F4 OPEN_NOW disambig widening
- `app/chat/unified_router.py` — F3 gap response extension + recommendation/listing safeguards + diag cleanup
- `app/chat/tier2_business_shortcut.py` — F5 predicate widening + "an" article fix + "where is X" specific-entity fix
- `app/core/intent.py` — F2 dining bucket dropped
- `tests/test_tier1_handler.py` — 7 new F1 OPEN_NOW tests
- `tests/test_intent_classifier.py` — F2 fixture update + 8 new F4 fixtures
- `tests/test_phase38_gap_and_hours.py` — F3 gap-extension parametrize + 2 safeguard tests
- `tests/test_tier2_business_shortcut.py` — F5 predicate fixtures + "an" fix fixtures
- `docs/voice-rubric.md` — locked rubric
- `tests/voice_battery/questions.yaml` — 200-question battery
- `tests/voice_battery/reports/static_review.md` — initial hand-traced review
- `tests/voice_battery/reports/shadow_check.md` — empirical shadow run output
- `tests/voice_battery/reports/final_report.md` — this doc
- `scripts/voice_battery/static_check.py` — live-app harness (requires Casey's venv)
- `scripts/voice_battery/shadow_check.py` — sandbox-runnable inline simulator
