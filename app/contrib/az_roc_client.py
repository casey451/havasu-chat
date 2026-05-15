"""Arizona Registrar of Contractors (AZ ROC) lookup helper (Phase 5).

The contractor search (`contractor-search` on Salesforce Experience Cloud) renders
results in-browser; :func:`lookup_contractor` drives headless Chromium via
Playwright. Callers (:mod:`scripts.az_roc_verify`) pass an ``httpx.Client`` only
for signature compatibility — it is intentionally unused here.

**Runtime setup:** one-time ``playwright install chromium`` on any machine that
runs live lookups. CI only needs the importable ``playwright`` package; tests
stay offline.

**Throughput:** v1 launches a fresh browser per call; if batch volume grows,
keep a module-level shared context/browser and reuse pages.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_URL = "https://azroc.my.site.com/AZRoc/s/contractor-search"


@dataclass(frozen=True)
class AzRocMatch:
    license_number: str
    classification: str | None
    status: str | None
    raw: dict[str, Any] | None = None


def lookup_contractor(
    client: httpx.Client,
    business_name: str,
    *,
    search_url: str = DEFAULT_SEARCH_URL,
) -> AzRocMatch | None:
    """Headless Playwright search; returns best table row or ``None`` on failure / no match.

    The ``client`` argument is unused but required so ``scripts/az_roc_verify`` can
    keep passing ``httpx.Client`` positionally.
    """
    _unused_client = client  # API compatibility — Playwright manages HTTP.
    query = business_name.strip()
    if not query:
        return None
    try:
        html = _fetch_results_table_html(search_url, query)
    except Exception:
        logger.warning(
            "AZ ROC Playwright lookup failed for %r (search URL %s)",
            query,
            search_url,
            exc_info=True,
        )
        return None

    rows = _parse_results_table(html)
    best = pick_best_az_roc_row(rows, query)
    if best is None:
        return None
    lic = (best.get("license_number") or "").strip()
    if not lic:
        return None

    payload = dict(best)
    return AzRocMatch(
        license_number=lic,
        classification=best.get("classification"),
        status=best.get("status"),
        raw=payload,
    )


def _fetch_results_table_html(search_url: str, query: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_navigation_timeout(120_000)
            page.set_default_timeout(90_000)
            page.goto(search_url, wait_until="networkidle", timeout=120_000)

            search_input = page.locator(
                "lightning-input input.slds-input, lightning-input input, input[type='text']"
            ).first
            search_input.wait_for(state="visible")
            search_input.click()
            search_input.fill(query)
            page.get_by_role("button", name="Search").first.click()
            page.wait_for_load_state("networkidle")

            page.locator(
                "table.slds-table_bordered tbody tr td[data-label='License No'], "
                "table.slds-table_bordered tbody"
            ).first.wait_for(state="attached", timeout=90_000)
            tbl = page.locator("table.slds-table_bordered").first
            return str(tbl.evaluate("el => el.outerHTML"))
        finally:
            browser.close()


def _separator_row(tds: list[Tag]) -> bool:
    if len(tds) != 1:
        return False
    lab = (tds[0].get("data-label") or "").strip()
    colspan = str(tds[0].get("colspan") or "")
    return lab == "line" or colspan in {"9", "10"}


def _td_plain_text(td: Tag) -> str:
    return td.get_text("\n", strip=True)


def _license_cell_text(td: Tag) -> str:
    tag_a = td.find("a")
    if tag_a and tag_a.get_text(strip=True):
        return tag_a.get_text(strip=True)
    tag_u = td.find("u")
    if tag_u and tag_u.get_text(strip=True):
        return tag_u.get_text(strip=True)
    return _td_plain_text(td)


def _class_cell_text(td: Tag) -> str:
    tag_a = td.find("a")
    if tag_a and tag_a.get_text(strip=True):
        return tag_a.get_text(strip=True)
    return _td_plain_text(td)


def _normalize_status(text: str) -> str | None:
    t = text.strip().upper()
    if not t:
        return None
    for tok in ("ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED", "CANCELLED"):
        if tok in t.replace(" ", ""):
            return tok
        if tok in t:
            return tok
    return t


def _parse_results_table(html: str) -> list[dict[str, Any]]:
    """Parse AZ ROC SLDS results table HTML into structured license rows (pure)."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    if tbody is None:
        return []

    sticky: dict[str, str | None] = {
        "business_name": None,
        "name_and_title": None,
        "address": None,
        "phone": None,
    }
    parsed: list[dict[str, Any]] = []

    for tr in tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        if _separator_row(tds):
            continue

        merged: dict[str, Any] = {
            "business_name": sticky["business_name"],
            "name_and_title": sticky["name_and_title"],
            "address": sticky["address"],
            "phone": sticky["phone"],
            "license_number": None,
            "classification": None,
            "qualifying_party": None,
            "status": None,
        }

        saw_license = False
        for td in tds:
            label = (td.get("data-label") or "").strip()
            plain = _td_plain_text(td)
            if label == "Business Name":
                sticky["business_name"] = plain
                merged["business_name"] = plain
            elif label == "Name and Title":
                sticky["name_and_title"] = plain
                merged["name_and_title"] = plain
            elif label == "Address":
                sticky["address"] = plain
                merged["address"] = plain
            elif label == "Phone":
                sticky["phone"] = plain
                merged["phone"] = plain
            elif label == "License No":
                lic = (_license_cell_text(td) or "").strip() or None
                merged["license_number"] = lic
                saw_license = bool(lic)
            elif label == "ClassName":
                cls_txt = (_class_cell_text(td) or "").strip() or None
                merged["classification"] = cls_txt
            elif label == "qp Name":
                merged["qualifying_party"] = plain or None
            elif label == "status":
                merged["status"] = _normalize_status(plain) if plain else None

        if saw_license:
            parsed.append(merged)

    return parsed


def _normalize_ws(value: str) -> str:
    return " ".join(value.split())


def _business_matches_query(blob: str | None, query_normalized: str) -> bool:
    if not blob or not query_normalized:
        return False
    blob_n = _normalize_ws(blob).lower()
    if blob_n == query_normalized:
        return True
    for segment in re.split(r"\n+|(?:DBA\s*:)", blob, flags=re.IGNORECASE):
        if _normalize_ws(segment).lower() == query_normalized:
            return True
    return False


def pick_best_az_roc_row(rows: list[dict[str, Any]], business_name: str) -> dict[str, Any] | None:
    """Select the best AZ ROC license row — pure helper for matching rules + tests."""
    if not rows:
        return None
    qnorm = _normalize_ws(business_name.strip()).lower()
    if qnorm:
        for row in rows:
            blob = row.get("business_name")
            if isinstance(blob, str) and _business_matches_query(blob, qnorm):
                return row
    for row in rows:
        if str(row.get("status") or "").upper() == "ACTIVE":
            return row
    return rows[0]
