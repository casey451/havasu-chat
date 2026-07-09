"""H1 (P6 security): merchant creative URLs are validated server-side.

The creative form's ``type="url"`` is client-only — a direct POST bypasses it.
``cta_url`` / ``image_url`` render onto public, cross-user pages (the CTA link and
a CSS background-image), so an unsafe scheme must be rejected before it persists.
"""

from __future__ import annotations

from app.portal.router import _CREATIVE_URL_ERROR, _creative_url_errors


def _errs(cta="", image="", image_mobile=""):
    return _creative_url_errors(cta_url=cta, image_url=image, image_url_mobile=image_mobile)


def test_https_and_relative_upload_paths_pass() -> None:
    assert _errs(cta="https://barleybros.com", image="/media/creatives/abc.png") == {}
    assert _errs(cta="http://example.com/menu") == {}


def test_empty_fields_are_allowed() -> None:
    # A creative may carry no CTA and use a file upload — empties never error.
    assert _errs() == {}
    assert _errs(cta="   ") == {}


def test_javascript_scheme_is_rejected() -> None:
    errs = _errs(cta="javascript:alert(document.cookie)")
    assert errs == {"cta_url": _CREATIVE_URL_ERROR}


def test_data_and_protocol_relative_image_urls_rejected() -> None:
    assert _errs(image="data:text/html;base64,PHNjcmlwdD4=") == {"image_url": _CREATIVE_URL_ERROR}
    assert _errs(image_mobile="//evil.example/x.png") == {"image_url_mobile": _CREATIVE_URL_ERROR}


def test_each_bad_field_reported_independently() -> None:
    errs = _errs(cta="vbscript:x", image="javascript:y", image_mobile="https://ok.example/i.png")
    assert set(errs) == {"cta_url", "image_url"}
