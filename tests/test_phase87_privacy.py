"""Phase 8.7 — privacy page, Sentry scrubbing, diagnostic gating, hint log redaction."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, scrub_sentry_breadcrumb, scrub_sentry_event


def test_scrub_sentry_event_scrubs_api_chat_request_body() -> None:
    event: dict = {
        "request": {
            "url": "https://example.com/api/chat",
            "method": "POST",
            "data": '{"query":"SECRET_QUERY","session_id":"x"}',
        }
    }
    out = scrub_sentry_event(event, {})
    assert out is not None
    assert out["request"]["data"] == "<scrubbed>"
    assert "SECRET_QUERY" not in json.dumps(out)


def test_scrub_sentry_event_does_not_scrub_legacy_chat_path() -> None:
    """Legacy ``POST /chat`` is unwired (H1); scrubbing applies only to ``/api/chat``.

    Synthetic Sentry payloads may still reference ``…/chat`` URLs from historical
    clients or breadcrumbs — those bodies are intentionally left intact so scrub
    scope matches the live routed endpoints only.
    """
    body = '{"message":"M1","session_id":"s"}'
    event: dict = {
        "request": {
            "url": "http://localhost:8000/chat",
            "data": body,
        }
    }
    out = scrub_sentry_event(event, {})
    assert out is not None
    assert out["request"]["data"] == body


def test_scrub_sentry_event_scrubs_sensitive_extra_keys() -> None:
    event: dict = {
        "request": {"url": "http://x/health"},
        "extra": {"query": "SHOULD_SCRUB", "ok": 1},
    }
    out = scrub_sentry_event(event, {})
    assert out["extra"]["query"] == "<scrubbed>"
    assert out["extra"]["ok"] == 1


def test_scrub_sentry_breadcrumb_scrubs_body_like_data() -> None:
    crumb: dict = {"category": "httplib", "data": {"body": '{"message":"X"}', "method": "POST"}}
    out = scrub_sentry_breadcrumb(crumb, {})
    assert out is not None
    assert out["data"]["body"] == "<scrubbed>"


@pytest.mark.parametrize(
    "raw_val",
    ["", "0", "false", "no", "FALSE"],
)
def test_is_search_diag_verbose_false(monkeypatch: pytest.MonkeyPatch, raw_val: str) -> None:
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", raw_val)
    from app.core.search_log import is_search_diag_verbose

    assert is_search_diag_verbose() is False


@pytest.mark.parametrize("raw_val", ["true", "1", "yes", "TRUE"])
def test_is_search_diag_verbose_true(monkeypatch: pytest.MonkeyPatch, raw_val: str) -> None:
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", raw_val)
    from app.core import search_log as sl

    assert sl.is_search_diag_verbose() is True


def test_search_log_skips_when_not_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARCH_DIAG_VERBOSE", raising=False)
    from app.core import search_log as sl

    sl._log.handlers.clear()
    mock_log = MagicMock()
    with patch.object(sl, "_log", mock_log):
        sl.log_query("secret", "SEARCH_EVENTS", {}, "RUN_BROAD")
    mock_log.info.assert_not_called()


def test_search_log_writes_when_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verbose mode must emit search_diag log records (file sink is OS-buffered in CI)."""
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", "true")
    from app.core import search_log as sl

    sl._log.handlers.clear()
    assert sl.is_search_diag_verbose() is True
    assert not isinstance(sl._log, MagicMock), (
        "search_diag logger must not stay mocked between tests"
    )
    with patch.object(sl._log, "info") as info:
        sl.log_query("hello", "SEARCH_EVENTS", {"a": 1}, "RUN_BROAD")
    assert info.call_count >= 2
    joined = " ".join(" ".join(str(a) for a in (c.args or ())) for c in info.call_args_list)
    assert "hello" in joined
    assert "SEARCH_EVENTS" in joined


def test_privacy_route_200_and_markers() -> None:
    with TestClient(app) as client:
        r = client.get("/privacy")
    assert r.status_code == 200
    body = r.text
    assert "hello@askhava.com" in body
    assert "What we collect" in body
    assert "Anthropic" in body
    assert "Plausible" in body
    # B-06 hygiene: no personal email, no drafting TODOs shipped to prod.
    assert "caseylsolomon@gmail.com" not in body
    assert "TODO" not in body


def test_terms_route_200_and_markers() -> None:
    with TestClient(app) as client:
        r = client.get("/terms")
    assert r.status_code == 200
    body = r.text
    assert "Terms of Service for Hava" in body
    assert "1. Acceptance" in body
    assert "State of Arizona" in body
    assert "hello@askhava.com" in body
    # Substance the monetization plan depends on: AI-accuracy disclaimer and
    # labeled-paid-placement disclosure must be present.
    assert "AI answers can be wrong" in body
    assert "Paid placements are always" in body
    # The attorney-review tripwire lives in the SOURCE markdown only — the
    # renderer strips HTML comments so drafting notes never ship in public
    # page source (QA audit 2026-06-10: live /terms exposed "Drafted by AI …
    # needs attorney review" to anyone who hit View Source).
    assert "needs attorney review before commercial launch" not in body
    from app.main import _TOS_MD_PATH

    assert "needs attorney review before commercial launch" in _TOS_MD_PATH.read_text(
        encoding="utf-8"
    )


def test_terms_has_no_lawyer_placeholders() -> None:
    """B-06: the live /terms page must not ship drafting notes or placeholders."""
    with TestClient(app) as client:
        r = client.get("/terms")
    assert r.status_code == 200
    body = r.text
    # NB: bare "placeholder" would false-positive on the topbar search input's
    # placeholder= attribute, so the old §9 note is matched in rendered form.
    for marker in (
        "jurisdiction to be specified",
        "<strong>placeholder</strong>",
        "lawyer review",
        "TODO",
        "caseylsolomon@gmail.com",
        "[COMPANY]",
        "[STATE]",
    ):
        assert marker not in body, f"placeholder marker still live: {marker!r}"


def test_root_redirects_to_home() -> None:
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert str(r.url).endswith("/home")
    # Lake Ink & Brass home: the base tokens stylesheet + the hero lede.
    assert "/static/styles/lake.css" in r.text
    assert '<h1 class="asklede">Everything in Lake Havasu, in one place.</h1>' in r.text


def test_jinja2_templates_directory_resolves() -> None:
    """Smoke: privacy_doc template renders /privacy without exploding (Slice 51 wiring).

    Catches the "templates dir wrong" failure mode early — if Jinja2Templates
    cannot resolve the configured directory, the call to render any page
    raises before the response is built.
    """
    with TestClient(app) as client:
        r = client.get("/privacy")
    assert r.status_code == 200
    # Lake Ink & Brass: the markdown doc renders inside the .article element.
    assert '<article class="article">' in r.text


def test_hint_extractor_validation_failure_logs_no_raw_json(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:

    from app.chat import hint_extractor as he

    bad_json = '{"extracted_hints": "not-an-object"}'

    class _Msg:
        content = bad_json

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]
        usage = None

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        class chat:
            class completions:
                @staticmethod
                def create(*a: object, **k: object) -> object:
                    return _Completion()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(he, "OpenAI", _Client)
    caplog.set_level(logging.INFO, logger="root")
    with caplog.at_level(logging.INFO):
        # Needs a query that passes the hint signal gate (age phrasing) so the
        # LLM path actually runs; "xyz123" remains the unique token we assert is
        # never logged. (Gate tightened in P1-2 — a bare digit no longer fires.)
        assert he.extract_hints("for my 8 year old, something unique xyz123") is None
    joined = caplog.text + "".join(str(r.getMessage()) for r in caplog.records)
    assert "xyz123" not in joined
    assert "not-an-object" not in joined
    assert "raw length=" in joined.lower() or "envelope validation failed" in joined.lower()
