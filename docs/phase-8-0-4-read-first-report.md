# Phase 8.0.4 — Voice/template fixes (read-first report)

**Date:** 2026-04-22  
**Scope:** Issue A (Q17 / OUT_OF_SCOPE trailing question), Issue B (London Bridge farmers market GOOD example in `prompts/system_prompt.txt`). Read-only; no code or prompt edits in this pass.

---

## Pre-flight (raw)

### 1. `git log --oneline -5`

```text
18c2bb8 Phase 8.0.3: mountain-bike retrieval tuning (entity matcher)
2c64fe9 Phase 8.0.2: router-level explicit-rec bypass (§8.4 Option 3)
5335447 docs: Phase 8.0.2 read-first report
0e7708f Phase 8.0.1.6: gitignore Cursor handback and pre-flight-stop reports
8d48eed Phase 8.0.1.5: archive Phase 6 + 8.0.1 process artifacts, gitignore chat-export prompts
```

**HEAD:** `18c2bb8` — **PASS** (matches prompt).

### 2. `git status`

```text
On branch main
Your branch is up to date with 'origin/main'.

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/phase-9-scoping-notes-2026-04-22.md

nothing added to commit but untracked files present (use "git add" to track)
```

**PASS** (only optional owner file untracked).

### 3. `.\.venv\Scripts\python.exe -m pytest -q`

```text
753 passed, 3 subtests passed in 446.30s (0:07:26)
```

**PASS** (753 tests).

---

## 1. Q17 / OUT_OF_SCOPE template — where it lives

### Primary location (unified concierge)

**File:** `app/chat/unified_router.py`  
**Lines:** `_OUT_OF_SCOPE_REPLY` tuple at **62–65** (joined into one string for chat mode).

**Full template text (verbatim):**

```text
That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?
```

**Selection / rendering:** `_handle_chat()` uses `intent_result.sub_intent == "OUT_OF_SCOPE"` branch and returns `_OUT_OF_SCOPE_REPLY` unchanged (`unified_router.py` ~154–155 in current tree). No conditional branches that add or omit the trailing sentence — **single static string**.

### Other app hits

- **`grep`** across `app/` for `Want me to point` / `outside what I cover`: **only** `app/chat/unified_router.py` (no `router.py` legacy copy, no `conversation_copy.py` duplicate in this repo snapshot).

### Triage cross-check (Q17)

`docs/phase-8-0-1-triage-report.md` **Item 3** documents `"Boat rentals on the lake?"` → `mode: chat`, `sub_intent: OUT_OF_SCOPE`, response ending with the same template (including **Want me to…**).

---

## 2. §3.9 vs §8.7 / §8.2 — handoff text (verbatim excerpts)

**Source file:** `HAVASU_CHAT_CONCIERGE_HANDOFF.md` (repo root).

### §3.9 Voice consistency (lines 487–497)

```text
### 3.9 Voice consistency

All tiers and all modes produce responses that are:

- 1–3 sentences (max 150 tokens on LLM)
- Contractions always ("it's", "they're", "what's")
- No filler ("Certainly", "Absolutely", "I'd be happy to")
- No follow-up questions unless the turn is intake or correction (where a question is the explicit next step)
- Direct answer, then stop
- Community-credit provenance when relevant (section 2.1)
- Light opinion default, stronger when asked (section 2.2)

Users must not be able to tell which tier answered.
```

**Observation:** Chat mode **OUT_OF_SCOPE** is **not** listed as an exception to the “no follow-up questions” bullet.

### §8.2 Hard rules (lines 1227–1234)

```text
### 8.2 Hard rules

- **1–3 sentences.** No exceptions except multi-option lists (which should still be tight).
- **Contractions always.** "It's," "they're," "what's," "there's."
- **No filler.** Never start with "Certainly," "Absolutely," "Great question," "I'd be happy to," "Let me help you," "Sure thing."
- **No self-reference to being an AI.** Never say "as an AI," "I'm a chatbot," "I don't have access to," etc.
- **No follow-up questions** unless in intake or correction flow (where the next question is the explicit point).
- **No "I don't know — here's what I have anyway."** If the chat doesn't know, say so and stop.
```

**Same rule** as §3.9 for follow-ups — again **no** explicit carve-out for out-of-scope chat.

### §8.7 Out-of-scope voice (lines 1270–1273)

```text
### 8.7 Out-of-scope voice

For restaurants, real estate, weather, etc.:
> *"That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?"*
```

**Observation:** The **normative §8.7 example** ends with a **trailing question** (`Want me to point you to anything else?`), which **contradicts** the unconditional wording of §3.9 / §8.2 unless an unstated exception exists.

### Handoff tech-debt note (context only)

`HAVASU_CHAT_CONCIERGE_HANDOFF.md` **§1d / line ~703** (deferred log) already flags London Bridge farmers market in `system_prompt.txt` vs Phase 4.7 — separate from §3.9/§8.7 tension but shows owners were aware of prompt inconsistency class.

---

## 3. London Bridge farmers market — `prompts/system_prompt.txt` + catalog evidence

### Prompt context (file: `prompts/system_prompt.txt`)

**Line 29** (explicit recommendation GOOD example), with **±5 lines** for context:

```text
L22:- Lead with the useful answer, then stop.
L23:- If the context block does not contain enough information, say so plainly and stop — do not invent venues, times, or prices.
L24:- If you cannot answer what they asked (e.g. you don't have that date, or the catalog has no row), say that once and stop. Do not pivot to listing other events, months, or venues they didn't ask for.
L25:  BAD: "I don't have tomorrow's date, so I can't tell you what's happening tomorrow. The catalog shows upcoming events in May and June 2026 (dance showcases, recitals, and theater), but nothing closer than that."
L26:  GOOD: "I don't have tomorrow's date locked in — I can't tell you what's on yet."
L27:- Explicit recommendation triggers (Option 3 — pick and commit): when the user says things like "what should I do," "pick one," "which is best," "worth it," "your favorite," or "what would you do," choose one concrete option from the Context and stand behind it. Do not open with "that depends," do not list unprompted alternatives, and do not ask what they want.
L28:  BAD: "That depends what you're into! You could check out Altitude, or a dance studio. What kind of activity interests you?"
L29:  GOOD: "Hit the Saturday farmers market at London Bridge — it's the main weekend draw if you want something local and low-key."
L30:
L31:Response style:
L32:- Respond in plain text only. Do not use markdown formatting — no asterisks, bold, italics, or headers.
```

**Immediate tension:** Lines **18–20** (anti-hallucination BAD/GOOD) explicitly warn against inventing **“Saturday farmers market at London Bridge”** as an uncontextualized fact; line **29** GOOD recommends **the same concrete image** as the positive Option 3 exemplar.

### Seed / catalog design (`app/db/seed.py`)

Relevant **seed events** (not executed against every local DB; **authoritative for shipped seed content**):

| Title | Date (seed) | `location_name` (seed) | Notes |
|--------|-------------|-------------------------|--------|
| **Lake Havasu Farmers Market** | 2026-06-13 | **The KAWS, 2144 McCulloch Blvd N** | Description: “Every **2nd and 4th Saturday**…” — **not** “London Bridge” as venue. |
| **Havasu Sunset Market** | 2026-06-20 | **London Bridge Beach walkway, Lake Havasu City** | Evening “sunset market” on walkway — **title does not say “farmers market.”** |

**Conclusion for Issue B read-first:** The line-29 GOOD example **does not accurately describe** the seeded **Lake Havasu Farmers Market** row (different address / naming). It **partially overlaps** “market + London Bridge geography” only via **Havasu Sunset Market** (different branding). So the read-first finding is: **the example is not a faithful catalog-backed pick** as written; triage’s “inconsistency with anti-hallucination” diagnosis remains valid. **Whether to “remove” vs “replace”** is an implement decision; read-first recommendation leans **replace** with an example that is either **clearly generic** or **tied to a real row** in Context (owner picks voice).

### Local DB spot-check (this environment)

One-off SQLAlchemy query against default `SessionLocal()` DB: **0** events matching `%farmers%` / `%market%` / London Bridge in title/location and **0** providers with farmers/London in name — **likely empty or non-seeded local DB** for this workspace snapshot. **Implement pass** should re-verify against a DB that has seed loaded; read-first treats **`seed.py`** as source of truth for “what shipped seed claims.”

### `scripts/` grep

No additional farmers-market **seed** definitions found under `scripts/*.py` beyond query batteries / audits referencing the phrase (no competing catalog source).

---

## 4. Other hallucination-risky references in `prompts/system_prompt.txt` (inventory only)

Scan of **named concrete local / catalog-style** content in examples (BAD and GOOD indented blocks):

| Approx. lines | Kind | Content summary | Risk note |
|----------------|------|------------------|-----------|
| 7–9 | GOOD (ask) | **Altitude** + hours/pricing style | **Fixture-aligned** — low risk if Altitude remains canonical. |
| 25–26 | BAD/GOOD | May/June **2026** events listed in BAD | **BAD-only** — teaches avoidance of inventing schedule lists. |
| 28–29 | BAD/GOOD | **Altitude** + “dance studio” vs **London Bridge farmers market** | **GOOD line 29** is the main **Option 3** tripwire called out in triage. |
| 18–20 | BAD/GOOD | **London Bridge farmers market** in BAD | Reinforces risk; pairs with line 29 inconsistency. |

**Handling gaps** section (lines 34–44): contribution invitation phrasing uses **bracket placeholder** `[the thing they asked about]` — **low hallucination risk** (not a fake entity name).

**No other** “Saturday … at London …” style picks found in this file on read-through.

---

## 5. Test coverage (`tests/` grep)

### Assertions tied to §8.7 verbatim / trailing `?`

**`tests/test_phase2_integration.py`**

- **Lines 25–28:** `OUT_OF_SCOPE_87` constant — **must match** `unified_router._OUT_OF_SCOPE_REPLY` **verbatim**, including **“Want me to point you to anything else?”**
- **Lines 31–32:** Comment: *§3.9: no trailing `?` except … **(OOS §8.7** …)*  
  `_SUBINTENT_TRAILING_QUESTION_OK = frozenset({"OUT_OF_SCOPE"})`
- **Lines 246–257:** `test_oos_end_to_end_verbatim_redirect` — asserts `body["response"] == OUT_OF_SCOPE_87` for weather / real estate / dining queries.
- **Lines 260–296:** `test_voice_trailing_question_guard` — if response ends with `?`, then `sub_intent` must be in `_SUBINTENT_TRAILING_QUESTION_OK` **or** SMALL_TALK “how are you”. **Encodes explicit exception for OUT_OF_SCOPE.**

**Implication for Issue A implement:** Removing the trailing question **breaks** `OUT_OF_SCOPE_87` parity tests unless they are **updated in the same change** (and the constant comment / `_SUBINTENT_TRAILING_QUESTION_OK` logic revisited if no OOS responses end with `?`).

### `tests/test_unified_router.py`

- **`test_chat_out_of_scope_voice` (~148–153):** Asserts substring `That's outside what I cover right now` and `things-to-do` — **does not** assert the trailing question verbatim (would still pass if suffix removed, unless response length / punctuation assertions added later).

### No direct assertions on line 29 London Bridge GOOD string

**`grep`** for `London Bridge`, `Saturday farmers market`, or `farmers market at London` under `tests/`: **no** assertion that the system prompt file must contain the line-29 GOOD text.

**Related but out-of-scope for line-29 lock-in:**

- `tests/test_tier2_formatter.py` — `pick one` in **user message** to formatter API, not system_prompt line 29.
- `tests/test_unified_router.py` — `"Is the farmers market worth it?"` appears in **explicit-rec routing** parametrize list (Tier 3 path), **not** prompt text assertion.

---

## 6. Proposed fix shape (do not implement here)

### Issue A — Q17 / OUT_OF_SCOPE trailing question

| Topic | Proposal |
|--------|----------|
| **Where** | **`app/chat/unified_router.py`** — `_OUT_OF_SCOPE_REPLY` only (single template). |
| **Minimal diff** | Remove the second sentence **or** replace with a **period-ending** scope reminder (e.g. same clause one sentence) — **exact copy** must be decided in implement to satisfy §3.9 if §3.9 “wins.” |
| **§3.9 vs §8.7** | **Handoff conflict is real** (§8.7 quoted string vs §3.9/§8.2 bullets). **Code + tests already encode a de facto exception** for OUT_OF_SCOPE trailing `?` in `test_phase2_integration.py`. Implement should **not** silently “fix” voice without an **owner call** on whether **§8.7 template** or **§3.9** is authoritative for chat OOS. If §3.9 wins: update **`HAVASU_CHAT_CONCIERGE_HANDOFF.md` §8.7** in a **docs** commit (track separately if you keep docs out of code commits) or note in 8.0.4-implement scope. |
| **Tests** | **Must** update `tests/test_phase2_integration.py`: `OUT_OF_SCOPE_87`, `test_oos_end_to_end_verbatim_redirect`, and likely **`test_voice_trailing_question_guard`** / `_SUBINTENT_TRAILING_QUESTION_OK` if OOS no longer ends with `?`. Re-grep for `Want me to point` after edit. |

**STOP-style flag (scope):** Still **one template + one test file** core; **not** multi-file scatter **unless** owner also updates handoff §8.7 (then two workstreams: code + doc).

---

### Issue B — London Bridge farmers market GOOD (line 29)

| Topic | Proposal |
|--------|----------|
| **Where** | **`prompts/system_prompt.txt`** — replace **line 29 GOOD** string only (keep BAD/GOOD structure for Option 3). |
| **Minimal diff** | **Replace** GOOD with a **catalog-honest** pick: e.g. cite **Lake Havasu Farmers Market** with **The KAWS** address from seed **only if** implement agrees Tier 3 context will usually include that event (context_builder behavior — **not re-audited here**). Safer default: **generic GOOD** (“Pick one row from Context and say why…” style **without** inventing a place name) **or** reuse **Altitude**-style fixture already trusted elsewhere in the same file. |
| **Tests** | **Optional stricter test** in implement: load `prompts/system_prompt.txt` and assert line-29-style contradiction is gone — **not currently required** (no existing assertion on that line). |
| **Scope** | **Single-file** edit unless owner expands to rewrite **§8.4** handoff examples that also mention farmers market / BMX (outside `system_prompt.txt`). |

**STOP-style flag:** If owner insists the GOOD **must** stay hyper-local, **verify** Tier 3 context includes the chosen entity on representative queries before locking copy.

---

## STOP triggers (read-first)

| Trigger | Result |
|---------|--------|
| Pre-flight failures | **None** — HEAD, status, 753 tests **PASS**. |
| Issue A deliberate exception | **Finding:** Not spelled in §3.9 prose, but **§8.7 + integration tests** encode the trailing question as **locked §8.7 voice**. Owner must pick **§3.9 vs §8.7** before implement. |
| Template scattered | **No** — single `_OUT_OF_SCOPE_REPLY` in `unified_router.py`. |
| Issue B example catalog-accurate | **Partially:** Farmers market **exists** in seed but **not at London Bridge** as in line 29; **replace** is appropriate. |
| Fix larger than single edit | **No STOP** for code volume; **handoff edit** may be separate commit if §8.7 updated. |

---

## Files touched in this pass

- **Created (uncommitted, per acceptance):** `docs/phase-8-0-4-read-first-report.md` (this file).

**No** edits to `app/`, `prompts/`, `tests/`, `docs/known-issues.md`, or `phase-9-scoping-notes`.

---

## Next step

Wait for **owner-approved fix shape** for 8.0.4-implement (especially **Issue A: §3.9 vs §8.7**). No commit, no push from this read-first pass.
