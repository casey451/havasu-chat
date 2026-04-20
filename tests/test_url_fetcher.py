"""Tests for ``app.contrib.url_fetcher`` (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.contrib.url_fetcher import fetch_url_metadata


def _client_mock_for_stream(resp: MagicMock) -> MagicMock:
    stream_cm = MagicMock()
    stream_cm.__enter__.return_value = resp
    stream_cm.__exit__.return_value = None
    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    return client


@patch("app.contrib.url_fetcher.httpx.Client")
def test_success_title_and_meta_description(mock_cls: MagicMock) -> None:
    body = b"<html><head><title>Plain</title><meta name='description' content='  Meta desc  '/></head></html>"
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = httpx.Headers({"content-type": "text/html; charset=utf-8"})
    resp.url = "https://example.com/page"
    resp.iter_bytes = MagicMock(return_value=iter([body]))
    mock_cls.return_value = _client_mock_for_stream(resp)
    r = fetch_url_metadata("https://example.com/page")
    assert r.status == "success"
    assert r.title == "Plain"
    assert r.description == "Meta desc"
    assert "example.com" in (r.final_url or "")


@patch("app.contrib.url_fetcher.httpx.Client")
def test_opengraph_preferred(mock_cls: MagicMock) -> None:
    body = (
        b"<html><head>"
        b"<title>Plain</title>"
        b"<meta property='og:title' content='OG Title'/>"
        b"<meta property='og:description' content='OG Desc'/>"
        b"</head></html>"
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = httpx.Headers({"content-type": "text/html"})
    resp.url = "https://ex.com/"
    resp.iter_bytes = MagicMock(return_value=iter([body]))
    mock_cls.return_value = _client_mock_for_stream(resp)
    r = fetch_url_metadata("https://ex.com/")
    assert r.status == "success"
    assert r.title == "OG Title"
    assert r.description == "OG Desc"


@patch("app.contrib.url_fetcher.httpx.Client")
def test_success_no_metadata(mock_cls: MagicMock) -> None:
    body = b"<html><head></head><body>hi</body></html>"
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = httpx.Headers({"content-type": "text/html"})
    resp.url = "https://ex.com/bare"
    resp.iter_bytes = MagicMock(return_value=iter([body]))
    mock_cls.return_value = _client_mock_for_stream(resp)
    r = fetch_url_metadata("https://ex.com/bare")
    assert r.status == "success"
    assert r.title is None
    assert r.description is None


@patch("app.contrib.url_fetcher.httpx.Client")
def test_http_404(mock_cls: MagicMock) -> None:
    resp = MagicMock()
    resp.status_code = 404
    resp.headers = httpx.Headers({"content-type": "text/html"})
    resp.url = "https://ex.com/missing"
    resp.iter_bytes = MagicMock(return_value=iter([b"gone"]))
    mock_cls.return_value = _client_mock_for_stream(resp)
    r = fetch_url_metadata("https://ex.com/missing")
    assert r.status == "error"
    assert "404" in (r.error_message or "")


@patch("app.contrib.url_fetcher.httpx.Client")
def test_timeout(mock_cls: MagicMock) -> None:
    client = MagicMock()
    client.stream.side_effect = httpx.TimeoutException("timeout")
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_cls.return_value = client
    r = fetch_url_metadata("https://ex.com/slow")
    assert r.status == "timeout"


@patch("app.contrib.url_fetcher.httpx.Client")
def test_connection_refused(mock_cls: MagicMock) -> None:
    client = MagicMock()
    client.stream.side_effect = httpx.RequestError("refused")
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_cls.return_value = client
    r = fetch_url_metadata("https://ex.com/ref")
    assert r.status == "error"


@patch("app.contrib.url_fetcher.httpx.Client")
def test_redirect_follows_and_records_final(mock_cls: MagicMock) -> None:
    body = b"<html><head><title>Final</title></head></html>"
    r1 = MagicMock()
    r1.status_code = 302
    r1.headers = httpx.Headers({"location": "/dest", "content-type": "text/html"})
    r1.url = "https://ex.com/start"
    r1.iter_bytes = MagicMock(return_value=iter([b""]))
    r2 = MagicMock()
    r2.status_code = 200
    r2.headers = httpx.Headers({"content-type": "text/html"})
    r2.url = "https://ex.com/dest"
    r2.iter_bytes = MagicMock(return_value=iter([body]))
    stream_cm1 = MagicMock()
    stream_cm1.__enter__.return_value = r1
    stream_cm1.__exit__.return_value = None
    stream_cm2 = MagicMock()
    stream_cm2.__enter__.return_value = r2
    stream_cm2.__exit__.return_value = None
    client = MagicMock()
    client.stream = MagicMock(side_effect=[stream_cm1, stream_cm2])
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_cls.return_value = client
    r = fetch_url_metadata("https://ex.com/start")
    assert r.status == "success"
    assert r.title == "Final"
    assert r.final_url.endswith("/dest")


@patch("app.contrib.url_fetcher.httpx.Client")
def test_redirect_to_private_ip_blocked(mock_cls: MagicMock) -> None:
    r1 = MagicMock()
    r1.status_code = 302
    r1.headers = httpx.Headers({"location": "http://10.0.0.1/h", "content-type": "text/html"})
    r1.url = "https://ex.com/start"
    r1.iter_bytes = MagicMock(return_value=iter([b""]))
    stream_cm1 = MagicMock()
    stream_cm1.__enter__.return_value = r1
    stream_cm1.__exit__.return_value = None
    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm1)
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_cls.return_value = client
    r = fetch_url_metadata("https://ex.com/start")
    assert r.status == "error"
    assert r.error_message and "blocked" in r.error_message


@patch("app.contrib.url_fetcher.httpx.Client")
def test_bad_content_type(mock_cls: MagicMock) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = httpx.Headers({"content-type": "application/octet-stream"})
    resp.url = "https://ex.com/bin"
    resp.iter_bytes = MagicMock(return_value=iter([b"\x00\x01"]))
    mock_cls.return_value = _client_mock_for_stream(resp)
    r = fetch_url_metadata("https://ex.com/bin")
    assert r.status == "error"
    assert "content_type" in (r.error_message or "").lower()
