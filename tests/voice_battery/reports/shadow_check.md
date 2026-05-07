# Voice battery — shadow check report

**Generated:** 2026-05-07T04:03:07.179556Z

- Total questions: **200**
- PASS (routing matches expected): **120**
- FAIL (routing mismatch — expected tier ≠ predicted tier): **80**

Routing predicted by inline simulation of post-Slice-F regex patterns.
Entity match uses a token-overlap heuristic against 2,266 LHC provider names
from `scripts/output/places_pull/enrichment_enriched.jsonl`.

FAILs do not all indicate bugs — many are pre-flagged in `notes` as known gaps
(e.g. dining queries that USED to be OOS now route to OPEN_ENDED, or 'best X'
queries that have no Tier 2 predicate). The report groups by intent_shape so
patterns are visible.

---

## ambiguous_entity (10 cases, 10 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_amb_001 | phone number for the diner | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_amb_002 | hours for cafe | 3 | gap_template | HOURS_LOOKUP |  | FAIL |
| edge_amb_003 | address for golf | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| edge_amb_004 | phone for shop | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_amb_005 | where is the bar | 3 | 2 | LOCATION_LOOKUP |  | FAIL |
| edge_amb_006 | rating for the place | 3 | gap_template | RATING_LOOKUP |  | FAIL |
| edge_amb_007 | phone for it | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_amb_008 | when is it open | 3 | gap_template | DATE_LOOKUP |  | FAIL |
| edge_amb_009 | address for that place | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| edge_amb_010 | phone number for them | 3 | gap_template | PHONE_LOOKUP |  | FAIL |

**Detail:**

- `edge_amb_001` (FAIL): 'phone number for the diner'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Multiple diners may match. Tier 1 picks one — could be wrong. FLAG: ambiguity handling.
- `edge_amb_002` (FAIL): 'hours for cafe'
  - expected=3 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Multiple cafes match. Same flag.
- `edge_amb_003` (FAIL): 'address for golf'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_amb_004` (FAIL): 'phone for shop'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_amb_005` (FAIL): 'where is the bar'
  - expected=3 observed=2 mode=ask sub=LOCATION_LOOKUP
  - response shape: Tier 2 listing — category='the bar', deterministic 5-bullet renderer
- `edge_amb_006` (FAIL): 'rating for the place'
  - expected=3 observed=gap_template mode=ask sub=RATING_LOOKUP
  - response shape: gap template for RATING_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_amb_007` (FAIL): 'phone for it'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Pronoun referent — exercises _prior_entity_fresh in unified_router. With no session, no entity.
- `edge_amb_008` (FAIL): 'when is it open'
  - expected=3 observed=gap_template mode=ask sub=DATE_LOOKUP
  - response shape: gap template for DATE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_amb_009` (FAIL): 'address for that place'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_amb_010` (FAIL): 'phone number for them'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## contribute_business (2 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_contrib_001 | just opened a coffee shop on McCulloch — address 400 McCu... | placeholder | placeholder | NEW_EVENT |  | PASS |
| conv_contrib_003 | adding a new yoga studio on swanson | placeholder | placeholder | NEW_EVENT |  | PASS |

## contribute_event (2 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_contrib_002 | there is a car show at the channel saturday at 6 | placeholder | placeholder | NEW_EVENT |  | PASS |
| conv_contrib_004 | i want to add a concert next friday at 8pm | placeholder | placeholder | NEW_EVENT |  | PASS |

## contribute_program (1 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_contrib_005 | new program — kids karate tuesdays 4pm | placeholder | placeholder | NEW_EVENT |  | PASS |

## correction (5 cases, 1 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_corr_001 | that's wrong, the phone changed | placeholder | placeholder | CORRECTION |  | PASS |
| conv_corr_002 | actually it's on Kiowa now, not McCulloch | placeholder | placeholder | CORRECTION |  | PASS |
| conv_corr_003 | the address moved to 50 Acoma Blvd | placeholder | placeholder | CORRECTION |  | PASS |
| conv_corr_004 | their hours are now 9 to 5 | placeholder | gap_template | HOURS_LOOKUP |  | FAIL |
| conv_corr_005 | changed to saturday at 7pm not friday | placeholder | placeholder | CORRECTION |  | PASS |

**Detail:**

- `conv_corr_004` (FAIL): 'their hours are now 9 to 5'
  - expected=placeholder observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## edge_empty (1 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_nm_010 | ? | 3 | 3 | OPEN_ENDED |  | PASS |

## factual_address (11 cases, 6 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_addr_001 | address for d1 performance | 1 | 1 | LOCATION_LOOKUP | D1 Performance (90) | PASS |
| t1_addr_002 | where is mudshark brewing | 1 | 2 | LOCATION_LOOKUP |  | FAIL |
| t1_addr_003 | location of altitude trampoline park | 1 | 1 | LOCATION_LOOKUP | Altitude Trampoline Park (90) | PASS |
| t1_addr_004 | where is iron wolf golf located | 1 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t1_addr_005 | address for the foundry | 1 | 1 | LOCATION_LOOKUP | Foundry (90) | PASS |
| t1_addr_006 | where can I find havasu lanes | 1 | 1 | LOCATION_LOOKUP | Havasu (90) | PASS |
| t1_addr_007 | street address for the tap room | 1 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t1_addr_008 | where's sloane's at | 1 | 2 | LOCATION_LOOKUP |  | FAIL |
| t1_addr_009 | located on what street is shugrue's | 1 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t1_addr_010 | directions to turtle beach bar | 3 | chat | OUT_OF_SCOPE |  | FAIL |
| edge_nm_006 | addres for d1 performance | 3 | 3 | OPEN_ENDED | D1 Performance (90) | PASS |

**Detail:**

- `t1_addr_002` (FAIL): 'where is mudshark brewing'
  - expected=1 observed=2 mode=ask sub=LOCATION_LOOKUP
  - response shape: Tier 2 listing — category='mudshark brewing', deterministic 5-bullet renderer
- `t1_addr_004` (FAIL): 'where is iron wolf golf located'
  - expected=1 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_addr_007` (FAIL): 'street address for the tap room'
  - expected=1 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_addr_008` (FAIL): "where's sloane's at"
  - expected=1 observed=2 mode=ask sub=LOCATION_LOOKUP
  - response shape: Tier 2 listing — category="sloane's at", deterministic 5-bullet renderer
- `t1_addr_009` (FAIL): "located on what street is shugrue's"
  - expected=1 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_addr_010` (FAIL): 'directions to turtle beach bar'
  - expected=3 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'
  - note: 'directions' triggers OUT_OF_SCOPE per app/core/intent.py. Tests OOS routing.
- `edge_nm_006` (note): 'addres for d1 performance'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Typo. FLAG.

## factual_age (2 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_age_001 | what age groups does sonics gymnastics accept | 1 | gap_template | AGE_LOOKUP |  | FAIL |
| t1_age_002 | how old does my kid need to be for little league | 1 | gap_template | AGE_LOOKUP |  | FAIL |

**Detail:**

- `t1_age_001` (FAIL): 'what age groups does sonics gymnastics accept'
  - expected=1 observed=gap_template mode=ask sub=AGE_LOOKUP
  - response shape: gap template for AGE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_age_002` (FAIL): 'how old does my kid need to be for little league'
  - expected=1 observed=gap_template mode=ask sub=AGE_LOOKUP
  - response shape: gap template for AGE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## factual_cost (2 cases, 1 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_cost_001 | how much does altitude cost | 1 | gap_template | COST_LOOKUP |  | FAIL |
| t1_cost_002 | pricing for ballet havasu | 1 | 1 | COST_LOOKUP | Havasu (90) | PASS |

**Detail:**

- `t1_cost_001` (FAIL): 'how much does altitude cost'
  - expected=1 observed=gap_template mode=ask sub=COST_LOOKUP
  - response shape: gap template for COST_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## factual_date (2 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_date_001 | when is the next bmx race | 1 | gap_template | NEXT_OCCURRENCE |  | FAIL |
| t1_date_002 | when's the next farmers market | 3 | gap_template | NEXT_OCCURRENCE |  | FAIL |

**Detail:**

- `t1_date_001` (FAIL): 'when is the next bmx race'
  - expected=1 observed=gap_template mode=ask sub=NEXT_OCCURRENCE
  - response shape: gap template for NEXT_OCCURRENCE: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_date_002` (FAIL): "when's the next farmers market"
  - expected=3 observed=gap_template mode=ask sub=NEXT_OCCURRENCE
  - response shape: gap template for NEXT_OCCURRENCE: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Farmers market not in catalog (Casey example). Tests gap response.

## factual_hours (9 cases, 7 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_hours_001 | what are the hours for d1 performance | 1 | 1 | HOURS_LOOKUP | D1 Performance (90) | PASS |
| t1_hours_002 | hours for mudshark brewing | 1 | gap_template | HOURS_LOOKUP |  | FAIL |
| t1_hours_003 | when is altitude open | 1 | gap_template | DATE_LOOKUP |  | FAIL |
| t1_hours_004 | business hours for iron wolf golf | 1 | gap_template | HOURS_LOOKUP |  | FAIL |
| t1_hours_005 | hours on saturday for the foundry | 1 | 1 | HOURS_LOOKUP | Foundry (90) | PASS |
| t1_hours_006 | what hours is the tap room | 1 | gap_template | HOURS_LOOKUP |  | FAIL |
| t1_hours_007 | hours of operation for sloane's | 1 | gap_template | HOURS_LOOKUP |  | FAIL |
| t1_hours_008 | when does shugrue's close | 1 | gap_template | DATE_LOOKUP |  | FAIL |
| edge_nm_004 | hour for d1 performance | 3 | 1 | HOURS_LOOKUP | D1 Performance (90) | FAIL |

**Detail:**

- `t1_hours_002` (FAIL): 'hours for mudshark brewing'
  - expected=1 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_hours_003` (FAIL): 'when is altitude open'
  - expected=1 observed=gap_template mode=ask sub=DATE_LOOKUP
  - response shape: gap template for DATE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: 'when' might match DATE_LOOKUP first. Order risk.
- `t1_hours_004` (FAIL): 'business hours for iron wolf golf'
  - expected=1 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_hours_005` (note): 'hours on saturday for the foundry'
  - expected=1 observed=1 mode=ask sub=HOURS_LOOKUP
  - response shape: Tier 1 template for HOURS_LOOKUP, entity='Foundry'
  - note: Day-aware variant — tests _hours_focus_for_weekday for Google providers.
- `t1_hours_006` (FAIL): 'what hours is the tap room'
  - expected=1 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_hours_007` (FAIL): "hours of operation for sloane's"
  - expected=1 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_hours_008` (FAIL): "when does shugrue's close"
  - expected=1 observed=gap_template mode=ask sub=DATE_LOOKUP
  - response shape: gap template for DATE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_nm_004` (FAIL): 'hour for d1 performance'
  - expected=3 observed=1 mode=ask sub=HOURS_LOOKUP
  - response shape: Tier 1 template for HOURS_LOOKUP, entity='D1 Performance'
  - note: 'hour' singular not in HOURS_LOOKUP regex. FLAG: regex too strict.

## factual_hours_day (2 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_dayhrs_001 | hours for d1 performance on monday | 1 | 1 | HOURS_LOOKUP | D1 Performance (90) | PASS |
| t1_dayhrs_003 | hours for the foundry on saturday | 1 | 1 | HOURS_LOOKUP | Foundry (90) | PASS |

**Detail:**

- `t1_dayhrs_001` (note): 'hours for d1 performance on monday'
  - expected=1 observed=1 mode=ask sub=HOURS_LOOKUP
  - response shape: Tier 1 template for HOURS_LOOKUP, entity='D1 Performance'
  - note: Tests _hours_focus_for_weekday over google_hours.weekdayDescriptions.

## factual_open_ended (2 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_nm_008 | mudshark | 3 | 3 | OPEN_ENDED |  | PASS |
| edge_nm_009 | d1 | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `edge_nm_008` (note): 'mudshark'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Just an entity name with no question. No Tier 1 intent matches.

## factual_open_now (9 cases, 4 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_open_001 | is d1 performance open right now | 1 | 1 | OPEN_NOW | D1 Performance (90) | PASS |
| t1_open_002 | is mudshark brewing open now | 1 | gap_template | OPEN_NOW |  | FAIL |
| t1_open_003 | are they open at altitude trampoline | 1 | 3 | OPEN_ENDED |  | FAIL |
| t1_open_004 | can I go to iron wolf right now | 3 | 3 | OPEN_ENDED |  | PASS |
| t1_open_005 | is the foundry open at the moment | 1 | 1 | OPEN_NOW | Foundry (90) | PASS |
| t1_open_006 | is havasu lanes currently open | 1 | 1 | OPEN_NOW | Havasu (90) | PASS |
| t1_open_007 | is the tap room open | 3 | gap_template | OPEN_NOW |  | FAIL |
| t1_open_008 | are you open now at sloane's | 1 | gap_template | OPEN_NOW |  | FAIL |
| t1_dayhrs_002 | is mudshark open on sundays | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `t1_open_001` (note): 'is d1 performance open right now'
  - expected=1 observed=1 mode=ask sub=OPEN_NOW
  - response shape: Tier 1 template for OPEN_NOW, entity='D1 Performance'
  - note: Current template wording is sterile ('outside today's posted window'). FLAG.
- `t1_open_002` (FAIL): 'is mudshark brewing open now'
  - expected=1 observed=gap_template mode=ask sub=OPEN_NOW
  - response shape: gap template for OPEN_NOW: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_open_003` (FAIL): 'are they open at altitude trampoline'
  - expected=1 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
- `t1_open_004` (note): 'can I go to iron wolf right now'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Doesn't match OPEN_NOW or HOURS_LOOKUP regex. Falls through.
- `t1_open_007` (FAIL): 'is the tap room open'
  - expected=3 observed=gap_template mode=ask sub=OPEN_NOW
  - response shape: gap template for OPEN_NOW: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Bare 'open' without 'now/right now/currently' falls to OPEN_ENDED. Coverage gap.
- `t1_open_008` (FAIL): "are you open now at sloane's"
  - expected=1 observed=gap_template mode=ask sub=OPEN_NOW
  - response shape: gap template for OPEN_NOW: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_dayhrs_002` (note): 'is mudshark open on sundays'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Day name + 'open on'. Currently OPEN_NOW disambig matches 'open'. Boundary case.

## factual_phone (14 cases, 7 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_phone_001 | phone number for d1 performance | 1 | 1 | PHONE_LOOKUP | D1 Performance (90) | PASS |
| t1_phone_002 | what's the phone for mudshark brewing | 1 | gap_template | PHONE_LOOKUP |  | FAIL |
| t1_phone_003 | contact number for altitude trampoline park | 1 | 1 | PHONE_LOOKUP | Altitude Trampoline Park (90) | PASS |
| t1_phone_004 | I need to call iron wolf golf | 1 | 3 | OPEN_ENDED |  | FAIL |
| t1_phone_005 | phone for the foundry | 1 | 1 | PHONE_LOOKUP | Foundry (90) | PASS |
| t1_phone_006 | how do I reach havasu lanes | 1 | 1 | PHONE_LOOKUP | Havasu (90) | PASS |
| t1_phone_007 | number for the tap room | 1 | gap_template | PHONE_LOOKUP |  | FAIL |
| t1_phone_008 | phone number for sloane's | 1 | gap_template | PHONE_LOOKUP |  | FAIL |
| t1_phone_009 | call number for shugrue's | 1 | gap_template | PHONE_LOOKUP |  | FAIL |
| t1_phone_010 | contact for turtle beach bar | 1 | 1 | PHONE_LOOKUP | Turtle Beach Bar (90) | PASS |
| edge_nm_001 | PHONE NUMBER FOR D1 PERFORMANCE | 1 | 1 | PHONE_LOOKUP | D1 Performance (90) | PASS |
| edge_nm_002 | phone number for D1 performance!!! | 1 | 1 | PHONE_LOOKUP | D1 Performance (90) | PASS |
| edge_nm_003 | phone number for d-1 performance | 1 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_nm_005 | pone number for d1 | 3 | gap_template | PHONE_LOOKUP |  | FAIL |

**Detail:**

- `t1_phone_002` (FAIL): "what's the phone for mudshark brewing"
  - expected=1 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_phone_004` (FAIL): 'I need to call iron wolf golf'
  - expected=1 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
- `t1_phone_006` (note): 'how do I reach havasu lanes'
  - expected=1 observed=1 mode=ask sub=PHONE_LOOKUP
  - response shape: Tier 1 template for PHONE_LOOKUP, entity='Havasu'
  - note: verb 'reach' isn't in PHONE_LOOKUP regex — likely falls through to OPEN_ENDED. Surfaces a regex gap.
- `t1_phone_007` (FAIL): 'number for the tap room'
  - expected=1 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_phone_008` (FAIL): "phone number for sloane's"
  - expected=1 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_phone_009` (FAIL): "call number for shugrue's"
  - expected=1 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_phone_010` (note): 'contact for turtle beach bar'
  - expected=1 observed=1 mode=ask sub=PHONE_LOOKUP
  - response shape: Tier 1 template for PHONE_LOOKUP, entity='Turtle Beach Bar'
  - note: 'contact' alone may not match PHONE_LOOKUP regex (`phone number|phone|contact number|call them|number`).
- `edge_nm_003` (FAIL): 'phone number for d-1 performance'
  - expected=1 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_nm_005` (FAIL): 'pone number for d1'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Typo in 'phone'. Tests fuzzy resilience (currently doesn't have).

## factual_rating (7 cases, 3 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_rating_001 | what is the rating for d1 performance | 1 | 1 | RATING_LOOKUP | D1 Performance (90) | PASS |
| t1_rating_002 | how is mudshark brewing rated | 1 | gap_template | RATING_LOOKUP |  | FAIL |
| t1_rating_003 | star rating for the foundry | 1 | 1 | RATING_LOOKUP | Foundry (90) | PASS |
| t1_rating_004 | how are the reviews for sloane's | 1 | gap_template | RATING_LOOKUP |  | FAIL |
| t1_rating_005 | how many stars does shugrue's have on google | 1 | gap_template | RATING_LOOKUP |  | FAIL |
| t1_rating_006 | is turtle beach bar any good | 1 | 1 | RATING_LOOKUP | Turtle Beach Bar (90) | PASS |
| edge_nm_007 | rateing for foundry | 3 | 3 | OPEN_ENDED | Foundry (90) | PASS |

**Detail:**

- `t1_rating_002` (FAIL): 'how is mudshark brewing rated'
  - expected=1 observed=gap_template mode=ask sub=RATING_LOOKUP
  - response shape: gap template for RATING_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_rating_004` (FAIL): "how are the reviews for sloane's"
  - expected=1 observed=gap_template mode=ask sub=RATING_LOOKUP
  - response shape: gap template for RATING_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_rating_005` (FAIL): "how many stars does shugrue's have on google"
  - expected=1 observed=gap_template mode=ask sub=RATING_LOOKUP
  - response shape: gap template for RATING_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_nm_007` (note): 'rateing for foundry'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Typo. FLAG.

## factual_review_count (4 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_revc_001 | how many reviews does mudshark have | 1 | gap_template | REVIEW_COUNT_LOOKUP |  | FAIL |
| t1_revc_002 | number of reviews for the foundry | 1 | 1 | REVIEW_COUNT_LOOKUP | Foundry (90) | PASS |
| t1_revc_003 | review count for d1 performance | 1 | 1 | REVIEW_COUNT_LOOKUP | D1 Performance (90) | PASS |
| t1_revc_004 | how many people reviewed altitude trampoline | 1 | gap_template | REVIEW_COUNT_LOOKUP |  | FAIL |

**Detail:**

- `t1_revc_001` (FAIL): 'how many reviews does mudshark have'
  - expected=1 observed=gap_template mode=ask sub=REVIEW_COUNT_LOOKUP
  - response shape: gap template for REVIEW_COUNT_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_revc_004` (FAIL): 'how many people reviewed altitude trampoline'
  - expected=1 observed=gap_template mode=ask sub=REVIEW_COUNT_LOOKUP
  - response shape: gap template for REVIEW_COUNT_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## factual_time (2 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_time_001 | what time does bmx start saturday | 1 | gap_template | TIME_LOOKUP |  | FAIL |
| t1_time_002 | opening time for the aquatic center | 1 | gap_template | TIME_LOOKUP |  | FAIL |

**Detail:**

- `t1_time_001` (FAIL): 'what time does bmx start saturday'
  - expected=1 observed=gap_template mode=ask sub=TIME_LOOKUP
  - response shape: gap template for TIME_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_time_002` (FAIL): 'opening time for the aquatic center'
  - expected=1 observed=gap_template mode=ask sub=TIME_LOOKUP
  - response shape: gap template for TIME_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## factual_website (8 cases, 5 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t1_web_001 | website for d1 performance | 1 | 1 | WEBSITE_LOOKUP | D1 Performance (90) | PASS |
| t1_web_002 | url for mudshark brewing | 1 | gap_template | WEBSITE_LOOKUP |  | FAIL |
| t1_web_003 | site for altitude | 1 | gap_template | WEBSITE_LOOKUP |  | FAIL |
| t1_web_004 | web address for iron wolf | 1 | gap_template | WEBSITE_LOOKUP |  | FAIL |
| t1_web_005 | do you have a website for the foundry | 1 | 1 | WEBSITE_LOOKUP | Foundry (90) | PASS |
| t1_web_006 | link for havasu lanes | 3 | 1 | WEBSITE_LOOKUP | Havasu (90) | FAIL |
| t1_web_007 | website for ballet havasu | 1 | 1 | WEBSITE_LOOKUP | Havasu (90) | PASS |
| t1_web_008 | site for flips for fun gymnastics | 1 | gap_template | WEBSITE_LOOKUP |  | FAIL |

**Detail:**

- `t1_web_002` (FAIL): 'url for mudshark brewing'
  - expected=1 observed=gap_template mode=ask sub=WEBSITE_LOOKUP
  - response shape: gap template for WEBSITE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_web_003` (FAIL): 'site for altitude'
  - expected=1 observed=gap_template mode=ask sub=WEBSITE_LOOKUP
  - response shape: gap template for WEBSITE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_web_004` (FAIL): 'web address for iron wolf'
  - expected=1 observed=gap_template mode=ask sub=WEBSITE_LOOKUP
  - response shape: gap template for WEBSITE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t1_web_006` (FAIL): 'link for havasu lanes'
  - expected=3 observed=1 mode=ask sub=WEBSITE_LOOKUP
  - response shape: Tier 1 template for WEBSITE_LOOKUP, entity='Havasu'
  - note: 'link' isn't in WEBSITE_LOOKUP regex (`website|site|url|web address`). Falls through.
- `t1_web_008` (FAIL): 'site for flips for fun gymnastics'
  - expected=1 observed=gap_template mode=ask sub=WEBSITE_LOOKUP
  - response shape: gap template for WEBSITE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'

## followup_pronoun (5 cases, 4 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_follow_001 | how about their hours | 3 | gap_template | HOURS_LOOKUP |  | FAIL |
| conv_follow_002 | and the phone | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| conv_follow_003 | any others | 3 | 2 | OPEN_ENDED |  | FAIL |
| conv_follow_004 | that's it | chat | 3 | OPEN_ENDED |  | FAIL |
| conv_follow_005 | tell me more | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `conv_follow_001` (FAIL): 'how about their hours'
  - expected=3 observed=gap_template mode=ask sub=HOURS_LOOKUP
  - response shape: gap template for HOURS_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: No prior context in test (single-turn). With session, would resolve via _prior_entity_fresh.
- `conv_follow_002` (FAIL): 'and the phone'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `conv_follow_003` (FAIL): 'any others'
  - expected=3 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='others', deterministic 5-bullet renderer
- `conv_follow_004` (FAIL): "that's it"
  - expected=chat observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Ends like small talk.

## gap_factual (10 cases, 6 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_gap_001 | phone number for fake business that does not exist | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_gap_002 | address for nonexistent shop xyz | gap_template | gap_template | LOCATION_LOOKUP |  | PASS |
| edge_gap_003 | hours for imaginary cafe | gap_template | gap_template | HOURS_LOOKUP |  | PASS |
| edge_gap_004 | when is the made-up festival | gap_template | gap_template | DATE_LOOKUP |  | PASS |
| edge_gap_005 | rating for a place not in your catalog | 3 | gap_template | RATING_LOOKUP |  | FAIL |
| edge_gap_006 | how many reviews for nonexistent biz | 3 | gap_template | REVIEW_COUNT_LOOKUP |  | FAIL |
| edge_gap_007 | website for some random thing | 3 | gap_template | WEBSITE_LOOKUP |  | FAIL |
| edge_gap_011 | phone number for foo bar baz | 3 | gap_template | PHONE_LOOKUP |  | FAIL |
| edge_gap_012 | where is the lake havasu space center | gap_template | 1 | LOCATION_LOOKUP | Havasu (90) | FAIL |
| edge_gap_013 | hours for shop that closed last year | gap_template | gap_template | HOURS_LOOKUP |  | PASS |

**Detail:**

- `edge_gap_001` (FAIL): 'phone number for fake business that does not exist'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: Should land on _catalog_gap_response — but PHONE_LOOKUP isn't in its allowed list. Currently falls to Tier 3.
- `edge_gap_002` (note): 'address for nonexistent shop xyz'
  - expected=gap_template observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: LOCATION_LOOKUP is in gap-template list.
- `edge_gap_004` (note): 'when is the made-up festival'
  - expected=gap_template observed=gap_template mode=ask sub=DATE_LOOKUP
  - response shape: gap template for DATE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: DATE_LOOKUP gap path.
- `edge_gap_005` (FAIL): 'rating for a place not in your catalog'
  - expected=3 observed=gap_template mode=ask sub=RATING_LOOKUP
  - response shape: gap template for RATING_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: RATING_LOOKUP not in gap-template list. FLAG: should be.
- `edge_gap_006` (FAIL): 'how many reviews for nonexistent biz'
  - expected=3 observed=gap_template mode=ask sub=REVIEW_COUNT_LOOKUP
  - response shape: gap template for REVIEW_COUNT_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: REVIEW_COUNT_LOOKUP not in gap-template list. FLAG.
- `edge_gap_007` (FAIL): 'website for some random thing'
  - expected=3 observed=gap_template mode=ask sub=WEBSITE_LOOKUP
  - response shape: gap template for WEBSITE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
  - note: WEBSITE_LOOKUP not in gap-template list. FLAG.
- `edge_gap_011` (FAIL): 'phone number for foo bar baz'
  - expected=3 observed=gap_template mode=ask sub=PHONE_LOOKUP
  - response shape: gap template for PHONE_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `edge_gap_012` (FAIL): 'where is the lake havasu space center'
  - expected=gap_template observed=1 mode=ask sub=LOCATION_LOOKUP
  - response shape: Tier 1 template for LOCATION_LOOKUP, entity='Havasu'

## gap_listing (5 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_gap_008 | find me a tea ceremony venue | 2 | 2 | OPEN_ENDED |  | PASS |
| edge_gap_009 | find me a unicorn rental | 2 | chat | OUT_OF_SCOPE |  | FAIL |
| edge_gap_010 | any good escape rooms | 2 | 2 | OPEN_ENDED |  | PASS |
| edge_gap_014 | any indoor skydiving in lhc | 2 | 2 | OPEN_ENDED |  | PASS |
| edge_gap_015 | pottery class for adults | 2 | 3 | OPEN_ENDED |  | FAIL |

**Detail:**

- `edge_gap_008` (note): 'find me a tea ceremony venue'
  - expected=2 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='tea ceremony venue', deterministic 5-bullet renderer
  - note: Shortcut hits, no rows match → falls through to Tier 3 LLM.
- `edge_gap_009` (FAIL): 'find me a unicorn rental'
  - expected=2 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'
- `edge_gap_015` (FAIL): 'pottery class for adults'
  - expected=2 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)

## greeting (5 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_greet_001 | hi | chat | chat | GREETING |  | PASS |
| conv_greet_002 | hey there | chat | chat | GREETING |  | PASS |
| conv_greet_003 | hello | chat | chat | GREETING |  | PASS |
| conv_greet_004 | good morning | chat | chat | GREETING |  | PASS |
| conv_greet_005 | yo | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `conv_greet_005` (note): 'yo'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: 'yo' isn't in _GREETING_ONLY regex. FLAG: greeting coverage.

## listing_business (20 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t2_biz_001 | find me a barber in LHC | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_002 | any good coffee shops | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_003 | where can I get a haircut | 2 | 2 | LOCATION_LOOKUP |  | PASS |
| t2_biz_004 | find me a coffee shop near me | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_005 | any good mexican food | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_006 | find a pizza place | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_007 | show me bars | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_008 | any auto shops in town | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_009 | find me a gym | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_010 | where can I find a nail salon | 2 | 2 | LOCATION_LOOKUP |  | PASS |
| t2_biz_011 | list of dentists | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_012 | any good restaurants | 3 | 2 | OPEN_ENDED |  | FAIL |
| t2_biz_013 | best place to eat | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_biz_014 | any good bars in lake havasu | 2 | 2 | OPEN_ENDED | Havasu (90) | PASS |
| t2_biz_015 | where's a good plumber | 2 | 2 | LOCATION_LOOKUP |  | PASS |
| t2_biz_016 | find me an electrician | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_017 | show me coffee shops in LHC | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_018 | any vet near me | 2 | 2 | OPEN_ENDED |  | PASS |
| t2_biz_019 | where can I find a chiropractor | 2 | 2 | LOCATION_LOOKUP |  | PASS |
| t2_biz_020 | find a real estate agent | 2 | chat | OUT_OF_SCOPE |  | FAIL |

**Detail:**

- `t2_biz_005` (note): 'any good mexican food'
  - expected=2 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='mexican food', deterministic 5-bullet renderer
  - note: 'mexican food' should match. Tests category w/ multiple words + Google taxonomy.
- `t2_biz_012` (FAIL): 'any good restaurants'
  - expected=3 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='restaurants', deterministic 5-bullet renderer
  - note: 'restaurant' triggers OUT_OF_SCOPE in app/core/intent.py. Surfaces a stale OOS rule that should be relaxed now that we have business catalog.
- `t2_biz_013` (note): 'best place to eat'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: OOS dining trigger. Same flag as t2_biz_012.
- `t2_biz_020` (FAIL): 'find a real estate agent'
  - expected=2 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'

## listing_events (10 cases, 2 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t2_evt_001 | what events are coming up this weekend | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_002 | anything happening tonight | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_003 | events for kids this weekend | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_004 | things to do saturday | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_005 | what's going on next week | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_006 | any concerts coming up | 3 | 2 | OPEN_ENDED |  | FAIL |
| t2_evt_007 | events in june | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_008 | any festivals this month | 3 | 2 | OPEN_ENDED |  | FAIL |
| t2_evt_009 | family events this weekend | 3 | 3 | OPEN_ENDED |  | PASS |
| t2_evt_010 | free events near me | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `t2_evt_001` (note): 'what events are coming up this weekend'
  - expected=3 observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: Tier 2 LLM parser path (events). Will spend tokens. Surface in report.
- `t2_evt_006` (FAIL): 'any concerts coming up'
  - expected=3 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='concerts coming up', deterministic 5-bullet renderer
- `t2_evt_008` (FAIL): 'any festivals this month'
  - expected=3 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='festivals this month', deterministic 5-bullet renderer

## oos_lodging (1 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_oos_002 | hotel recommendations near the lake | chat | chat | OUT_OF_SCOPE |  | PASS |

## oos_realestate (1 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_oos_004 | where should I buy a house | chat | chat | OUT_OF_SCOPE |  | PASS |

## oos_transportation (2 cases, 1 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_oos_003 | how do I get to the foundry | chat | 3 | OPEN_ENDED | Foundry (90) | FAIL |
| edge_oos_005 | rent a car in havasu | chat | chat | OUT_OF_SCOPE |  | PASS |

**Detail:**

- `edge_oos_003` (FAIL): 'how do I get to the foundry'
  - expected=chat observed=3 mode=ask sub=OPEN_ENDED
  - response shape: Tier 3 Haiku synthesis (would call LLM)
  - note: 'how do I get to' triggers transportation OOS. Test routing.

## oos_weather (1 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| edge_oos_001 | what's the weather this weekend | chat | chat | OUT_OF_SCOPE |  | PASS |

## small_talk (5 cases, 0 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| conv_smal_001 | thanks | chat | chat | SMALL_TALK |  | PASS |
| conv_smal_002 | thank you | chat | chat | SMALL_TALK |  | PASS |
| conv_smal_003 | appreciate it | chat | chat | SMALL_TALK |  | PASS |
| conv_smal_004 | how are you | chat | chat | SMALL_TALK |  | PASS |
| conv_smal_005 | bye | chat | chat | SMALL_TALK |  | PASS |

## synthesis_multi (10 cases, 3 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t3_multi_001 | kid friendly restaurant open tonight | 3 | gap_template | OPEN_NOW |  | FAIL |
| t3_multi_002 | gym with childcare on saturdays | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_003 | cheap coffee shop with wifi | 3 | chat | OUT_OF_SCOPE |  | FAIL |
| t3_multi_004 | outdoor event tomorrow afternoon for kids under 10 | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_005 | late night food open after 10pm | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_006 | free thing to do with toddlers in the morning | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_007 | cheap haircut place open on sundays | 3 | chat | OUT_OF_SCOPE |  | FAIL |
| t3_multi_008 | dinner spot with patio and live music | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_009 | workout class for someone over 60 | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_multi_010 | family friendly restaurant under 20 dollars per person | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `t3_multi_001` (FAIL): 'kid friendly restaurant open tonight'
  - expected=3 observed=gap_template mode=ask sub=OPEN_NOW
  - response shape: gap template for OPEN_NOW: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_multi_003` (FAIL): 'cheap coffee shop with wifi'
  - expected=3 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'
- `t3_multi_007` (FAIL): 'cheap haircut place open on sundays'
  - expected=3 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'

## synthesis_rec (30 cases, 8 FAIL)

| id | query | expected | observed | sub_intent | entity | verdict |
|---|---|---|---|---|---|---|
| t3_rec_001 | where's a good place for date night | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_002 | what should I do with kids this weekend | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_003 | best place for happy hour | 3 | 3 | HOURS_LOOKUP |  | PASS |
| t3_rec_004 | what's worth doing this weekend | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_005 | where would you eat tonight | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_006 | what would you recommend for a first time visitor | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_007 | best activity for a hot summer day | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_008 | i need an activity for my 8 year old after school | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_009 | what's the best place to watch the sunset | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_010 | where do locals go for breakfast | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_011 | what's a good morning activity | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_012 | pick something for me to do today | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_013 | compare mudshark and the foundry | 3 | 3 | OPEN_ENDED | Foundry (90) | PASS |
| t3_rec_014 | which is better — bridge city or tap room jiu jitsu | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_015 | what's the difference between altitude and sonics | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_016 | i'm visiting for two days, what should I do | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_017 | tell me about lake havasu | 3 | 3 | OPEN_ENDED | Havasu (90) | PASS |
| t3_rec_018 | what kind of stuff is there to do here | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_019 | any local secrets | 3 | 2 | OPEN_ENDED |  | FAIL |
| t3_rec_020 | what's lake havasu known for | 3 | 3 | OPEN_ENDED | Havasu (90) | PASS |
| t3_rec_021 | best things to do on the lake | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_022 | where do you go on a slow tuesday | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_023 | i'm bored, suggest something | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_024 | what would you do with a free afternoon | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_025 | best kid friendly restaurant | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_026 | where should we go for our anniversary dinner | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_027 | any cool spots for a coffee meeting | 3 | 3 | OPEN_ENDED |  | PASS |
| t3_rec_028 | what's a good rainy day activity | 3 | chat | OUT_OF_SCOPE |  | FAIL |
| t3_rec_029 | where to take out of town friends | 3 | gap_template | LOCATION_LOOKUP |  | FAIL |
| t3_rec_030 | pick a workout class for someone new to fitness | 3 | 3 | OPEN_ENDED |  | PASS |

**Detail:**

- `t3_rec_001` (FAIL): "where's a good place for date night"
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_rec_005` (FAIL): 'where would you eat tonight'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_rec_010` (FAIL): 'where do locals go for breakfast'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_rec_019` (FAIL): 'any local secrets'
  - expected=3 observed=2 mode=ask sub=OPEN_ENDED
  - response shape: Tier 2 listing — category='local secrets', deterministic 5-bullet renderer
- `t3_rec_022` (FAIL): 'where do you go on a slow tuesday'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_rec_026` (FAIL): 'where should we go for our anniversary dinner'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
- `t3_rec_028` (FAIL): "what's a good rainy day activity"
  - expected=3 observed=chat mode=chat sub=OUT_OF_SCOPE
  - response shape: OOS reply: 'outside what I cover'
- `t3_rec_029` (FAIL): 'where to take out of town friends'
  - expected=3 observed=gap_template mode=ask sub=LOCATION_LOOKUP
  - response shape: gap template for LOCATION_LOOKUP: 'I don't have ... in the catalog yet. Add it at /contribute ...'
