"""Tests for the shared contact normalizers (Item D).

Run: python -m pytest tests/test_contact_norm.py -q
"""

from __future__ import annotations

from app.utils.contact_norm import is_identity_domain, norm_domain, norm_phone


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


def test_is_identity_domain_accepts_real_business_hosts():
    assert is_identity_domain("joesbar.com") is True
    assert is_identity_domain("havasumedicalgroup.com") is True
    # expects a bare host (as from norm_domain); a real business subdomain is fine
    assert is_identity_domain("shop.joesbar.com") is True


def test_is_identity_domain_rejects_multitenant_hosts():
    # social, aggregators, marketplaces, builders -> not a same-business signal
    for host in (
        "facebook.com",
        "m.facebook.com",  # subdomain of a denylisted base
        "instagram.com",
        "linktr.ee",
        "yelp.com",
        "maps.google.com",  # covered by google.com base
        "business.site",
        "bluepillow.com",
        "foo.wixsite.com",  # any builder subdomain is a different tenant
    ):
        assert is_identity_domain(host) is False, host


def test_is_identity_domain_empty_is_false():
    assert is_identity_domain(None) is False
    assert is_identity_domain("") is False
    assert is_identity_domain("   ") is False
