"""Arizona Corporation Commission eCorp public business search client (V1.5
Trust-Signal Verifier Bundle wave 3, ticket #21).

Public entity search lives at ``https://arizonabusinesscenter.azcc.gov/businesssearch``
(2026-05-24 URL drift from legacy ``ecorp.azcc.gov/EntitySearch/Index``). The
Angular UI POSTs to ``https://api-azbusinessconnectonline.azcc.gov/api/publicsearch/public-search``
with a reCAPTCHA / image-captcha gate before results are returned.

This client uses headless Playwright (``playwright.sync_api``, same pattern as
:mod:`app.contrib.az_roc_client`) to drive the public search form and intercept
the JSON response when the portal returns rows without a captcha challenge.
When captcha blocks automation, the fetch returns an empty list so the verifier
can count ``skipped_no_match`` rather than crash the whole pass.

The ``httpx.Client`` argument mirrors sibling verifier clients for signature
compatibility; Playwright manages HTTP for live lookups.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_URL: Final[str] = "https://arizonabusinesscenter.azcc.gov/businesssearch"
PUBLIC_SEARCH_API_FRAGMENT: Final[str] = "publicsearch/public-search"


def fetch_azcc_entity_search(
    client: httpx.Client,
    *,
    name: str,
    search_url: str = DEFAULT_SEARCH_URL,
    county: str | None = None,
) -> list[dict[str, Any]]:
    """Return normalized AZCC entity rows whose names fuzzy-match ``name``.

    Each dict includes at minimum ``corp_id`` (entity/business id) and
    ``entity_name`` (display name). Additional registry fields are preserved
    when present in the API payload.

    Returns ``[]`` on transport/captcha failure — parallels
    :func:`app.contrib.azre_client.fetch_azre_lhc_vacation_rentals` fail-soft
    semantics so batch verify passes can continue.
    """
    _unused_client = client
    query = (name or "").strip()
    if not query:
        return []
    try:
        payload = _fetch_public_search_payload(search_url, query, county=county)
    except Exception:
        logger.warning(
            "azcc_towing_client.fetch_failed",
            extra={"name": query, "search_url": search_url},
            exc_info=True,
        )
        return []
    rows = _normalize_search_rows(payload)
    logger.info(
        "azcc_towing_client.fetch_complete",
        extra={"name": query, "county": county, "total": len(rows)},
    )
    return rows


def _fetch_public_search_payload(
    search_url: str,
    query: str,
    *,
    county: str | None,
) -> Any:
    from playwright.sync_api import sync_playwright

    captured: dict[str, Any] | None = None
    session_cookies = _parse_session_cookies((os.getenv("AZCC_SESSION_COOKIE") or "").strip())

    def _on_response(response) -> None:
        nonlocal captured
        if PUBLIC_SEARCH_API_FRAGMENT not in response.url:
            return
        if response.status != 200:
            return
        try:
            body = response.json()
        except Exception:
            return
        if isinstance(body, dict) and body.get("succeeded") and body.get("data"):
            captured = body

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            if session_cookies:
                try:
                    context.add_cookies(session_cookies)
                    logger.info(
                        "azcc_towing_client.cookie_primed",
                        extra={"count": len(session_cookies)},
                    )
                except Exception:
                    logger.warning(
                        "azcc_towing_client.cookie_prime_failed",
                        exc_info=True,
                    )
            page = context.new_page()
            page.on("response", _on_response)
            page.set_default_navigation_timeout(120_000)
            page.set_default_timeout(60_000)
            page.goto(search_url, wait_until="networkidle", timeout=120_000)

            name_input = page.locator("input#businessName, input[name='businessName']").first
            name_input.wait_for(state="visible", timeout=30_000)
            name_input.fill(query)

            if county:
                # County filter is optional; best-effort if the mat-select exists.
                county_select = page.locator("mat-select[formcontrolname='county'], mat-select").first
                if county_select.count():
                    try:
                        county_select.click()
                        page.get_by_role("option", name=county, exact=False).first.click()
                    except Exception:
                        logger.debug(
                            "azcc_towing_client.county_filter_skipped",
                            extra={"county": county},
                        )

            page.get_by_role("button", name="Business Search").click()
            page.wait_for_timeout(8_000)

            if captured is not None:
                return captured

            # Captcha gate -- portal shows image validation instead of API rows.
            if page.get_by_text("User validation required", exact=False).count():
                from app.contrib import _azcc_captcha_solver as _solver

                if _solver.is_tesseract_enabled():
                    max_retries = _solver.get_max_retries()
                    for _attempt in range(max_retries):
                        img_locator = page.locator("img.captcha-image").first
                        if not img_locator.count():
                            break
                        src = img_locator.get_attribute("src") or ""
                        guess = _solver.solve_captcha_image(src)
                        if guess:
                            page.locator("input[placeholder*='Enter the text']").first.fill(guess)
                            page.get_by_role("button", name="Verify").click()
                            page.wait_for_timeout(3_000)
                            if captured is not None:
                                return captured
                        refresh = page.locator(
                            "button[aria-label*='refresh'], .captcha-refresh"
                        ).first
                        if refresh.count():
                            try:
                                refresh.click()
                                page.wait_for_timeout(800)
                            except Exception:
                                break
                    logger.info(
                        "azcc_towing_client.captcha_unsolved",
                        extra={"name": query, "attempts": max_retries},
                    )
                else:
                    logger.info(
                        "azcc_towing_client.captcha_blocked",
                        extra={"name": query},
                    )
                return {"succeeded": False, "data": []}

            # Fall back to parsing any visible mat-table rows if API wasn't intercepted.
            table_text = page.locator("table, mat-table").first.inner_text(timeout=5_000)
            return {"succeeded": True, "data": _parse_table_fallback(table_text)}
        finally:
            browser.close()


def _parse_table_fallback(table_text: str) -> list[dict[str, Any]]:
    """Best-effort parse when JSON interception fails but HTML table rendered."""
    out: list[dict[str, Any]] = []
    for line in table_text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("business"):
            continue
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) >= 2:
            out.append({"corp_id": parts[0], "entity_name": parts[1]})
    return out


def _normalize_search_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, dict):
        rows = data.get("results") or data.get("businesses") or data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        corp_id = (
            row.get("businessId")
            or row.get("entityId")
            or row.get("entityNumber")
            or row.get("corp_id")
            or row.get("id")
        )
        entity_name = (
            row.get("businessName")
            or row.get("entityName")
            or row.get("name")
            or row.get("entity_name")
        )
        if corp_id is None and entity_name is None:
            continue
        normalized = dict(row)
        if corp_id is not None:
            normalized["corp_id"] = str(corp_id).strip()
        if entity_name is not None:
            normalized["entity_name"] = str(entity_name).strip()
        status = row.get("status") or row.get("entityStatus") or row.get("businessStatus")
        if status is not None:
            normalized["status"] = str(status).strip()
        out.append(normalized)
    return out


def _parse_session_cookies(raw: str) -> list[dict[str, Any]]:
    """Parse AZCC_SESSION_COOKIE env value (JSON list of cookie dicts).

    Returns [] on empty, malformed, or non-list input. Each cookie dict must
    have at minimum 'name' and 'value'; other keys passed through to
    Playwright's context.add_cookies as-is. Domain defaults to '.azcc.gov'
    when absent so operator-pasted cookies from the seed helper work without
    edits.
    """
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("azcc_towing_client.cookie_parse_failed")
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for c in parsed:
        if not isinstance(c, dict):
            continue
        if "name" not in c or "value" not in c:
            continue
        if "domain" not in c and "url" not in c:
            c = {**c, "domain": ".azcc.gov", "path": "/"}
        out.append(c)
    return out
