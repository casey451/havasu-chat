"""Chat → interactive calendar deep-links (A4 / Phase E build half).

The chat events-intent path renders an inline component (``day_agenda`` for a
single day, ``week_strip`` for a 7-day window). A4 lands those answers on the
interactive, filtered ``/events-ui`` calendar (Today / Week / Month views, plus
the ``?family=1`` kid/family toggle) by attaching a ``calendar_url`` deep-link
derived from the detected window — so an events query opens the live calendar
instead of dead-ending on the inline list.

Pure + dependency-free so it is trivially unit-testable and safe to call from
the hot chat path.
"""

from __future__ import annotations

from typing import Any

#: Chat component types that represent an events/calendar answer and therefore
#: get a ``calendar_url`` deep-link. ``card_row`` is intentionally excluded — it
#: is reused for non-events business rows, so labeling it could mis-link.
EVENTS_CALENDAR_COMPONENTS: frozenset[str] = frozenset({"day_agenda", "week_strip"})

#: Event-intent ``when`` values that map to the 7-day Week view (the closest
#: interactive view that contains them).
_WEEK_WHENS: frozenset[str] = frozenset(
    {"week", "this_week", "next_week", "weekend", "this_weekend", "tomorrow"}
)
_MONTH_WHENS: frozenset[str] = frozenset({"month", "this_month"})

_FAMILY_KEYWORDS: tuple[str, ...] = (
    "kid",
    "kids",
    "family",
    "families",
    "children",
    "child",
    "toddler",
)


def events_calendar_url(when: str | None, *, family: bool = False) -> str:
    """The ``/events-ui`` URL for an events-intent ``when``.

    ``today`` / ``tonight`` / unknown → the default Today view; ``tomorrow`` /
    weekend / week → the Week view (the smallest interactive view that contains
    them, since ``/events-ui`` has no weekend-only view); month → the Month view.
    ``family=True`` appends the ``?family=1`` kid/family toggle.
    """
    w = (when or "").strip().lower()
    if w in _MONTH_WHENS:
        url = "/events-ui?view=month"
    elif w in _WEEK_WHENS:
        url = "/events-ui?view=week"
    else:  # today / tonight / unknown
        url = "/events-ui"
    if family:
        url += ("&" if "?" in url else "?") + "family=1"
    return url


def is_family_query(query: str | None) -> bool:
    """Whether ``query`` reads as a kid/family events ask (drives ``?family=1``)."""
    low = (query or "").lower()
    return any(kw in low for kw in _FAMILY_KEYWORDS)


def attach_calendar_link(
    component_type: str,
    component_data: dict[str, Any],
    *,
    when: str | None,
    query: str | None = None,
) -> dict[str, Any]:
    """Return ``component_data`` with a ``calendar_url`` deep-link added when the
    component is an events component AND an events ``when`` is known; otherwise
    return it unchanged.

    Pure and non-mutating (returns a shallow copy when it adds the key), so it is
    safe to call unconditionally on the hot chat path. Dormant for every
    non-events answer — the inline component renders exactly as before.
    """
    if not when or component_type not in EVENTS_CALENDAR_COMPONENTS:
        return component_data
    return {
        **component_data,
        "calendar_url": events_calendar_url(when, family=is_family_query(query)),
    }
