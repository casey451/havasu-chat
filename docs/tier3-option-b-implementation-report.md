# Tier 3 Option B — implementation report

**Date:** 2026-04-24  
**Spec:** `docs/tier3-option-b-unlinked-events-spec.md`

## Commit

- **Hash:** `88556bb5951725726c7934c95a97a610ece085e9` (short: `88556bb`)
- **Pushed:** No (hold for review / push approval)

## Diff summary

| File | Change |
|------|--------|
| `app/chat/context_builder.py` | +53 lines (net) |
| `tests/test_context_builder.py` | +193 / −3 |

**Totals:** 2 files, 243 insertions, 3 deletions.

## Code changes

- Added `RESERVED_UNLINKED_WORDS = 300`, `_UNLINKED_EVENTS_LIMIT = 10`, `_unlinked_future_events`, and `_format_unlinked_event_line` in `app/chat/context_builder.py`.
- `build_context_for_tier3` collects `linked_event_ids` from every `_events_future_for` event, fetches unlinked events (live, `provider_id` null, `today <= date <= today+365`, SQL `limit(10)`), then filters with `exclude_ids`. If the list is empty, **no** “General calendar” block.
- If there is a block: trim **only** the provider body with `_trim_to_word_budget(..., max(1, MAX_CONTEXT_WORDS - RESERVED_UNLINKED_WORDS))`, then append the unlinked section (not trimmed). If there is no block, behavior matches the old path: trim the full body to `MAX_CONTEXT_WORDS`.
- Unlinked line format: same as provider-tied “Upcoming event” lines, extended with ` — {url or em dash}`.

## Tests (`tests/test_context_builder.py`)

- Unlinked row appears under the General calendar header (with URL).
- `_unlinked_future_events` drops rows when `exclude_ids` contains the id (defensive dedup).
- 15 unlinked future rows → only the first 10 by date in context.
- **`test_empty_unlinked_omits_general_calendar_section`:** no unlinked rows → no “General calendar” / “not attached…” text.
- **`test_word_budget_reserved_tail_keeps_unlinked_visible`:** huge `Program.title` so the provider section exceeds the reserved head budget; marker unlinked event still appears after the General calendar header.  
  (`schedule_note` is not used to inflate context here because the builder truncates that field to 120 characters in the program line; the test uses a long `title` instead.)
- 300 days out: included; 400 days: excluded.
- Three unlinked events: order in the string is increasing by date.

## `system_prompt.txt`

- **Not edited.** Tier 3 system prompt lives at repo root `prompts/system_prompt.txt` (not `app/chat/prompts/...`). It already tells the model to ground on Context rows; optional v1 one-liner for “General calendar” was skipped so system behavior is unchanged.

## Pytest (local)

The agent environment could not run Python. On your machine, from the repo root:

```bash
python -m pytest tests/test_context_builder.py -v
```

## Note

The commit message body may include a `Made-with: Cursor` line from tooling; amend with `git commit --amend` if you want the body to match the template exactly.

## Follow-up

- After green `pytest` locally, review and approve push.
- Then validate in prod against the five already-approved events (per project plan).
