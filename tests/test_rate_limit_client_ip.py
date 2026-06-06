"""P1-10: the rate-limit key must be the real client IP (leftmost
X-Forwarded-For behind Railway), not the shared proxy peer address."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.rate_limit import client_ip_key


def _req(headers: dict[str, str], host: str) -> SimpleNamespace:
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_uses_leftmost_forwarded_for() -> None:
    req = _req({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
    assert client_ip_key(req) == "203.0.113.7"


def test_single_forwarded_for_entry() -> None:
    req = _req({"x-forwarded-for": "198.51.100.9"}, "10.0.0.1")
    assert client_ip_key(req) == "198.51.100.9"


def test_falls_back_to_peer_when_no_header() -> None:
    req = _req({}, "198.51.100.5")
    assert client_ip_key(req) == "198.51.100.5"


def test_malformed_forwarded_for_falls_back_to_peer() -> None:
    # A garbage X-Forwarded-For must not become a shared rate-limit key.
    req = _req({"x-forwarded-for": "not-an-ip, 10.0.0.1"}, "198.51.100.5")
    assert client_ip_key(req) == "198.51.100.5"


def test_ipv6_forwarded_for_is_accepted() -> None:
    req = _req({"x-forwarded-for": "2001:db8::1, 10.0.0.1"}, "10.0.0.1")
    assert client_ip_key(req) == "2001:db8::1"
