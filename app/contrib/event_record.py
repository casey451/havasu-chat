"""Shared EventRecord + schema.org JSON-LD helpers for event-source scrapers.

The aggregator/event sources (allevents, bandsintown, eventbrite, senior_center,
movies) all normalise to :class:`EventRecord`. These sources heavily overlap
with golakehavasu/RiverScene on marquee events, so the build rule is: dedupe on
the normalised ``(title, start date, venue)`` key.

At ingestion time those records route through the existing event contribution
flow + ``app.events.dedup.find_duplicate`` (the cross-source guard). This module
provides the *same* normalised key so a dry-run can show within-batch dedup and
the eventual loader can dedupe cross-source consistently. No DB access here.
"""

from __future__ import annotations

import html as html_mod
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.events.scrapers.base import normalize_event_title


@dataclass
class EventRecord:
    source: str
    title: str
    start_date: date | None
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    url: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    image_url: str | None = None
    raw: dict = field(default_factory=dict)

    def normalized_dedupe_key(self) -> str:
        """Normalised (title, start date, venue) — the cross-source dedupe key."""
        title = normalize_event_title(self.title)
        day = self.start_date.isoformat() if self.start_date else "?"
        venue = re.sub(r"[^a-z0-9]+", " ", (self.venue_name or "").lower()).strip()
        return f"{title}|{day}|{venue}"


def dedupe_within(records: list[EventRecord]) -> list[EventRecord]:
    """Drop within-batch duplicates by the normalised key (keep first seen)."""
    seen: set[str] = set()
    out: list[EventRecord] = []
    for rec in records:
        key = rec.normalized_dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return dateutil_parser.parse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError, TypeError):
        return None


def _iter_jsonld_nodes(data: Any):
    """Yield dict nodes from a JSON-LD blob, walking @graph and lists."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                yield from _iter_jsonld_nodes(item)
        # ItemList -> itemListElement -> {item: Event} / Event
        if data.get("@type") in ("ItemList",) and isinstance(data.get("itemListElement"), list):
            for el in data["itemListElement"]:
                if isinstance(el, dict):
                    yield from _iter_jsonld_nodes(el.get("item", el))
        yield data


def _type_is_event(node: dict) -> bool:
    t = node.get("@type")
    if isinstance(t, list):
        return any(str(x).endswith("Event") for x in t)
    return isinstance(t, str) and t.endswith("Event")


def _place_name_address(loc: Any) -> tuple[str | None, str | None]:
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, str):
        return loc.strip() or None, None
    if not isinstance(loc, dict):
        return None, None
    name = (loc.get("name") or "").strip() or None
    addr = loc.get("address")
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress"),
            addr.get("addressLocality"),
            addr.get("addressRegion"),
            addr.get("postalCode"),
        ]
        addr_str = ", ".join(p for p in parts if p) or None
    elif isinstance(addr, str):
        addr_str = addr.strip() or None
    else:
        addr_str = None
    return name, addr_str


def parse_jsonld_events(html: str, *, source: str) -> list[EventRecord]:
    """Extract schema.org Event nodes from a page's JSON-LD blocks."""
    soup = BeautifulSoup(html, "html.parser")
    records: list[EventRecord] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = script.string or script.get_text()
        if not raw_text:
            continue
        try:
            data = json.loads(raw_text)
        except (ValueError, TypeError):
            continue
        for node in _iter_jsonld_nodes(data):
            if not isinstance(node, dict) or not _type_is_event(node):
                continue
            name = html_mod.unescape((node.get("name") or "")).strip()
            if not name:
                continue
            organizer = node.get("organizer")
            if isinstance(organizer, list):
                organizer = organizer[0] if organizer else None
            organizer_name = (
                html_mod.unescape((organizer.get("name") or "").strip())
                if isinstance(organizer, dict)
                else (html_mod.unescape(organizer.strip()) if isinstance(organizer, str) else None)
            )
            start = parse_dt(node.get("startDate"))
            end = parse_dt(node.get("endDate"))
            venue_name, venue_addr = _place_name_address(node.get("location"))
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            offers_price, is_free = _parse_offers(node.get("offers"))
            records.append(
                EventRecord(
                    source=source,
                    title=name,
                    start_date=start.date() if start else None,
                    start_time=start.time().replace(tzinfo=None) if start else None,
                    end_date=end.date() if end else None,
                    end_time=end.time().replace(tzinfo=None) if end else None,
                    venue_name=html_mod.unescape(venue_name) if venue_name else venue_name,
                    venue_address=html_mod.unescape(venue_addr) if venue_addr else venue_addr,
                    url=(node.get("url") or "").strip() or None,
                    description=html_mod.unescape((node.get("description") or "")).strip() or None,
                    image_url=str(image).strip() if image else None,
                    raw={
                        "@type": node.get("@type"),
                        "organizer": organizer_name,
                        **({"offers_price": offers_price} if offers_price else {}),
                        **({"is_free": True} if is_free else {}),
                    },
                )
            )
    return records


def _parse_offers(offers: Any) -> tuple[str | None, bool]:
    """Pull a human price label + free flag from a schema.org ``offers`` node.

    Returns ``(price_label, is_free)``. ``price_label`` is a short "$N" string
    (currency-aware only for USD; bare numbers get a ``$`` prefix). Free is True
    when price is 0 / "0" / "Free". Handles a single Offer, a list of Offers, or a
    bare string."""
    if offers is None:
        return None, False
    if isinstance(offers, list):
        # Use the lowest-priced concrete offer for the label.
        prices: list[float] = []
        free = False
        label: str | None = None
        for o in offers:
            p, f = _parse_offers(o)
            if f:
                free = True
            if p:
                label = label or p
                m = re.search(r"\d+(?:\.\d+)?", p)
                if m:
                    prices.append(float(m.group(0)))
        if prices:
            lo = min(prices)
            return (f"${lo:g}", False)
        return (label, free)
    if isinstance(offers, str):
        s = offers.strip()
        if s.lower() in ("free", "0", "0.00"):
            return None, True
        m = re.search(r"\d+(?:\.\d+)?", s)
        return (f"${m.group(0)}" if m else None, False)
    if isinstance(offers, dict):
        price = offers.get("price")
        if price is None and isinstance(offers.get("priceSpecification"), dict):
            price = offers["priceSpecification"].get("price")
        if price is None:
            return None, False
        try:
            val = float(str(price).replace(",", ""))
        except (ValueError, TypeError):
            ps = str(price).strip()
            return (ps or None, False)
        if val == 0:
            return None, True
        return (f"${val:g}", False)
    return None, False


# --------------------------------------------------------------------------- #
# Fix 2.1 — recover start time + venue from aggregator description prose.
# --------------------------------------------------------------------------- #
# AllEvents.in index JSON-LD frequently lacks ``startDate``/``location`` but the
# description body states them, e.g.
#   "...at London Bridge Resort... at 5:00 pm MST"
#   "The OGs ... at 317 S Lake Havasu Ave ... 7:00 PM"
# These extractors pull a structured time + venue from that prose so the event
# lands with a real time/venue instead of "Time TBD" / "Lake Havasu City".

# A clock time like "5:00 PM", "10 am", "5:30 pm MST" (optional trailing tz).
_DESC_TIME_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\.?\b",
    re.IGNORECASE,
)


def extract_time_from_text(text: str | None) -> time | None:
    """Return the first clock time stated in prose, or ``None``.

    Recognises "5pm", "5:00 PM", "10 am", "5:30 pm MST". Picks the first match —
    aggregator bodies lead with the start time ("Doors at 5:00 PM"). Rejects
    out-of-range hours/minutes so a stray "13:99" can't produce a bad time.
    """
    if not text:
        return None
    for m in _DESC_TIME_RE.finditer(text):
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3).lower()
        if not (1 <= hour <= 12) or minute > 59:
            continue
        if ampm == "p" and hour != 12:
            hour += 12
        elif ampm == "a" and hour == 12:
            hour = 0
        return time(hour, minute)
    return None


# Venue connectors: the prose names the venue right after "at"/"@". We stop the
# venue at a sentence/clause boundary or at a stated time so we don't swallow the
# rest of the sentence. The pattern deliberately allows a leading street number
# ("317 S Lake Havasu Ave") so a bare-address venue is still recovered.
_DESC_VENUE_RE = re.compile(
    r"(?:\bat\b|@)\s+"
    r"([A-Z0-9][A-Za-z0-9'&.\- ]{2,79}?)"
    r"(?=\s*(?:[,.;:!?\n]|\bon\b|\bat\b|\bfrom\b|\bstarting\b|"
    r"\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?|$))",
)

# Tokens that, when they form the WHOLE captured venue, are not real venue names
# (a time-of-day word, a weekday, a generic preposition object).
_VENUE_STOPWORDS = frozenset(
    {
        "the", "a", "an", "noon", "midnight", "night", "all", "least",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "least", "last", "first", "this", "that",
    }
)


def extract_venue_from_text(text: str | None) -> str | None:
    """Return the venue named after "at"/"@" in prose, or ``None``.

    Tuned for AllEvents bodies such as "Join us at London Bridge Resort..." or
    "EMMANUEL Live at Hangar 24". Returns the first plausible venue (>=3 chars,
    not a bare stopword/time word). Conservative: a non-match yields ``None`` so
    the caller keeps its existing/default venue.
    """
    if not text:
        return None
    for m in _DESC_VENUE_RE.finditer(text):
        cand = re.sub(r"\s{2,}", " ", m.group(1)).strip(" -,.;:&")
        if len(cand) < 3:
            continue
        if cand.lower() in _VENUE_STOPWORDS:
            continue
        # Reject a capture that is only a time word run (e.g. "at 5" guarded above,
        # but "at PM" style leftovers).
        if re.fullmatch(r"(?:[ap]\.?m\.?|am|pm)", cand, re.IGNORECASE):
            continue
        return cand
    return None


# --------------------------------------------------------------------------- #
# Fix 2.2 — parse a human-readable price out of source text.
# --------------------------------------------------------------------------- #
_FREE_RE = re.compile(r"\b(free admission|free entry|no cover|free)\b", re.IGNORECASE)
# "$20", "$10-$25", "$10 - $25", "$5.00", "$1,000"
_PRICE_RANGE_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d{2})?\s*(?:[-–—]|to)\s*\$?\s?\d[\d,]*(?:\.\d{2})?"
)
_PRICE_SINGLE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")


def extract_cost_from_text(text: str | None) -> str | None:
    """Return a short human-readable price label, or ``None``.

    Prefers an explicit dollar figure / range ("$20", "$10-$25"); falls back to
    "Free" when the text clearly says free and carries no price. Mirrors the
    short-label shape ``Program.cost`` stores. Whitespace inside ranges is
    normalised so "$10 - $25" becomes "$10-$25".
    """
    if not text:
        return None
    rng = _PRICE_RANGE_RE.search(text)
    if rng:
        norm = re.sub(r"\s+", "", rng.group(0)).replace("–", "-").replace("—", "-")
        norm = norm.replace("to", "-")
        return norm
    single = _PRICE_SINGLE_RE.search(text)
    if single:
        return re.sub(r"\$\s+", "$", single.group(0))
    if _FREE_RE.search(text):
        return "Free"
    return None


# A leading price token a feed bled into the venue field: "$45 - Aquatic Center",
# "$10-$25 — Rotary Park", "Free | London Bridge", "$5 per person - Jane Camlin".
# Anchored at the start and REQUIRES a trailing separator, so a venue that merely
# contains a price ("$5 Pizza Place") or leads with a street number ("1420
# McCulloch") is never touched. An optional unit clause ("per person", "each",
# "/car") may sit between the price and the separator.
_COST_PREFIX_RE = re.compile(
    r"^\s*(?:\$\s?\d[\d,]*(?:\.\d{2})?"
    r"(?:\s*(?:[-–—]|to)\s*\$?\s?\d[\d,]*(?:\.\d{2})?)?|free)"
    r"(?:\s+per\s+\w+|\s+each|\s+pp|\s*/\s*\w+)?"
    r"\s*[-–—:|]\s*",
    re.IGNORECASE,
)


def strip_cost_prefix(venue: str | None) -> str | None:
    """Drop a leading price token a feed bled into a venue ("$45 - ", "Free | ").

    Returns the residual venue, or ``None`` when nothing real remains. Conservative:
    only a price/``free`` token *followed by a separator* is removed, so real venue
    names (a street number, or an embedded price with no separator) pass through.
    """
    if not venue:
        return None
    return _COST_PREFIX_RE.sub("", str(venue)).strip() or None


# --------------------------------------------------------------------------- #
# Fix 2.7 — venue normalization: collapse doubled city tokens, tidy.
# --------------------------------------------------------------------------- #
# "Lake Havasu City, Lake Havasu City, AZ" -> "Lake Havasu City, AZ".
_DOUBLED_CITY_RE = re.compile(
    r"\b(lake havasu city)\b\s*,\s*\b(lake havasu city)\b", re.IGNORECASE
)


def canonicalize_venue(venue: str | None) -> str | None:
    """Collapse doubled location tokens + tidy a venue string.

    Fixes the "Lake Havasu City, Lake Havasu City, AZ" doubling seen in feed
    data, and de-duplicates any immediately-repeated comma segment ("X, X" -> "X").
    Whitespace + stray separators are tidied. Returns ``None`` for empty input.
    """
    if not venue:
        return None
    text = _DOUBLED_CITY_RE.sub(r"\1", str(venue))
    # Collapse any adjacent duplicate comma-separated segments ("Foo, Foo, AZ").
    segs = [s.strip() for s in text.split(",")]
    out: list[str] = []
    for s in segs:
        if s and (not out or out[-1].lower() != s.lower()):
            out.append(s)
    text = ", ".join(out)
    return re.sub(r"\s{2,}", " ", text).strip(" ,") or None


def event_sample(rec: EventRecord) -> dict:
    return {
        "title": rec.title,
        "start": rec.start_date.isoformat() if rec.start_date else None,
        "time": rec.start_time.strftime("%H:%M") if rec.start_time else None,
        "venue": rec.venue_name,
        "url": rec.url,
        "tags": rec.tags,
    }
