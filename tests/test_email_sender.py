"""Tests for app.auth.email_sender (Phase 2A.1 Resend scaffold)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.auth.email_sender import send_magic_link


def test_send_magic_link_dev_mode_logs_and_skips_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.setenv("AUTH_MAGIC_LINK_BASE_URL", "https://app.example.com")
    with patch("app.auth.email_sender.httpx.Client") as client_cls:
        with patch("app.auth.email_sender.logger.info") as mock_info:
            send_magic_link("user@example.com", "secret-token-xyz")
            client_cls.assert_not_called()
            mock_info.assert_called_once()
            fmt, email_arg, url_arg = mock_info.call_args[0]
            assert "AUTH_DEV_MODE" in fmt
            assert email_arg == "user@example.com"
            assert url_arg == "https://app.example.com/auth/callback?token=secret-token-xyz"


def test_send_magic_link_missing_base_url_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_MAGIC_LINK_BASE_URL", raising=False)
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    with pytest.raises(RuntimeError, match="AUTH_MAGIC_LINK_BASE_URL"):
        send_magic_link("x@example.com", "tok")


def test_send_magic_link_prod_posts_resend_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    monkeypatch.setenv("AUTH_MAGIC_LINK_BASE_URL", "https://prod.example.com/")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "Hava <noreply@example.com>")

    mock_http = MagicMock()
    ok = MagicMock()
    ok.raise_for_status = MagicMock()
    mock_http.post.return_value = ok
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_http
    mock_cm.__exit__.return_value = None

    with patch("app.auth.email_sender.httpx.Client", return_value=mock_cm):
        send_magic_link("buyer@example.com", "plain-tok")

    mock_http.post.assert_called_once()
    args, kwargs = mock_http.post.call_args
    assert args[0] == "https://api.resend.com/emails"
    body = kwargs["json"]
    assert body["from"] == "Hava <noreply@example.com>"
    assert body["to"] == ["buyer@example.com"]
    assert body["subject"] == "Sign in to Havasu Chat"
    assert "html" in body and "text" in body
    assert "https://prod.example.com/auth/callback?token=plain-tok" in body["text"]
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer re_test_key"
    assert headers["Content-Type"] == "application/json"


def test_send_magic_link_resend_4xx_5xx_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    monkeypatch.setenv("AUTH_MAGIC_LINK_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "Hava <noreply@example.com>")

    req = httpx.Request("POST", "https://api.resend.com/emails")
    bad = httpx.Response(502, request=req)

    mock_http = MagicMock()
    mock_http.post.return_value = bad
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_http
    mock_cm.__exit__.return_value = None

    with patch("app.auth.email_sender.httpx.Client", return_value=mock_cm):
        with pytest.raises(httpx.HTTPStatusError):
            send_magic_link("x@example.com", "tok")
