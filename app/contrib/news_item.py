"""Shared NewsItem record for news/civic feed scrapers (source-expansion).

Ask Hava has no news/announcement store yet — providers and events have tables,
but city press releases, council newsflashes, sheriff bulletins, and local news
articles have nowhere to land. Rather than each news/civic scraper inventing its
own shape, they all normalise to :class:`NewsItem`.

This is a transport dataclass only — it deliberately does NOT touch the
database. The proposed persistent store (a ``news_items`` table, or routing
through the contribution queue with ``entity_type="news"``) is written up in the
source-rollout PR for Casey's decision; no migration ships in the build-only
branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsItem:
    """One normalised news/announcement item from any news/civic feed."""

    source: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    author: str | None = None
    image_url: str | None = None
    # Free-form provenance kept for review/debugging; never persisted verbatim.
    raw: dict = field(default_factory=dict)

    def dedupe_key(self) -> str:
        """Stable identity for de-duplication: the canonical article URL."""
        return (self.url or "").strip().lower()
