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
NON_LOCAL_SECTIONS = frozenset({SECTION_BEYOND})

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
