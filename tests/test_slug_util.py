"""Unit tests for app.utils.slug."""

from __future__ import annotations

from app.utils.slug import make_unique_slug, slugify


def test_slugify_basic_strings() -> None:
    assert slugify("Acme Plumbing") == "acme-plumbing"
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  trim me  ") == "trim-me"


def test_slugify_empty_input() -> None:
    assert slugify(None) == "untitled"
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"


def test_slugify_unicode_transliterated() -> None:
    # B1 (2026-06-10): accented letters fold to their ASCII base instead of
    # being dropped — "Cafés" must never again become "caf-s".
    assert slugify("Café Olé") == "cafe-ole"
    assert slugify("Cafés & Coffee") == "cafes-coffee"
    assert slugify("Crème Brûlée Niño") == "creme-brulee-nino"


def test_slugify_non_decomposable_unicode_still_drops() -> None:
    # Characters with no ASCII decomposition (CJK etc.) drop as before.
    assert slugify("日本語") == "untitled"
    assert slugify("日本語 cafe") == "cafe"


def test_make_unique_slug_no_collision() -> None:
    used: set[str] = set()
    assert make_unique_slug("acme", used) == "acme"
    assert "acme" in used


def test_make_unique_slug_collision_appends_2() -> None:
    used = {"acme"}
    assert make_unique_slug("acme", used) == "acme-2"
    assert "acme-2" in used


def test_make_unique_slug_collision_skips_to_next() -> None:
    used = {"acme", "acme-2", "acme-3"}
    assert make_unique_slug("acme", used) == "acme-4"


def test_make_unique_slug_truncation() -> None:
    long_base = "x" * 200
    used: set[str] = set()
    out = make_unique_slug(long_base, used, max_length=96)
    assert len(out) == 96
    assert out == "x" * 96
