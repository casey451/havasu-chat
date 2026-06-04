"""chamber_directory — Havasu Chamber GrowthZone member directory enumeration.

source-expansion #20. Chamber membership is a legitimacy signal Google can't
give. The GrowthZone directory enumerates via
``/active-member-directory/FindStartsWith?term=A`` … ``Z`` (plain HTML listings)
plus member detail pages.

This is an ENRICHMENT signal (``chamber_member=true``) applied to EXISTING
providers via the reconciler — NOT a primary creator of new providers. Gentle
rate limit + attribution. Inert build-only module: fetch + parse only, no DB
writes, no orchestrator registration. NEEDS_PROD_VERIFY: listing markup parsed
defensively.
"""

from __future__ import annotations

import logging
import string
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.contrib.ingest_reconciler import slugify
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "chamber_directory"
BASE_URL = "https://business.havasuchamber.com"
FIND_URL = f"{BASE_URL}/active-member-directory/FindStartsWith"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
ALPHABET = string.ascii_uppercase
_LIMITER = SourceLimiter("chamber_directory", qps=0.3)  # gentle


@dataclass
class ChamberMember:
    name: str
    url: str | None
    address: str | None = None
    phone: str | None = None
    name_slug: str = ""
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name_slug:
            self.name_slug = slugify(self.name)

    def enrichment_signal(self) -> dict[str, object]:
        """The reconciler-applied signal for a matched provider."""
        return {"chamber_member": True, "chamber_url": self.url, "attribution": "Havasu Chamber"}


def parse_member_listing(html: str, *, base_url: str = BASE_URL) -> list[ChamberMember]:
    """Parse a GrowthZone FindStartsWith HTML listing into ChamberMember records."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".gz-directory-card, li.mn-listing, .card, .gz-list-card")
    members: list[ChamberMember] = []
    seen: set[str] = set()
    for card in cards:
        link = card.find("a", href=True)
        if not link:
            continue
        name = link.get_text(" ", strip=True)
        href = link["href"].strip()
        if not name or not href:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        addr_el = card.select_one(".gz-address, .mn-address, .address")
        phone_el = card.select_one(".gz-phone, .mn-phone, .phone")
        members.append(
            ChamberMember(
                name=name,
                url=url,
                address=addr_el.get_text(" ", strip=True) if addr_el else None,
                phone=phone_el.get_text(" ", strip=True) if phone_el else None,
            )
        )
    return members


def fetch_members(*, letters: str = ALPHABET, client: httpx.Client | None = None) -> list[ChamberMember]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    members: list[ChamberMember] = []
    seen: set[str] = set()
    try:
        for letter in letters:
            resp = _LIMITER.call_with_retry(
                lambda ltr=letter: c.get(FIND_URL, params={"term": ltr}, timeout=30.0)
            )
            if resp is None or resp.status_code >= 400:
                continue
            for m in parse_member_listing(resp.text):
                if m.url and m.url in seen:
                    continue
                if m.url:
                    seen.add(m.url)
                members.append(m)
    finally:
        if owns:
            c.close()
    return members


def member_sample(m: ChamberMember) -> dict:
    return {"name": m.name, "url": m.url, "address": m.address, "name_slug": m.name_slug}
