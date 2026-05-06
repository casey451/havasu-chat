"""Slice 56 — verify ProgramBase.parse_hhmm converts HH:MM strings to time.

These tests replace the deleted ``tests/test_program_typed_time_dual_write.py``
(which exercised the Slice 53 ``@validates`` ORM-layer dual-write). Slice 56
moved string-to-time conversion from the ORM to the Pydantic schema boundary;
this test file covers the equivalent contract at the new layer.
"""

from __future__ import annotations

from datetime import time

import pytest
from pydantic import ValidationError

from app.schemas.program import ProgramCreate


def _base_kwargs(**overrides) -> dict:
    base = dict(
        title="Schema Time Parsing Test",
        description="Slice 56 schema validator test for HH:MM parsing.",
        activity_category="test",
        schedule_days=["monday"],
        schedule_start_time="09:00",
        schedule_end_time="10:30",
        location_name="Test Location",
        provider_name="Test Provider",
    )
    base.update(overrides)
    return base


def test_string_input_converts_to_time() -> None:
    p = ProgramCreate(**_base_kwargs())
    assert p.schedule_start_time == time(9, 0)
    assert p.schedule_end_time == time(10, 30)


def test_time_input_passes_through() -> None:
    """Direct ``time`` instances bypass the string-parse branch."""
    p = ProgramCreate(
        **_base_kwargs(
            schedule_start_time=time(13, 45),
            schedule_end_time=time(14, 15),
        )
    )
    assert p.schedule_start_time == time(13, 45)
    assert p.schedule_end_time == time(14, 15)


def test_invalid_string_rejected() -> None:
    with pytest.raises(ValidationError):
        ProgramCreate(**_base_kwargs(schedule_start_time="not-a-time"))


def test_unpadded_hour_rejected() -> None:
    """Pre-Slice-56 validator rejected ``9:00`` (single-digit hour); preserved."""
    with pytest.raises(ValidationError):
        ProgramCreate(**_base_kwargs(schedule_start_time="9:00"))


def test_seconds_rejected() -> None:
    """HH:MM format only; HH:MM:SS is not accepted by the validator."""
    with pytest.raises(ValidationError):
        ProgramCreate(**_base_kwargs(schedule_start_time="09:00:00"))
