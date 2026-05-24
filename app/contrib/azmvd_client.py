"""Arizona MVD Valid Dealer Report client (V1.5 Trust-Signal Verifier Bundle
wave 3, ticket #20).

§3.1 probe (2026-05-24): the legacy ``azdot.gov/.../dealer-locator`` URL 404s;
``azmvd.gov/mvd/locator/Dealers`` is unreachable from automation. ADOT publishes
a bulk **Valid Dealer Report** link on the Dealer Licensing page — an HTML table
served as ``.xls`` (``Content-Type: text/html``) updated Tue/Thu:

``https://azdot.gov/mvd/businesses-organizations/dealer-licensing``
→ ``https://apps.azdot.gov/files/26/valid-dealer-report/report*.xls``

This REST path avoids Playwright. Parsed with BeautifulSoup (already a project
dependency). Mohave / Lake Havasu City filtering is optional; the verifier loads
the statewide report once per pass and fuzzy-matches in memory (same shape as
:mod:`app.contrib.azdhs_client` bulk county fetch).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Final

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEALER_LICENSING_PAGE: Final[str] = (
    "https://azdot.gov/mvd/businesses-organizations/dealer-licensing"
)
VALID_DEALER_REPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"https://apps\.azdot\.gov/files/26/valid-dealer-report/report\d+\.xls",
    re.I,
)

DEFAULT_OUT_FIELDS: Final[tuple[str, ...]] = (
    "dealer_number",
    "business_name",
    "doing_business_as",
    "license_renewal_due",
    "dealership_license_status",
    "license_status_reason",
    "product_by_make",
    "street_address",
    "city",
    "state",
    "zip",
    "country",
    "mailing_address",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
    "mailing_country",
    "phone",
    "license_type",
)


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }


def resolve_valid_dealer_report_url(client: httpx.Client) -> str:
    """Scrape the current Valid Dealer Report URL from the licensing page."""
    resp = client.get(DEALER_LICENSING_PAGE, headers=_browser_headers(), timeout=60.0)
    resp.raise_for_status()
    match = VALID_DEALER_REPORT_RE.search(resp.text)
    if not match:
        raise RuntimeError(
            "AZ MVD Valid Dealer Report link not found on dealer-licensing page; "
            "expected apps.azdot.gov/files/26/valid-dealer-report/report*.xls"
        )
    return match.group(0)


def fetch_azmvd_dealers(
    client: httpx.Client,
    *,
    report_url: str | None = None,
    city_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return normalized dealer rows from the ADOT Valid Dealer Report.

    ``city_filter`` optionally narrows to a single city (case-insensitive exact
    match on the ``city`` column). Defaults to statewide load for verifier
    fuzzy-match passes.
    """
    url = report_url or resolve_valid_dealer_report_url(client)
    resp = client.get(url, headers=_browser_headers(), timeout=120.0)
    resp.raise_for_status()
    html = resp.content.decode("iso-8859-1", errors="replace")
    rows = _parse_dealer_report_html(html)
    if city_filter:
        city_norm = city_filter.strip().lower()
        rows = [r for r in rows if (r.get("city") or "").strip().lower() == city_norm]
    logger.info(
        "azmvd_client.fetch_complete",
        extra={"report_url": url, "city_filter": city_filter, "total": len(rows)},
    )
    return rows


def _parse_dealer_report_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("AZ MVD Valid Dealer Report HTML missing <table> root")

    trs = table.find_all("tr")
    if not trs:
        return []

    headers = [_cell_text(c) for c in trs[0].find_all(["th", "td"])]
    header_map = _header_index_map(headers)
    out: list[dict[str, Any]] = []
    for tr in trs[1:]:
        cells = [_cell_text(c) for c in tr.find_all(["th", "td"])]
        if not cells or not any(cells):
            continue
        row = _row_from_cells(cells, header_map)
        dealer_number = (row.get("dealer_number") or "").strip()
        if not dealer_number:
            continue
        out.append(row)
    return out


def _cell_text(tag) -> str:
    return tag.get_text(" ", strip=True)


def _header_index_map(headers: list[str]) -> dict[str, int]:
    canonical = {
        "mvd dealer license number": "dealer_number",
        "business name": "business_name",
        "doing business as": "doing_business_as",
        "license renewal due": "license_renewal_due",
        "dealership license status": "dealership_license_status",
        "license status reason": "license_status_reason",
        "product by make": "product_by_make",
        "street address line 1": "street_address",
        "city": "city",
        "state/province": "state",
        "zip/postal code": "zip",
        "country": "country",
        "mailing address line 1": "mailing_address",
        "phone": "phone",
        "license type": "license_type",
    }
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(headers):
        key = canonical.get(raw.strip().lower())
        if key:
            mapping[key] = idx
    # Repeated city/state/zip/country columns after mailing block.
    lower_headers = [h.strip().lower() for h in headers]
    for label, field in (
        ("city", "mailing_city"),
        ("state/province", "mailing_state"),
        ("zip/postal code", "mailing_zip"),
        ("country", "mailing_country"),
    ):
        if field in mapping:
            continue
        seen_city = False
        for idx, h in enumerate(lower_headers):
            if h == label:
                if label == "city" and not seen_city:
                    seen_city = True
                    continue
                mapping[field] = idx
                break
    return mapping


def _row_from_cells(cells: list[str], header_map: dict[str, int]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in DEFAULT_OUT_FIELDS:
        idx = header_map.get(field)
        if idx is None or idx >= len(cells):
            continue
        val = cells[idx].strip()
        if val:
            row[field] = val
    return row
