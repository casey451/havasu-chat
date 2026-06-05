"""P1.8 — meta-description sanitizer (app/seo/meta.py + meta_desc filter)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seo.meta import meta_description


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_short_text_passes_through() -> None:
    assert meta_description("A tidy one-liner.") == "A tidy one-liner."


def test_newlines_and_runs_collapse() -> None:
    raw = "Line one.\n\nLine two.\t  Line   three."
    assert meta_description(raw) == "Line one. Line two. Line three."


def test_none_and_empty_are_safe() -> None:
    assert meta_description(None) == ""
    assert meta_description("") == ""


def test_sentence_boundary_truncation() -> None:
    text = ("The first sentence runs about eighty characters to leave room "
            "for a clean cut here. The second sentence would push the total "
            "well past one hundred and sixty characters, so it gets dropped.")
    out = meta_description(text, 160)
    assert out.endswith("clean cut here.")
    assert len(out) <= 160


def test_word_boundary_fallback_gets_ellipsis() -> None:
    text = "word " * 60  # no sentence punctuation at all
    out = meta_description(text.strip(), 160)
    assert len(out) <= 160
    assert out.endswith("…")
    assert not out[:-1].endswith(" ")


def test_no_stub_sentences() -> None:
    text = "Tiny. " + "x" * 300
    out = meta_description(text, 160)
    # 'Tiny.' (5 chars) is below the stub threshold -> word-boundary path.
    assert out != "Tiny."


def test_idempotent_on_clean_input() -> None:
    clean = meta_description("Some text.\nWith a newline and " + "padding " * 40)
    assert meta_description(clean) == clean


def test_filter_registered_for_provider_templates() -> None:
    from fastapi.templating import Jinja2Templates

    from app.core.provider_name import register_template_filters

    t = Jinja2Templates(directory="app/templates")
    register_template_filters(t)
    assert "meta_desc" in t.env.filters
