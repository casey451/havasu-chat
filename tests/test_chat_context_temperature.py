"""P1-15 contract guard: a real 0°F reading must be honored, not treated as
falsy and replaced by the stub temperature.

The router fix (unified_router) delivers a live 0.0 into ChatRequestContext via
an ``is not None`` check instead of an ``or`` chain; this pins the downstream
half — effective_temperature_f must return the real 0.0 (heat bias off).
"""

from __future__ import annotations

from app.chat.chat_request_context import ChatRequestContext
from app.core.ranking import STUB_CURRENT_TEMPERATURE_F


def test_zero_temperature_is_honored_not_stubbed() -> None:
    ctx = ChatRequestContext(temperature_f=0.0)
    assert ctx.effective_temperature_f() == 0.0
    assert ctx.effective_temperature_f() != STUB_CURRENT_TEMPERATURE_F
    assert ctx.heat_bias_active() is False


def test_none_temperature_falls_back_to_stub() -> None:
    ctx = ChatRequestContext(temperature_f=None)
    assert ctx.effective_temperature_f() == STUB_CURRENT_TEMPERATURE_F
