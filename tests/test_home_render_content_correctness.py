"""GET /home rendered-content correctness guard rails (PR 1).

Unit-level coverage of ``_category_label`` and ``_card_blurb`` lives in
``tests/test_home_queries_lane_a.py``. This module covers the
*rendered output* contract -- the Part E acceptance criteria #1 and #2:

  1. No underscore-shaped slug appears in any user-visible text on /home.
  2. No card blurb contains http, a newline, or an ISO date.

Why both layers: the unit helpers are correct today, but a future
template change could bypass them (e.g. printing ``provider.category``
directly into the meta line instead of going through the builder). The
rendered-output assertions are the seatbelt against that class of
regression.

Strategy: render /home through TestClient, parse with BeautifulSoup,
isolate the .blurb / .meta / .name / .footer elements, and assert no
forbidden pattern appears in the visible card text. Sentinel patterns
in stylesheet href/src are ignored.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.main import app

# Card-text classes the user reads when scanning the home page. These
# are the only places where forbidden patterns matter; URLs in href
# and src attributes are out of scope.
CARD_TEXT_SELECTORS = (
    "p.blurb",
    "h3.name",
    "div.meta",
    "div.footer",
)

# Forbidden patterns in card text.
_UNDERSCORE_SLUG = re.compile(r"[a-z]+_[a-z]+")  # food_drink, religion_community, ...
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_HTTP = re.compile(r"https?://", re.IGNORECASE)
_LABELLED_FIELD = re.compile(
    r"\b(Date|Time|Venue|Organizer|Categories?|Tags?|Cost|Price|Phone|Website|URL|Link)\s*:",
    re.IGNORECASE,
)


def _card_text_blocks(html: str) -> list[str]:
    """Return the visible text of every card body element on the page."""
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[str] = []
    for sel in CARD_TEXT_SELECTORS:
        for node in soup.select(sel):
            blocks.append(node.get_text(" ", strip=True))
    return blocks


def test_home_renders_200() -> None:
    """Smoke: /home must render before any other assertion has meaning."""
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200


def test_no_underscore_slugs_in_card_text() -> None:
    """C1 acceptance: no enum-shaped strings (food_drink, etc.) reach the surface."""
    with TestClient(app) as client:
        r = client.get("/home")
    blocks = _card_text_blocks(r.text)
    offenders: list[tuple[str, str]] = []
    for block in blocks:
        m = _UNDERSCORE_SLUG.search(block)
        if m:
            offenders.append((m.group(0), block))
    assert not offenders, (
        "Found underscore-shaped slug(s) in rendered card text. "
        "Run the category through _category_label or LEGACY_PROVIDER_CATEGORY_LABELS. "
        f"Offenders: {offenders[:5]}"
    )


def test_no_http_in_card_blurbs() -> None:
    """C3 acceptance: card blurbs never contain raw URLs."""
    with TestClient(app) as client:
        r = client.get("/home")
    soup = BeautifulSoup(r.text, "html.parser")
    offenders: list[str] = []
    for node in soup.select("p.blurb"):
        text = node.get_text(" ", strip=True)
        if _HTTP.search(text):
            offenders.append(text)
    assert not offenders, (
        "Found http/https in rendered card blurb text. _card_blurb's URL "
        f"scrub should have stripped these. Offenders: {offenders[:5]}"
    )


def test_no_iso_date_in_card_blurbs() -> None:
    """C3 acceptance: card blurbs never contain raw ISO dates (YYYY-MM-DD)."""
    with TestClient(app) as client:
        r = client.get("/home")
    soup = BeautifulSoup(r.text, "html.parser")
    offenders: list[str] = []
    for node in soup.select("p.blurb"):
        text = node.get_text(" ", strip=True)
        if _ISO_DATE.search(text):
            offenders.append(text)
    assert not offenders, (
        "Found ISO-formatted date in rendered card blurb text. The date "
        "should be rendered through _format_time/_meta_line_for_event "
        f"instead. Offenders: {offenders[:5]}"
    )


def test_no_labelled_field_prefix_in_card_blurbs() -> None:
    """C4 acceptance: no 'Date:', 'Venue:', 'Organizer:' style prefixes in blurbs."""
    with TestClient(app) as client:
        r = client.get("/home")
    soup = BeautifulSoup(r.text, "html.parser")
    offenders: list[str] = []
    for node in soup.select("p.blurb"):
        text = node.get_text(" ", strip=True)
        if _LABELLED_FIELD.search(text):
            offenders.append(text)
    assert not offenders, (
        "Found a labelled-field prefix (Date: / Venue: / etc.) in rendered "
        "card blurb text. _LABEL_LINE_RE in queries.py should have stripped "
        f"these at builder time. Offenders: {offenders[:5]}"
    )


def test_no_555_01xx_placeholder_phone_rendered() -> None:
    """Phone scrubber acceptance: NANP 555-01XX reserved range never renders as tel."""
    with TestClient(app) as client:
        r = client.get("/home")
    soup = BeautifulSoup(r.text, "html.parser")
    offenders: list[str] = []
    placeholder_re = re.compile(r"\(?\d{3}\)?[\s\-]?555[\s\-]?01\d{2}")
    for node in soup.select("a[href^='tel:']"):
        text = node.get_text(" ", strip=True)
        href = node.get("href", "")
        if placeholder_re.search(text) or placeholder_re.search(href):
            offenders.append(f"{text!r} ({href!r})")
    assert not offenders, (
        "Found NANP-reserved 555-01XX placeholder phone in rendered output. "
        f"_format_phone should have returned None. Offenders: {offenders[:5]}"
    )
