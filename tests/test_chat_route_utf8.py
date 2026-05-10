"""BACKLOG #56 — regression tests for JSON body encoding on ``POST /api/chat``.

Architectural assumption being pinned:

If a future middleware decodes body bytes with ``errors="replace"`` instead of
strict UTF-8, latin-1 / mis-encoded input will return **200** with mojibake
characters in the parsed ``query`` rather than **400** from Starlette's strict
body decode — silently regressing accented-query handling. These tests fail
loudly when that change ships.

``json.dumps`` defaults to ``ensure_ascii=True``, which escapes non-ASCII code
points as ``\\uXXXX`` so the wire payload stays ASCII-only. That never exercises
UTF-8 decoding of accented bytes. Accented-on-wire cases therefore use
``ensure_ascii=False``.

See BACKLOG #51 close-out (doc-only): Starlette rejects mislabeled bytes with
400 before any FastAPI handler runs — there was no automated coverage until #56.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import app

ACCENTED_QUERY = "múdshärk bréwery"
SESSION_ID = "smoke-56"

_STRICT_JSON_UTF8 = "application/json; charset=utf-8"

# Observed Starlette / FastAPI response when JSON body bytes cannot be decoded
# as declared (strict UTF-8). Pin exact string so regressions are visible.
STARLETTE_BODY_PARSE_ERROR_MSG = "There was an error parsing the body"

_EXPECTED_RESPONSE_KEYS = frozenset(
    {
        "response",
        "voice",
        "component",
        "mode",
        "sub_intent",
        "entity",
        "tier_used",
        "latency_ms",
        "llm_tokens_used",
        "chat_log_id",
    }
)


def _assert_concierge_chat_response_shape(data: dict[str, Any]) -> None:
    """Response matches :class:`ConciergeChatResponse` JSON shape."""
    assert set(data.keys()) == _EXPECTED_RESPONSE_KEYS
    assert isinstance(data["latency_ms"], int)
    assert isinstance(data["component"], dict)
    assert "type" in data["component"]


def test_api_chat_accented_query_utf8_bytes_round_trips_200() -> None:
    """Case (a): UTF-8 bytes + ``charset=utf-8`` — handler runs (200).

    Matcher behavior (entity null vs hit) is orthogonal to wire decoding.
    """
    payload = {"query": ACCENTED_QUERY, "session_id": SESSION_ID}
    body_utf8 = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            content=body_utf8,
            headers={"Content-Type": _STRICT_JSON_UTF8},
        )
    assert r.status_code == 200
    data = r.json()
    _assert_concierge_chat_response_shape(data)


def test_api_chat_latin1_wire_bytes_return_400_parse_error() -> None:
    """Case (b): ISO-8859-1 bytes — 400 (JSON body must be UTF-8 octets).

    Mirrors PowerShell's default wire encoding for accented text: bytes are not
    valid UTF-8 sequences. Starlette's JSON body path rejects them **before** the
    FastAPI handler — even when ``Content-Type`` declares ``charset=latin-1``,
    JSON parsing still expects UTF-8 per RFC 8259.

    Same failure mode if those latin-1 bytes are mislabeled as UTF-8 (common
    client bug): strict decode raises ``UnicodeDecodeError`` → 400 with the same
    ``detail`` string.
    """
    payload = {"query": ACCENTED_QUERY, "session_id": SESSION_ID}
    body_latin1 = json.dumps(payload, ensure_ascii=False).encode("latin-1")
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            content=body_latin1,
            headers={"Content-Type": "application/json; charset=latin-1"},
        )
    assert r.status_code == 400
    assert r.json() == {"detail": STARLETTE_BODY_PARSE_ERROR_MSG}


def test_api_chat_utf8_wire_valid_declared_charset_matches_200() -> None:
    """Case (c): strict UTF-8 decode succeeds — 200; semantic mojibake ≠ transport 400.

    Raw Windows-1252 / latin-1 octets labeled ``charset=utf-8`` often **fail**
    UTF-8 decoding (see case (b)) → 400. CC's matrix instead targets the case where
    the **bytes are valid UTF-8** (declaration matches; Starlette accepts) while the
    resulting Unicode text is still wrong for the user's intent — classic
    double-decoding mojibake: UTF-8 bytes reinterpreted through latin-1.

    That corruption must not be “fixed” by middleware that decodes wire bytes with
    ``errors="replace"`` — which would turn decode failures into silent 200s with
    junk queries.
    """
    mojibake_query = ACCENTED_QUERY.encode("utf-8").decode("latin-1")
    payload = {"query": mojibake_query, "session_id": SESSION_ID}
    body_utf8_mojibake = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            content=body_utf8_mojibake,
            headers={"Content-Type": _STRICT_JSON_UTF8},
        )
    assert r.status_code == 200
    data = r.json()
    _assert_concierge_chat_response_shape(data)


def test_api_chat_ascii_json_baseline_200() -> None:
    """Case (d): pure ASCII JSON — sanity check that ``content=`` POST works."""
    payload = {"query": "mudshark brewery", "session_id": SESSION_ID}
    body = json.dumps(payload).encode("ascii")
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            content=body,
            headers={"Content-Type": _STRICT_JSON_UTF8},
        )
    assert r.status_code == 200
    data = r.json()
    _assert_concierge_chat_response_shape(data)
