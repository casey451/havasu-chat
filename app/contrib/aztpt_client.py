"""Arizona Transaction Privilege Tax (TPT) license verification client (V1.5
Trust-Signal Verifier Bundle wave 4, ticket #22).

§3.1 probe (2026-05-24): the public verifier at
``https://www.aztaxes.gov/Home/LicenseVerification`` is client-rendered and
accepts **eight-digit license numbers only** (not business names). The form is
gated by Google reCAPTCHA. There is no documented bulk roster or name-search
REST API.

This client uses headless Playwright (``playwright.sync_api``, same pattern as
:mod:`app.contrib.azcc_towing_client`) to load the verifier page. When reCAPTCHA
blocks automation or the portal cannot search by business name, the fetch returns
an empty list so the verifier counts ``skipped_no_match`` rather than crash
(functional-but-inert per pattern win 33).

The ``httpx.Client`` argument mirrors sibling verifier clients for signature
compatibility; Playwright manages HTTP for live lookups.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_URL: Final[str] = "https://www.aztaxes.gov/Home/LicenseVerification"


def fetch_aztpt_license_search(
    client: httpx.Client,
    *,
    name: str,
    verify_url: str = DEFAULT_VERIFY_URL,
) -> list[dict[str, Any]]:
    """Return normalized TPT license rows for ``name``.

    The AZTaxes portal verifies by license number, not business name. Without
    a captcha-free name lookup this returns ``[]`` after detecting the
    reCAPTCHA gate (functional-but-inert path). When automation can submit a
    license lookup in future, rows include ``tpt_license_number`` and
    ``business_status``.
    """
    _unused_client = client
    query = (name or "").strip()
    if not query:
        return []
    try:
        return _playwright_lookup(verify_url, query)
    except Exception:
        logger.warning(
            "aztpt_client.fetch_failed",
            extra={"name": query, "verify_url": verify_url},
            exc_info=True,
        )
        return []


def _playwright_lookup(verify_url: str, query: str) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_navigation_timeout(120_000)
            page.set_default_timeout(60_000)
            page.goto(verify_url, wait_until="domcontentloaded", timeout=120_000)

            if page.locator("input#LicenseNumber, input[name='LicenseNumber']").count() == 0:
                logger.info(
                    "aztpt_client.form_missing",
                    extra={"name": query, "verify_url": verify_url},
                )
                return []

            recaptcha = page.locator(
                "iframe[src*='recaptcha'], input[name='RecaptchaResponse']"
            ).count()
            if recaptcha:
                logger.info(
                    "aztpt_client.captcha_blocked",
                    extra={"name": query, "verify_url": verify_url},
                )
                return []

            body = page.locator("body").inner_text().lower()
            if "eight digit" in body and "license number" in body:
                logger.info(
                    "aztpt_client.license_number_only",
                    extra={"name": query, "verify_url": verify_url},
                )
                return []

            license_input = page.locator("input#LicenseNumber, input[name='LicenseNumber']").first
            license_input.fill(query[:8])
            page.locator("input#idSubmit, input[type='submit']").first.click()
            page.wait_for_timeout(5_000)

            if page.locator("text=Invalid").count():
                return []

            result_text = page.locator("body").inner_text()
            return _parse_result_text(result_text, query)
        finally:
            browser.close()


def _parse_result_text(text: str, query: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    if "valid" in lowered and "license" in lowered:
        return [
            {
                "tpt_license_number": query[:8],
                "business_status": "Valid",
                "business_name": query,
            }
        ]
    if "invalid" in lowered or "not found" in lowered:
        return []
    return []
