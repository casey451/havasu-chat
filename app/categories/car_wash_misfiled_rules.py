"""Rules for detailing shops mis-shelved under the ``car-wash`` leaf.

Audit 2026-07-06 (T3.2): the ``car-wash`` leaf holds auto-detailing / ceramic-
coating shops (Accelerated Detail, Tapped Out Mobile Detailing, Detail Specialties
& Ceramic Coating, …). Detailing is its own leaf (``auto-detailing``); a car wash
and a detailer are different services, so "car wash" surfaced detailers.

This encodes the unambiguous correction: a name signalling detailing / ceramic
coating -> ``auto-detailing``. Everything else returns ``None`` (a genuine car
wash stays put). Used by ``scripts/recategorize_car_wash_detailers_2026_07_06.py``
(DRY-RUN by default; review the change list before --apply). The caller scopes to
rows whose CURRENT primary leaf is ``car-wash`` so this never touches a correct row.
"""

from __future__ import annotations

_DETAILING_LEAF = "auto-detailing"


def classify_car_wash_misfiled_leaf(name: str | None) -> str | None:
    """Return ``"auto-detailing"`` for a detailing/ceramic-coating shop currently
    shelved under ``car-wash``, else ``None`` (leave a real car wash untouched)."""
    n = (name or "").lower()
    if "detail" in n or "ceramic coat" in n:
        return _DETAILING_LEAF
    return None
