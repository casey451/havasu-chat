"""WCAG 2.1 AA contrast regression for the Lake Ink & Brass palette (Phase 0).

A Node-free guard (rides the required pytest job) for the text/background pairs
that axe/pa11y flagged on the styleguide and that the lake-components.css
hardening fixes: the brass CTA (white on the deeper brass) and the footer
tagline (no longer inheriting the chip's light background). Pins the rationale
so a future "tidy-up" can't quietly drop white text back onto mid-tone brass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_STYLES = Path(__file__).resolve().parents[1] / "app" / "static" / "styles"

AA_NORMAL = 4.5  # WCAG 2.1 AA, normal-size text


def _lin(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, description) — every pair must clear AA normal text.
AA_PAIRS = [
    ("#ffffff", "#835914", "brass CTA: white on --brass-deep"),
    ("#90a3ae", "#13242f", "footer tagline on footer ink (lightest gradient stop)"),
    ("#5e6e79", "#ffffff", "--muted on --raised"),
    ("#835914", "#ffffff", "--brass-deep link/eyebrow on --raised"),
    ("#374954", "#ffffff", "--ink-2 body on --raised"),
    ("#2c7d57", "#ffffff", "--good (open-now) on --raised"),
    ("#835914", "#f7ecd5", "sponsored tag: --brass-deep on --brass-wash"),
    ("#b4511c", "#ffffff", "--warn on --raised"),
]


@pytest.mark.parametrize("fg,bg,desc", AA_PAIRS)
def test_lake_pair_meets_aa(fg: str, bg: str, desc: str) -> None:
    ratio = _contrast(fg, bg)
    assert ratio >= AA_NORMAL, f"{desc}: {ratio:.2f}:1 < {AA_NORMAL}:1"


def test_white_on_midtone_brass_would_fail_aa() -> None:
    """Documents WHY the CTA uses --brass-deep: white on the mid-tone --brass
    (#b07a22) is only ~3.7:1 — the trap pa11y caught."""
    assert _contrast("#ffffff", "#b07a22") < AA_NORMAL


def test_hardening_is_present_in_css() -> None:
    css = (_STYLES / "lake-components.css").read_text(encoding="utf-8")
    assert ".btn-brass{background:var(--brass-deep)" in css
    assert ".ft .tag{background:none" in css
