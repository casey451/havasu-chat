"""Fetch-step decode: honor explicit server charset, otherwise assume UTF-8.

Regression guard for the "Wellness & Beauty Event 💋" -> "?" emoji corruption:
when a source page omits its charset header, httpx may fall back to a non-UTF-8
codec (latin-1) that mangles multibyte/emoji bytes. The scrapers force UTF-8 in
that case while still respecting an explicitly declared charset.
"""

from __future__ import annotations

import httpx

from app.contrib.allevents import _decode_response as allevents_decode
from app.events.scrapers.base import _decode_response as base_decode

# UTF-8 bytes for a title with an emoji; the kiss-mark emoji is the regression case.
_TITLE = "Wellness & Beauty Event 💋"
_UTF8_BODY = _TITLE.encode("utf-8")


def _resp(content: bytes, content_type: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": content_type})


def test_allevents_decodes_emoji_without_charset_header() -> None:
    # No charset declared: must not corrupt the emoji into "?".
    resp = _resp(_UTF8_BODY, "text/html")
    out = allevents_decode(resp)
    assert "💋" in out
    assert out == _TITLE
    assert "?" not in out


def test_base_decodes_emoji_without_charset_header() -> None:
    resp = _resp(_UTF8_BODY, "text/html")
    out = base_decode(resp)
    assert "💋" in out
    assert out == _TITLE


def test_explicit_server_charset_is_honored() -> None:
    # A server that genuinely serves latin-1 and says so must be decoded as latin-1.
    body = "Café".encode("latin-1")
    resp = _resp(body, "text/html; charset=iso-8859-1")
    assert allevents_decode(resp) == "Café"
    assert base_decode(resp) == "Café"


def test_explicit_utf8_charset_preserves_emoji() -> None:
    resp = _resp(_UTF8_BODY, "text/html; charset=utf-8")
    assert allevents_decode(resp) == _TITLE
    assert base_decode(resp) == _TITLE
