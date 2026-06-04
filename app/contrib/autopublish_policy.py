"""Auto-publish policy for the schedule-hunt loop (default OFF kill-switch).

The single gate ``SCHEDULE_HUNT_AUTOPUBLISH`` governs ALL no-human publishing of
scraped findings — both the auto-at-ingest path and the batch
``POST /api/ingest/publish`` endpoint. Default unset/empty/falsey → disabled, so
nothing publishes without a manual approve until Casey flips it per-environment
(Railway env var; "flip via a setting, not a code change"). Read at call time.

``meets_confidence_bar`` is the gate-independent quality check (confidence ≥
threshold, has a proposed_record, is a class-schedule/program finding) used for
dry-run previews; ``is_eligible`` = enabled AND meets the bar.
"""

from __future__ import annotations

import os

from app.db.models import Contribution

_DEFAULT_THRESHOLD = 0.85
_TRUTHY = ("1", "true", "yes", "on")


def autopublish_enabled() -> bool:
    """Master kill-switch, read at call time. Default OFF."""
    return os.environ.get("SCHEDULE_HUNT_AUTOPUBLISH", "").strip().lower() in _TRUTHY


def autopublish_threshold() -> float:
    """Confidence floor for auto-publish (default 0.85), clamped to [0, 1]."""
    raw = os.environ.get("SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD", "").strip()
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return _DEFAULT_THRESHOLD
    return min(1.0, max(0.0, value))


def meets_confidence_bar(contribution: Contribution) -> bool:
    """Quality bar independent of the kill-switch (used for dry-run preview).

    Auto-publish is scoped to class-schedule (``program``) findings that carry a
    confidence at/above threshold and a structured ``proposed_record``.
    """
    if contribution.entity_type != "program":
        return False
    if contribution.confidence is None or contribution.confidence < autopublish_threshold():
        return False
    return isinstance(contribution.proposed_record, dict)


def is_eligible(contribution: Contribution) -> bool:
    """Eligible to auto-publish now: the kill-switch is on AND the bar is met."""
    return autopublish_enabled() and meets_confidence_bar(contribution)
