"""Lead-capture core — Phase B7 DORMANT scaffolding.

``leads_enabled()`` is the single kill switch. Unlike the intent layer
(default ON), pay-per-lead is a dormant, unreleased feature, so this flag is
default OFF and must be *explicitly* turned on (``LEADS_ENABLED`` = one of
``1`` / ``true`` / ``yes`` / ``on``). When off:

* :func:`capture_lead` is a no-op that returns ``None`` (writes no row).
* the HTTP hook (:mod:`app.leads.routes`) returns 404.

When on, :func:`capture_lead` records exactly one :class:`app.db.models.Lead`
row from a :class:`LeadInput`. There is NO billing/payment/pricing logic here
or anywhere in this lane — capture is storage + attribution only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Lead

_FLAG_ENV = "LEADS_ENABLED"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def leads_enabled() -> bool:
    """True only when ``LEADS_ENABLED`` is explicitly truthy. Default OFF."""
    return (os.environ.get(_FLAG_ENV) or "").strip().lower() in _TRUTHY


@dataclass
class LeadInput:
    """Inbound lead payload (provider + attribution + contact).

    ``provider_id`` is the only required field. Attribution back-links
    (``intent_key`` / ``chat_log_id`` / ``query_log_id``) and the contact
    payload are all optional so a lead can originate from a static provider
    page with no chat/query context.
    """

    provider_id: str
    category: str | None = None
    source: str = "web_form"
    intent_key: str | None = None
    chat_log_id: str | None = None
    query_log_id: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_message: str | None = None


def capture_lead(db: Session, lead: LeadInput) -> Lead | None:
    """Record a single :class:`Lead`, or no-op when the flag is OFF.

    Returns the persisted :class:`Lead` when capture is enabled, else ``None``
    (dormant — nothing is written). Best-effort caller-facing contract: the
    flag check happens first so a disabled deployment never touches the DB.

    The caller owns the transaction boundary in tests; this function flushes so
    the row gets its server-side defaults / id, but does not commit.
    """
    if not leads_enabled():
        return None
    row = Lead(
        provider_id=lead.provider_id,
        category=lead.category,
        source=lead.source or "web_form",
        intent_key=lead.intent_key,
        chat_log_id=lead.chat_log_id,
        query_log_id=lead.query_log_id,
        contact_name=lead.contact_name,
        contact_phone=lead.contact_phone,
        contact_email=lead.contact_email,
        contact_message=lead.contact_message,
        status="new",
    )
    db.add(row)
    db.flush()
    return row
