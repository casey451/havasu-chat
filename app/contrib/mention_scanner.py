"""Extract candidate local-entity mentions from Tier 3 response text (Phase 5.5)."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.llm_mention_store import create_mention

logger = logging.getLogger(__name__)

STOP_PHRASES: frozenset[str] = frozenset(
    (
        "Lake Havasu",
        "Lake Havasu City",
        "Havasu",
        "Havasu Chat",
        "Arizona",
        "United States",
        "USA",
        "North America",
        "West Coast",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "Google",
        "Google Search",
        "YouTube",
        "Lake Havasu CVB",
        "Convention Visitors Bureau",
    )
)
STOP_PHRASES_LC: frozenset[str] = frozenset(s.lower() for s in STOP_PHRASES)

_TITLE_PHRASE = re.compile(
    r"\b[A-Z][a-zA-Z0-9&']+(?:[\s-][A-Z][a-zA-Z0-9&']+){1,4}\b",
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass
class MentionCandidate:
    mentioned_name: str
    context_snippet: str


def _strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", text or "")


def _trim_trailing_punct(phrase: str) -> str:
    return phrase.rstrip(".,;:!?\"'").strip()


def _context_snippet(text: str, start: int, end: int, radius: int = 60) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi].strip()


def scan_tier3_response(response_text: str) -> list[MentionCandidate]:
    """Extract title-case entity candidates from a Tier 3 response. Deduped within response."""
    raw = response_text or ""
    cleaned = _strip_urls(raw)
    seen: set[str] = set()
    out: list[MentionCandidate] = []
    for m in _TITLE_PHRASE.finditer(cleaned):
        phrase = m.group(0)
        name = _trim_trailing_punct(phrase)
        if len(name) < 6:
            continue
        key = name.lower()
        if key in STOP_PHRASES_LC:
            continue
        if key in seen:
            continue
        seen.add(key)
        snippet = _context_snippet(cleaned, m.start(), m.end())[:500]
        out.append(MentionCandidate(mentioned_name=name[:300], context_snippet=snippet))
    return out


def scan_and_save_mentions(
    chat_log_id: str,
    response_text: str,
    session_factory: Callable[[], Session],
) -> None:
    """Background task: scan Tier 3 text and persist mentions (best-effort; never raises)."""
    try:
        db = session_factory()
        try:
            for c in scan_tier3_response(response_text):
                create_mention(db, chat_log_id, c.mentioned_name, c.context_snippet)
        finally:
            db.close()
    except Exception:
        logger.exception("scan_and_save_mentions failed chat_log_id=%s", chat_log_id)
