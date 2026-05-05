# local_voice_matcher

`app/chat/local_voice_matcher.py` (~94 lines)

## Purpose

Match curated **local-voice blurbs** (short opinion strings stored in `app/data/local_voice.py`) to the user's query, current season, and onboarding hints. The matched blurbs are inserted into Tier 3's context block so Haiku can echo Hava's curated local perspective rather than confabulating a generic one. Phase 6.5-lite implementation; the surface is small and the rules are explicit.

## Public surface

**`find_matching_blurbs(query: str, session_hints: Mapping[str, Any] | None, current_date: date, max_results: int = 3, *, blurbs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]`** — Score blurbs against the query, filter by season and session hints, return up to `max_results` ordered by keyword-hit count (desc), stable within ties.

`blurbs` is a kwarg-only escape hatch for tests; production callers leave it `None` to use `_local_voice_data.LOCAL_VOICE`.

## Inputs and outputs

**Input.**
- `query`: free-text user query (stripped before scoring).
- `session_hints`: mapping with optional `has_kids`, `visitor_status` keys.
- `current_date`: today's date in Lake Havasu local time (callers pass `now_lake_havasu().date()`).
- `max_results`: clamp on the result count (defaulted to 3, the Tier 3 caller's convention).

**Output.** A list of blurb dicts, each shaped per `app/data/local_voice.LOCAL_VOICE`. Empty list if no blurb has any keyword hit, or all blurbs are filtered out by season/hints.

## Internal structure

`find_matching_blurbs` is a four-pass linear scan:

1. **Season filter.** `_season_includes_date(season, current_date)` — accepts `None`, `"year_round"`, `"winter"`, `"summer"`, `"spring_fall"`, `"holiday"`. Holiday is a hard-coded Nov 20 → Jan 5 window.
2. **Session-hint filter.** `_passes_session_filters` excludes blurbs that conflict with the user's onboarding (`adults_only` blurb when `has_kids=True`; `local_focused` blurb when `visitor_status="visiting"`; `visitor_friendly` blurb when `visitor_status="local"`).
3. **Keyword scoring.** `_keyword_hits` counts how many of a blurb's `keywords` list appear in the query (whole-word, case-insensitive via `\b`-anchored regex per keyword).
4. **Sort and clamp.** Sort by `(-score, idx)` so higher scores come first; ties break to the earlier blurb in `LOCAL_VOICE`. Take up to `max_results`.

Zero-score blurbs are dropped before sorting.

## Conventions

**Whole-word keyword matching.** `_keyword_boundary_pattern` wraps each keyword in `\b...\b` after `re.escape`. The keyword `"hike"` fires on the literal word "hike" (and on "hike." or "hike,"), but does **not** fire on "hiked", "hiking", or "hikes" — the trailing letters are word characters, so the right-side `\b` boundary is not satisfied. If you need an inflected form to match, add it explicitly to `keywords`; do not loosen the regex.

**Stable ordering on ties.** The `idx` tiebreaker means the order of blurbs in `LOCAL_VOICE` is the curator's preference signal — earlier means "show me first when scores tie."

**Filter precedence: season, then hints, then score.** Blurbs that fail any filter are dropped without scoring. Saves cycles and prevents zero-score blurbs from leaking through.

**Defensive `keywords` typing.** Non-list `keywords` is silently treated as zero-score (the blurb is skipped). Allows `LOCAL_VOICE` curation errors to fail gracefully rather than crashing the matcher.

## Known limitations and design notes

**No partial-match scoring.** A keyword either appears as a whole word or it doesn't. `"kayak"` does not fire on "kayaking" (the trailing "ing" suppresses the right-side `\b`); `"boat"` does not fire on "houseboat" (the leading "house" suppresses the left-side `\b`). Add the inflected or compound form explicitly to `keywords` if you need it to match.

**Hard-coded season windows.** Holiday is Nov 20 – Jan 5; summer is May–Sep; spring/fall is Mar/Apr/Oct/Nov; winter is Dec/Jan/Feb. These are Lake Havasu-specific (summer is "the season" and runs longer than astronomical summer). Other geographies would need different windows.

**Session-hint filters are ANDed silently.** If a user is `visiting` AND `has_kids=False`, the blurb has to pass *both* filters to be eligible. There's no "any-pass" mode. Acceptable because the current filter set is short.

**No de-emphasis of recently-shown blurbs.** Two consecutive Tier-3 turns can show the same top-3 blurbs. A future improvement: rotate against `session.recent_voice_ids`.

**Output is the raw blurb dict.** Callers (Tier 3 handler) re-shape into `Local voice:\n- {text}` lines. The matcher doesn't pre-format because tests want to assert on the dict structure.

## Configuration

No environment configuration. All thresholds and season windows are module constants. The blurb data lives in `app/data/local_voice.py` (separate file so non-engineers can edit blurbs without touching matcher logic).

## Related

**Direct callers:**

- `app/chat/tier3_handler.py` `answer_with_tier3` — calls with the user query, onboarding hints, and current local date; takes up to 3 results and inlines them into the `mid` block of the user prompt.
- `tests/test_local_voice_matcher.py` — direct surface coverage.
- `tests/test_tier3_local_voice_injection.py` — integration coverage of the Tier-3 wiring.

**Direct dependencies:**

- `app.data.local_voice.LOCAL_VOICE` — the curated blurb list.

**Cross-references:**

- `docs/persona-brief.md` §6.7 — curated-vs-bulk voice rationale; this module is the "curated" half's matcher.
- `docs/components/tier3_handler.md` — describes how blurbs are stitched into the prompt.
