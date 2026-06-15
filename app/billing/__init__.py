"""F4 billing scaffolding (Stripe) — DORMANT by default.

This package is the wiring for taking real money via Stripe: checkout/
subscription creation, webhook handling (paid → activate placement, lapse →
release), refunds, and an append-only revenue ledger. It is intentionally
inert until the operator:

  1. adds ``stripe`` to ``requirements.txt`` (a deliberate, version-pinned bump
     verified against a Railway build — never float; see CLAUDE.md),
  2. sets ``STRIPE_SECRET_KEY`` + ``STRIPE_WEBHOOK_SECRET`` in the Railway env,
  3. sets ``STRIPE_BILLING_ENABLED=true``.

Until all three are true, :func:`app.billing.config.billing_enabled` returns
``False``: the ``/billing/*`` routes return 404 and no Stripe API call is ever
made. The agent never handles keys — the operator sets them in Railway.
"""

from __future__ import annotations
