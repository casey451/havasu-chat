"""Shared primitives for the event dedup matchers (audit 2026-07-01).

Three call sites compared event titles + start times with independently-drifted
copies of the same arithmetic:

* ingest ``dedup.find_duplicate`` (± window on the start time),
* the render-time cross-source pass in ``dedup`` (start-gap + token subset), and
* the class-occurrence guards in ``class_occurrences`` (± window + token subset).

They each keep their OWN tokenizer (the ingest path fuzzes the full normalized
title; the render path filters stopwords; the class path strips paren/clock/day
tokens) and their OWN thresholds — those are genuinely different signals. What
they share, and what drifted, is the low-level arithmetic: the default window
constant, start-time-in-minutes, the same-occurrence window test, and the
subset token match. Centralizing just those keeps the numbers visible in one
place so they can't silently diverge again.

``series.build_series_index`` deliberately does NOT use these: it groups by an
EXACT natural key ``(normalized_title, location, HH:MM)``, not a fuzzy window,
so it has nothing to share here.
"""

from __future__ import annotations

from datetime import time

# Default ± tolerance (minutes) for treating two start times as the same
# occurrence. ``dedup`` reads an env override off this default for its ingest
# window; ``class_occurrences`` uses the default directly.
DEFAULT_DEDUP_TIME_WINDOW_MINUTES = 30


def start_minutes(t: time) -> int:
    """Minutes since midnight for a start time."""
    return t.hour * 60 + t.minute


def times_within_window(
    a: time | None,
    b: time | None,
    *,
    window_minutes: int = DEFAULT_DEDUP_TIME_WINDOW_MINUTES,
    missing_is_wildcard: bool,
) -> bool:
    """Two start times describe the same occurrence within ``window_minutes``.

    ``missing_is_wildcard`` sets the policy when EITHER time is ``None``: ``True``
    means a missing time matches anything (the class-occurrence / ingest
    contract — a TBD-time row must still suppress its timed twin); ``False`` means
    a missing time never matches (the cross-source same-session pass, which
    requires two real timed rows).
    """
    if a is None or b is None:
        return missing_is_wildcard
    return abs(start_minutes(a) - start_minutes(b)) <= window_minutes


def tokens_subset_match(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> bool:
    """Both token sets non-empty and one is a subset of the other.

    The tight "same activity, differently-worded title" signal: ``{swim}`` ⊆
    ``{swim, family}`` collapses, but ``{cosmic, bowling}`` vs ``{humane, bowl}``
    (neither a subset of the other) stays apart.
    """
    return bool(a) and bool(b) and (a <= b or b <= a)


# Title words too generic to imply "same session" on their own — shared by the
# render-time cross-source pass (``dedup._significant_title_tokens``) and the
# class-occurrence qualifier-stripped guard (2026-07-22), one list so the two
# can't drift. "Free Family Swim" / "Open Swim" both reduce to ``{"swim"}``;
# "Mini Bakers" / "Sports Camp" share nothing significant.
GENERIC_TITLE_QUALIFIERS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "free", "day", "days", "night", "nights",
    "family", "kids", "open", "lake", "havasu", "city", "event", "events",
    "class", "classes", "series", "summer", "winter", "spring", "fall", "live",
    "music", "party", "sponsored", "annual", "session", "sessions", "community",
    "public", "all", "ages", "adult", "adults", "youth", "senior", "seniors",
})


def significant_tokens(tokens: frozenset[str] | set[str]) -> frozenset[str]:
    """Drop the generic qualifier words — what's left names the activity."""
    return frozenset(t for t in tokens if t not in GENERIC_TITLE_QUALIFIERS)
