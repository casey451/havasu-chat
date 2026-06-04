"""azgfd_fishing — Arizona Game & Fish fishing reports (Lake Havasu section).

source-expansion #18. Two paths:

* **GovDelivery bulletins** (primary): the monthly report archive at
  ``https://www.azgfd.com/fishing-2/where-to-fish/fishing-report-archive/``
  links to bulletins on ``content.govdelivery.com`` (plain HTML). We extract
  only the Lake Havasu section.
* **FishAZ WP REST** (secondary): ``https://fishaz.azgfd.com/wp-json/wp/v2/posts?search=havasu``.

azgfd.com is Cloudflare-protected to datacenter IPs, so requests route through
the proxy env pattern (``AZGFD_SCRAPE_PROXY_URL`` → ``GAS_SCRAPE_PROXY_URL``
fallback). Inert build-only module: fetch + parse only, no DB writes, no
orchestrator registration. NEEDS_PROD_VERIFY: re-verify from prod / proxy; the
archive markup + bulletin structure are parsed defensively.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "azgfd_fishing"
ARCHIVE_URL = "https://www.azgfd.com/fishing-2/where-to-fish/fishing-report-archive/"
FISHAZ_POSTS_URL = "https://fishaz.azgfd.com/wp-json/wp/v2/posts"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
AZGFD_PROXY_ENV = "AZGFD_SCRAPE_PROXY_URL"
_FALLBACK_PROXY_ENV = "GAS_SCRAPE_PROXY_URL"
_LIMITER = SourceLimiter("azgfd_fishing", qps=0.4)


@dataclass
class FishingReport:
    source: str
    title: str
    url: str
    published_at: datetime | None
    lake_havasu_section: str | None
    raw: dict = field(default_factory=dict)


def _proxy_url() -> str | None:
    specific = (os.getenv(AZGFD_PROXY_ENV) or "").strip()
    if specific:
        return specific
    return (os.getenv(_FALLBACK_PROXY_ENV) or "").strip() or None


def build_client(*, timeout: float = 30.0) -> httpx.Client:
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "headers": {"User-Agent": USER_AGENT, "Accept": "text/html, application/json"},
        "follow_redirects": True,
    }
    proxy = _proxy_url()
    if proxy:
        try:
            return httpx.Client(proxy=proxy, **kwargs)
        except TypeError:  # older httpx
            return httpx.Client(proxies=proxy, **kwargs)
    return httpx.Client(**kwargs)


def discover_bulletin_links(html: str, *, base_url: str = ARCHIVE_URL) -> list[str]:
    """Find GovDelivery bulletin links on the archive page."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "govdelivery.com" in href or "/bulletins/" in href:
            full = urljoin(base_url, href)
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links


def extract_lake_havasu_section(html: str) -> str | None:
    """Extract the 'Lake Havasu' section text from a GovDelivery bulletin."""
    soup = BeautifulSoup(html, "html.parser")
    # Strategy: find a heading/strong/paragraph whose text starts with "Lake
    # Havasu", then collect following sibling text until the next heading-like node.
    for node in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b", "p"]):
        text = node.get_text(" ", strip=True)
        if text.lower().startswith("lake havasu"):
            parts = [text]
            for sib in node.find_all_next(["h1", "h2", "h3", "h4", "strong", "b", "p"]):
                sib_text = sib.get_text(" ", strip=True)
                if sib.name in ("h1", "h2", "h3", "h4", "strong", "b"):
                    # Stop at the next (non-Havasu) water-body heading.
                    if sib_text and not sib_text.lower().startswith("lake havasu"):
                        break
                elif sib.name == "p" and sib_text:
                    parts.append(sib_text)
                if sum(len(p) for p in parts) > 1200:
                    break
            return " ".join(parts).strip() or None
    return None


def parse_fishaz_posts(payload: Any) -> list[FishingReport]:
    """Parse FishAZ WP REST posts into FishingReport records (Havasu mentions)."""
    if not isinstance(payload, list):
        return []
    out: list[FishingReport] = []
    for post in payload:
        if not isinstance(post, dict):
            continue
        title_obj = post.get("title")
        title = (title_obj.get("rendered") if isinstance(title_obj, dict) else title_obj) or ""
        title = BeautifulSoup(str(title), "html.parser").get_text(" ", strip=True)
        link = (post.get("link") or "").strip()
        if not title or not link:
            continue
        published = None
        if post.get("date"):
            try:
                published = dateutil_parser.parse(str(post["date"])).replace(tzinfo=None)
            except (ValueError, OverflowError):
                published = None
        content_obj = post.get("content") or post.get("excerpt")
        content = content_obj.get("rendered") if isinstance(content_obj, dict) else content_obj
        section = BeautifulSoup(str(content or ""), "html.parser").get_text(" ", strip=True) or None
        out.append(
            FishingReport(
                source=f"{SOURCE}_fishaz",
                title=title,
                url=link,
                published_at=published,
                lake_havasu_section=section[:1200] if section else None,
                raw={"id": post.get("id")},
            )
        )
    return out


def fetch_bulletins(*, limit: int = 3, client: httpx.Client | None = None) -> list[FishingReport]:
    """Discover the latest bulletins and extract their Lake Havasu sections."""
    owns = client is None
    c = client or build_client()
    reports: list[FishingReport] = []
    try:
        archive_resp = _LIMITER.call_with_retry(lambda: c.get(ARCHIVE_URL, timeout=30.0))
        if archive_resp is None:
            raise RuntimeError("azgfd archive fetch failed")
        archive_resp.raise_for_status()
        links = discover_bulletin_links(archive_resp.text)[:limit]
        for link in links:
            resp = _LIMITER.call_with_retry(lambda url=link: c.get(url, timeout=30.0))
            if resp is None:
                continue
            resp.raise_for_status()
            section = extract_lake_havasu_section(resp.text)
            reports.append(
                FishingReport(
                    source=SOURCE,
                    title="AZGFD Fishing Report",
                    url=link,
                    published_at=None,
                    lake_havasu_section=section,
                )
            )
    finally:
        if owns:
            c.close()
    return reports


def report_sample(r: FishingReport) -> dict:
    return {
        "source": r.source,
        "title": r.title,
        "url": r.url,
        "lake_havasu_section": (r.lake_havasu_section or "")[:240] or None,
    }
