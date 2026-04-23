# Phase 6.5 — Local Voice: Deferral Decision and Correct-and-Grow Plan

**Status:** Original Phase 6.5 spec deferred. Replaced with a correct-and-grow approach where local-voice content accumulates from production feedback rather than being written upfront.

**Decision date:** 2026-04-22

**Owner:** Casey

---

## 1. What Phase 6.5 originally was

Per `HAVA_CONCIERGE_HANDOFF.md` §5 Phase 6.5 and §2.7:

> "OWNER TASK. Owner writes 20–30 pieces of editorial knowledge (favorite sunset spot, which market is better, when the BMX race is actually worth it, etc.). Content structure: each piece is a tagged blurb with keywords for retrieval. Stored in `app/data/local_voice.py` as a list of dicts with `keywords`, `text`, `category`. Context builder matches on keywords and injects relevant blurbs into Tier 3 context."

And explicitly called out as owner territory (§2.7):

> "Writing the 20–30 local-voice editorial content pieces (opinions must come from the owner)"

The purpose was to give the app specifically local opinions that don't exist in the catalog — things like "Thursday's farmers market is better than Saturday's" or "the BMX race is the one thing locals actually show up for." Facts are in the catalog; opinions come from the owner.

---

## 2. Why the 30-blurb upfront approach was deferred

The original plan asked the owner to write 20–30 blurbs before launch. In conversation 2026-04-22, the owner proposed a different sequencing: defer the writing exercise, launch without populated blurbs, and write opinions in response to actual user queries post-launch — "when the app answers something in a way I don't love, write a blurb that fixes it, and build the profile from those corrections."

This approach was evaluated and accepted as genuinely better for several reasons:

1. **Real queries beat imagined ones.** Writing 30 blurbs cold requires guessing what users ask about. Post-launch feedback shows what actually matters and where the app's voice falls short.

2. **Corrections have tighter signal than freewrites.** "The app said X, should have said Y" is a concrete writing task. "Write an opinion about the BMX race" is vague — what angle? What context? Hard to do well from a blank page.

3. **Voice gaps are easier to find reactively than proactively.** Noticing a specific bad response is easier than auditing a blank space and asking "what's missing?"

4. **It matches the app's own philosophy.** Handoff §1a states: *"Havasu Chat is a community-grown local knowledge base where the shape of the database emerges from what residents and visitors actually ask about and contribute."* Growing the voice content from real traffic applies that same pattern to the voice layer.

5. **Ships sooner.** 30 blurbs is a real writing chunk. Deferring means Phase 6 closes now and Phase 8 (pre-launch hardening) starts immediately.

---

## 3. What the app's voice looks like at launch without populated blurbs

The app will have:

- Consistent voice (Phase 6.1 voice audit)
- Feedback signals (Phase 6.2 thumbs)
- Onboarding hints: visitor/local, kids y/n (Phase 6.3)
- Session memory: age, location hints, prior-entity recall (Phase 6.4)
- Recommended-entity capture for pronoun follow-ups (Phase 6.4.1)
- Date-anchored temporal answers (Phase 6.4 — t3-01 closed)

What the app will NOT have at launch:

- Specific Havasu opinions that only a local knows

Meaning: the app will answer like a well-briefed concierge but not like a neighbor. "Here are three things happening Saturday" rather than "skip the market, go to the BMX race — it's the one thing locals actually show up for."

This is a known tradeoff. The owner accepts it.

---

## 4. The correct-and-grow workflow (how blurbs get written post-launch)

Once launched, the workflow for adding local-voice content is:

1. **Owner reviews real responses.** This happens naturally through:
   - Casey using the app themselves
   - Reviewing thumbs-down feedback from Phase 6.2 signals
   - Friends/family/community members flagging responses that feel off

2. **When a response feels wrong or thin,** owner articulates what the response *should* have said. That "should have said" is a blurb draft.

3. **Owner adds the blurb to `app/data/local_voice.py`** with appropriate keywords, category, and any context_tags (see §5 for the data format).

4. **Deploy.** Next time a user asks something that triggers those keywords, the blurb is in Tier 3's context.

5. **Iterate.** Over weeks and months, the file grows from empty → 10 → 30 → 100+ entries, each one earning its place by being a response to real observed need.

---

## 5. The data structure (locked for when plumbing ships)

When the plumbing ships (see §6), entries in `app/data/local_voice.py` will follow this shape:

```python
LOCAL_VOICE = [
    {
        "id": "bmx_race_saturday",
        "keywords": ["bmx", "race", "saturday", "night", "kids", "family"],
        "category": "events",
        "text": "The Saturday night BMX race at Sara Park is the one thing locals actually show up for — get there by 6 if you want a spot on the bleachers.",
        "context_tags": ["kids_ok", "evening", "free", "weekly"],
        "season": "year_round",
    },
]
```

**Fields:**

- `id` (required): snake_case identifier. Used for logs, tests, debugging ("why did this blurb fire?").
- `keywords` (required): list of lowercase strings. Retrieval key — blurb fires when query contains any keyword. Include broad AND specific terms, plus synonyms. Typical count: 4-8 per blurb. These are the *vocabulary of user questions that should trigger this opinion*, not the vocabulary of the opinion itself.
- `category` (required): high-level bucket for filtering. Suggested set: `events`, `activities`, `places`, `seasons`, `visiting`, `family`, `practical`. Extensible — add categories as needed while writing.
- `text` (required): 1-3 sentences, follows handoff §8 voice rules (contractions, no filler, direct opinion, no follow-up questions).
- `context_tags` (optional): filters matching session hints from 6.3/6.4. Examples: `kids_ok`, `adults_only`, `visitor_friendly`, `local_focused`, `evening`, `morning`, `weekend`, `free`, `cheap`, `indoor`, `outdoor`. Omit if blurb is universally applicable.
- `season` (optional): `year_round` (default), `summer`, `winter`, `spring_fall`, `holiday`. Only specify if relevant.

**Deliberately omitted** (kept out for simplicity): confidence scores, provenance, expiration dates, display priority, author/last_updated timestamps. Git history + owner ownership cover what's needed.

---

## 6. Two options for handling the plumbing

There are two ways to handle the code side of Phase 6.5. The owner has NOT yet chosen between them (decision pending when the next chat resumes Phase 6.5 work).

### Option 1: Ship the plumbing now, empty (6.5-lite)

Create `app/data/local_voice.py` with an empty `LOCAL_VOICE = []` list, wire `context_builder.py` to read it and inject into Tier 3 context (handling empty-list gracefully — no "Local voice:" section is added when the list is empty or when nothing matches), add a system prompt mention, add tests.

**Pros:**
- Infrastructure is in place. Adding a blurb post-launch is a one-line edit, no Cursor session needed.
- Owner can add blurbs the moment they want to.
- Removes any future "I need to set up the feature before I can fix this response" friction.

**Cons:**
- ~2 hours of Cursor time for code we don't have content for yet.
- Tests and system prompt mention infrastructure for something currently unused.

**Estimated scope:** Small Cursor prompt. Would create:
- `app/data/local_voice.py` with empty list and schema docstring
- `context_builder.py` changes to read and inject
- System prompt addition explaining "Local voice:" section handling
- Tests: schema validation, empty-list handling, keyword matching, context injection format

### Option 2: Defer the plumbing entirely

Skip the code work for now. When the owner has their first blurb ready and wants to ship it, one larger Cursor session does both the plumbing AND the first batch of content at once.

**Pros:**
- No code in the repo for an unused feature.
- Plumbing gets built when there's real content to exercise it.

**Cons:**
- The first blurb can't ship without a full code session.
- Small cost: "see bad response → schedule Cursor session → then fix" vs "see bad response → edit local_voice.py → deploy."

**Estimated scope when it ships:** Slightly larger Cursor prompt than Option 1 — same code work plus initial content integration.

---

## 7. Recommendation (stated for future reference)

**Option 1** (ship the plumbing now, empty). Reasoning:

- The code cost is small (~2 hours of Cursor time).
- Removes any future friction between "owner wants to fix a response" and "owner can fix a response."
- Matches how other parts of the app are structured — infrastructure exists before content fills it (e.g., contributions table exists before anyone contributes, mention scanner exists before entries are promoted).
- Zero behavioral change at launch: empty list means no "Local voice:" injection happens, Tier 3 behavior is identical to not having the feature.

This is the recommendation but not the decision. Owner decides when 6.5 work resumes.

---

## 8. Relationship to Phase 8 and launch

Phase 8 (pre-launch hardening) is the gating work before soft launch. Phase 6.5 deferral means Phase 8 can start immediately after Phase 6.4.1 closes. The path to launch is:

1. ✅ Phase 6.1-6.4.1 — all code work shipped
2. ⏳ Phase 6.5 — decision pending (Option 1 plumbing, or Option 2 full defer)
3. ⏳ Phase 8 — pre-launch hardening (§5 Phase 8 in handoff)
4. ⏳ Soft launch

Phase 6.5 in either option does not block Phase 8 from starting. They can run in parallel if needed, though there's no reason to split attention.

**Post-launch, Phase 6.5 becomes ongoing work:** blurbs get written as corrections happen, not as a scheduled phase.

---

## 9. What a future Claude should do with this doc

If you're Claude in a future chat session reading this doc:

- **If the owner asks about Phase 6.5 or local voice:** The content here is the current state. Phase 6.5's original spec is deferred; correct-and-grow replaces it.

- **If the owner says "let's do 6.5":** Ask whether they want Option 1 (ship empty plumbing now) or Option 2 (full defer until first blurb). If Option 1, draft a small Cursor prompt for the plumbing work using the data structure in §5. If Option 2, note it and move on.

- **If the owner says "I noticed the app said something weird, here's what it should have said":** That's a blurb candidate. If the plumbing exists (Option 1 has shipped), walk them through adding an entry to `app/data/local_voice.py` using the schema in §5. If the plumbing doesn't exist yet (Option 2), suggest it's time to do the Option 1 work plus this first blurb.

- **If the owner asks "should I write the 30 blurbs now?":** No. That was the original plan and it was deferred. Correct-and-grow is the current approach.

- **Don't treat this as a failure mode.** Deferring 6.5 isn't a problem to solve. It's a deliberate product decision that makes sense given the app's community-grown philosophy. The app launches without populated local voice, and it's fine.

---

## 10. Handoff doc update

The main `HAVA_CONCIERGE_HANDOFF.md` §5 Phase 6.5 section should be updated to reference this doc. Suggested text to append to the §5 Phase 6.5 block:

> **Note (2026-04-22):** Phase 6.5 sequencing changed post-6.4.1. The 20-30 blurb upfront approach was deferred in favor of a correct-and-grow workflow. See `docs/PHASE_6_5_LOCAL_VOICE_HANDOFF.md` for the current plan, data structure, and plumbing options.

This update is a docs-only change and can ship in a standalone commit when convenient.
