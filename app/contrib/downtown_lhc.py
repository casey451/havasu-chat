"""downtown_lhc — Downtown Lake Havasu Main Street member directory.

source-expansion #22. WordPress site with member pages at ``/member/<slug>/``.
Used as an ENRICHMENT signal (``downtown_member=true``) on existing providers
via the reconciler — like the chamber directory (#20).

We DELIBERATELY SKIP this site's events: they syndicate from golakehavasu and
would be a dedupe hazard. Inert build-only module: fetch + parse only, no DB
writes, no orchestrator registration. NEEDS_PROD_VERIFY: markup parsed
defensively.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.contrib.ingest_reconciler import slugify
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "downtown_lhc"
BASE_URL = "https://downtownlakehavasu.com"
DIRECTORY_URL = f"{BASE_URL}/members/"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_MEMBER_HREF_RE = re.compile(r"/member/[^/]+/?$")
_LIMITER = SourceLimiter("downtown_lhc", qps=0.3)


@dataclass
class DowntownMember:
    name: str
    url: str
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    name_slug: str = ""
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name_slug:
            self.name_slug = slugify(self.name)

    def enrichment_signal(self) -> dict[str, object]:
        return {"downtown_member": True, "downtown_url": self.url, "attribution": "Downtown Lake Havasu"}


def parse_member_links(html: str, *, base_url: str = BASE_URL) -> list[str]:
    """Find member detail page links (/member/<slug>/) on a directory page."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _MEMBER_HREF_RE.search(href):
            full = urljoin(base_url, href)
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links


def parse_member_detail(html: str, url: str) -> DowntownMember | None:
    """Parse a member detail page into a DowntownMember."""
    soup = BeautifulSoup(html, "html.parser")
    name_el = soup.find(["h1", "h2"])
    name = name_el.get_text(" ", strip=True) if name_el else None
    if not name:
        return None
    addr_el = soup.select_one(".address, .member-address, [itemprop='address']")
    phone_el = soup.select_one(".phone, .member-phone, [itemprop='telephone']")
    site_link = soup.select_one("a.website, a.member-website, a[rel='external']")
    return DowntownMember(
        name=name,
        url=url,
        address=addr_el.get_text(" ", strip=True) if addr_el else None,
        phone=phone_el.get_text(" ", strip=True) if phone_el else None,
        website=(site_link.get("href") if site_link else None),
    )


def fetch_members(*, limit: int = 100, client: httpx.Client | None = None) -> list[DowntownMember]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    members: list[DowntownMember] = []
    try:
        dir_resp = _LIMITER.call_with_retry(lambda: c.get(DIRECTORY_URL, timeout=30.0))
        if dir_resp is None:
            raise RuntimeError("downtown_lhc directory fetch failed")
        dir_resp.raise_for_status()
        for link in parse_member_links(dir_resp.text)[:limit]:
            detail = _LIMITER.call_with_retry(lambda url=link: c.get(url, timeout=30.0))
            if detail is None or detail.status_code >= 400:
                continue
            member = parse_member_detail(detail.text, link)
            if member:
                members.append(member)
    finally:
        if owns:
            c.close()
    return members


def member_sample(m: DowntownMember) -> dict:
    return {"name": m.name, "url": m.url, "address": m.address, "website": m.website}
