"""Billing configuration + the dormancy gate.

All Stripe wiring keys off :func:`billing_enabled`, which is ``True`` only when
the operator has fully provisioned billing. Reading config never imports the
``stripe`` package at module load — the import is lazy in :func:`stripe_library`
so the whole app imports cleanly whether or not ``stripe`` is installed.
"""

from __future__ import annotations

import os
from types import ModuleType

from app.bootstrap_env import ensure_dotenv_loaded

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str) -> str:
    ensure_dotenv_loaded()
    return (os.environ.get(name) or "").strip()


def stripe_secret_key() -> str:
    return _env("STRIPE_SECRET_KEY")


def stripe_publishable_key() -> str:
    return _env("STRIPE_PUBLISHABLE_KEY")


def stripe_webhook_secret() -> str:
    return _env("STRIPE_WEBHOOK_SECRET")


def billing_flag_on() -> bool:
    """The explicit master switch (independent of whether keys are present)."""
    return _env("STRIPE_BILLING_ENABLED").lower() in _TRUE


def stripe_library() -> ModuleType | None:
    """The ``stripe`` module if installed, else ``None`` (lazy, never raises)."""
    try:
        import stripe  # lazy: the dependency is optional / not installed today
    except ImportError:
        return None
    return stripe


def billing_enabled() -> bool:
    """Dormant unless ALL of: master flag on, secret key set, ``stripe`` installed.

    Any one missing keeps the whole billing surface inert (routes 404, no Stripe
    call made). This is the single gate every billing entry point checks.
    """
    return bool(billing_flag_on() and stripe_secret_key() and stripe_library() is not None)
