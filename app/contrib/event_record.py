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
            name = (node.get("name") or "").strip()
            if not name:
                continue
            start = parse_dt(node.get("startDate"))
            end = parse_dt(node.get("endDate"))
            venue_name, venue_addr = _place_name_address(node.get("location"))
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            records.append(
                EventRecord(
                    source=source,
                    title=name,
                    start_date=start.date() if start else None,
                    start_time=start.time().replace(tzinfo=None) if start else None,
                    end_date=end.date() if end else None,
                    end_time=end.time().replace(tzinfo=None) if end else None,
                    venue_name=venue_name,
                    venue_address=venue_addr,
                    url=(node.get("url") or "").strip() or None,
                    description=(node.get("description") or "").strip() or None,
                    image_url=str(image).strip() if image else None,
                    raw={"@type": node.get("@type")},
                )
            )
    return records


def event_sample(rec: EventRecord) -> dict:
    return {
        "title": rec.title,
        "start": rec.start_date.isoformat() if rec.start_date else None,
        "time": rec.start_time.strftime("%H:%M") if rec.start_time else None,
        "venue": rec.venue_name,
        "url": rec.url,
        "tags": rec.tags,
    }
