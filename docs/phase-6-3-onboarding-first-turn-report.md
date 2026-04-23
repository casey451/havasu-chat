# Phase 6.3 — Onboarding first-turn (completion report)

**Status:** Implementation complete on branch; **no commit** until owner sends explicit *approved, commit and push*.

---

## 1. What shipped

- **Session:** `onboarding_hints` on the in-memory concierge session (`visitor_status`: `local` \| `visiting` \| `None`, `has_kids`: `bool` \| `None`), initialized in `clear_session_state` and `get_session` (`app/core/session.py`).
- **API:** `POST /api/chat/onboarding` — updates hints for `session_id`; validates that at least one of `visitor_status` or `has_kids` is present (`app/api/routes/chat.py`, `app/schemas/chat.py`).
- **Tier 3:** Compact `User context: …` line inserted in **`answer_with_tier3`** between the classifier block and the catalog block; `build_context_for_tier3` unchanged (`app/chat/tier3_handler.py`). `unified_router.route` reads hints from `get_session` when `session_id` is provided (`app/chat/unified_router.py`).
- **System prompt:** Clarifies that a `User context` line is bias-only; catalog **Context** remains the sole factual source (`prompts/system_prompt.txt`).
- **Static UI (`app/static/index.html`):** Unconditional first-turn onboarding: **Bubble 1** — *Hey — welcome to Havasu. You visiting, or local?* with **[Visiting]** / **[Local]** chips; **Bubble 2** (after Q1) — *Kids with you?* with **[Yes]** / **[No]**; then existing three **example prompt** chips. First typed message removes all `.chips-wrap` (skip path). No explainer line about the mechanic.

---

## 2. Pre-flight findings (summary)

Source: `docs/phase-6-3-preflight-report.md` and owner refinements applied before implementation.

| Topic | Finding |
| --- | --- |
| Git (last 20) | No prior `6.3` / `onboarding` / `first-turn` commit subjects on `HEAD` at pre-flight time. |
| Session | In-process `dict` keyed by `session_id`; new keys require `clear_session_state` + `get_default` discipline — done for `onboarding_hints`. |
| Frontend | Messages are plain-text bubbles; interactive UI matched **welcome `.chips-wrap`** pattern (chips after bot row), not feedback thumbs. |
| Tier 3 context | Clean insertion point: **`user_text` in `tier3_handler`**, not `context_builder`. |
| System prompt | Factual rule referenced only the catalog **Context** block; added paired rule for **User context** bias so the model does not treat hints as facts. |
| Refinements | No `should_show_onboarding` / no bootstrap endpoint; no `asked` flag; unconditional onboarding on each page load (new `sessionId` per load). |

---

## 3. Test counts

| Milestone | Count |
| --- | ---: |
| Pre–Phase 6.3 (per owner context) | 681 |
| After Phase 6.3 implementation | **688** |

Delta: **+7** tests (`tests/test_api_chat_onboarding.py`, plus `compact_onboarding_user_context_line` / user-payload ordering in `tests/test_tier3_handler.py`). Full suite: **688 passed** (local run before this report).

---

## 4. Voice spot-check (gate)

- **Command:** `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py`
- **Result:** Smoke test **OK**; battery **20/20** HTTP successes; report written to `scripts/output/voice_spotcheck_2026-04-21T19-41.md` (output under `scripts/output/` is typically gitignored).
- **Target:** **19 / 1 / 0** or better (PASS / MINOR / FAIL over the 20-query battery per `HAVA_CONCIERGE_HANDOFF.md`).

**Manual score (same rubric as prior closes):** **19 / 1 / 0**

- **MINOR — Query 17** (*Boat rentals on the lake?*): Persistent per handoff — routed to **`chat`** / out-of-scope template; closing line ends with a follow-up question. Not introduced by Phase 6.3 (production path unchanged for this query).
- **Query 7** (*Family activities this month*): Tier 3 reply follows the same pattern as earlier archived batteries (e.g. `voice_spotcheck_2026-04-20T21-54.md`): date-gap honesty plus catalog-forward examples and a CVB pointer. Counted as **PASS** for parity with the documented **19/1/0** baseline, not a regression.
- **Gate:** **Holds at 19/1/0** — no STOP condition triggered.

---

## 5. Deviations from spec (with reasoning)

| Item | Deviation | Reasoning |
| --- | --- | --- |
| Owner copy pass | Initial ship used a longer explainer bubble; replaced per final owner copy (this report §1). | Resolved before commit approval. |
| `localStorage` | Returning vs first-time **welcome copy** removed entirely. | Owner direction: unconditional onboarding; each load gets a new `sessionId` anyway. See §7. |
| Voice battery | Scored **manually** from markdown + handoff rubric; script does not print `x/y/z`. | Matches historical Phase 4.7 / 5.4 workflow. |

No intentional deviation from: sequential two-tap flow, `POST /api/chat/onboarding`, Tier 3 user-context placement, skip-on-type, or session migration discipline.

---

## 6. Owner tasks (before / at commit)

1. **Explicit git approval:** Reply *approved, commit and push* when ready (single consolidated commit per handoff; no commit from agent until then).
2. **Optional:** Re-run voice spot-check after deploy if you want production to include any future Tier 3 / copy changes in the same session.

---

## 7. Removed `localStorage` branching — prior behavior vs now

**Before (removed):**

- Key: `havasuchat_has_visited` in `localStorage`.
- **First visit (`false`):** Bot: *Welcome. Ask what’s happening in town…* plus **three** example-prompt chips (*What's on this weekend?*, *Kids activities or swim lessons*, *I'd like to add an event*). On first load, `markVisited()` set the flag to `true`.
- **Returning visit (`true`):** Different bot line: *Welcome back — what's happening in Havasu?* plus **two** chips (*This weekend* → prefills a weekend query, *Add an event* → prefills add flow).
- A `setTimeout(150)` re-ran the welcome if no `.chips-wrap` was found (failsafe).

**After:**

- No `localStorage` read/write for welcome. **Everyone** sees the same **onboarding** Bubble 1 + Visiting/Local chips, then Bubble 2 + Yes/No, then the **same three** example chips as the old first-visit set.
- **Returning users:** They **no longer** get the shorter *Welcome back* line or the two-chip shortcut row. They **do** see onboarding on every full page load (aligned with *fresh `sessionId` per load* and owner *unconditional onboarding*). Session **hints** are still empty until they tap or they skip by typing; returning locals are not remembered across reloads for UI purposes (only the static example chips return after Q2, same as before for first-timers post-welcome).

**Regression assessment:** The only **UX** regression for returning visitors is losing the distinct *welcome back* message and the two tailored chips — intentional per spec. No change to **`POST /api/chat`****,** rate limits, or Track A `POST /chat`**. Server-side session for Track B flows in `app/chat/router.py` is unchanged.

---

## 8. Files changed (Phase 6.3 body of work)

| File | Role |
| --- | --- |
| `app/core/session.py` | `onboarding_hints` defaults + reset |
| `app/schemas/chat.py` | `ChatOnboardingRequest` / `ChatOnboardingResponse` |
| `app/api/routes/chat.py` | `POST /api/chat/onboarding` |
| `app/chat/tier3_handler.py` | `compact_onboarding_user_context_line`, `answer_with_tier3(..., onboarding_hints=)` |
| `app/chat/unified_router.py` | Load hints from session; pass into Tier 3 |
| `prompts/system_prompt.txt` | User context vs catalog facts |
| `app/static/index.html` | Unconditional onboarding UI + copy |
| `tests/test_api_chat_onboarding.py` | API + session + router wiring |
| `tests/test_tier3_handler.py` | Bias line + payload order |

Supporting / earlier artifacts (optional in repo): `docs/phase-6-3-preflight-report.md`, `docs/phase-6-3-implementation-summary.md`.

---

## 9. Suggested commit message (when approved)

`Phase 6.3: onboarding first-turn (visitor status + kids quick-tap)`

---

*Report generated as part of Phase 6.3 completion workflow step 5. Agent will not commit until owner approval.*
