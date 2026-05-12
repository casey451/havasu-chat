# ChatGPT Prompt — Phase 3 District Paragraphs (V1 draft)

> Paste the block below into a fresh ChatGPT chat. ChatGPT returns drafts; Casey reviews + polishes the local-knowledge specifics; finals land in the `districts` table when Phase 3 ships (master plan §4 Phase 3 + design locked at session-15 commit `ec84eb4` as V1/V1.5/V2 hybrid).
>
> Voice anchor: Opus README.md §2.4 samples (lines 59 + 61 of `outputs/opus_design_handoff/README.md`). Two paragraphs Opus wrote in the target voice.

---

```
You're helping draft hyperlocal "district paragraph" copy for a Lake
Havasu City, Arizona local directory + AI chat product called Havasu
Chat. Each named district in Havasu gets ONE paragraph stored in a
districts table. That paragraph then renders on every business profile
in that district. The paragraph is the hyperlocal moat — it's
uncopyable by national platforms because the seasonal/snowbird/
local-traffic patterns only exist in a few US cities.

THE VOICE — match this exactly:

Sample 1 (English Village):
"English Village fills up after 5pm Fri–Sun — parking lots near the
bridge get tight by 6. Walkable to the lighthouse loop and three bars
next door. Snowbird-heavy crowd Nov–March."

Sample 2 (Downtown / Main Street, south of bridge):
"The main strip running south from the bridge — busy after work and
on weekends. Parking is easier than English Village. Heavy snowbird
crowd Nov–March; tourist crowd thins after spring break."

VOICE RULES — hold to these strictly:
- 2-4 sentences per paragraph. Compact.
- Specific timing details. Real numbers ("5pm Fri-Sun," "by 6,"
  "Nov-March"). No vague hand-waves ("evenings," "winter months").
- Practical + sensory framing: parking, walkability, crowd
  composition, when it fills up, when it dies down.
- Seasonal beat — snowbird (Nov-March) vs tourist (spring break,
  summer) vs local-only timing. Lake Havasu has a very distinct
  seasonal rhythm; honor that.
- NO marketing language. Ban these words/phrases: "vibrant,"
  "thriving," "bustling," "experience," "destination," "perfect,"
  "stunning," "charming," "hidden gem," "must-visit." If you find
  yourself reaching for one, find a concrete fact instead.
- NO exclamation points anywhere.
- Em-dashes are good (the voice samples use them heavily).
- Reader assumed to know Havasu basics (knows what the London Bridge
  is, knows the lake is there). Don't explain those.
- Speak from local-knowledge perspective. NOT a chamber-of-commerce
  pitch. NOT a tourism brochure.

DELIVERABLE: One paragraph per district from this list. Output as
markdown — district name as `### Heading`, paragraph below.

The district list (10 districts; aim for 2-4 sentences each):

1. **English Village** — at the foot of the London Bridge, bridge-end
   shops + restaurants + boat-tour kiosks. (Sample 1 above is from
   Opus; rewrite/refine if you think you can improve it, but keep
   the same factual anchors.)
2. **Downtown / Main Street** — the strip running south from the
   bridge, mix of restaurants + retail + local services. (Sample 2
   above is from Opus; same instruction — rewrite/refine if you can.)
3. **North End** — north side of town, residential-feeling, with
   some commercial along Highway 95.
4. **Lakefront** — properties + businesses directly along the
   western lake-facing strip outside English Village.
5. **Mesquite Bay** — bay area on the south side, marinas + boat-
   adjacent businesses.
6. **Highway 95 Corridor** — the main north-south artery through
   town, big-box retail + auto + chains.
7. **Site Six** — boat ramp + park area on the south side of town,
   launch point for many on-the-water activities.
8. **Pittsburgh Point** — peninsula area, known for [CASEY: confirm
   primary use — residential? recreational? bridge of access?].
9. **Castle Rock area** — north-end neighborhood + landmark.
10. **South side** — south of the airport / outside the main commercial
    core, more residential-feeling.

INSTRUCTIONS FOR YOU:

(a) Write each paragraph as if you're a local who's lived in Havasu
    long enough to know the timing patterns. If you don't have
    confident specifics about a district (especially Pittsburgh Point
    + Castle Rock + South side, which are less famous than English
    Village + Downtown), mark the paragraph with [CASEY: this
    paragraph needs your local knowledge — I drafted what I could but
    flag any specifics that are wrong] at the end of that paragraph.
    Don't fabricate specifics.

(b) Some districts I gave you only a one-line hint. If a hint mentions
    [CASEY: confirm <X>], leave that placeholder INSIDE your draft
    paragraph for the operator to fill in.

(c) Maintain the voice rules above strictly. If you write something
    that sounds like a tourism brochure, rewrite it.

(d) After all 10 paragraphs, write a short "Casey to verify" section
    listing any specific facts you weren't sure about (e.g., "Mesquite
    Bay — I assumed it's south of English Village, please confirm").

(e) Don't add any preamble explaining what you're doing or the format
    requirements. Just give me the 10 markdown sections + the "Casey
    to verify" appendix.

Begin.
```

---

## After ChatGPT returns

Casey pastes ChatGPT's response back to the Cowork primary. Primary:

1. Strips any ChatGPT-appended tracking params (`?utm_source=chatgpt.com`) from URLs if any sneak in (gotcha #6 — unlikely here, district paragraphs don't typically need URLs)
2. Polishes markdown structure if needed (ChatGPT sometimes skips `#`/`##` headers)
3. Saves to `outputs/chatgpt_response_district_paragraphs_v1.md` (matches the existing `chatgpt_response_*_spec.md` naming convention in `outputs/`)
4. Surfaces the "Casey to verify" appendix + the `[CASEY: ...]` placeholders to Casey for filling in
5. Once Casey polishes the locals + fills in placeholders, the finals are ready for the Phase 3 districts-table backfill (each paragraph becomes a row in `districts.paragraph`)

## Workflow this fits into

Per master plan §4 Phase 3 operator workload: "Author 8-12 district paragraphs (~1 hour). Suggested districts: English Village, Downtown / Main Street, North End, Lakefront, Mesquite Bay, Highway 95 corridor, Site Six, Pittsburgh Point, Castle Rock area, South side. Each gets a one-paragraph description per Opus design samples."

Casey's effective time on this drops from ~1 hour to ~15-20 min if ChatGPT drafts the bulk and he edits/verifies + fills in the `[CASEY: ...]` placeholders. Net win for V1 launch readiness.

Phase 3 hasn't started yet — these drafts sit in `outputs/` until Phase 3 dispatches. Per dispatch_channels gotcha #12 (durable workspace `outputs/` artifacts), they'll persist across sessions.
