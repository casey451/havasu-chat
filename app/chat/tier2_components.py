"""Deprecated — see ``app/chat/tier2_day_agenda.py``.

This module was an early scaffold for the day-shape component branch that
was superseded before merge by the cleaner ``tier2_day_agenda`` helper.
Import path is preserved as a no-op shim for any in-flight references;
new callers should import from ``tier2_day_agenda`` directly.
"""

from __future__ import annotations

from app.chat.tier2_day_agenda import try_build_day_agenda  # noqa: F401
