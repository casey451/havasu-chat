"""food_inspections — Mohave County environmental-health inspection PDFs.

source-expansion #19. Monthly county PDFs (verified through Apr 2026):

    index:  https://www.mohave.gov/departments/public-health/environmental-health/reports/
    files:  /media/ldcfiinh/food-safety-inspections_2026-04-apr.pdf

pdfplumber tabular parse; we keep only the Lake Havasu region rows and match
establishments to existing Providers by name+address (reusing the reconciler's
slugify/haversine helpers at integration time). A differentiating feature with
zero legal risk.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the PDF column layout is parsed defensively
against header-name heuristics — confirm against a real monthly PDF.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.ingest_reconciler import slugify
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "food_inspections"
INDEX_URL = "https://www.mohave.gov/departments/public-health/environmental-health/reports/"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
LAKE_HAVASU_MARKERS = ("lake havasu", "lhc", "86403", "86404", "86406")
_PDF_NAME_RE = re.compile(r"food-safety-inspections_[\w-]+\.pdf", re.I)
_LIMITER = SourceLimiter("food_inspections", qps=0.4)


@dataclass
class InspectionRecord:
    establishment: str
    address: str | None
    city: str | None
    inspection_date: date | None
    result: str | None
    name_slug: str = ""
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name_slug:
            self.name_slug = slugify(self.establishment)


def discover_pdf_links(index_html: str, *, base_url: str = INDEX_URL) -> list[str]:
    """Find food-safety inspection PDF links on the reports index page."""
    soup = BeautifulSoup(index_html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _PDF_NAME_RE.search(href):
            full = urljoin(base_url, href)
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links


def _header_index(header: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, col in enumerate(header):
        c = (col or "").strip().lower()
        if any(k in c for k in ("establishment", "facility", "name")):
            idx.setdefault("establishment", i)
        elif "address" in c:
            idx.setdefault("address", i)
        elif "city" in c:
            idx.setdefault("city", i)
        elif "date" in c:
            idx.setdefault("date", i)
        elif any(k in c for k in ("result", "grade", "score", "violation")):
            idx.setdefault("result", i)
    return idx


def _is_lake_havasu(*fields: str | None) -> bool:
    blob = " ".join(f for f in fields if f).lower()
    return any(m in blob for m in LAKE_HAVASU_MARKERS)


def parse_inspection_rows(rows: list[list[str]]) -> list[InspectionRecord]:
    """Parse extracted table rows (first row = header) into Lake Havasu records."""
    if not rows:
        return []
    header = rows[0]
    idx = _header_index(header)
    if "establishment" not in idx:
        return []
    out: list[InspectionRecord] = []
    for row in rows[1:]:
        def cell(key: str) -> str | None:
            i = idx.get(key)
            if i is None or i >= len(row):
                return None
            v = (row[i] or "").strip()
            return v or None

        establishment = cell("establishment")
        if not establishment:
            continue
        address = cell("address")
        city = cell("city")
        if not _is_lake_havasu(address, city):
            continue
        date_raw = cell("date")
        parsed_date = None
        if date_raw:
            try:
                parsed_date = dateutil_parser.parse(date_raw, fuzzy=True).date()
            except (ValueError, OverflowError):
                parsed_date = None
        out.append(
            InspectionRecord(
                establishment=establishment,
                address=address,
                city=city,
                inspection_date=parsed_date,
                result=cell("result"),
            )
        )
    return out


def extract_pdf_rows(pdf_bytes: bytes) -> list[list[str]]:
    """Extract table rows from an inspection PDF via pdfplumber (all pages)."""
    import pdfplumber

    rows: list[list[str]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    rows.append([(c or "").strip() for c in row])
    return rows


def fetch_latest(*, client: httpx.Client | None = None) -> list[InspectionRecord]:
    """Discover the latest PDF, download it, and parse Lake Havasu rows."""
    owns = client is None
    c = client or httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        index = _LIMITER.call_with_retry(lambda: c.get(INDEX_URL, timeout=30.0))
        if index is None:
            raise RuntimeError("food_inspections index fetch failed")
        index.raise_for_status()
        links = discover_pdf_links(index.text)
        if not links:
            return []
        pdf_resp = _LIMITER.call_with_retry(lambda: c.get(links[0], timeout=60.0))
        if pdf_resp is None:
            raise RuntimeError("food_inspections pdf fetch failed")
        pdf_resp.raise_for_status()
        return parse_inspection_rows(extract_pdf_rows(pdf_resp.content))
    finally:
        if owns:
            c.close()


def inspection_sample(r: InspectionRecord) -> dict[str, Any]:
    return {
        "establishment": r.establishment,
        "address": r.address,
        "city": r.city,
        "date": r.inspection_date.isoformat() if r.inspection_date else None,
        "result": r.result,
        "name_slug": r.name_slug,
    }
