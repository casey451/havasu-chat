"""Clean user-facing event descriptions (mirror of ``title_clean`` / ``field_recovery``).

Aggregator + scraper ingestion historically wrote non-prose into the user-facing
``Event.description`` field, which then rendered as "no info" on the event detail
page. Two failure modes were observed in production:

* **Metadata-as-description** — the body was only ``label: value`` scaffolding
  (``Venue:`` / ``Address:`` / ``Organizer:`` / ``Categories:`` / ``Coordinates:``
  / ``Image:`` lines, plus a redundant date/time heading). RiverScene and Go Lake
  Havasu both did this when the source page had no real prose.
* **Auto-generated placeholder** — a synthesised sentence such as
  "<title> - community event in Lake Havasu City. See source listing for details."
  that satisfied a length check but told the reader nothing.

:func:`clean_event_description` strips that scaffolding and those placeholder
sentences, returning the real prose or ``""`` when nothing real remains. An empty
result is intentional: the event detail template already renders a structured
"sparse event" card (When / Where + organizer link) for description-less events,
which is more honest and more useful than a fabricated sentence.

The same function is used by the ingest/approval path (new rows land clean) and
by ``scripts/clean_event_descriptions.py`` (existing rows repaired) — exactly the
shared-helper pattern used by ``title_clean`` and ``field_recovery``.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

# Minimum length of genuine prose worth showing. Below this the sparse-event card
# (When/Where) is a better experience than a one-liner, so we return "".
_MIN_REAL_PROSE = 20

# ``label:`` lines that are structured metadata, never user-facing prose. Anchored
# at line start so a real sentence that merely contains "time:" mid-clause is safe.
_METADATA_LINE_RE = re.compile(
    r"^[ \t]*(?:venue|address|location|organizer|organiser|categories|category|"
    r"coordinates|image|photo|date|time|when|where|cost|price|admission|fee|fees|"
    r"event page|event link|source|tickets?|website|facebook|instagram)[ \t]*:.*$",
    re.IGNORECASE,
)

# A standalone date heading line, e.g. "Saturday, June 21" or
# "June 21 - June 22, 2026" (ingest scaffolding duplicates the structured columns).
_MONTHS = (
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec"
)
_DATE_HEADING_RE = re.compile(
    rf"^[ \t]*(?:(?:mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)[a-z]*,?\s+)?"
    rf"(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*[-–—to]+\s*"
    rf"(?:(?:{_MONTHS})\s+)?\d{{1,2}})?(?:,?\s*\d{{4}})?[ \t]*$",
    re.IGNORECASE,
)

# A line that is nothing but a bare URL.
_BARE_URL_RE = re.compile(r"^[ \t]*https?://\S+[ \t]*$", re.IGNORECASE)

# Auto-generated placeholder sentences (legacy + current). Removed wherever they
# appear so the remaining real prose (if any) survives.
_PLACEHOLDER_SENTENCE_RES = (
    re.compile(r"[^.\n]*\bcommunity event in lake havasu city\b[^.\n]*\.?", re.IGNORECASE),
    re.compile(r"\bsee (?:the )?source listing for details\.?", re.IGNORECASE),
    re.compile(r"\bdetails? (?:are )?(?:still )?(?:being gathered|to follow|tba)\b[^.\n]*\.?", re.IGNORECASE),
)


def _strip_placeholder_sentences(text: str) -> str:
    for rx in _PLACEHOLDER_SENTENCE_RES:
        text = rx.sub(" ", text)
    return text


def clean_event_description(raw: str | None) -> str:
    """Return real user-facing prose from ``raw``, or ``""`` when none remains.

    Conservative: only removes lines/sentences that are unambiguously ingest
    scaffolding or known placeholders; genuine prose is never altered.
    """
    if not raw:
        return ""
    text = _strip_placeholder_sentences(str(raw))
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _METADATA_LINE_RE.match(line):
            continue
        if _DATE_HEADING_RE.match(line):
            continue
        if _BARE_URL_RE.match(line):
            continue
        kept.append(line)
    # Collapse runs of blank lines, trim.
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    # Require some genuine prose (a couple of words), else hand off to the
    # sparse-event card.
    if len(out) < _MIN_REAL_PROSE or " " not in out.strip():
        return ""
    return out


def is_synthetic_placeholder(
    raw: str | None,
    *,
    title: str | None = None,
    location_name: str | None = None,
    start_date: date | None = None,
) -> bool:
    """True when ``raw`` is an auto-generated placeholder with no real prose.

    Catches both the legacy "<title> - community event …" form and the
    "<title> at <location> on <Mon DD, YYYY>." synthesis, by checking whether any
    real prose survives :func:`clean_event_description`. The ``title`` / ``location``
    / ``date`` hints let the backfill recognise the exact synthesised sentence even
    if its wording drifts.
    """
    if not raw:
        return False
    text = str(raw).strip()
    # Exact-match the "<title> at <location> on <Mon DD, YYYY>." synthesis that the
    # ingest fallback used to emit, using the row's own fields to rebuild it.
    if title and start_date:
        loc = (location_name or "").strip() or "Lake Havasu City"
        synth = f"{title.strip()} at {loc} on {start_date.strftime('%b %d, %Y')}."
        if _norm(text) == _norm(synth):
            return True
        synth2 = f"{title.strip()} at {loc} on an upcoming date."
        if _norm(text) == _norm(synth2):
            return True
    if clean_event_description(raw):
        return False
    # Nothing real survived cleaning -> it was scaffolding/placeholder.
    return True


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# --- URL + location helpers (shared so every source validates identically) ----

# Hosts that are dead/placeholder for event click-throughs. ``havasuchat.com`` is
# the pre-rename domain that now fails to resolve for event pages.
DEAD_EVENT_LINK_HOSTS = frozenset({"havasuchat.com", "www.havasuchat.com"})


def valid_event_url(raw: str | None) -> str | None:
    """Return a clean http(s) click-through URL, or ``None`` when invalid.

    Rejects: non-http(s) schemes, an ``@`` in the authority (an email address used
    as a URL, e.g. ``https://info@ijsba.com/`` seen in production), hosts with no
    dot, and known-dead placeholder hosts.
    """
    if not isinstance(raw, str):
        return None
    url = raw.strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    parts = urlsplit(url)
    netloc = parts.netloc
    if not netloc or "@" in netloc:
        return None
    host = netloc.split(":")[0].lower()
    if "." not in host or host in DEAD_EVENT_LINK_HOSTS:
        return None
    return url


# Insert the missing space in a glued "<letter>Lake Havasu City" (the
# "Blvd NLake Havasu City" production glitch) without touching internal caps like
# "McCulloch".
_GLUED_CITY_RE = re.compile(r"([A-Za-z])(Lake Havasu City)")
_NO_ADDRESS_RE = re.compile(r"\s*No Address Available\s*$", re.IGNORECASE)


def normalize_location_text(raw: str | None) -> str:
    """Tidy a venue/location string: fix the glued-city glitch, drop the
    'No Address Available' tail, collapse whitespace."""
    if not raw:
        return ""
    text = _GLUED_CITY_RE.sub(r"\1 \2", str(raw))
    text = _NO_ADDRESS_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()
