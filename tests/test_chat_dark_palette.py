"""/chat surface styling pins (Desert Modern reskin, 2026-06-07).

Originally written for the Q1 dark-palette flip; updated when /chat moved to
the Desert Modern skin (``desert_base.html`` + ``desert.css`` +
``desert_chat.css``). The *intent* of each pin is unchanged:

Pinned contracts:

- ``<body ... class="ll-page ll-chat">`` -- the body classes that
  ``chat_cards.css`` (B-01 svg/img clamps, feedback controls, composer
  clearance) and ``desert_chat.css`` scope every selector under. Dropping or
  renaming them silently unstyles the transcript.
- The skin stylesheets are wired -- ``desert.css`` (tokens + chrome, loaded
  by the base) and ``desert_chat.css`` (the chat transcript/composer skin).
  (Defense-in-depth alongside the existing
  ``test_plausible_script_renders_on_chat_page`` smoke.)
- The empty-state markup the skin styles still ships -- the ``empty-state``,
  ``chips``, and ``stuck-composer`` hooks the selectors target. If a
  refactor renames any of those, the visual flip silently breaks even with
  the body classes intact.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_chat_serves_dark_body_class() -> None:
    """``/chat`` renders with the chat body classes the chat CSS scopes under."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert 'class="ll-page ll-chat"' in r.text, (
        "chat.html must carry ll-page/ll-chat body classes -- chat_cards.css "
        "and desert_chat.css scope every chat selector under body.ll-chat"
    )


def test_chat_loads_chat_css() -> None:
    """``/chat`` references the base (lake) + chat skin stylesheets."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    # v4.5 PR-5: /chat moved to the standalone base_redesign shell; the desert
    # chat skin is retired (its rules live in lake_redesign.css now). chat_cards.css
    # stays — it carries the B-01 svg/img size clamps for the JS-rendered cards.
    assert "/static/styles/lake_redesign.css" in r.text
    assert "/static/styles/chat_cards.css" in r.text
    assert "/static/styles/desert_chat.css" not in r.text


def test_chat_empty_state_hooks_present() -> None:
    """The empty-state markup the dark rules target still ships.

    The Q1 dark overrides are scoped to ``.empty-state``, ``.chips``,
    and ``.stuck-composer``. If any of those are renamed in a future
    refactor, the body class flip alone won't produce the dark surface
    -- this test fails loudly so the CSS selectors get updated too.
    """
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    body = r.text
    assert 'class="empty-state"' in body
    assert 'class="chips"' in body
    assert 'class="stuck-composer"' in body
