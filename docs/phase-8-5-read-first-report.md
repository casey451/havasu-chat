# Phase 8.5 — read-first report (ToS + privacy v2)

**Date:** 2026-04-22  
**HEAD:** `b36f727` (Phase 8.2: load testing — smoke script, targeted mitigations)  
**Read-first only:** no ToS or privacy drafting, no app code changes, no commit.

## Pre-flight

| Check | Result |
|--------|--------|
| `git log -1` | `b36f727` — **PASS** |
| `git status` | Clean except `?? docs/phase-9-scoping-notes-2026-04-22.md` — **PASS** (per spec) |
| `.\.venv\Scripts\python.exe -m pytest -q` | **793 passed** — **PASS** |

## 1. Inventory — ToS / legal-adjacent content

**Docs / filenames**

- No `docs/tos.md`, `docs/terms.md`, or `docs/legal.md` in the repo.
- `HAVA_CONCIERGE_HANDOFF.md` references future **Terms of service** and **takedown policy** as owner/legal tasks (not drafted in-repo).

**Grep-style survey**

- **UI / templates:** `app/static/index.html` footer has only **Privacy** → `/privacy`. No Terms link, no “Terms of Service” / “terms of use” strings in templates.
- **Routes:** `app/main.py` serves `/privacy` from `docs/privacy.md` (HTML wrapper). No `/terms` or `/tos` route.
- **Acceptance copy:** No “by using this service you agree to…” (or similar) in `app/` static or obvious user-facing strings.

**Conclusion:** **Zero** committed user-facing ToS or terms pages. The only related material is handoff text describing **future** ToS/takedown work. No conflict with a new `docs/tos.md` + footer link in a later implement phase.

**Note (scope beyond this read-first):** Handoff still mentions a **takedown policy** alongside ToS. For 8.5 implement, owner may fold a short “content complaints / takedown requests” subsection into the ToS, or keep a separate doc—either is compatible with this inventory.

## 2. What the ToS should cover (repo-grounded)

### 2.1 Service purpose and audience

- **Havasu Chat** is a Lake Havasu–focused concierge: chat UI, catalog of activities/events, calendar, permalinks, and a **contribute** path (`/contribute`, `app/api/routes/contribute.py`). Header copy: *“Lake Havasu activities & events — search, browse, or share something new.”* — conservative; no payment or guarantee claims that would need special clauses.

### 2.2 Account model

- **No user accounts, no login.** Session is a **random `session_id`** created in the browser on page load (`app/static/index.html`: `crypto.randomUUID()` or fallback). It is sent with chat requests; it is **not** stable across devices and is not tied to a profile. ToS should say: no account required; session is a technical identifier, not a personal account.

**Minor accuracy nuance (vs privacy “close the chat”):** Privacy says the session *resets when you close the chat*; implementation is **per page load** (new ID when the user reloads or opens a new tab). Privacy v2 may tighten that wording; ToS can describe “per visit / until you refresh or leave the page” consistently.

### 2.3 Usage rules (spirit + technical reality)

- **Rate limits (IP-based, `slowapi`):** e.g. chat and related POSTs **`120/minute`** (`app/api/routes/chat.py`, `app/chat/router.py`); some routes **`5/minute`** or **`3/minute`** (`app/programs/router.py`); public **`POST /events`** **`5/minute`** (`app/main.py`). `RATE_LIMIT_DISABLED` truthy values disable limits (`app/core/rate_limit.py`, tests set this).
- **Contribute spam control:** at most **one submission per IP hash per rolling hour** (when rate limiting is enabled) via `count_submissions_since_by_ip_hash` in `app/api/routes/contribute.py`.
- **Abuse framing for ToS:** no scraping/automation to overload the service; no attempts to evade limits; no harmful or illegal content; no false or misleading catalog contributions; operator may block or throttle. (Plain English, not over-specific to every route.)

### 2.4 Contributions (UGC) — the distinctive clause set

- **Flow:** `GET/POST /contribute` form; entity types include provider, program, event, tip; optional **submitter email**; content stored in **`contributions`**; operator approves via admin/approval path (`app/contrib/approval_service.py` and related). Status model includes pending/approved/rejected (see models and admin flows in repo).
- **ToS should cover honestly:**
  - User represents they have the right to submit what they send.
  - **License to use submissions:** user grants the operator a **non-exclusive license** to **store, review, display, and incorporate** approved material into the catalog; user **retains ownership** of their original expression subject to that license.
  - **No obligation to publish**; operator may reject or remove contributions for any reasonable reason (fit, quality, legal risk, spam).
  - **Optional email** is for follow-up, not a contract for inclusion.

*(Implement phase: align wording with how admin labels rejection reasons if any are user-visible—read-first did not require UI audit beyond contribute + privacy.)*

### 2.5 Intellectual property (high level)

- **App code and compiled product:** operator-owned; not a user license grant except normal browsing (no need to over-lawyer).
- **Catalog:** mix of **operator-curated** data, **community contributions** (per above), and **enrichment** (e.g. Google Places–derived fields on contributions as implemented in `app/contrib/places_client.py` and stored on `contributions.google_enriched_data`). ToS should say third-party data remains subject to **Google’s (and other providers’)** terms; users are not getting a license to **Google’s** underlying data beyond what the service displays.
- **Google Places** is used in the **contribution enrichment** path; privacy already says that at a high level.
- **User chat messages and model outputs:** not offered as “your IP license to us” beyond normal operation; optional one-liner: queries/responses are handled per the **Privacy** page; the service may log them as described there.

### 2.6 Disclaimers (plain English)

- Information (hours, prices, schedules) may be **wrong or out of date**; local businesses change.
- **No professional advice** (not medical/legal/financial).
- **“As is”** — no warranty; **limitation of liability** in plain terms (not specific dollar caps or state-specific legal formulas—reserved for lawyer pass).

### 2.7 Changes to terms; contact; governing law

- **Changes:** terms may be updated; continued use after notice (or after posting) constitutes acceptance—wording to be kept generic.
- **Contact:** same as privacy (`caseylsolomon@gmail.com` today + feedback UI); cross-link **`/privacy`**.
- **Governing law / venue:** **placeholder** only in Cursor draft: e.g. laws of **[operator jurisdiction TBD]** — **flag for lawyer and pre-launch checklist**, per owner prompt. No invented citations, arbitration clauses, or state-specific rules.

### 2.8 Functionality that would trigger “special” legal language

- **Not found in repo at HEAD:** payments/subscriptions, age gating, consumer accounts, marketplace, health data pipelines beyond generic chat. No STOP on “requires specialized statute-by-statute language” from feature inspection alone.

## 3. Privacy page (v2) — drift vs `b36f727` and §1–6 check

**Sources:** `docs/privacy.md` (as served by `app/main.py`); `app/db/models.py` (`ChatLog`, `Contribution`, `LlmMentionedEntity` / `llm_mentioned_entities`); subprocessors in code paths.

### 3.1 Section 1 — “What we collect”

- **Chat logs (`chat_logs`):** Messages, `session_id`, intent/mode/tier/latency/token fields, optional `query_text_hashed`, optional `normalized_query` for rate/analytics, optional **feedback** signal — consistent with the spirit of the privacy page (chat content + metadata + hashed query for rate limiting). **No rewrite needed** for the table list; the page does not name every column, which is acceptable.
- **`llm_mentioned_entities`:** The app can record **phrases or names** from model output linked to a `chat_log_id` for review. The privacy page does not mention this table explicitly. **Minor edit (optional):** one sentence that derived “mentioned entity” records may be stored for **internal review/quality** (not sold, operator access only)—if the owner wants full inventory-style disclosure.

**Verdict:** **No material drift**; optional **minor addition** for `llm_mentioned_entities` if owner wants maximum transparency.

### 3.2 Section 3 — Subprocessors (Anthropic, OpenAI, Google, Railway, Sentry)

- **No new host or analytics provider** surfaced in this pass beyond **Railway + Sentry** already named.
- **Nuance (minor edit recommended):**  
  - **OpenAI** is used for more than “hints” in isolation: e.g. **`app/core/hint_extractor.py`** (session hints), **`app/core/search.py`** (optional **query embeddings** for semantic search with user query text), and other **`gpt-4.1-mini`** call paths in **`app/core/extraction.py`**. The current line *“for extracting hints that help us remember context within a session”* is **incomplete** vs actual behavior.  
  - **Anthropic** is used for **main concierge responses** and **additional pipeline steps** (e.g. tier-2/tier-3 text generation/parsing in `app/chat/` and `app/core/`), not only a single “Haiku for responses” one-liner.  
- **Verdict:** **Minor edit needed** to subprocessor bullets so they do not **understate** what is sent to OpenAI/Anthropic. Not a “rewrite the page” situation.

### 3.3 Section 4 — Retention

- Still **indefinite** by design; `pre-launch-checklist.md` already tracks a **retention review**. **No change needed** unless owner wants to repeat the checklist cross-reference in prose.

### 3.4 Contact

- Still **`caseylsolomon@gmail.com`** + HTML `TODO` for a dedicated address — **matches** pre-launch checklist. **No change** until the inbox is ready (checklist item drives the edit).

### 3.5 Operational / runbook items vs privacy

| Item | Relevant to privacy v2? |
|------|-------------------------|
| `SEARCH_DIAG_VERBOSE` | **Minor cross-reference** already implied by `docs/runbook.md` pointing at privacy for diagnostic logging. Privacy could add **one short sentence** that the operator may temporarily enable **verbose search diagnostics** (e.g. extra log file on the server) and should leave it off by default—**optional**, aligns with 8.4/8.7. |
| 45s LLM HTTP timeouts (Phase 8.2) | **No** — operational; does not change what data is collected. |
| Smoke / load scripts (`scripts/smoke_concurrent_chat.py`) | **No** — operator/CI tooling, not end-user data handling. |
| Multi-worker / scaling | Out of scope for 8.5; runbook already documents. |

**Overall privacy drift since 8.7:** **None** that would invalidate the page. **Targeted copy improvements** in subprocessor accuracy (and optional session/mention/diagnostics lines) are the main v2 candidates—not a ground-up rewrite.

## 4. Proposed `docs/tos.md` outline (headings from owner prompt + guidance)

**Target size note:** The read-first pack mentioned **“600–1000 lines of markdown”** for the eventual ToS. That would be an **enormous** document for a solo service; for implement, aim for **readable web length** (roughly **~100–250 lines** of markdown, or a few print pages) unless the owner explicitly wants exhaustive clause-by-clause text. The **structure** below can stay; depth is a product choice.

Below: each section = **content guidance (1–3 sentences)**, **length**, **source**, **STOP / lawyer flags**.

---

### # Terms of Service for Havasu Chat

`Last updated: [date]` — set at implement.

---

#### 1. Acceptance

- **Guidance:** Using the site means you accept these terms and the linked Privacy page; if you do not agree, do not use the service.  
- **Length:** Short paragraph.  
- **Source:** Standard boilerplate + link to `/privacy`.  
- **STOP:** None beyond ensuring the Privacy link is live.

#### 2. What Havasu Chat is

- **Guidance:** Local concierge for Lake Havasu—chat, event/program discovery, links to **contribute**; **not** professional advice; no accounts.  
- **Length:** 1 short section.  
- **Source:** `index.html` copy + routes overview.  
- **STOP:** Do not promise accuracy or “official” status.

#### 3. Using the service

- **Guidance:** Acceptable use: human, non-abusive use; no automated scraping or attempts to break rate limits; respect contribute limits. Describe **spirit** of limits (per-IP rate limits, contribute throttle) without drafting every number as a contractual guarantee (numbers can be “may change”).  
- **Length:** 1–2 short subsections.  
- **Source:** `rate_limit.py`, `contribute.py`, chat/programs/main routes.  
- **STOP:** Optional footnote that limits are enforced technically and may change.

#### 4. Your contributions

- **Guidance:** What you submit; license grant to process and publish if approved; no guarantee of inclusion; rejection; optional email; represent rights to submit; no spam. Tie to how contributions work in code.  
- **Length:** Meatiest user-facing section after disclaimers.  
- **Source:** `contribute` flow + `Contribution` model + approval service.  
- **STOP:** Indemnity—keep **generic** or defer heavy indemnity to lawyer; no dollar caps in Cursor draft.

#### 5. Information and accuracy

- **Guidance:** Catalog and answers may be incomplete or wrong; users should verify with businesses directly for critical details.  
- **Length:** 1 paragraph.  
- **Source:** App nature + local info.  
- **STOP:** None.

#### 6. Intellectual property

- **Guidance:** Service branding and site content as operated by the operator; user retains ownership of their contributions subject to the license in §4; display of third-party data (e.g. Places) subject to third parties’ terms; no scraping/reuse of the database beyond personal use.  
- **Length:** 1–2 short subsections.  
- **Source:** Product mix + `places_client` + catalog model.  
- **STOP:** Do not paste Google or Anthropic TOS; link at high level.

#### 7. Disclaimers and limitations

- **Guidance:** As-is, no warranties; limitation of liability in **plain English**; not liable for indirect damages to the extent permitted by law (generic, not jurisdiction-cited).  
- **Length:** 1–2 short subsections.  
- **Source:** Standard solo-operator style + owner “not a lawyer” constraints.  
- **STOP:** **High** — lawyer to finalize force and scope; no statutory citations.

#### 8. Changes to these terms

- **Guidance:** We may update; material changes will be posted [and optionally dated]; continued use = acceptance, or stop using.  
- **Length:** 1 short paragraph.  
- **Source:** Boilerplate.  
- **STOP:** How “notice” is given (in-app only vs email) — owner choice.

#### 9. Governing law

- **Guidance:** Placeholder: governed by the laws of **[jurisdiction TBD]**, without choosing a court venue in Cursor draft unless owner supplies it.  
- **Length:** 1–2 sentences.  
- **Source:** Placeholder.  
- **STOP:** **Lawyer** must replace placeholder.

#### 10. Contact

- **Guidance:** Same as privacy: feedback in UI + `caseylsolomon@gmail.com` (until replaced); link to Privacy.  
- **Length:** Short.  
- **Source:** `docs/privacy.md` + `index.html` feedback behavior.  
- **STOP:** Email swap coordinated with pre-launch checklist.

**Optional 11. Takedown / complaints (if owner wants handoff alignment)**

- **Guidance:** How to report copyright or other serious issues with catalog content; operator may remove content; not a DMCA agent clause unless lawyer adds it.  
- **Length:** Short.  
- **Source:** Handoff; owner/legal.  
- **STOP:** DMCA 512-style agent language only with lawyer.

## 5. Proposed `docs/privacy.md` v2 edits (concrete)

If the owner prefers **only** subprocessor accuracy and no other churn, the minimal v2 is **edit A (+ possibly B)**.

| ID | Where | Current (abridged) | Proposed | Rationale |
|----|--------|-------------------|----------|------------|
| A | §3, OpenAI bullet | “…GPT-4.1 mini model for extracting hints that help us remember context within a session.” | Broaden to: e.g. **OpenAI** may process your messages for **session context hints**, **semantic search embeddings** (when that path is used), and other **small model assists** (e.g. supporting catalog/event workflows)—see codebase paths in read-first if owner wants a footnote in implement. | **Accuracy:** code uses OpenAI beyond a single “hints” purpose; avoids under-disclosure. |
| B | §3, Anthropic bullet | “…Claude model (Haiku) for generating concierge responses.” | Clarify: Haiku (and any configured Claude model) is used for **user-facing answers** and for **certain internal pipeline steps** that still process your message. | **Accuracy:** tier-2 / tier-3 and related paths are not only the final “concierge” string. |
| C | §1 or §2 | (No mention) | **Optional** one sentence on **derived “mentioned entity”** records for internal review quality (`llm_mentioned_entities`). | **Transparency** if owner wants the DB inventory reflected. |
| D | “Your session resets when you close the chat” | (§2 Your choices) | e.g. **“When you load or reload the app, you get a new session identifier; we don’t tie it to a profile.”** | **Alignment** with client behavior (per-load UUID). |
| E | §1 or end of §1 | (No `SEARCH_DIAG_VERBOSE` mention) | **Optional** one sentence: operator may temporarily enable **verbose search diagnostics** (extra logs on the server); default off; see runbook. | **Runbook / privacy** alignment; still optional. |

**If owner wants minimal change:** **A (+ B)** are the only **substantive** edits recommended from this read-first. **C–E** are optional polish.

## 6. Proposed pre-launch checklist additions (`docs/pre-launch-checklist.md`)

Proposed new **Open** items (one line each; rationale in parentheses):

1. **Lawyer review of Terms of Service** before public launch. *(Binding language, liability, IP, and jurisdiction need professional review for public release.)*  
2. **Lawyer review of Privacy page** (or “privacy + data practices as stated on site”) before public launch. *(Even though 8.7 was solid, ToS+privacy should be reviewed as a pair for a public cut.)*  
3. **Replace governing-law / venue placeholders** in ToS with final jurisdiction-specific text. *(Fills gap after draft placeholders.)*  
4. **Add Terms link in footer** next to Privacy, and **confirm** ToS and Privacy are consistent on contact email and data descriptions. *(Navigation + consistency.)*  
5. **(If not already implied)** Confirm **no unintended IP / subprocessor** claims on marketing pages vs privacy. *(One-time consistency pass.)*

**Existing** items (Sentry alerts, contact email, retention) remain; 8.5 read-first does not duplicate their removal.

---

## STOP / escalation triggers encountered

- **None** requiring a stop-and-ask: HEAD matches, tests pass, no conflicting committed ToS, no homepage claims that clearly contradict a reasonable ToS/privacy pair.
- **Notable for owner judgment:** (1) OpenAI/Anthropic privacy lines **understate** current code paths—address in v2, not ignored. (2) Handoff **takedown policy** is separate from the 10-section outline—include or skip in implement. (3) **600–1000 “lines”** for ToS is likely **not** the intended final size; confirm desired depth in implement.

---

*Report path: `docs/phase-8-5-read-first-report.md` (local only; not committed).*
