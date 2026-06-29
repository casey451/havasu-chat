"""Aggregate the wired local-news sources into one cache row, and read it back
for the home news ticker + the ``/news`` page.

No new table: the merged, deduped, recency-sorted headline list is stored as
JSON in the shared ``ExternalConditionsCache`` under
:data:`app.conditions.constants.SOURCE_NEWS_LOCAL` (the ``news_item.py`` docstring
left the persistent store to Casey's call — this is the no-migration path). Only
headlines, links, dates, and a few keywords are stored; article bodies are never
persisted (paywall/copyright rule 6 — see ``app/contrib/news_herald.py``).

Populate the cache with :func:`pull_local_news` (run by ``scripts/news_pull.py``
on a schedule); render it with :func:`ticker_view` / :func:`page_view`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.conditions.cache import read_source, record_fetch_failure, upsert_source
from app.conditions.constants import SOURCE_NEWS_LOCAL
from app.contrib import lhc_newsflash, mcso_press, news_herald, river_scene_news
from app.contrib.news_item import NewsItem

logger = logging.getLogger(__name__)

# Friendly label per wired source key (the cache stores the raw key).
SOURCE_LABELS: dict[str, str] = {
    "news_herald": "Havasu News-Herald",
    "lhc_newsflash": "City of Lake Havasu",
    "river_scene_news": "River Scene Magazine",
    "mcso_press": "Sheriff's Office",
}

# How many headlines to retain in the cache row (the ticker shows the top few;
# the /news page shows the rest). Extra wired sources (abc15_havasu, lhusd) drop
# in as one more tuple each — keep the list short and well-understood.
_MAX_ITEMS = 60

# (source key, zero-arg fetch callable → list[NewsItem]). Each callable makes its
# own live HTTP request; failures are isolated per source in pull_local_news.
_SOURCES: tuple[tuple[str, Callable[[], list[NewsItem]]], ...] = (
    ("news_herald", news_herald.fetch_news_sitemap),
    ("lhc_newsflash", lhc_newsflash.fetch_newsflash),
    ("river_scene_news", river_scene_news.fetch_posts),
    ("mcso_press", mcso_press.fetch_press_releases),
)


def _source_label(key: str) -> str:
    return SOURCE_LABELS.get(key, key.replace("_", " ").title())


def _item_to_dict(item: NewsItem) -> dict:
    return {
        "source": item.source,
        "source_label": _source_label(item.source),
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "keywords": item.keywords[:6],
    }


def _pub_sort_key(item: NewsItem) -> datetime:
    """Naive-UTC published time for sorting; undated items sink to the bottom.
    Normalizes tz-aware and naive timestamps so sources never compare-clash."""
    dt = item.published_at
    if dt is None:
        return datetime.min
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def pull_local_news(db: Session, *, now: datetime | None = None) -> int:
    """Fetch every wired source, merge/dedupe/recency-sort, and write the cache
    row. Returns the number of headlines stored.

    Per-source failures are logged and skipped so one dead feed never blanks the
    whole ticker; only when EVERY source fails do we record a fetch failure (and
    leave the prior cache row intact for graceful degradation)."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    collected: list[NewsItem] = []
    ok_sources = 0
    for key, fetch in _SOURCES:
        try:
            items = fetch() or []
        except Exception:  # noqa: BLE001 - one dead feed must not kill the rest
            logger.warning("news.pull_source_failed source=%s", key, exc_info=True)
            continue
        ok_sources += 1
        collected.extend(items)

    if ok_sources == 0:
        record_fetch_failure(db, SOURCE_NEWS_LOCAL, "all news sources failed", now=now)
        return 0

    # Dedupe by canonical URL (each source yields its own URLs), then recency
    # first — undated items sink to the bottom rather than disappearing.
    seen: set[str] = set()
    unique: list[NewsItem] = []
    for it in collected:
        key = it.dedupe_key()
        if not key or key in seen or not it.title or not it.url:
            continue
        seen.add(key)
        unique.append(it)
    unique.sort(key=_pub_sort_key, reverse=True)

    items = [_item_to_dict(it) for it in unique[:_MAX_ITEMS]]
    upsert_source(db, SOURCE_NEWS_LOCAL, {"items": items}, now=now)
    return len(items)


@dataclass(frozen=True)
class NewsView:
    items: list[dict]
    is_stale: bool
    updated_at: datetime | None


def _relative_label(iso: str | None, now: datetime) -> str | None:
    """Short recency label: ``Just now`` / ``5m ago`` / ``3h ago`` / ``2d ago`` /
    ``Jun 12``. ``None`` for undated items so the template omits the dot."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    secs = (now - dt).total_seconds()
    if secs < 60:
        return "Just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    if days < 7:
        return f"{days}d ago"
    return dt.strftime("%b ") + str(dt.day)


def _view(db: Session, *, limit: int | None, now: datetime | None) -> NewsView:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_NEWS_LOCAL, now=now)
    if row is None:
        return NewsView(items=[], is_stale=False, updated_at=None)
    raw = row.data.get("items") if isinstance(row.data, dict) else None
    items = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict) or not it.get("title") or not it.get("url"):
            continue
        entry = dict(it)
        entry["published_label"] = _relative_label(it.get("published_at"), now)
        out.append(entry)
        if limit is not None and len(out) >= limit:
            break
    return NewsView(items=out, is_stale=bool(row.is_stale), updated_at=row.fetched_at)


def ticker_view(db: Session, *, limit: int = 6, now: datetime | None = None) -> NewsView:
    """Top headlines for the home news ticker (honest-omit when empty)."""
    return _view(db, limit=limit, now=now)


def page_view(db: Session, *, now: datetime | None = None) -> NewsView:
    """The full headline list for the ``/news`` page."""
    return _view(db, limit=None, now=now)
