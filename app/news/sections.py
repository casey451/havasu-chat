"""WS13 / M18 — local-first news sectioning.

The `/news` page and the homepage news module mixed genuine Havasu reporting with
the syndicated national wire and lifestyle filler the News-Herald republishes, so
"Pringles debuts Pop Dog Buns" and "California woman killed by Florida alligator"
ran under a "Havasu headlines" H1. This classifier routes each headline into a
section by its source and URL path — the heuristics the audit found are clean:

  * ``lhc_newsflash`` (City of Lake Havasu) → **City Hall**
  * ``river_scene_news`` / ``mcso_press`` (local magazine / sheriff) → **Local**
  * News-Herald and any wire source, by URL path:
      ``/opinion/`` → **Opinion**
      ``/nation``, ``/lifestyle/``, ``/entertainment/``, ``/business/`` → **Beyond Havasu**
      otherwise → **Local**

The homepage module surfaces Local + City Hall (never Beyond); `/news` can tab
across all four. This module is pure — it never touches the DB.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

SECTION_LOCAL = "local"
SECTION_CITY_HALL = "city_hall"
SECTION_OPINION = "opinion"
SECTION_BEYOND = "beyond"

SECTION_LABELS: dict[str, str] = {
    SECTION_LOCAL: "Local",
    SECTION_CITY_HALL: "City Hall",
    SECTION_OPINION: "Opinion",
    SECTION_BEYOND: "Beyond Havasu",
}

# Wire/syndication sections that never belong in the homepage "Local news" module.
# Opinion joins Beyond here: the News-Herald's op-eds and letters ("Dave Eaton:
# World Cup vs. TDS") are not Havasu reporting and rode onto the front page.
NON_LOCAL_SECTIONS = frozenset({SECTION_BEYOND, SECTION_OPINION})

_CITY_SOURCES = frozenset({"lhc_newsflash"})
_LOCAL_SOURCES = frozenset({"river_scene_news", "mcso_press"})

# URL-path markers (substring match on the lowercased path).
_OPINION_MARKERS = ("/opinion", "/letters-to-the-editor", "/columns/")
_BEYOND_MARKERS = (
    "/nation", "/national", "/nation-world", "/world/", "/lifestyle/",
    "/entertainment/", "/business/", "/wire/", "/ap/", "/celebrity",
)


def news_section(source: str | None, url: str | None, title: str | None = None) -> str:
    """Route a headline into one of the four sections (never raises)."""
    src = (source or "").strip().lower()
    if src in _CITY_SOURCES:
        return SECTION_CITY_HALL
    if src in _LOCAL_SOURCES:
        return SECTION_LOCAL
    try:
        path = urlparse(url or "").path.lower()
    except (ValueError, TypeError):
        path = ""
    if any(m in path for m in _OPINION_MARKERS):
        return SECTION_OPINION
    if any(m in path for m in _BEYOND_MARKERS):
        return SECTION_BEYOND
    return SECTION_LOCAL


def is_trusted_local_source(source: str | None) -> bool:
    """True for sources that are inherently local (City Hall / River Scene /
    Sheriff), whose items belong on the homepage regardless of headline text."""
    src = (source or "").strip().lower()
    return src in _CITY_SOURCES or src in _LOCAL_SOURCES


# A headline routed to Local (the catch-all) only earns a homepage slot when it
# names Havasu proper or sits under a local URL path. Without this, the
# News-Herald's bare-URL national wire — "Unstable NYC building…", "Half of
# Americans support placing the Ten Commandments…" — inherits the Local default
# and rides onto the front page. `/news` keeps the full Local tab (this gate is
# homepage-only); the immediate-region strip (Parker/Kingman/Bullhead/Needles)
# is handled separately by the store's word-boundary region labeller.
_LOCAL_PATH_MARKERS = ("/news/local", "/local/")
_LOCAL_SIGNAL_RE = re.compile(r"\b(lake havasu|havasu|lhc|london bridge|mohave)\b", re.IGNORECASE)


def has_local_signal(
    url: str | None, title: str | None = None, summary: str | None = None
) -> bool:
    """True when a headline names Havasu proper or sits under a local URL path."""
    try:
        path = urlparse(url or "").path.lower()
    except (ValueError, TypeError):
        path = ""
    if any(m in path for m in _LOCAL_PATH_MARKERS):
        return True
    return bool(_LOCAL_SIGNAL_RE.search(f"{path} {title or ''} {summary or ''}"))
