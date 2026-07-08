"""Every ``<a>`` must have a non-empty accessible name — no icon-only anchor may
fall back to announcing its raw ``href``.

An icon-only anchor with no accessible name (no inner text, no ``aria-label`` /
``aria-labelledby``, no labeled SVG ``<title>``, no ``<img alt>``) makes
text-mode consumers — screen readers, HTML-to-text converters, some crawlers —
read out the raw ``href`` (e.g. a search icon announced as "/chat"). This test
permanently retires that whole raw-path-label class (M14): it holds across EVERY
chrome, current and future, not just the ones we know about today.

Two complementary checks:
* ``test_rendered_pages`` — parses real rendered HTML for a representative page
  per template family (authoritative; the shared header/footer ride on each).
* ``test_all_templates`` — a static scan over every template file, so
  data-dependent templates the render check can't reach (department / provider /
  leaf pages that need seeded rows) are still covered.
"""

from __future__ import annotations

import glob
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

# A representative renderable page per template family (each also carries the
# shared header/footer, where the icon-only anchors live).
_PAGES: tuple[str, ...] = (
    "/home",
    "/night",
    "/lake",
    "/family",
    "/family/camps",
    "/seniors",
    "/events-ui",
    "/calendar",
    "/movies",
    "/categories",
    "/gas",
    "/map",
    "/today",
    "/search?q=pizza",
    "/chat",
    "/about",
    "/help",
    "/contact",
)

_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_RE = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')
_JINJA_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)


def _attrs(attr_str: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR_RE.findall(attr_str)}


def _has_accessible_name(attr_str: str, inner: str) -> bool:
    attrs = _attrs(attr_str)
    if attrs.get("aria-label", "").strip() or attrs.get("aria-labelledby", "").strip():
        return True
    if _TAG_RE.sub("", inner).strip():  # visible text
        return True
    if re.search(r"<title\b[^>]*>\s*\S", inner, re.IGNORECASE):  # labeled SVG
        return True
    if re.search(r'<img\b[^>]*\balt\s*=\s*"[^"]*\S[^"]*"', inner, re.IGNORECASE):
        return True
    return False


@pytest.mark.parametrize("path", _PAGES)
def test_rendered_pages(path: str) -> None:
    with TestClient(app) as client:
        resp = client.get(path)
    assert resp.status_code == 200, f"{path} did not render (got {resp.status_code})"
    offenders = [
        f'href="{_attrs(a).get("href", "?")}"'
        for a, inner in _ANCHOR_RE.findall(resp.text)
        if not _has_accessible_name(a, inner)
    ]
    assert not offenders, (
        f"{path}: {len(offenders)} anchor(s) with no accessible name — a text-mode "
        f"reader would announce the raw href: {offenders}"
    )


def _template_has_accessible_name(attr_str: str, inner: str) -> bool:
    """Static (pre-render) variant: a Jinja ``{{ label }}`` / ``{{ x.title }}``
    expression in the inner counts as text (it renders to a name), but an
    ``{{ icon(...) }}`` / ``{{ cicon(...) }}`` call does not."""
    if "aria-label" in attr_str.lower() or "aria-labelledby" in attr_str.lower():
        return True
    if re.search(r"<title\b[^>]*>", inner, re.IGNORECASE):
        return True
    if re.search(r"<img\b[^>]*\balt=", inner, re.IGNORECASE):
        return True
    # plain literal text (tags + jinja stripped)
    if _TAG_RE.sub("", _JINJA_RE.sub("", inner)).strip():
        return True
    # a non-icon Jinja expression, e.g. {{ label }}, renders to a name
    without_svg = re.sub(r"<svg.*?</svg>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    for m in re.finditer(r"{{(.*?)}}", without_svg, re.DOTALL):
        if not re.match(r"\s*c?icon\s*\(", m.group(1)):
            return True
    return False


def test_all_templates() -> None:
    offenders: list[str] = []
    for path in glob.glob("app/**/*.html", recursive=True):
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        for attr_str, inner in _ANCHOR_RE.findall(html):
            if not _template_has_accessible_name(attr_str, inner):
                offenders.append(f"{path}: <a{attr_str.rstrip()}>")
    assert not offenders, (
        f"{len(offenders)} icon-only anchor(s) with no accessible name — add an "
        f"aria-label:\n  " + "\n  ".join(offenders)
    )
