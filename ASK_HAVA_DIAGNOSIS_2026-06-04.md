# Ask Hava chat diagnosis — 2026-06-04

Read-only investigation (no code changed, no git ops). Probed prod
(`https://havasu-chat-production.up.railway.app/api/chat`) with ~20 live queries and
traced the routing code. **The service is not hard-down** — every probe returned
HTTP 200 and all tiers respond. What's broken is *routing*: the wrong tier answers
the wrong question, and queries that should be zero-token are burning ~4k LLM
tokens each.

## 1. The system as actually built

The "3-tier" design has more API surface than the name implies:

| Path | API calls | Notes |
|---|---|---|
| Tier 1 templates (`tier1_handler`) | 0 | Requires classifier sub_intent + **entity match** |
| Intent layer (`app/chat/intents/`) | 0 | Flag `USE_INTENT_LAYER` — **confirmed ON in prod** (its `"Here's what's good to eat."` voice line is live) |
| Tier 2 shortcut paths (business listing, day_agenda, week_strip, card_row) | 0 | |
| Tier 2 full path | **2 OpenAI calls** | `tier2_parser.parse` + `tier2_formatter.format`, exact-match cached 1 day |
| LLM router (`USE_LLM_ROUTER`) | **+1 call per query** when on | Can't confirm flag state without Railway access |
| Tier 3 | 1+ calls (gpt-4.1-mini) | semantic cache |

So "Tier 2" is only API-free on its shortcut paths. Any query that misses Tier 1 /
intent layer / shortcuts pays 2–3 API calls. A `tier_used: "2"` log row does **not**
mean zero tokens.

## 2. Root cause: entity matching is phrasing-brittle, and everything downstream depends on it

Live A/B evidence (identical info need, different phrasing):

| Query | tier | tokens | entity |
|---|---|---|---|
| `phone for mudshark` | 1 | 0 | Mudshark Brewery and Public House |
| `phone number for mudshark brewery` | 1 | 0 | matched |
| `what are the hours for Mudshark Brewery` | 1 | 0 | matched |
| `whats the phone number for Mudshark Brewery` | 2 | 4,052 | **null** |
| `what is the phone number for mudshark brewery` | 2 | 4,028 | **null** |
| `tell me about Mudshark Brewery` | 2 | — | **null** → wrong answer (see §3) |

The "what's the / what is the" prefix defeats entity extraction → Tier 1 can't fire →
the query falls into the LLM path. Natural conversational phrasing is exactly what
real users type, so a large share of simple factual lookups are paying ~4k tokens
(until the 1-day exact-match cache catches the *identical* string — token count went
4052 → 0 on repeat).

## 3. Intent layer over-claims when the entity miss happens

`runtime.try_intent_layer` guards against claiming entity turns — but the guard is
`if entity and entity.strip(): return None`. It trusts the upstream matcher. When the
matcher misses (§2), the resolver keyword-matches and claims the turn:

- **"tell me about Mudshark Brewery"** → resolver sees cuisine token "brewery" →
  `eat_find` → *"Here's what's good to eat."* + a generic restaurant list. This is the
  exact case the docstring says it must never claim (runtime.py line ~163).
- **"mexican food near the channel"** → same generic eat list; the cuisine/area slots
  don't visibly filter.
- The "Restaurants" list itself is polluted: top items included a Bakery and
  "Lovedwell Creative" (category: **Service**) — category needles too loose, ordering
  looks like rating-5.0-first regardless of relevance.

## 4. Other live failures observed

- **`best happy hour in town`** → Tier 3, 4,698 tokens, answer: *"Try
  https://www.golakehavasu.com/ for what's around… Their listed number is (928)
  302-4001"* — deflection + an unexplained phone number. Worst answer in the battery
  and the most expensive.
- **`where can i rent a boat`** → `gap_template` near-match reply ("Lake Havasu RV
  and Boat Rentals is at… If you meant a different place, /contribute…") — a
  recommendation-shaped query handled as a single-entity factual lookup.
  `_RECOMMENDATION_SHAPED` covers "where can i find/get" but not "rent".
- **"two days in havasu with kids, what should we plan"** → single card for Western
  Winter Blast fireworks, **"Wed Feb 10"** — a February event served in June (2,345
  tokens spent to pick it).
- **Markdown leaks into voice**: `[Mudshark Brewery and Public House](https://…)`
  rendered raw in the phone-lookup response (tier-2 formatter output not sanitized
  on that path).
- unified_router.py:207 has a standing comment: Tier 2/3 LLM path "still has
  unresolved API issues on prod" — consistent with the degraded Tier 3 answers.

## 5. What worked

Greetings/small talk (chat tier, 0 tokens), hours/phone lookups *with plain
phrasing* (Tier 1), event windows ("this weekend" → week_strip, "today" →
day_agenda, 0 tokens), open-now empty-state honesty, out-of-scope deflection
(weather).

## 6. Where to look when fixing (no changes made)

1. **Entity matcher** (`entity_matcher.py`): make extraction robust to
   "what's the / what is the / tell me about" lead-ins — this single fix restores
   Tier 1 coverage AND stops the intent layer over-claiming (§3 guard starts
   working again).
2. **Intent layer resolver**: don't claim when the query contains a probable
   proper-noun span that failed to match (e.g. capitalized bigram not in any dict) —
   belt-and-suspenders for §3.
3. **Category needles / ordering** in the eat_find query template (Service/Bakery in
   "Restaurants", rating-first ordering).
4. `_RECOMMENDATION_SHAPED` regex: add rent/hire/book shapes.
5. Tier-2 formatter postprocess: strip markdown links from voice.
6. Verify `USE_LLM_ROUTER` state in Railway (needs Casey — env reads are gated).
   If on, it adds an OpenAI call to every non-Tier-1 query for routing alone.
7. Stale/seasonal event selection in single_card picks (Feb event in June).

Probe transcripts: session ids `diag-*` in prod chat_logs, 2026-06-04.
