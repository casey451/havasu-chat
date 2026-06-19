"""ADA / WCAG 2.1 AA enforcement (2026-06-10 compliance pass).

Two layers:

1. A structural walk over every public page: images carry alt, form fields
   are programmatically labeled, links/buttons have accessible names, exactly
   one h1, a <main> landmark and a skip link exist, lang is set, ids are
   unique, zoom is never blocked, focusable elements are never aria-hidden,
   inline SVG is either decorative (aria-hidden) or named.
2. Contrast regression on the desert palette, parsed live from desert.css so
   a future palette tweak that breaks AA fails here, with the specific pair
   named. Design rule pinned: --orange is NEVER paired with --cream at body
   sizes (use --orange-deep); --orange-deep must clear 4.5:1 on all three
   light surfaces.

Heading-LEVEL skips (h1 -> h3 card titles on listing pages) are deliberately
not asserted: WCAG 2.4.10 is advisory, and card-title levels are a design
choice. Everything asserted here is a hard AA requirement.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_CSS_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "styles"

NAMELESS_INPUT_TYPES = {"hidden", "submit", "button", "image", "reset"}

ROUTES = [
    "/home",
    "/events-ui",
    "/events-ui?view=month",
    "/chat",
    "/categories",
    "/map",
    "/search?q=pizza",
    "/about",
    "/help",
    "/contact",
    "/login",
    "/contribute",
    "/gas",
    "/portal",
    "/portal/claim",
    "/privacy",
    "/terms",
    "/today",
    "/account",
    # Lake Ink & Brass redesign (Phase 0): the new base_lake layout + the full
    # component library, exercised through the same structural a11y contract.
    "/lake-styleguide",
]


class _A11yChecker(HTMLParser):
    """String-level WCAG structural checks (the v32 cheap-tripwire pattern)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[str] = []
        self.stack: list[tuple[str, dict]] = []
        self.text_for: list[list[str]] = []
        self.ids: Counter = Counter()
        self.h1 = 0
        self.has_main = False
        self.has_lang = False
        self.title_text = ""
        self._in_title = False
        self.label_for: set[str] = set()
        self.inputs_needing_label: list[tuple[str, dict]] = []
        self.skip_link = False
        self.label_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.has_lang = True
        if tag == "main" or a.get("role") == "main":
            self.has_main = True
        if tag == "title":
            self._in_title = True
        if a.get("id"):
            self.ids[a["id"]] += 1
        if tag == "img" and "alt" not in a:
            self.issues.append(f"img missing alt: src={a.get('src', '?')[:60]}")
        if tag == "iframe" and not a.get("title"):
            self.issues.append(f"iframe missing title: src={a.get('src', '?')[:60]}")
        if tag == "h1":
            self.h1 += 1
        tb = a.get("tabindex")
        if tb and tb.lstrip("+").isdigit() and int(tb) > 0:
            self.issues.append(f"positive tabindex={tb} on <{tag}>")
        if tag == "meta" and a.get("name") == "viewport":
            c = (a.get("content") or "").lower()
            if "user-scalable=no" in c or re.search(r"maximum-scale\s*=\s*(1(\.0*)?|0)\b", c):
                self.issues.append(f"viewport blocks zoom: {c}")
        if tag == "label":
            self.label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        if tag in ("a", "button"):
            self.stack.append((tag, a))
            self.text_for.append([])
        if tag == "a" and (a.get("href") or "").startswith("#main"):
            self.skip_link = True
        if tag in ("input", "textarea", "select"):
            t = (a.get("type") or "text").lower() if tag == "input" else tag
            if t not in NAMELESS_INPUT_TYPES and "hidden" not in a and self.label_depth == 0:
                self.inputs_needing_label.append((t, a))
        if tag == "input" and (a.get("type") or "").lower() in ("submit", "button", "image"):
            if not (a.get("value") or a.get("aria-label") or a.get("alt")):
                self.issues.append("input submit/button without value/aria-label")
        if tag == "svg":
            named = a.get("aria-label") or a.get("role") == "img"
            in_named_control = any(
                s[1].get("aria-label") or s[1].get("aria-labelledby") for s in self.stack
            )
            has_sibling_text = bool(self.stack) and any("".join(b).strip() for b in self.text_for)
            if a.get("aria-hidden") != "true" and not named:
                if not (in_named_control or has_sibling_text):
                    self.issues.append("inline svg neither aria-hidden nor labelled")
        if a.get("aria-hidden") == "true" and tag in ("a", "button", "input", "select", "textarea"):
            self.issues.append(f"aria-hidden on focusable <{tag}>")

    def handle_data(self, data):
        if self._in_title:
            self.title_text += data
        for bucket in self.text_for:
            bucket.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "label" and self.label_depth:
            self.label_depth -= 1
        if tag in ("a", "button") and self.stack and self.stack[-1][0] == tag:
            _, a = self.stack.pop()
            text = "".join(self.text_for.pop()).strip()
            if not (text or a.get("aria-label") or a.get("title") or a.get("aria-labelledby")):
                ident = a.get("href") or a.get("class") or a.get("id") or "?"
                self.issues.append(f"<{tag}> without accessible name: {str(ident)[:70]}")

    def finish(self) -> list[str]:
        out = list(self.issues)
        if not self.has_lang:
            out.append("html missing lang attribute")
        if not self.title_text.strip():
            out.append("empty <title>")
        if not self.has_main:
            out.append("no <main> landmark")
        if self.h1 != 1:
            out.append(f"expected exactly one h1, found {self.h1}")
        if not self.skip_link:
            out.append("no skip link (href=#main)")
        out.extend(f"duplicate id '{i}' x{n}" for i, n in self.ids.items() if n > 1)
        for t, a in self.inputs_needing_label:
            if a.get("aria-label") or a.get("aria-labelledby") or a.get("title"):
                continue
            if a.get("id") and a["id"] in self.label_for:
                continue
            ident = a.get("name") or a.get("id") or a.get("placeholder") or "?"
            out.append(f"unlabeled {t} input: {str(ident)[:50]}")
        return out


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", ROUTES)
def test_page_meets_structural_a11y_contract(client: TestClient, path: str) -> None:
    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert (r.headers.get("content-type") or "").startswith("text/html"), path
    checker = _A11yChecker()
    checker.feed(r.text)
    issues = checker.finish()
    assert not issues, f"{path}: " + "; ".join(sorted(set(issues)))


# --------------------------------------------------------------------------- #
# Contrast regression — palette parsed live from desert.css
# --------------------------------------------------------------------------- #


def _palette() -> dict[str, str]:
    css = (_CSS_DIR / "desert.css").read_text(encoding="utf-8")
    return dict(re.findall(r"--([a-z-]+):(#[0-9a-fA-F]{6})", css))


def _luminance(hexv: str) -> float:
    r, g, b = (int(hexv.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, minimum). 4.5 = AA normal text; 3.0 = AA large
# text / UI components. Pairs reflect how the desert design system actually
# uses the palette (see the palette notes at the top of desert.css).
_CONTRAST_CONTRACT = [
    ("black", "sand-light", 4.5),
    ("black", "sand", 4.5),
    ("black", "cream", 4.5),
    ("orange-deep", "sand-light", 4.5),
    ("orange-deep", "sand", 4.5),
    ("orange-deep", "cream", 4.5),
    ("cream", "orange-deep", 4.5),  # solid CTA hover state
    ("cream", "blue", 4.5),
    ("cream", "blue-deep", 4.5),
    ("cream", "black", 4.5),
    ("sky", "blue", 4.5),
    ("sky", "blue-deep", 4.5),
    ("sky", "black", 4.5),
    ("peach", "blue", 4.5),
    ("peach", "blue-deep", 4.5),
    ("peach", "black", 4.5),
    ("orange", "black", 4.5),  # ticker eyebrow, bottom-nav active tab
    ("orange", "sand-light", 3.0),  # display-size headings + focus ring only
    ("black", "orange", 4.5),  # chips/badges with black-on-orange
]


@pytest.mark.parametrize("fg,bg,minimum", _CONTRAST_CONTRACT)
def test_palette_pair_meets_contrast(fg: str, bg: str, minimum: float) -> None:
    p = _palette()
    r = _ratio(p[fg], p[bg])
    assert r >= minimum, f"--{fg} on --{bg} = {r:.2f}, needs >= {minimum}"


def test_no_cream_text_on_brand_orange_in_css() -> None:
    """--orange + --cream at body sizes is 3.7:1 (AA fail). The 2026-06-10
    pass moved every such pairing to --orange-deep; keep it that way."""
    offenders = []
    for css_path in _CSS_DIR.rglob("*.css"):
        css = css_path.read_text(encoding="utf-8")
        for m in re.finditer(r"[^}]*\{[^}]*\}", css):
            rule = m.group(0)
            if "background:var(--orange)" in rule.replace(" ", "") and (
                "color:var(--cream)" in rule.replace(" ", "")
            ):
                offenders.append(f"{css_path.name}: {rule[:90]}")
    assert not offenders, "cream-on-orange (3.7:1, AA fail) reintroduced: " + " | ".join(offenders)


def test_placeholder_color_meets_contrast() -> None:
    """Placeholders are text (1.4.3); the old #8c7f6b was 3.3-3.9:1 on the
    light surfaces. #716552 clears 4.5:1 on cream/white/sand-light."""
    for css_path in _CSS_DIR.rglob("*.css"):
        css = css_path.read_text(encoding="utf-8")
        for m in re.finditer(r"::placeholder\s*\{[^}]*color:\s*(#[0-9a-fA-F]{6})", css):
            color = m.group(1)
            for bg in ("#fbf4e6", "#ffffff", "#f5ead4"):
                r = _ratio(color, bg)
                assert r >= 4.5, f"{css_path.name} placeholder {color} on {bg} = {r:.2f}"
