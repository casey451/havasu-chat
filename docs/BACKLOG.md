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

## Ship log - Session 2 follow-up, Tier 2 deterministic event rendering (**`d279165`**)

**What shipped:** Deterministic Python rendering for all-event Tier 2 catalog responses; `tier2_formatter.format()` dispatches empty rows → fixed empty message, all-event rows → renderer `(text, 0, 0)`, mixed/non-event rows → unchanged Anthropic path. Programs and providers remain LLM-formatted (scope-limited to events where dropping/count bugs were observed).

**Why:** Formatter LLM dropped rows and fabricated counts on event-date queries; prompt additions in **`1c262ad`** had **zero observable effect** on that behavior.

**Links / backlog:** Event markdown links from catalog data; Backlog **6** closed; Backlog **4** documentation closed as above. Layer 3 formatter-link prompt obviated for events.

**Tests / verification:** +22 tests, suite total 997; pre-commit pytest and post-deploy May 2/8/9 sampling with catalog fingerprint and `tier_used` response checks per session runbook.
