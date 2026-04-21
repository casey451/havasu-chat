# Havasu Chat — Phase 6 pre-scoping (read-only verification)

**Purpose:** Authoritative answers from `HAVASU_CHAT_CONCIERGE_HANDOFF.md` at commit **`9707f7c`**, plus current repo/git checks. No code or handoff edits were performed when producing this file.

**Source:** `9707f7c:HAVASU_CHAT_CONCIERGE_HANDOFF.md` matches the working-tree handoff (`git diff 9707f7c HEAD -- HAVASU_CHAT_CONCIERGE_HANDOFF.md` empty at time of capture).

---

## 1. Phase 6 definition

**A build-phase definition exists** under the Build Plan heading `### Phase 6 — Voice, Feedback, and Onboarding (1–2 weeks, 15–25 hours)`. Verbatim from `9707f7c`:

```
### Phase 6 — Voice, Feedback, and Onboarding (1–2 weeks, 15–25 hours)

**Goal:** Polish. The phase that turns "working" into "good."

**Sub-phases:**

**6.1 Voice audit.** Create `prompts/voice_audit.txt` from the existing master file's voice audit prompt. Run the full Tier 1 template library through it. Run 30 sampled Tier 3 responses through it. Generate a report. **Fixing flagged items is owner task** (Claude Code can draft fixes, owner approves — per 2.7).

**6.2 Feedback signals.** Add thumbs up/down to Tier 3 recommendations in `app/static/index.html`. Posts to new endpoint `POST /chat/feedback` (reuse from 5.6). Writes to `chat_logs.feedback_signal`. Admin panel gets a new analytics view: feedback ratio per mode/sub-intent/over time.

**6.3 Onboarding first-turn.** On first session visit, chat greets and asks two quick-tap questions:
- "Visiting or local?" → `local` / `visiting`
- "Kids with you?" → `yes` / `no`

Stored in session state. Fed into context builder as user context for subsequent queries. If skipped, chat operates without that signal.

**6.4 Session memory.** Extend session state to capture:
- Age hints volunteered during conversation ("my 6-year-old")
- Location hints ("we're near the island bridge")
- Prior entities asked about (for natural follow-ups like "what time does it open" after asking about a place)

Context builder reads session state and injects into LLM context. Scope: within-session only, cleared after 30 min idle. No cross-session memory (per 1.4).

**6.5 Local-voice content. OWNER TASK.** Flag this in the phase completion note. Owner writes 20–30 pieces of editorial knowledge (favorite sunset spot, which market is better, when the BMX race is actually worth it, etc.). Content structure: each piece is a tagged blurb with keywords for retrieval. Stored in `app/data/local_voice.py` as a list of dicts with `keywords`, `text`, `category`. Context builder matches on keywords and injects relevant blurbs into Tier 3 context.

**Exit criterion:**
- Voice audit completed, all flagged items addressed or explicitly accepted by owner.
- Feedback thumbs live on Tier 3 responses, data flowing to `chat_logs`.
- Onboarding works for first-time visitors.
- Session memory improves context on multi-turn conversations (tested manually).
- Owner has drafted initial local_voice content (or flagged that they will do so before launch).
```

**Other occurrences of the string `Phase 6` in the same file (not the full phase spec):**

- `1. **Email infrastructure** (Phase 6 candidate). Contribution receipts, approval confirmations, needs-info replies. Provider choice (SES / Mailgun / Postmark). Deliverability, unsubscribe, rate limits.`

- `9. **Public launch criteria.** No trigger. Likely after Phase 6 email + Phase 7 polish.`

- `### 4.5 \`chat_logs\` (extend existing — Phase 6 migration adds feedback_signal)`

- `feedback_signal         text nullable          -- Phase 6 adds: 'positive' | 'negative' | null`

- File-structure tree: `session.py` (extend in Phase 4 and Phase 6), `local_voice.py` (NEW — Phase 6), `chat_logs_feedback_signal` — Phase 6, `voice_audit.txt` NEW — Phase 6.

- `- **Voice drift across tiers.** Ongoing tuning required. Phase 6 does a pass; owner re-audits periodically post-launch.`

---

## 2. Roadmap table

**Ambiguity:** The handoff does **not** contain a single markdown **table** whose rows are **`### Phase 1` … `### Phase 8`** with timeline columns. That sequence in §5 is written as **sequential `### Phase N — …` sections**, not one table.

The only **multi-row table** whose first column is **`Phase`** and that lists shipped engineering work through 5.6 is **§1d**. Verbatim from `9707f7c`:

```
| Phase | Status | Commit | Notes |
| --- | --- | --- | --- |
| 1 | ✅ | — | Project setup, FastAPI, SQLAlchemy, seed data |
| 2.x | ✅ | — | Chat API, classifier, Tier 3, ChatLog, rate limiter |
| 3.1–3.5 | ✅ | — | Tier 1 templates, routing, gap handling |
| 3.6 | ✅ | — | Voice revision (Option B community-credit, anti-delegation — later reversed) |
| 3.7 | ✅ | — | Organic traffic diagnostic, 50% gap finding |
| 3.8 | ✅ | `c9d9fac` | HOURS_LOOKUP variants + gap_template + rate-limit test mode |
| 4.0 Re-plan | ✅ | — | Tier 2 moved ahead of Contribute mode |
| 4.1 Parser | ✅ | `9a30909` | Tier2Filters schema + intent parser |
| 4.2 DB+Formatter | ✅ | — | tier2_db_query, tier2_formatter, tier2_handler |
| 4.3 Routing+Schema | ✅ | `903032c` | Router integration + token split columns |
| 4.4 Voice battery | ✅ | `16038ca` | Reusable voice-battery script + baseline |
| 4.5 Row cleanup | ✅ | `67f5bf4` | ~15% Tier 2 row payload reduction |
| 4.6 Voice cleanup | ✅ | `c2800a8` | Day-aware hours + external-delegation rule |
| 4.7 Anti-hallucination | ✅ | `1c27e21` | Tier 3 fabrication guardrail |
| 5.1 Contribution model | ✅ | `200f545` | `contributions` table + admin JSON API |
| 5.2 URL + Places | ✅ | `f5c4463` | `url_fetcher`, `places_client`, `enrichment`, BackgroundTasks |
| 5.3 Operator review UI | ✅ | `7fa2630` | HTML admin at `/admin/contributions`, approval creates catalog rows |
| 5.4 User form | ✅ | `5c58f52` | Public `/contribute` form, gap_template + system prompt updates |
| 5.5 Mention scanner | ✅ | `ce11e75` | `llm_mentioned_entities` + admin at `/admin/mentioned-entities` |
| 5.6 Categories + hours | ✅ | `b2f3fa9` | `/admin/categories`, `providers.hours_structured`, Tier 2 open_now filter |
```

Other tables in the handoff (voice battery `| Run | Score | Notes |`, tier targets, etc.) are separate and not the Build Plan phase roadmap.

---

## 3. Phase 4 status (intake / contribute mode)

**Naming:** “Phase 4” is used for **two different things**:

**A) Engineering sub-phases `4.0`–`4.7` in §1d:** all rows through `4.7 Anti-hallucination` show **`✅`**.

**B) Roadmap contribute vs shipped work — verbatim:**

```
**Implementation note (2026-04):** Tier 2 retrieve-then-generate shipped in production as engineering sub-phases **4.1–4.7** (see **§1b**); Contribute mode shipped as **5.1–5.6** (see **§1c–§1d**). The **Phase 4 — Contribute Mode** and **Phase 7 — Tier 2 Handlers** headings in this section are the **original product roadmap**; execution order was re-planned so Tier 2 preceded Contribute mode.
```

```
**Still deferred vs. original roadmap:** chat-based contribute/correct intake state machines in §3 remain partially aspirational; the shipped path is the web form + operator queue. Email receipts, CSRF, and bulk ops are in **§1d Deferred decisions**.
```

**Git log** (`git log --grep="Phase 4" -i --oneline -30`):

```
9707f7c Handoff doc consolidation: Phase 4 + Phase 5 close state
92b5b17 Phase 4 close: handoff consolidation + Phase 5 prerequisite notes
1c27e21 Phase 4.7: Anti-hallucination rule for Tier 3
c2800a8 Phase 4.6: Voice cleanup - day-aware hours + external delegation
c899fe3 docs: Phase 4.4–4.5 reports, migration notes, Tier 2 token diagnostic
67f5bf4 Phase 4.5: Tier 2 row payload cleanup
16038ca Phase 4.4: Voice battery script + baseline run
903032c Phase 4.3: Routing integration + token split schema + cost analytics
bc0fe83 docs: add session exports, phase summaries, and Phase 4.2 preflight report
7668151 Phase 4.2: Tier 2 DB query layer + formatter + orchestrator
9a30909 Phase 4.1: Tier 2 filter schema + intent parser
```

**`app/chat/intake.py`:** Glob `**/intake*.py` under `app` returned **0 files** at capture time.

The doc does **not** label roadmap “Phase 4 — Contribute / intake” with the exact words shipped / in progress / deferred / skipped; use only the **Implementation note** and **Still deferred** lines above.

---

## 4. Phase 5 close — session notes vs facts

**669 passing tests** — Handoff:

```
- 139 new tests added across Phase 5. Total suite: 669 passing.
```

**`pytest -q`** at capture: `669 passed` (exact line may vary by seconds).

**`19/1/0`** — Doc defines scoring for the 20-query battery:

```
20-query battery, Q1–Q20 from `scripts/run_voice_spotcheck.py`. Scoring: PASS / MINOR / FAIL.
```

```
- Voice battery at Phase 5.4 re-run: 19/1/0 unchanged.
```

```
- Final voice battery: 19 PASS / 1 MINOR / 0 FAIL (up from Phase 3.6 baseline 17/3/0).
```

So **`19/1/0` aligns with PASS / MINOR / FAIL** in the same section; the explicit expansion is **19 PASS / 1 MINOR / 0 FAIL**.

**Correction + `field_history`** — Data model says:

```
### 4.4 `field_history` (new — Phase 1 creates schema, wired in Phase 5)

Greenfield table. Audit log and contested-state source of truth. Schema is created in Phase 1 and seeded with baseline `established` rows; correction flow writes to it in Phase 5.
```

Shipped Phase 5 block does **not** mention correction; it defers chat contribute/correct vs §3. **No** `app/chat/correction*.py` was found at capture (glob 0). Do not infer “correction shipped” from handoff + tree without owner clarification.

**`9707f7c` unpushed** — **False** at capture: `git log origin/main..HEAD --oneline` was **empty**; branch reported **up to date with `origin/main`**.

---

## 5. Git state (at capture)

**`git status`:** Not clean — **untracked** docs only; no modified tracked files:

- `docs/handoff-doc-consolidation-phase-4-5-2026-04-20.md`
- `docs/havasu-chat - Shortcut.lnk`
- `docs/phase-4-6-completion-report.md`
- `docs/phase-4-7-completion-report.md`
- `docs/phase-5-2-smoke-followup-and-5-3-readiness.md`
- `docs/phase-5-2-smoke-test-results.md`
- `docs/phase-5-6-ship-and-migration-report.md`

**`git log origin/main..HEAD --oneline`:** *(empty)*

**`git log --oneline -10`:**

```
9707f7c Handoff doc consolidation: Phase 4 + Phase 5 close state
b2f3fa9 Phase 5.6: Category discovery + hours normalization
ce11e75 Phase 5.5: LLM-inferred facts logging
5c58f52 Phase 5.4: Public user contribution form
7fa2630 Phase 5.3: Operator review UI + approval creates catalog rows
f5c4463 Phase 5.2: URL validation + Google Places integration
200f545 Phase 5.1: Contribution data model + admin backend
5e61105 docs(PHASE_5_PLAN): sync owner draft + clarify chat_log_id type
fcf9ef0 docs: add Phase 5 Contribute mode plan (draft for owner review)
92b5b17 Phase 4 close: handoff consolidation + Phase 5 prerequisite notes
```

---

*End of verification capture. Commit this file to the repo if you want it versioned alongside Phase 6 scoping.*
