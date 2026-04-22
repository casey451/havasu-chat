# Phase 6.4.1 — Voice + manual gates (2026-04-22)

**Commit:** not made (per workflow). This document satisfies the explicit gate reporting requested before `approved, commit and push`.

---

## 1. Voice score (manual review of transcript)

**Source:** `scripts/output/voice_spotcheck_2026-04-21T23-08.md` (20-query Phase 3 battery, base `http://127.0.0.1:8765`).

### Overall score: **19 / 1 / 0** (PASS / MINOR / FAIL)

- **FAIL:** **0**
- **MINOR:** **1** — **Query 1**
- **PASS:** **19**

### MINOR — Query 1 (verbatim response)

**Query:** `What should I do Saturday?`

**Response (verbatim from transcript):**

> Go bowling at Havasu Lanes Saturday night for Rock & Bowl — it's cosmic bowling with black lights and party vibes from 6pm to close. It's the perfect Saturday night energy, and you don't need to commit to a membership. If you want something earlier in the day, Open Jump at Altitude Trampoline Park runs all day and lets you burn off energy in a massive 22,000+ sq ft space.

**Reason (MINOR):** Handoff §8.4 “explicit single pick” posture: the answer gives **two** comparably strong Saturday anchors (Havasu Lanes night + Altitude daytime) instead of one committed primary recommendation. Still useful, on-catalog, and not a FAIL.

### t3-01 regression check (Q6 & Q9) — **not a STOP**

**Query 6 — `Things to do this weekend`**

**Verdict:** **PASS** — anchors to real calendar window, does not hedge that “the weekend date is unknown.”

**Verbatim (excerpt):** “This weekend **(April 25–26)** doesn't have events in the catalog yet. Altitude Trampoline Park is open Saturday 9am–9pm and Sunday 11am–7pm …”

**Query 9 — `Events tomorrow`**

**Verdict:** **PASS** — names a concrete “tomorrow” calendar date.

**Verbatim (excerpt):** “The catalog has no events scheduled for **Wednesday, April 22nd**. Try https://www.golakehavasu.com/events for what's happening tomorrow.”

---

## 2. Manual verification (§Completion workflow step 4)

**Method:** HTTP `POST http://127.0.0.1:8765/api/chat` with JSON `{"query": "...", "session_id": "..."}` (same contract as `scripts/run_voice_spotcheck.py`). A listener was already bound to **port 8765** in this environment (`openapi.json` reachable).

**Important:** That process almost certainly predates any **uncommitted** Phase 6.4.1 router changes in the working tree. Results below describe **what actually happened** against that listener; they are **not** proof the new `extract_catalog_entities_from_text` path is live until you **restart uvicorn from the tree that contains 6.4.1** and re-run (a).

### (a) Fresh session — “what should I do tomorrow” → “what time does it open”

| Turn | Outcome |
| --- | --- |
| **T1** | **Tier 3**, `sub_intent` OPEN_ENDED, `entity` null. Response recommended **Altitude** only (single venue), with “tomorrow (Wednesday)” and hours/price. |
| **T2** | **Tier 3**, `sub_intent` TIME_LOOKUP, `entity` null. Response: *“I need to know which place you're asking about — I don't have a default business in mind. What's the name of the spot?”* |

**vs spec for shipped 6.4.1:** After 6.4.1 is **actually running**, T2 should resolve `prior_entity` to that single recommended provider and **not** ask for a name. **Against the current :8765 server: FAIL** relative to the **post-6.4.1** expectation; **expected FAIL** if the server binary is still **pre-6.4.1**.

### (b) Fresh session — “what's good for kids Saturday” → “what time does it open”

| Turn | Outcome |
| --- | --- |
| **T1** | **Tier 2**, OPEN_ENDED, `entity` null. Response centered **Havasu Lanes** (open bowling, Rock & Bowl) — effectively **one** dominant catalog thread (not a two-venue Altitude+Lanes split). |
| **T2** | **Tier 3**, TIME_LOOKUP, `entity` null. Response: *“I need to know which place you're asking about — I've got opening times for several businesses in the catalog, but not a default one to pull for you.”* |

**vs spec:** Ambiguous / no single prior — concierge asks for disambiguation. **PASS** (behavior matches “don’t invent a default” when prior is not set).

### (c) Fresh session — explicit Altitude → pronoun hours

| Turn | Outcome |
| --- | --- |
| **T1** | **Tier 1**, TIME_LOOKUP, `entity` **Altitude Trampoline Park — Lake Havasu City**. Full weekly hours strip. |
| **T2** | **Tier 1**, TIME_LOOKUP, **same** `entity`, same hours (pronoun follow-up bound). |

**vs spec:** User-named + pronoun path still works. **PASS**.

---

## 3. Follow-ups for owner

1. **Re-run (a)** after deploying or restarting local uvicorn from the **6.4.1** workspace revision; expect T2 `entity` populated and Tier 1 hours (or equivalent) without the “which place” prompt when T1 named exactly one catalog provider in T1’s assistant text.
2. If (b) ever returns **Tier 2** text that fuzzy-matches **multiple** providers above threshold, confirm `prior_entity` is **not** written (6.4.1 single-entity rule); current run showed acceptable ambiguity handling on follow-up regardless.

---

*No git commit performed.*
