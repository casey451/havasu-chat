# Phase 8.0.7 — `docs/known-issues.md` reconciliation (read-first report)

**Date:** 2026-04-22  
**Repo:** `c:\Users\casey\projects\havasu-chat`  
**Mode:** Inspection + plan only. **No** edits to `docs/known-issues.md`, **no** code changes, **no** commit.

---

## Pre-flight results

| Check | Spec | Actual | Result |
|--------|------|--------|--------|
| `git log --oneline -1` | HEAD Phase 8.0.6 = `4f3f45b` | `4f3f45b Phase 8.0.6: chat validation message + admin nav consistency` | **PASS** |
| `git log --oneline -5` | (context) | `4f3f45b` … `2c64fe9` matches prompt’s 8.0.2–8.0.6 chain | **PASS** |
| `git status` | Clean **or** only `docs/phase-9-scoping-notes-2026-04-22.md` untracked | `## main...origin/main` / `?? docs/phase-9-scoping-notes-2026-04-22.md` only (before this report file existed) | **PASS** |
| `.\.venv\Scripts\python.exe -m pytest -q` | 759 passing | `759 passed, 3 subtests passed` (~7m10s) | **PASS** |

**STOP triggers fired:** None.

---

## 1) Full inventory of `docs/known-issues.md`

File shape today: one-line purpose blurb, then **`## Open (deferred)`** (one entry), then **`## Resolved`** (four entries). No other section headings.

| # | Section | Entry title / identifier | Status as written | Commit refs in text | Notes |
|---|---------|--------------------------|-------------------|---------------------|-------|
| 1 | *(preamble)* | *(none — intro sentence only)* | N/A | None | Serves as file purpose statement. |
| 2 | **Open (deferred)** | `2026-04-21 — Tier 3 date hedging on open-ended temporal queries (Phase 6.1 voice audit)` | Open — `t3-01` / `context_builder` / weekend hedging | None (refs JSON `scripts/voice_audit_results_2026-04-21-phase614-verify.json` — **file exists** in repo) | Priority line says “Investigate during Phase 6.3 or later” — **Phase 6.3 is shipped**; wording is stale. |
| 3 | **Resolved** | `2026-04-21 — Tier 2 handling of explicit-recommendation queries (Phase 6.1 voice audit)` | RESOLVED by **Phase 8.0.2** | **Phase name only** (no SHA) | Maps to commit **`2c64fe9`**. |
| 4 | **Resolved** | `2026-04-21 — Mountain-bike retrieval miss` | RESOLVED by **Phase 8.0.3** | **Phase name only** (no SHA) | Maps to commit **`18c2bb8`**. |
| 5 | **Resolved** | `2026-04-21 — Tier 3 recommended-entity not captured for prior_entity (Phase 6.4)` | RESOLVED by **Phase 6.4.1** but body says *“implementation on `main` pending owner commit”* | Phase + pointer to `docs/phase-6-4-1-recommended-entity-capture-report.md` only | **Internally inconsistent** with current `main` at `4f3f45b`. Implementation shipped in **`3b6315e`**. |
| 6 | **Resolved** | `Tier 3 feedback thumbs not rendering (Phase 6.2.2)` | RESOLVED; owner prod confirmation 2026-04-21 | **No** phase/SHA in file | Git shows doc update closing the item: **`f409286`** (`docs: resolve deferred Tier 3 thumbs issue in known-issues`). |

**Entries not in 8.0.1 triage:** All six rows are **pre–Phase 8.0.1 lineage** (Phase 6.x voice audit / memory / feedback). That is **expected** — `known-issues.md` is a **long-lived tracker**, not a slice of the triage doc. **No “triage missed this” flag** — they are older items the triage report did not need to duplicate.

**Determinability:** Every current row’s resolution state is **determinable** from git history + phase reports; **no owner STOP** for ambiguous rows.

**Structure vs 8.0.3 assumption:** Still **Open (deferred)** + **Resolved** only — **matches** what 8.0.3’s edit assumed. **No material reorganization** has occurred.

---

## 2) Cross-reference against 8.0 commits (per prompt SHAs)

Prompt anchor SHAs:

| Sub-phase | SHA | Subject (short) |
|-----------|-----|-----------------|
| 8.0.2 | `2c64fe9` | Router explicit-rec bypass |
| 8.0.3 | `18c2bb8` | Mountain-bike retrieval tuning |
| 8.0.4 | `a4beb5a` | London Bridge example in `system_prompt` (§8.4) |
| 8.0.5 | `dc4ac14` | Analytics cleanup — Track A sentinel, §3.10 reconciliation |
| 8.0.6 | `4f3f45b` | Chat validation copy + admin nav |

### Open entry (#2 — `t3-01` date hedging)

- **Still open after 8.0.2–8.0.6?** **Yes.** None of those commits target `context_builder` date injection or Tier 3 temporal context for `t3-01`.
- **Closed by a commit without `known-issues` update?** **No.**

### Resolved entries — phase vs SHA

| Entry | Phase cited in file | Add SHA (implement pass) | Closing / related commit (if not same) |
|-------|---------------------|--------------------------|----------------------------------------|
| Explicit-rec Tier 2 | Phase 8.0.2 | **`2c64fe9`** | Same. |
| Mountain-bike | Phase 8.0.3 | **`18c2bb8`** | Same. |
| Recommended-entity | Phase 6.4.1 | **`3b6315e`** | Remove “pending owner commit”; optional note first logged in **`ce64b92`**, closed in **`3b6315e`**. |
| Thumbs | *(none)* | **`f409286`** *(optional but good audit trail)* | Original log **`4944b5b`**; resolved doc commit **`f409286`**. |

---

## 3) New entries to add (8.0.4 / 8.0.5 / 8.0.6 findings)

Each evaluated for fit in `known-issues.md` **purpose** (“one-line log for bugs deferred…” — the file already hosts **resolved** and **operational** notes; slight stretch for “documented carry-over” is **owner-requested**).

### 3.A — From 8.0.4

**A1 — Handoff §3.9 vs §8.7 contradiction (doc debt, deferred)**

- **Belongs in known-issues?** **Yes** — owner asked for an **open-but-deferred** tracker until a **separate handoff-doc pass** (explicitly out of 8.0.7-implement code/prompt scope for *fixing* the handoff).
- **Section:** **Open (deferred)**.
- **Proposed text (verbatim for owner edit):**

```markdown
### Handoff documentation — §3.9 vs §8.7 trailing-question contradiction (deferred)

**Issue:** `HAVA_CONCIERGE_HANDOFF.md` reads as if **§3.9 / §8.2** forbid trailing follow-up questions outside intake/correction, while **§8.7**’s normative out-of-scope example ends with *“Want me to point you to anything else?”* The codebase already treats **OUT_OF_SCOPE** as a **carve-out** (e.g. `OUT_OF_SCOPE_87` fixture and `test_voice_trailing_question_guard` in `tests/test_phase2_integration.py`).

**Status:** **Deferred** — reconcile handoff prose in a **dedicated handoff-doc pass** (post–Phase 8.0 track), not as part of the 8.0 bug-fix code line. See `docs/phase-8-0-4-read-first-report.md` / `docs/phase-8-0-4-read-first-handback-2026-04-22.md` for read-first context.

**Priority:** Documentation consistency only. Does not block launch behavior (product matches locked tests + §8.7 template).
```

**A2 — Q17 “Boat rentals on the lake?” (voice battery MINOR → owner adjudication: not a bug)**

- **Tracked today in known-issues?** **No.** It lives in **`HAVA_CONCIERGE_HANDOFF.md`** (e.g. §1d “Remaining MINOR: Q17…”, §5 tech-debt style bullets), not in `known-issues.md`.
- **Belongs in known-issues?** **Yes** — centralizes “voice battery MINOR closed by decision” so the tracker matches shipped intent.
- **Section:** **Resolved** — suggest heading **“Resolved by adjudication (intentional behavior)”** as an `###` **inside** `## Resolved` (see §5 — **minor structure**, not a rewrite).

**Proposed text (verbatim):**

```markdown
### Q17 voice battery — “Boat rentals on the lake?” (Phase 3.6 onward MINOR)

**Status:** RESOLVED by **owner adjudication** (Phase 8.0.4 read-first / close-out). Correct behavior is **chat / out-of-scope** handling with the **§8.7** template (including the trailing *“Want me to point you to anything else?”* where applicable), **not** a catalog retrieval bug.

**Evidence / locking:** `app/chat/unified_router.py` **`_OUT_OF_SCOPE_REPLY`**; integration tests **`OUT_OF_SCOPE_87`** + `test_voice_trailing_question_guard` in `tests/test_phase2_integration.py`.

**Note:** Optional cross-link: `docs/phase-8-0-4-read-first-report.md` §1 (Q17 / OUT_OF_SCOPE). Handoff narrative bullets that still label Q17 as an open MINOR should be cleaned in the **handoff-doc pass** tracked above — **out of scope** for 8.0.7-implement if that pass is fenced separately.
```

**A3 — London Bridge §8.4 example replacement (`a4beb5a`)**

- **Belongs in known-issues?** **Optional / low value.** It was **prompt hygiene**, not a logged open defect in this file. **Recommendation:** **omit** from `known-issues.md` unless you want a one-line **Resolved** audit breadcrumb; the phase report already records it.

---

### 3.B — From 8.0.5

**B1 — Legacy NULL + `placeholder` `tier_used` rows (~2% in prod; historical Track A + early writes)**

- **Belongs?** **Yes** — “documented acceptable / won’t grow” carry-over.
- **Section:** Prefer **new third top-level section** (see §5) titled e.g. **`## Documented (metrics / carry-over)`** with a **single** entry — avoids mis-labeling as “bug fixed” or “bug open.”

**Proposed text (verbatim):**

```markdown
### Production `chat_logs` — legacy NULL `tier_used` (~2% class) + `placeholder`

**What this is:** A **small historical share** of rows (handoff ~**2.4%** `placeholder` + `null`; Phase 8.0.5 prod sampling ~**2.1%** combined) where `tier_used` is **SQL NULL** (primarily **Track A `POST /chat` / `log_chat_turn`** writes that predate unified-router analytics columns) or the explicit unified sentinel **`placeholder`**. **Not a runtime defect** in current `/api/chat` logging.

**What shipped:** **Phase 8.0.5** — **`dc4ac14`** — adds a **non-NULL sentinel** for new Track A assistant rows so the **NULL share does not grow** from current code paths; **historical NULL rows are not backfilled** (by design).

**Operational note:** Tier-mix / cost scripts should continue to **filter or bucket** NULL/`placeholder` explicitly (see `docs/phase-8-0-5-read-first-report.md`).
```

**B2 — Handoff §3.10 drift (`message` vs `response_text`, `created_at` vs abstract `timestamp`)**

- **Belongs?** **Yes** — short **Resolved** audit entry (closed by **8.0.5**, same commit **`dc4ac14`**).
- **Section:** **Resolved**.

**Proposed text (verbatim):**

```markdown
### Handoff §3.10 — `ChatLog` field naming drift vs code (`message`, `created_at`)

**Status:** RESOLVED by **Phase 8.0.5** — commit **`dc4ac14`** — reconciled handoff **§3.10** prose to match the **implemented** SQLAlchemy model (`message`, `created_at`, etc.).

**Note:** Pure documentation alignment; **no** schema migration.
```

---

### 3.C — From 8.0.6

**C1 — Misleading `/api/chat` validation JSON message (event-centric `friendly_errors` default)**

- **Belongs?** **Yes.**
- **Section:** **Resolved** — **`4f3f45b`**.

**Proposed text (verbatim):**

```markdown
### `POST /api/chat` validation — misleading 422 `message` body (event-centric copy)

**Status:** RESOLVED by **Phase 8.0.6** — commit **`4f3f45b`** — chat validation errors now return **chat-appropriate** copy (see `app/core/event_quality.py` / `app/main.py` validation handler; details in `docs/phase-8-0-6-read-first-report.md` §1).

**Scope note:** Fixes **server JSON** for API/curl clients; the **browser** main chat UI may still show generic connection copy for 422 (tracked separately below).
```

**C2 — Admin HTML nav inconsistency across Phase 5 modules**

- **Belongs?** **Yes.**
- **Section:** **Resolved** — **`4f3f45b`**.

**Proposed text (verbatim):**

```markdown
### Admin HTML — navigation consistency across Phase 5 modules

**Status:** RESOLVED by **Phase 8.0.6** — commit **`4f3f45b`** — shared nav include / consistent links across admin templates (see phase-8-0-6 delivery / diff).
```

**C3 — `app/static/index.html` masks **422** as generic “connection” error**

- **Belongs?** **Yes** — consciously **not** fixed in 8.0.6; **open** radar.
- **Section:** **Open (deferred)**.

**Proposed text (verbatim):**

```markdown
### Frontend — main chat `fetch` treats 422 like transport failure

**Observed:** `app/static/index.html` concierge path uses `if (!res.ok) throw new Error("Request failed")` then a **catch** bubble: *“Hmm, that didn’t go through — check your connection and try again.”* **422** validation responses never surface the server’s JSON **`message`** (even after **8.0.6** improved that message for `/api/chat`).

**Expected (future):** Branch on **`res.status === 422`**, parse JSON, show **`message`** (or a dedicated validation line). Optional pairing with further server copy tuning.

**Priority:** Post-launch UX polish — **not** blocking; **8.0.6** intentionally scoped to server-side copy + admin nav only.
```

---

## 4) Stale entries / terminology

| Entry | Stale element | Proposed handling (implement) |
|-------|----------------|------------------------------|
| `t3-01` open | “Investigate during Phase 6.3 or later” | **UPDATE** to neutral forward ref (“future hardening / post-launch” or “Phase 9+ investigation”) — **do not** imply 6.3 is still future. |
| `t3-01` open | *(substance)* | **KEEP** open — still accurate vs `4f3f45b`. |
| Recommended-entity resolved | “pending owner commit” | **UPDATE** — delete that clause; add **`3b6315e`**. |
| Explicit-rec / mountain-bike resolved | phase-only | **UPDATE** — append SHAs **`2c64fe9`**, **`18c2bb8`**. |
| Thumbs resolved | no SHA | **UPDATE** — add **`f409286`** (and optionally original log **`4944b5b`**). |

**Files / paths verified:** `scripts/voice_audit_results_2026-04-21-phase614-verify.json` **exists** — `t3-01` reference is not dead.

**No REMOVE** candidates — nothing is obsolete top-to-bottom; only **UPDATE** and **ADD**.

---

## 5) Structure check

**Current structure:** Two buckets — **Open (deferred)** vs **Resolved** — plus a one-line intro. **Consistent** with a small tracker; **8.0.3 did not assume a different layout**.

**Friction:** Owner wants three **distinct semantics**:

1. **Open bugs / limitations** (real follow-up work)  
2. **Resolved fixes** (code shipped)  
3. **Documented carry-over** (NULL `tier_used` class — **not** “fixed data,” **not** “open bug”)

**Recommendation:** **Minor adjustment** — add **one** third top-level section:

> **`## Documented (metrics / carry-over)`** — exactly **one** entry (NULL `tier_used` / `placeholder` explainer).

Everything else stays under **Open** or **Resolved**. Inside **`## Resolved`**, add **`### Resolved by adjudication (intentional behavior)`** as a **subsection header** before the Q17 block so **“resolved”** does not read like **“shipped a code fix.”**

**Significant rethink?** **No STOP** — a third top-level section + one `###` under Resolved is **small** and keeps the file scannable.

---

## 6) Proposed reconciliation plan (for 8.0.7-implement)

**Goal:** Tight, judgment-free implement pass: apply the edits below in **one** `docs:` commit (subject to owner approval), **`docs/known-issues.md` only** (unless owner expands fence).

### 6.1 Structural edits (file skeleton)

1. Keep intro blurb (optionally tighten one clause: tracker covers **deferred bugs, resolved fixes, adjudications, and documented metrics** — **one sentence max**).
2. Reorder top-level to: **`## Open (deferred)`** → **`## Documented (metrics / carry-over)`** → **`## Resolved`** *(optional order: Resolved before Documented — either is fine; recommend **Open → Documented → Resolved** so “what’s actionable” is first)*.
3. Under **`## Resolved`**, insert subsection heading **`### Resolved by adjudication (intentional behavior)`** **immediately before** the new Q17 entry (or only Q17 lives under it if you prefer zero empty headings).

### 6.2 Entries to **UPDATE** (exact intent)

| Target | Change |
|--------|--------|
| **`t3-01` open block** | Replace “Phase 6.3 or later” with **current** phrasing (e.g. “Post–Phase 8.0 / future session” + keep suggested `context_builder` scope). |
| **Explicit-rec resolved** | After “Phase 8.0.2”, add **`(commit 2c64fe9)`** or “— `2c64fe9`”. |
| **Mountain-bike resolved** | After “Phase 8.0.3”, add **`(commit 18c2bb8)`** or “— `18c2bb8`”. |
| **6.4.1 recommended-entity** | Remove **“implementation on `main` pending owner commit”**; add **`(commit 3b6315e)`**; keep link to `docs/phase-6-4-1-recommended-entity-capture-report.md`. |
| **Thumbs** | Add line: **Resolved in repo:** `f409286` (optional: originally logged `4944b5b`). |

### 6.3 Entries to **ADD**

| Location | Item |
|----------|------|
| **Open** | §3.9 vs §8.7 handoff contradiction — **verbatim block §3.A1** (owner may trim). |
| **Open** | Frontend 422 masking — **verbatim block §3.C3**. |
| **Documented (metrics / carry-over)** | NULL `tier_used` — **verbatim block §3.B1**. |
| **Resolved** | §3.10 drift — **verbatim block §3.B2**. |
| **Resolved** | Chat validation 422 copy — **verbatim block §3.C1**. |
| **Resolved** | Admin nav — **verbatim block §3.C2**. |
| **Resolved** (adjudication subsection) | Q17 — **verbatim block §3.A2**. |

### 6.4 Entries to **MOVE**

- **None** (Q17 is new text, not a move from Open).

### 6.5 Entries to **REMOVE**

- **None.**

### 6.6 Optional / owner calls

- **London Bridge `a4beb5a` one-liner** in Resolved — **skip unless** you want maximum audit density.
- **Chronological ordering** inside Resolved — currently date-ish; after adds, either **keep newest-at-bottom** or **group by theme** — implement can follow **“append new blocks at end of Resolved”** for minimal diff churn.

### 6.7 Out of scope (reaffirmed)

- **No** `HAVA_CONCIERGE_HANDOFF.md` edits in 8.0.7-implement **unless** owner expands the fence (contradiction remains **tracked** in known-issues until a handoff pass).
- **No** code, tests, prompts, `scripts/`, `alembic/`.

---

## 7) One-paragraph summary (for owner)

`docs/known-issues.md` is **small and structurally intact** (Open + Resolved only). **Pre-flight passed** (`4f3f45b`, allowed untracked `phase-9` only, **759** tests). Every row is **deterministically** classifiable; the only **hard staleness** is the **6.4.1 “pending owner commit”** line and the **`t3-01` priority** still naming **Phase 6.3** as future. **8.0.7-implement** should **append SHAs** to the **8.0.2 / 8.0.3** resolved rows (**`2c64fe9`**, **`18c2bb8`**), fix **6.4.1** to **`3b6315e`**, optionally pin **thumbs** to **`f409286`**, add **five** new blocks (two **Open**, one **Documented carry-over**, three **Resolved** fixes, one **Resolved-by-adjudication** Q17), and introduce a **third thin top-level section** for the **NULL `tier_used`** explainer so it is **not** misread as a bug. **No significant file rewrite** is required.

---

## 8) Handback

- **This report (tracked path for review):** `docs/phase-8-0-7-read-first-report.md` — **intentionally not gitignored**; **do not commit** until owner approves the reconciliation plan for 8.0.7-implement.
- **Optional separate handback** (gitignored pattern `phase-8-0-7-read-first-handback-*.md`): **not created** — all content is in this file.

**Post-save working tree expectation:** untracked **`docs/phase-8-0-7-read-first-report.md`** plus existing **`docs/phase-9-scoping-notes-2026-04-22.md`**; **no** tracked file modifications.
