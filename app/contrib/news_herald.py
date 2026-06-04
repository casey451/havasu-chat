"""news_herald — Today's News-Herald (havasunews.com) via TownNews/BLOX.

source-expansion #6. The flagship local-news source. Two paths:

* **News sitemap** (the working path): a Google News sitemap at
  ``https://www.havasunews.com/tncms/sitemap/news.xml`` gives title, publication
  date, and rich keywords for every recent article. (The classic BLOX
  ``?f=rss`` section feeds are dead on this site.)
* **Fishing column** via the working BLOX search RSS:
  ``…/search/?q=fishing+report&t=article&f=rss&s=start_time&sd=desc&l=5``.

PAYWALL ETHICS (build rule 6): havasunews.com is a TownNews/BLOX metered
paywall. We ingest ONLY the headline, date, keywords, and the freely-served
lede (first ~2 paragraphs). :func:`extract_lede` reads only visible paragraph
text — it deliberately does NOT decode the ROT47-obfuscated article body, which
would be paywall circumvention.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. Produces NewsItem records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.civicplus_rss import fetch_feed_text, parse_feed
from app.contrib.news_item import NewsItem
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "news_herald"
SITEMAP_URL = "https://www.havasunews.com/tncms/sitemap/news.xml"
FISHING_RSS_URL = (
    "https://www.havasunews.com/search/?q=fishing+report&t=article&f=rss&s=start_time&sd=desc&l=5"
)
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"

_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_LIMITER = SourceLimiter("news_herald", qps=0.5)


def parse_news_sitemap(xml: str) -> list[NewsItem]:
    """Parse a Google-News sitemap into NewsItem records (title/date/keywords).

    No article fetch — the sitemap alone carries everything we are allowed to
    store cheaply. Namespaced via the standard sitemap + news schemas.
    """
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        logger.warning("news_herald.sitemap_parse_error", exc_info=True)
        return items

    for url_el in root.findall(f"{{{_SM_NS}}}url"):
        loc = url_el.findtext(f"{{{_SM_NS}}}loc")
        news_el = url_el.find(f"{{{_NEWS_NS}}}news")
        if loc is None or news_el is None:
            continue
        title = news_el.findtext(f"{{{_NEWS_NS}}}title")
        if not title:
            continue
        pub = news_el.findtext(f"{{{_NEWS_NS}}}publication_date")
        keywords_raw = news_el.findtext(f"{{{_NEWS_NS}}}keywords") or ""
        published: datetime | None = None
        if pub:
            try:
                published = dateutil_parser.parse(pub).replace(tzinfo=None)
            except (ValueError, OverflowError):
                published = None
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        items.append(
            NewsItem(
                source=SOURCE,
                title=title.strip(),
                url=loc.strip(),
                published_at=published,
                keywords=keywords,
            )
        )
    return items


def extract_lede(html: str, *, max_paragraphs: int = 2) -> str | None:
    """Return the freely-served lede (first ~2 visible paragraphs) only.

    Rule 6: reads ONLY visible <p> text from the article body. Does NOT decode
    any obfuscated/encoded body content (the ROT47-encoded paywalled remainder
    is never touched).
    """
    soup = BeautifulSoup(html, "html.parser")
    body = (
        soup.select_one("[itemprop='articleBody']")
        or soup.select_one("div.asset-content")
        or soup.select_one("#article-body")
        or soup.find("article")
        or soup
    )
    paras: list[str] = []
    for p in body.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text:
            paras.append(text)
        if len(paras) >= max_paragraphs:
            break
    return " ".join(paras) or None


def fetch_news_sitemap(*, client: httpx.Client | None = None) -> list[NewsItem]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/xml"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(SITEMAP_URL, timeout=30.0))
        if resp is None:
            raise RuntimeError("news_herald sitemap fetch failed")
        resp.raise_for_status()
        xml = resp.text
    finally:
        if owns:
            c.close()
    return parse_news_sitemap(xml)


def fetch_fishing_column(*, client: httpx.Client | None = None) -> list[NewsItem]:
    """Fetch the weekly fishing column via the working BLOX search RSS."""
    text = fetch_feed_text(FISHING_RSS_URL, client=client)
    return parse_feed(text, source=f"{SOURCE}_fishing")


def article_sample(item: NewsItem) -> dict:
    return {
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "keywords": item.keywords[:8],
        "lede": item.summary,
    }
