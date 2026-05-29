"""Q1 (2026-05-29) -- /chat empty state adopts the dark cinematic palette.

Mirrors ``test_home_c_redesign.py`` for the /chat surface. The handoff
``outputs/v48_handoff_q1_chat_dark_empty_state.md`` flipped the chat
chrome from the light cream tokens to the dark night-ink palette so the
brand reads continuous from /home into /chat.

Pinned contracts:

- ``<body class="chat-dark">`` -- the body class chat.css scopes its
  dark overrides under. A future PR that drops or renames the class
  would silently revert /chat to the light palette; this test catches
  that.
- ``chat.css`` is still wired -- the stylesheet that *carries* the dark
  rules. (Defense-in-depth alongside the existing
  ``test_plausible_script_renders_on_chat_page`` smoke.)
- The empty-state markup the dark rules style still ships -- the
  ``empty-state``, ``chips``, and ``stuck-composer`` hooks the new
  selectors target. If a refactor renames any of those, the visual
  flip silently breaks even with the body class intact.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_chat_serves_dark_body_class() -> None:
    """``/chat`` renders with ``class="chat-dark"`` on <body>."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert 'class="chat-dark"' in r.text, (
        "chat.html must carry the chat-dark body class; chat.css scopes "
        "all dark-palette overrides under this selector"
    )


def test_chat_loads_chat_css() -> None:
    """``/chat`` references ``chat.css`` -- the stylesheet that carries
    the dark-palette rules. If the link tag is dropped or renamed, the
    body class flip alone won't produce the dark surface."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert "/static/styles/chat.css" in r.text


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
