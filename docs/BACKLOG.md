# Backlog

Open and recently-closed work items with attribution to commits. Updated at the end of each session that opens, closes, or ships against a backlog item.

Status conventions:

- **OPEN** — identified, not yet addressed
- **RESOLVED** / **CLOSED** — shipped; commit referenced
- **DEFERRED** — explicitly out of scope until a precondition is met
- Numbered backlog items predate the canonical-docs introduction; new items can use the same format or whatever shape suits

Ship log entries at the bottom record what shipped per session. New ones are appended; old ones are not edited.

---

# Multi-day events - Tier 2 backlog

**Context:** Multi-day schema/retrieval work and parser prompt updates are now shipped together and verified in production.

---

## Backlog 1 - `tier2_parser` date extraction gap (**RESOLVED**)

**Original issue:** Tier 2 parser often emitted `time_window` and left `date_exact` null for natural-language calendar queries, so date-specific retrieval could not reliably execute.

**Resolution shipped:**
- **`63a4535`** - parser prompt contract update in `prompts/tier2_parser.txt`:
  - documents `date_exact`, `date_start`/`date_end`, `month_name`, `season`
  - enforces one temporal-group rule with priority
  - adds few-shots for explicit date, range, month, season, and precedence cases
- **`d763775`** - multi-day schema/retrieval plus backfill support needed for end-to-end correctness once `date_exact`/range fields are extracted.

**Verification:** Local and production chat checks confirmed date-specific queries now route through correct temporal fields and return expected events for middle-day overlap cases.

---

## Backlog 2 - `_time_bucket_first_hits` and broad `span` (**OPEN**)

**Issue:** For broad windows (`span > 30`) with many matches, `_time_bucket_first_hits` can sample across the window and omit chronologically clustered events.

**Effect:** Returned top-eight list can hide relevant early-window events even when SQL overlap is correct.

**Scope:** Product/UX decision (sampling vs strict chronological priority) and potential query/selection adjustment.

**Reference:** `app/chat/tier2_db_query.py` (`_is_still_clustered_early`, `_time_bucket_first_hits`).

---

## Backlog 3 - year inference for undated calendar queries (**OPEN**)

**Issue:** `tier2_parser` does not pass current local date context into the model prompt. Queries like "events on May 8" (no year) rely on model guesswork.

**Desired fix:** Code change in `app/chat/tier2_parser.py` prompt assembly to inject current local date context (user/system note) so undated calendar phrases resolve deterministically to the intended year.

**Out of scope of shipped fix:** Prompt docs/few-shots alone; this needs parser code-path context injection.

---

## Backlog 4 - day relevance ranking for overlapping multi-day events (**RESOLVED**)

**Original issue:** For a queried day, events that *start on that day* should rank above events that merely overlap the day from earlier start dates.

**Resolution shipped:** **`1c262ad`** — SQL `ORDER BY` for `date_exact` queries in `app/chat/tier2_db_query.py` prioritizes `Event.date == date_exact` (starts-on-day) before overlap-only rows, then `Event.date`, then `start_time`. Verified in production (e.g. May 9, Session 2).

**Documentation closure:** Backlog 4 remained marked OPEN in this file until Session 2 follow-up (**`d279165`**), which records the close explicitly. No further code change required for this backlog item.

---

## Backlog 5 - clickable source URLs in chat output (**OPEN**)

**Issue:** Chat output does not consistently surface `event_url` links for events.

**Effect:** Users cannot click through to RiverScene/source pages for full details.

**Desired fix:** Ensure formatter includes clickable event links where available in Tier 2 responses.

---

## Backlog 6 - formatter count/prose drift (**CLOSED**)

**Original issue:** Response prose could claim a different event count than the rendered list; Tier 2 formatter LLM omitted rows despite prompt guardrails (Session 2 verification failures on May 2 and May 8; flaky on May 9).

**Resolution shipped:** **`d279165`** — For Tier 2 rows that are **all** `type: event`, catalog text is rendered deterministically in Python via **`render_tier2_events`** in **`app/chat/tier2_catalog_render.py`**. Row count, order (matching SQL), verbatim titles, and optional `{n} events:` header are structurally guaranteed. `event_url` is emitted as markdown `[title](url)` when non-empty. Mixed or non-event rows continue to use the existing LLM formatter path and `prompts/tier2_formatter.txt`.

**Supersedes:** Session 2 prompt-only completeness/count/order rules at **`1c262ad`** are **architecturally insufficient** for the observed failure mode (LLM ignored mid-prompt rules); deterministic rendering replaces that approach for event listings.

**Historical notes:** Past-date retrieval context in `6934d1d`; Session 2 SQL ordering partial ship at `1c262ad`; Session 3 Layer 2 UI markdown link rendering at `cdc4ac7`. Session 3 **Layer 3** (formatter prompt to emit markdown links) is **closed without ship** — the renderer emits links for events; no separate Layer 3 prompt session is required for that intent.

---

## Backlog 7 - `event_quality.py` orphan symbols after legacy `/chat` removal (**OPEN**)

**Context:** After **H1** (`61387e4`..`23a39a5`), `app/core/event_quality.py` is imported from `app/main.py` (`friendly_errors` on `RequestValidationError`) and indirectly via the unified router stack. Many symbols existed primarily for the deleted legacy router path.

**Symbols to verify and likely trim (per-symbol usage audit):** `apply_user_reply_to_field`, `build_pending_review_create`, `first_invalid_field`, `has_any_contact`, `normalize_partial_event`, `try_build_event_create`, `CONTACT_OPTIONAL_PROMPT`, `REVIEW_OFFER_MESSAGE`, `SUBMITTED_REVIEW_MESSAGE`.

**Scope:** Small follow-up ship — delete dead exports / consolidate after grep confirms no references.

---

## Backlog 8 - `unified_router.py` `tier_used` comment (**OPEN**)

**Issue:** Near line ~96, the `tier_used` enumeration includes `'track_a'` (documented as DB-only; unified path never emits `track_a`). After H1, **no code path emits `track_a`** anywhere — it exists only on historical `chat_logs` rows.

**Desired fix:** Update the comment to state that `track_a` appears only in historical DB rows, not in current emitters.

---

## Backlog 9 - Tier 1 hit rate (**OPEN**)

**Observation:** ~33/486 ≈ **7%** Tier 1 hits pre-H1 — lower than expected for templated provider lookups.

**Next step:** After bulk import (**Phase 8.11**), re-measure; if it stays low, investigate (signal worth pulling on).

---

## Backlog 10 - `HAVASU_CHAT_MASTER.md` test fixture (**OPEN**)

**Issue:** Eight seed/backfill tests fail in environments missing **`HAVASU_CHAT_MASTER.md`** at the repo root.

**Options:** Bundle a minimal fixture, mark tests skip-when-absent, or document dev-env setup explicitly.

**Note:** Pre-existing; unrelated to H1, but visible on every local `pytest` run without the file.

---

## Backlog 11 - slowapi deprecation warnings on Python 3.14 (**OPEN**)

**Issue:** Six identical **`DeprecationWarning`** lines from `slowapi/extension.py:717` (`asyncio.iscoroutinefunction` vs `inspect.iscoroutinefunction`).

**Scope:** Library-side / upstream. Track until **`slowapi`** releases a fix or a version pin is warranted.

---

## Ship log - Session 2 follow-up, Tier 2 deterministic event rendering (**`d279165`**)

**What shipped:** Deterministic Python rendering for all-event Tier 2 catalog responses; `tier2_formatter.format()` dispatches empty rows → fixed empty message, all-event rows → renderer `(text, 0, 0)`, mixed/non-event rows → unchanged Anthropic path. Programs and providers remain LLM-formatted (scope-limited to events where dropping/count bugs were observed).

**Why:** Formatter LLM dropped rows and fabricated counts on event-date queries; prompt additions in **`1c262ad`** had **zero observable effect** on that behavior.

**Links / backlog:** Event markdown links from catalog data; Backlog **6** closed; Backlog **4** documentation closed as above. Layer 3 formatter-link prompt obviated for events.

**Tests / verification:** +22 tests, suite total 997; pre-commit pytest and post-deploy May 2/8/9 sampling with catalog fingerprint and `tier_used` response checks per session runbook.

---

## Ship log - H1 deletion ship — legacy `/chat` router (**`61387e4`..`23a39a5`**)

**What shipped:** Deleted legacy **`POST /chat`** router and dependents; **`POST /api/chat`** (unified concierge) unchanged. Removed **`app/chat/router.py`**, **`app/core/venues.py`**, **`tests/test_phase4.py`**, **`tests/test_search_relevance.py`**; trimmed **`app/main.py`**, **`app/db/chat_logging.py`**, **`app/schemas/chat.py`**, and mixed tests per plan. **Production:** `/health` 200 (`db_connected`, `event_count` 114); `/chat` → 404; `/api/chat` → 200 concierge shape. **Deploy** `6c416456-d1aa-4945-922a-cd6d7466c133`.

**Tests / verification:** 942 passing post-ship vs 987 pre-ship (**45** legacy `/chat` tests removed); **8** seed/backfill failures unchanged (baseline).

**Follow-ups:** Backlog **7**–**11** (`event_quality` orphan trim, `unified_router` comment, Tier 1 hit rate, `HAVASU_CHAT_MASTER.md` fixture, slowapi warnings).
