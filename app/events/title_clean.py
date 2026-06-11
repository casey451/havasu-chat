"""Display-grade event-title cleaning (fixlist §2.3).

The parks-rec / aggregator imports pack junk into event titles that should never
be user-facing: numeric room/course codes ("Fit & Flex (155) Stephanie"),
instructor first names ("Motion & Mobility Margie", "Tai Chi Vince"), the event
date ("Pickleball Round Robin June 25"), leading/trailing time tokens
("9 AM Beginner Pilates"), day-of-week parentheticals ("(Wed/Fri)"), a trailing
"at {venue}", and — worst — whole description blurbs ("Free Family Swim
Sponsored by: Abundant Grace Church Event is limited to the first 400 people").

``clean_event_title`` strips that junk CONSERVATIVELY — it only removes patterns
that are unambiguously not part of a real title, so a genuine distinguishing
word is never lost, and it never returns empty (falls back to the original).
Same function is used by the ingest path (new rows land clean) and the
``scripts/clean_event_titles.py`` backfill (existing rows repaired) — the
``clean_venue_shape`` pattern, applied to titles.
"""

from __future__ import annotations

import re

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
)

# Recurring instructor first names the aquatics/parks source appends to class
# titles. Curated + easily extended. Only an EXACT trailing token match (with at
# least one other word remaining) is stripped, so a real title word is safe.
INSTRUCTOR_NAMES: frozenset[str] = frozenset(
    {"margie", "vince", "stephanie", "kj", "renae", "danica"}
)

# Everything from a sponsor/registration/"limited to" marker onward is body
# prose, not title. DOTALL so it eats a multi-sentence tail.
_DESCRIPTION_TAIL_RE = re.compile(
    r"\s*(?:[-–—:]\s*)?(?:sponsored by|presented by|brought to you by|"
    r"hosted by|in partnership with|event is limited|limited to|register(?:ation)?"
    r"\s+(?:at|by|opens)|tickets?\s+(?:at|on sale)|rsvp|more info|details? at)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
_PAREN_CODE_RE = re.compile(r"\s*\(\s*\d+\s*\)")  # "(155)"
_DAY_PARENS_RE = re.compile(
    r"\s*\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[A-Za-z0-9/&,:.\s]*\)", re.IGNORECASE
)
_TIME_RANGE_RE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.IGNORECASE
)
_TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.IGNORECASE)
_TIME_PARENS_RE = re.compile(r"\s*\(\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*\)", re.IGNORECASE)
_TRAILING_DATE_RE = re.compile(
    rf"\s*[-–—,:]?\s*(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\s*$", re.IGNORECASE
)
_TRAILING_PREP_RE = re.compile(r"\s+(?:with|w/|by|feat\.?|ft\.?)\s*$", re.IGNORECASE)
_WS_RE = re.compile(r"\s{2,}")
_TRIM_CHARS = " -–—,:;|"


def clean_event_title(title: str | None, *, location_name: str | None = None) -> str:
    """Strip non-title junk for display. Conservative; never returns empty."""
    if not title:
        return title or ""
    original = str(title).strip()
    t = original

    # 1. Cut sponsor/description/registration tails.
    t = _DESCRIPTION_TAIL_RE.sub("", t).strip()
    # 2. Numeric paren room/course codes "(155)".
    t = _PAREN_CODE_RE.sub("", t)
    # 3. Day-of-week parentheticals "(Wed/Fri)", "(Wed 4 PM)".
    t = _DAY_PARENS_RE.sub("", t)
    # 4. Time parentheticals "(6 AM)", then ranges, then bare times.
    t = _TIME_PARENS_RE.sub("", t)
    t = _TIME_RANGE_RE.sub(" ", t)
    t = _TIME_RE.sub(" ", t)
    # 5. Trailing month-day date ("June 25").
    t = _TRAILING_DATE_RE.sub("", t).strip(_TRIM_CHARS)
    # 6. Redundant trailing "at {venue}".
    if location_name and location_name.strip():
        loc = re.escape(location_name.strip())
        t = re.sub(rf"\s+at\s+{loc}\s*$", "", t, flags=re.IGNORECASE).strip()
    # 7. Trailing known-instructor first name (+ any dangling "with"/"by").
    parts = t.split()
    if len(parts) >= 2 and parts[-1].lower().strip(".,") in INSTRUCTOR_NAMES:
        t = " ".join(parts[:-1])
        t = _TRAILING_PREP_RE.sub("", t)
    # 8. Tidy whitespace + edge separators.
    t = _WS_RE.sub(" ", t).strip(_TRIM_CHARS)

    return t or original
