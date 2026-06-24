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
_DAYS = (
    r"Mon|Tue|Tues|Wed|Weds|Thu|Thur|Thurs|Fri|Sat|Sun|"
    r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
)
# Trailing baked-in date. Matches the short form ("June 25") AND the long form
# with an optional leading weekday, ordinal day, a 4-digit year, and a trailing
# bang ("Friday June 12th 2026!"). Anchored at end so an internal date is safe.
_TRAILING_DATE_RE = re.compile(
    rf"\s*[-–—,:]?\s*(?:(?:{_DAYS})\.?,?\s+)?(?:{_MONTHS})\.?\s+"
    rf"\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\s*[!.]*\s*$",
    re.IGNORECASE,
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


# Venue labels arrive from scrapers as a mix of clean names and full mashed
# addresses ("Rotary Park 1400 S. Smoketree Ave. Lake Havasu City, AZ. 86403",
# "Lake Havasu City Aquatic Center, 100 Park Avenue, Room 153/154, …"). For
# display we keep the leading NAME and drop the trailing street address: cut at
# the first ", <number>…" (comma then street number) or the first " <3+ digit>…"
# run (a bare street number). Conservative — a name with a comma+word
# ("Elite Martial Arts, Inc.") or a 1-2 digit number ("Pier 66") is untouched,
# and a label that is ONLY an address (starts with the number) is left as-is
# (there is no name to keep). Future scrapes get the same cleanup for free.
_VENUE_ADDR_CUT_RE = re.compile(r"\s*,\s*\d.*$|\s+\d{3,}\b.*$")

# Some venues arrive from scrapers as ONLY a street address (no name to keep), so
# the address-strip can't help. This maps the known bare-address venues to their
# real name (verified 2026-06-23). Keyed by the lowercased street-number prefix;
# also rewrites a same-address label a second source emitted (e.g. river_scene's
# "2146 McCulloch Blvd" for GraceArts Live), so the two feeds read consistently.
_VENUE_ADDR_TO_NAME: dict[str, str] = {
    "2134 mcculloch": "Havasu Lanes",
    "2144 mcculloch": "Downtown Lake Havasu",
    "2146 mcculloch": "GraceArts Live",
    "3516 mcculloch": "Abundant Grace Church",
}

# Known scraped misspellings in venue/location text, corrected as whole-word
# substitutions wherever a venue label is cleaned for display — so a source typo
# is fixed on the calendar AND survives a re-scrape (the underlying DB row may
# still carry the typo; a gated data correction handles that separately). Keep
# this TIGHT: only unambiguous, verified misspellings of real local venues, so it
# can never mangle a legitimately-spelled name.
_VENUE_SPELLING_FIXES: dict[str, str] = {
    "roatary": "Rotary",  # "Roatary Community Ball Fields" (Splash Bash, Jul 25)
}
_VENUE_SPELLING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _VENUE_SPELLING_FIXES) + r")\b",
    re.IGNORECASE,
)


def fix_venue_spelling(name: str) -> str:
    """Correct known scraped venue misspellings (whole-word, case-insensitive)."""
    return _VENUE_SPELLING_RE.sub(lambda m: _VENUE_SPELLING_FIXES[m.group(0).lower()], name)


def clean_venue_label(name: str | None) -> str | None:
    """Tidy a venue label: name a known bare-address venue, else drop a trailing
    street address, keeping the leading name. Known scraped misspellings are
    corrected last so the display name is always right."""
    if not name:
        return name
    low = name.strip().lower()
    for prefix, real in _VENUE_ADDR_TO_NAME.items():
        if low.startswith(prefix):
            return real
    cleaned = _VENUE_ADDR_CUT_RE.sub("", name).strip().rstrip(",").strip()
    return fix_venue_spelling(cleaned or name)
