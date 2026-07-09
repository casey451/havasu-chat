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
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.conditions.cache import read_source, record_fetch_failure, upsert_source
from app.conditions.constants import SOURCE_NEWS_LOCAL
from app.contrib import lhc_newsflash, mcso_press, news_herald, river_scene_news
from app.contrib.news_item import NewsItem
from app.news.sections import (
    NON_LOCAL_SECTIONS,
    SECTION_LABELS,
    SECTION_LOCAL,
    has_local_signal,
    is_trusted_local_source,
    news_section,
)

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

# Syndicated, non-local-news filler the wire feeds repeat daily (Casey 2026-06-29).
# Dropped outright — it's not local news and it floods the ticker.
_FILLER_TITLE_BITS = (
    "celebrity cipher",
    "horoscope",
    "your stars",
    "sudoku",
    "crossword",
    "jumble",
    "lottery numbers",
    "daily puzzle",
)

_TITLE_DATEISH_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|\d+", re.IGNORECASE
)
_TITLE_NONWORD_RE = re.compile(r"[^a-z0-9]+")


def _is_filler(title: str) -> bool:
    t = (title or "").lower()
    return any(bit in t for bit in _FILLER_TITLE_BITS)


def _normalize_title(title: str) -> str:
    """Collapse a headline to a stable key so the same recurring column posted
    under many URLs/dates dedupes to one (e.g. 'Celebrity Cipher for June 28' and
    'Celebrity Cipher for July 1' → 'celebrity cipher for')."""
    t = (title or "").lower()
    t = _TITLE_DATEISH_RE.sub(" ", t)
    t = _TITLE_NONWORD_RE.sub(" ", t).strip()
    return t


# (source key, zero-arg fetch callable → list[NewsItem]). Each callable makes its
# own live HTTP request; failures are isolated per source in pull_local_news.
_SOURCES: tuple[tuple[str, Callable[[], list[NewsItem]]], ...] = (
    ("news_herald", news_herald.fetch_news_sitemap),
    ("lhc_newsflash", lhc_newsflash.fetch_newsflash),
    ("river_scene_news", river_scene_news.fetch_posts),
    ("mcso_press", mcso_press.fetch_press_releases),
)


def _naive_utc(now: datetime | None) -> datetime:
    """Coerce ``now`` to the naive-UTC the conditions cache stores and compares
    against (``read_source`` / ``_is_stale`` subtract naive ``fetched_at``). A
    tz-aware caller (e.g. the /news router passing ``now_lake_havasu()``) would
    otherwise blow up on naive-vs-aware subtraction."""
    if now is None:
        return datetime.now(UTC).replace(tzinfo=None)
    if now.tzinfo is not None:
        return now.astimezone(UTC).replace(tzinfo=None)
    return now


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
    now = _naive_utc(now)
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

    # Newest first, then collapse: drop syndicated filler (Celebrity Cipher,
    # horoscopes, puzzles…) and near-duplicate titles — the same recurring column
    # posted under many URLs/dates. The sources repeat these; we fix it our end.
    collected.sort(key=_pub_sort_key, reverse=True)
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    unique: list[NewsItem] = []
    for it in collected:
        if not it.title or not it.url or _is_filler(it.title):
            continue
        url_key = it.dedupe_key()
        title_key = _normalize_title(it.title)
        if url_key in seen_url or (title_key and title_key in seen_title):
            continue
        seen_url.add(url_key)
        if title_key:
            seen_title.add(title_key)
        unique.append(it)

    stored = [_item_to_dict(it) for it in unique[:_MAX_ITEMS]]
    upsert_source(db, SOURCE_NEWS_LOCAL, {"items": stored}, now=now)
    return len(stored)


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


def _view(
    db: Session,
    *,
    limit: int | None,
    now: datetime | None,
    drop_sections: frozenset[str] = frozenset(),
    local_only: bool = False,
) -> NewsView:
    now = _naive_utc(now)
    row = read_source(db, SOURCE_NEWS_LOCAL, now=now)
    if row is None:
        return NewsView(items=[], is_stale=False, updated_at=None)
    raw = row.data.get("items") if isinstance(row.data, dict) else None
    items = raw if isinstance(raw, list) else []
    # Defensive re-clean at read time too, so a cache row written before the
    # filler/title-dedup fix still renders clean without waiting for a re-pull.
    out: list[dict] = []
    seen_title: set[str] = set()
    for it in items:
        if not isinstance(it, dict) or not it.get("title") or not it.get("url"):
            continue
        title = str(it.get("title") or "")
        if _is_filler(title):
            continue
        # M18: route into Local / City Hall / Opinion / Beyond Havasu. The
        # homepage module drops wire/nation/lifestyle before the limit so it
        # still fills with local headlines (no "Pringles" under a Havasu H1).
        url = str(it.get("url") or "")
        source = str(it.get("source") or "")
        summary = str(it.get("summary") or "")
        section = news_section(source, url, title)
        if section in drop_sections:
            continue
        region_label = _region_label(title, summary)
        # Homepage-only local gate: a catch-all "Local" item from a syndication-
        # prone source (News-Herald wire) needs a positive Havasu or immediate-
        # region signal to make the front page. Without it, bare-URL national
        # stories ("Unstable NYC building…") ride the Local default onto /home.
        # Trusted-local sources and labelled nearby-region items always pass.
        if (
            local_only
            and section == SECTION_LOCAL
            and not is_trusted_local_source(source)
            and region_label is None
            and not has_local_signal(url, title, summary)
        ):
            continue
        title_key = _normalize_title(title)
        if title_key and title_key in seen_title:
            continue
        if title_key:
            seen_title.add(title_key)
        entry = dict(it)
        entry["published_label"] = _relative_label(it.get("published_at"), now)
        entry["region_label"] = region_label
        entry["section"] = section
        entry["section_label"] = SECTION_LABELS.get(section, "Local")
        out.append(entry)
        if limit is not None and len(out) >= limit:
            break
    return NewsView(items=out, is_stale=bool(row.is_stale), updated_at=row.fetched_at)


# 2026-07-01 master audit §6.2: the local pull (River Scene et al.) covers the
# whole Parker/La Paz strip, so out-of-town items ran as bare Havasu headlines
# ("Horseshoe tournament July 4 at Manataba Park" — that's Parker). Label them
# honestly instead of dropping them (they're legitimately nearby news). Word-
# boundary matched; "Parker Dam" alone reads as the local landmark and counts.
_REGION_SIGNALS: tuple[tuple[str, str], ...] = (
    ("Parker", r"\bparker\b(?!\s+dam)"),
    ("Parker", r"\bmanataba\b|\bla paz county\b|\bla paz\b|\bquartzsite\b|\bposton\b|\bbouse\b"),
    ("Kingman", r"\bkingman\b"),
    ("Bullhead City", r"\bbullhead\b"),
    ("Needles", r"\bneedles\b"),
)
_REGION_RES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE)) for label, pattern in _REGION_SIGNALS
)


def _region_label(title: str, summary: str = "") -> str | None:
    """Out-of-town region label for a headline, or ``None`` for Havasu items.

    A headline that names Lake Havasu explicitly stays unlabeled even when it
    also mentions a neighbor (a Havasu story about a Parker game is local)."""
    blob = f"{title} {summary}"
    if re.search(r"\b(lake havasu|havasu city|lhc)\b", blob, re.IGNORECASE):
        return None
    for label, rx in _REGION_RES:
        if rx.search(blob):
            return label
    return None


def ticker_view(db: Session, *, limit: int = 6, now: datetime | None = None) -> NewsView:
    """Top headlines for the home news ticker (honest-omit when empty).

    M18: local-first — the homepage never surfaces wire/nation/lifestyle
    syndication (``Beyond Havasu``) or op-eds (``Opinion``) as a Havasu headline,
    and a catch-all ``Local`` item must carry a Havasu / immediate-region signal
    (``local_only``) so bare-URL national wire can't ride the default onto /home."""
    return _view(
        db, limit=limit, now=now, drop_sections=NON_LOCAL_SECTIONS, local_only=True
    )


def page_view(db: Session, *, now: datetime | None = None) -> NewsView:
    """The full headline list for the ``/news`` page."""
    return _view(db, limit=None, now=now)
