"""Tests for the shared contact normalizers (Item D).

Run: python -m pytest tests/test_contact_norm.py -q
"""

from __future__ import annotations

from app.utils.contact_norm import norm_domain, norm_phone


def test_norm_domain_strips_scheme_www_path_query_port():
    assert norm_domain("https://www.JoesBar.com/contact?x=1") == "joesbar.com"
    assert norm_domain("http://joesbar.com") == "joesbar.com"
    assert norm_domain("joesbar.com:8080/") == "joesbar.com"
    assert norm_domain("https://www.joes.com") == norm_domain("http://joes.com/")
    assert norm_domain("#frag-only") is None or norm_domain("#frag-only") == ""
    assert norm_domain("") is None
    assert norm_domain(None) is None


def test_norm_domain_host_only_collapses_paths():
    # The dedup semantic: two pages on one site -> same key.
    assert norm_domain("joes.com/menu") == "joes.com"
    assert norm_domain("joes.com/contact") == "joes.com"
    assert norm_domain("joes.com/menu") == norm_domain("joes.com/contact")


def test_norm_phone_last10_strips_country_code():
    assert norm_phone("(702) 787-9568") == "7027879568"
    assert norm_phone("+1 702-787-9568") == "7027879568"
    assert norm_phone("1.702.787.9568") == "7027879568"
    assert norm_phone("787-9568") is None
    assert norm_phone("12345") is None
    assert norm_phone(None) is None
