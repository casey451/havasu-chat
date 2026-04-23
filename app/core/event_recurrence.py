from __future__ import annotations

import re
from typing import Any

# Multiword phrases: substring match in combined blob.
_RECURRENCE_PHRASES: tuple[str, ...] = (
    "every saturday",
    "every sunday",
    "every friday",
    "farmers market",
    "first friday",
)

# Single-token patterns — whole-word only (avoids e.g. "irregular" matching "regular").
_TOKENS: frozenset[str] = frozenset(
    {
        "every",
        "weekly",
        "daily",
        "monthly",
        "recurring",
        "ongoing",
        "series",
        "regular",
    }
)


def _word_pat(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)


def event_text_blob(
    title: str,
    description: str,
    tags: list[str] | None,
) -> str:
    t = (title or "").lower()
    d = (description or "").lower()
    tag_s = " ".join(str(x).lower() for x in (tags or []))
    return f"{t} {d} {tag_s}"


def is_recurring_heuristic(text_blob: str) -> bool:
    """Return True if any built-in pattern matches the combined lowercase text."""
    b = (text_blob or "").lower()
    for phrase in _RECURRENCE_PHRASES:
        if phrase in b:
            return True
    for w in _TOKENS:
        if _word_pat(w).search(b):
            return True
    return False


def is_recurring_from_event_model(event: Any) -> bool:
    """Convenience: blob from a SQLAlchemy Event (or any object with title/description/tags)."""
    tags = getattr(event, "tags", None)
    if tags is None:
        tags = []
    return is_recurring_heuristic(
        event_text_blob(
            str(getattr(event, "title", "") or ""),
            str(getattr(event, "description", "") or ""),
            list(tags) if not isinstance(tags, list) else tags,
        )
    )
