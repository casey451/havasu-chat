"""One factory for the app's Jinja2Templates instances (audit 2026-07-01).

Every router module used to hand-build its own ``Jinja2Templates`` and then had
to remember to call BOTH ``register_template_filters`` and
``register_template_globals`` on it. Forgetting either silently drops
template features — the live ``/gas`` page shipped with no canonical + no
``og:*`` tags because its module built the instance but skipped the registrars
(see the comment that used to live in ``app/api/routes/gas.py``).

``make_templates()`` is the single blessed constructor: it points at the one
``app/templates`` directory and always runs both registrars, so a new router
can't reintroduce that footgun.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.provider_name import register_template_filters, register_template_globals

# The one templates directory (``app/templates``); ``app/core`` is one level down.
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def make_templates() -> Jinja2Templates:
    """Return a ``Jinja2Templates`` for ``app/templates`` with both registrars run."""
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    register_template_filters(templates)
    register_template_globals(templates)
    return templates
