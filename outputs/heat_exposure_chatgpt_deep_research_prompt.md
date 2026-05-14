# ChatGPT Deep Research Prompt — heat_exposure priority-30 list validation

> **Operator:** paste the fenced block below into ChatGPT (deep research mode). It runs an
> independent pass over the same 30-venue list Cowork primary first-pass-filled in
> `outputs/heat_exposure_priority_30_list.md`. When ChatGPT returns, send the response back
> to the Cowork chat — we reconcile the two passes against your local knowledge and lock the
> final 30.
>
> **Why two passes:** Cowork's first pass is general web search (tourism/city/directory pages).
> ChatGPT deep research goes deeper and independently — the value is in the *disagreements*
> between the two passes, which is exactly where the operator's local knowledge gets applied.

---

```
You are doing deep research on Lake Havasu City, Arizona to validate a list of ~30 local
venues for a community directory app. The app has a "heat_exposure" tag on each venue that
drives summer heat-warning alerts, so tagging accuracy directly affects whether a venue shows
up in a "be careful in the heat today" advisory. I need you to verify and correct the list.

## The heat_exposure rubric (4 values)

- outdoor — venue's primary use is outdoors, no significant shade, full sun. Parks, sports
  fields, dog parks, open-air markets, courts.
- shaded — venue's primary use is outdoors but with persistent shade (ramadas, mature trees,
  covered patios usable in mid-day heat). The "outdoor but bearable in summer" tier.
- water_adjacent — venue is on/at the water; heat is moderated by water proximity, breezes,
  and swimming access. Marinas, beaches, lakeside restaurants, public boat ramps.
- indoor — the default; everything not on this list.

## What I need for EACH of the 30 entries below

1. Does this venue exist, and is it currently open/operating (2026)? If closed, renamed, or
   you can't confirm it, say so.
2. Exact name + street address (or GPS area if no street address).
3. Your recommended heat_exposure tag (outdoor / shaded / water_adjacent / indoor) with a
   one-line reason.
4. For entries flagged below with a QUESTION — answer the specific question.
5. Confidence: high / medium / low, and the source(s) you used.
6. Flag duplicates, venues that don't belong, or better candidates I'm missing.

## The draft list

OUTDOOR (full-sun):
1. SARA Park — large desert park (~1,100 acres), disc golf + dog park + trails. Confirm scale; confirm `outdoor` is the right dominant tag.
2. Rotary Community Park — QUESTION: this looks like a 40-acre WATERFRONT beach park on Thompson Bay with a swim area AND 16 shade-canopy picnic areas. Should it be `water_adjacent`, `shaded`, or `outdoor`? What's the dominant character?
3. SARA Park Disc Golf Course — confirm it exists at SARA Park.
4. Dylan's Dog Park at SARA Park — confirm; is it the largest LHC off-leash dog park?
5. Avalon Park dog park (1294 Avalon Ave) — QUESTION: does Avalon Park have enough shade (covered ramadas, shaded benches) that it should be `shaded` not `outdoor`?
6. Patrick A. Tinnell Memorial Sports Complex / Tinnell Memorial Skatepark — QUESTION: it's described as "lakefront" — is it genuinely water-adjacent, or is it a concrete skate facility that just happens to be near the lake? Which tag?
7. Lake Havasu City BMX — QUESTION: is there a standalone USA-BMX-sanctioned track separate from the Tinnell complex? Is there a separate pump track anywhere in LHC?
8. Lake Havasu High School tennis courts — confirm 8 outdoor courts, public access.
9. Mike Delaney Pickleball Complex at Dick Samp Memorial Park — confirm 16 outdoor courts.
10. Island Ball Fields — QUESTION: what is the canonical CITY softball/baseball field complex in LHC? Island Ball Fields, Rotary Park fields, Tinnell, or something else?
11. Lake Havasu Farmers Market — confirm current location + whether it's seasonal.
12. QUESTION: does Lake Havasu City have any dedicated OUTDOOR amphitheater / concert venue? (I've only found indoor/pool/club venues.) If yes, name it.

SHADED (outdoor but persistently shaded):
13. Jack Hardie Park — confirm it's a shade-heavy park (ramadas + covered playground) and NOT on the water.
14. Avalon Park — same venue as #5; confirm whether the park overall is shade-dominant.
15-17. QUESTION: name 2-4 Lake Havasu City restaurants with genuinely shaded outdoor patios
   (sail shades, mature trees, permanent covered structures) that are NOT on the water — i.e.
   patios usable in mid-day summer heat. Be specific and sourced.
18. QUESTION: is there a library or community-center patio in LHC that is a genuine shaded
   OUTDOOR destination (vs. an indoor building)? If not, say so.

WATER ADJACENT (on/at the water):
19. Lake Havasu State Park — confirm.
20. London Bridge Beach — confirm (ramadas, swim area, contains Lions Dog Park).
21. Site Six public boat ramp — confirm it's the free public ramp.
22. Pier 19 Bar & Grill — QUESTION: is this restaurant still open in 2026? It didn't appear
   in recent restaurant listings.
23. English Village / Bridgewater Channel restaurant cluster — confirm the roster of
   restaurants ON the channel by London Bridge. Candidates I found: Shugrue's, Makai Cafe,
   Barley Brothers, Javelina Cantina, The Heat Bar. Correct/complete this list.
24. Lake Havasu City Aquatic Center (100 Park Ave) — QUESTION: are its pools indoor or
   outdoor? That decides whether it's `water_adjacent` or `indoor`.
25. Cattail Cove State Park — confirm it exists; confirm roughly how far south of LHC it is
   (I believe ~15 miles, Parker direction).
26. Lake Havasu Marina — confirm (Island marina, ~1,000+ slips, public ramp).
27. Havasu Riviera Marina — confirm (newer marina, multi-lane ramp, fuel dock).
28. QUESTION: besides Site Six, Lake Havasu State Park, Lake Havasu Marina, and Havasu Riviera
   — is there a distinct OTHER public boat ramp in LHC worth listing? Name it or say there isn't.
29. QUESTION: name 1-2 BLM-land or informal lake-access points / beaches near LHC (within
   ~10 miles) that locals use but that aren't official parks.
30. QUESTION: name a notable lakeside / dock-and-dine restaurant in LHC that is DISTINCT from
   the English Village channel cluster in #23 (e.g. at a marina or farther down the lakeshore).

## Output format

Return a numbered list 1-30. For each: venue name, address, recommended heat_exposure tag +
reason, answer to any QUESTION, confidence, and source(s). At the end, add a "Corrections &
additions" section: anything in the draft that's wrong, closed, duplicated, or that you'd
swap for a better candidate. Cite sources throughout.
```

---

## Operator instructions

1. **Paste the fenced block** into ChatGPT with deep research / web browsing enabled.
2. **Send the full response** back to the Cowork chat.
3. Cowork reconciles ChatGPT's pass against its own first pass (in `heat_exposure_priority_30_list.md`)
   and against your local Lake Havasu knowledge — producing a final 30 with every `tag check`,
   `RECLASSIFY FLAG`, and `operator — left blank` row resolved.
4. You commit the locked list. That closes Phase 5.0 item B2-c.

---

*Authored by Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session (2026-05-14).
Lives at `outputs/heat_exposure_chatgpt_deep_research_prompt.md` — brand-new `outputs/` file,
safe under the parallel-chat scope lock. Companion to the Cowork first-pass fill in
`outputs/heat_exposure_priority_30_list.md`.*
