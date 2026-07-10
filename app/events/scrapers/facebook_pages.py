"""Facebook Pages event connector — INTERFACE ONLY (WS12 C1).

Facebook is the highest-yield coverage source (it closes the two client-named
gaps at once: Altitude's camps/Glow nights and Barley Brothers' happy hour +
live music) and the hardest to access — there is no free, ToS-clean way to read
~50 pages you don't own. So this module ships the **contract, watchlist, and
extraction seam**, but is a deliberate **no-op until an access path is
configured**. See ``docs/askhava-fixes/WS12_FACEBOOK_DECISION_BRIEF.md`` for the
Meta-token / Bright-Data / manual-relay decision (Casey's call — spend + ToS).

Two complementary paths land Facebook findings in the SAME review pipeline:

* **Pull (this connector).** When an access path is wired (a Meta Graph token,
  or a third-party FB data API key), :meth:`discover` reads the watchlist pages'
  posts/events, :func:`extract_events_from_text` turns each post into candidate
  events with a confidence score (WS6 gating), and the runner files them as
  ``facebook_scrape`` contributions — PENDING for review.
* **Push (already live).** ``app/api/routes/ingest.py`` accepts POSTed findings
  from an external scraper ("OpenClaw"), also as ``facebook_scrape`` pending
  contributions. A manual-relay or vendor path can push there instead.

Nothing here scrapes Facebook directly (bot-walled + fragile + ToS). The
connector stays registered and schedulable; unconfigured it simply returns 0
rows, so ``scrape_events.py --all`` is safe.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

# Findings land as this source so pull + push share one review pipeline and one
# provenance string (matches app/api/routes/ingest.py::_INGEST_SOURCE).
FACEBOOK_SOURCE = "facebook_scrape"


@dataclass(frozen=True)
class WatchPage:
    """One Facebook page on the coverage watchlist."""

    handle: str  # facebook.com/<handle> (or a business name to resolve)
    label: str
    kind: str  # "venue" | "brewery" | "church" | "youth" | "track" | ...
    client_named_gap: bool = False  # a gap the client explicitly called out
    tags: tuple[str, ...] = ()  # default tags applied to this page's events


# The seed watchlist (WS12 §12 / credential checklist §1). Confirm each handle
# is current + public before wiring access. Grows toward ~50 (bars, churches,
# youth studios, venues).
WATCHLIST: tuple[WatchPage, ...] = (
    WatchPage("altitudelakehavasu", "Altitude Lake Havasu", "venue",
              client_named_gap=True, tags=("family", "kids", "trampoline")),
    WatchPage("splitfingerathletics", "Split Finger Athletics", "youth",
              client_named_gap=True, tags=("youth", "kids", "baseball", "camps")),
    WatchPage("BarleyBrothers", "Barley Brothers", "brewery",
              client_named_gap=True, tags=("nightlife", "live music", "happy hour")),
    WatchPage("CollegeStreet", "College Street Brewhouse", "brewery",
              tags=("nightlife", "live music")),
    WatchPage("flyingxsaloon", "Flying X Saloon", "venue", tags=("nightlife", "live music")),
    WatchPage("kokomohavasu", "Kokomo Beach Club", "venue", tags=("nightlife", "live music")),
    WatchPage("ladyleeshavasu", "Lady Lee's", "venue", tags=("nightlife",)),
    WatchPage("calvarybaptistlhc", "Calvary Baptist", "church", tags=("community", "worship")),
    WatchPage("calvarychapellhc", "Calvary Chapel LHC", "church", tags=("community", "worship")),
    WatchPage("lakehavasubaseballacademy", "Lake Havasu Baseball Academy", "youth",
              tags=("youth", "kids", "baseball", "camps")),
    WatchPage("graceartslive", "Grace Arts Live", "venue", tags=("arts", "theater")),
    WatchPage("havasu95speedway", "Havasu 95 Speedway", "track", tags=("motorsports",)),
)

# Access modes. The connector is a no-op until one is configured via env.
#   FB_ACCESS_MODE = "graph"   + FB_GRAPH_TOKEN            (Meta Graph API)
#   FB_ACCESS_MODE = "vendor"  + FB_VENDOR_API_KEY         (3rd-party FB data API)
#   (unset / "off")                                        -> disabled (default)
_ACCESS_MODE_ENV = "FB_ACCESS_MODE"


@dataclass
class ExtractedEvent:
    """One candidate event pulled from a post, with a WS6 confidence score."""

    title: str
    start_date: str | None  # ISO
    start_time: str | None  # ISO HH:MM
    end_date: str | None = None
    end_time: str | None = None
    description: str = ""
    confidence: float = 0.0
    tags: list[str] = field(default_factory=list)


def extract_events_from_text(
    text: str,
    *,
    page: WatchPage,
) -> list[ExtractedEvent]:
    """Post text -> candidate events (LLM extraction seam, WS6 confidence gating).

    INTERFACE ONLY. The production body will prompt the classifier LLM for
    date/time/title/price and return each candidate with a confidence in
    ``[0, 1]``; the runner routes low-confidence rows to the review queue (they
    already all do, since ``facebook_scrape`` is not auto-approved). Left
    unimplemented on purpose so no half-built extraction runs against real posts
    before the access + prompt design is signed off.
    """
    raise NotImplementedError(
        "Facebook post->event extraction is not wired yet — see "
        "WS12_FACEBOOK_DECISION_BRIEF.md. Configure an access path first."
    )


class FacebookPagesClient(EventIngestClient):
    """Pull-side Facebook connector. No-op until an access path is configured."""

    source_name = "facebook"
    scrape_source = FACEBOOK_SOURCE
    watchlist: tuple[WatchPage, ...] = WATCHLIST

    @staticmethod
    def access_mode() -> str:
        """Configured access mode, or "off" when unset/disabled."""
        return (os.getenv(_ACCESS_MODE_ENV) or "off").strip().lower()

    @classmethod
    def is_configured(cls) -> bool:
        """True only when an access path is set up. Default: False (gated off)."""
        mode = cls.access_mode()
        if mode == "graph":
            return bool((os.getenv("FB_GRAPH_TOKEN") or "").strip())
        if mode == "vendor":
            return bool((os.getenv("FB_VENDOR_API_KEY") or "").strip())
        return False

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        """Read watchlist pages' posts/events — but only when configured.

        Unconfigured (the default) this returns ``[]`` so the connector is a
        safe no-op: it can be registered and scheduled today, and starts
        producing review-queue rows the moment an access path + extraction are
        wired. The per-mode fetch is the gated seam.
        """
        if not self.is_configured():
            return []
        # Gated seam — a real access path fetches each page's posts/events here
        # and calls extract_events_from_text(...) per post. Not implemented until
        # Casey selects a path (see the decision brief).
        raise NotImplementedError(
            f"Facebook access mode {self.access_mode()!r} is configured but the "
            "fetch/extract path is not implemented yet."
        )

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        return EventPayload(
            name=str(raw["title"]),
            entity_type="event",
            source=self.scrape_source,
            start_date=raw.get("start_date"),
            start_time=raw.get("start_time"),
            end_date=raw.get("end_date"),
            end_time=raw.get("end_time"),
            venue_name=str(raw.get("venue_name") or ""),
            description=str(raw.get("description") or ""),
            event_url=str(raw["event_url"]),
            source_stable_url=str(raw["event_url"]),
            category_slug="events",
            tags=list(raw.get("tags") or []),
        )
