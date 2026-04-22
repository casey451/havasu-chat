# Phase 6.5-lite — local voice plumbing (report)

**Date:** 2026-04-21  
**Status:** Implementation complete in tree; **commit intentionally deferred** until owner approval (requested message: `Phase 6.5-lite: local voice plumbing (empty, ready to grow)`).

## What shipped

1. **`app/data/local_voice.py`** — `LOCAL_VOICE` starts as an empty list; each dict is validated at import (`id`, `keywords`, `category`, `text`; optional `context_tags`, `season`).
2. **`app/chat/local_voice_matcher.py`** — `find_matching_blurbs(query, session_hints, current_date, max_results=3, blurbs=None)`:
   - Word-boundary keyword scoring (case-insensitive).
   - Session filters: `adults_only` dropped when `has_kids` is true; `local_focused` dropped when `visitor_status == "visiting"`; `visitor_friendly` dropped when `visitor_status == "local"`. `kids_ok` is permissive (never excludes for “no kids”).
   - Season gate: `winter` / `spring_fall` / `summer` / `holiday` (Nov 20–Jan 5) / `year_round` (default when omitted).
   - Optional **`blurbs=`** for unit tests without patching the live list.
3. **`app/chat/tier3_handler.py`** — After the `Now` line and before catalog context, appends a `Local voice:` bulleted block when the matcher returns hits; uses `now_lake_havasu().date()` for season evaluation.
4. **`prompts/system_prompt.txt`** — Clarifies that `Local voice` is operator tone/hints like `User context`, not a factual catalog source.
5. **Tests:** `tests/test_local_voice_matcher.py`, `tests/test_tier3_local_voice_injection.py`; `tests/test_tier3_user_text_context.py` asserts no `Local voice:` when the list is empty.

## Verification

| Check | Result |
|--------|--------|
| **pytest** | Not executed in the agent environment (Windows image had no working `python` / `py` on PATH—only Store stubs). **Owner should run:** `python -m pytest -q` from the repo root. |
| **Voice spot-check (19/1/0)** | Not run here; same reason. |
| **Manual temp blurb** | Not performed in agent session; if you add a row to `LOCAL_VOICE` locally for a smoke test, remove it before committing. |

## Follow-ups (optional)

- Grow `LOCAL_VOICE` with real blurbs and re-run pytest + a short Tier 3 smoke in staging.
- If temporal/cost tags should actively constrain matches when the query *does* contain signals, extend `_passes_session_filters` in a later phase (6.5-lite deliberately leaves them non-filtering).
