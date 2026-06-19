"""Phase 5a — Lake Ink & Brass editorial / trust pages.

/about, /help, /contact, /privacy, /terms all render on an empty DB (static
copy + markdown docs), so they go through the real routes (TestClient). Asserts
flag-swap + desert default, single-h1, structural a11y, and the FAQPage (help) +
AboutPage (about) JSON-LD.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app


def _ld(html: str) -> list[dict]:
    return [json.loads(b) for b in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


def _client() -> TestClient:
    return TestClient(app)


def test_desert_editorial_is_default() -> None:
    for path in ("/about", "/help", "/contact", "/privacy", "/terms"):
        b = _client().get(path).text
        assert 'data-theme="lake"' not in b, path
        assert "lake_editorial.css" not in b, path


def test_lake_about_aboutpage_schema() -> None:
    b = _client().get("/about?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_editorial.css" in b
    about = next(x for x in _ld(b) if x.get("@type") == "AboutPage")
    assert about["name"] == "About Ask Hava"
    assert "no engagement loops" in b  # real copy ported
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_help_faqpage_schema() -> None:
    b = _client().get("/help?theme=lake").text
    assert 'data-theme="lake"' in b
    faq = next(x for x in _ld(b) if x.get("@type") == "FAQPage")
    assert len(faq["mainEntity"]) == 5
    assert faq["mainEntity"][0]["name"] == "How do I sign in?"
    assert faq["mainEntity"][0]["acceptedAnswer"]["@type"] == "Answer"
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_contact() -> None:
    b = _client().get("/contact?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "hello@askhava.com" in b
    assert 'href="/contribute"' in b and 'href="/account"' in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_privacy_and_terms() -> None:
    for path, marker in (("/privacy", "Privacy"), ("/terms", "Terms")):
        b = _client().get(f"{path}?theme=lake").text
        assert 'data-theme="lake"' in b, path
        assert "/static/styles/lake_editorial.css" in b, path
        assert marker in b, path  # markdown body rendered
        assert b.count("<h1") == 1, path  # one h1 (from the markdown body)
        assert not _a11y(b), path
