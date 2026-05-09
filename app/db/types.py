"""SQLAlchemy column types — SQLite/PG parity helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

from app.core.timezone import LAKE_HAVASU_TZ


class TZAwareDateTime(TypeDecorator):
    """Wraps ``DateTime(timezone=True)`` so SQLite round-trips stay usable.

    Python's SQLite driver returns naive datetimes even when the declared SQLAlchemy
    column uses timezone-aware semantics. On load, naive values are interpreted as
    UTC wall time, then converted to timezone-aware datetimes in
    :data:`app.core.timezone.LAKE_HAVASU_TZ` (America/Phoenix). This matches
    ``now_lake_havasu()`` so callers can compare directly without stripping tzinfo.

    Values that are already timezone-aware (e.g. Postgres TIMESTAMPTZ) are normalized
    with ``.astimezone(LAKE_HAVASU_TZ)``.

    Writes must supply timezone-aware datetimes; naive values raise ``ValueError``.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "timezone-naive datetimes are not allowed for TZAwareDateTime columns; "
                "pass an aware datetime (e.g. UTC or LAKE_HAVASU_TZ)."
            )
        return value

    def _to_aware_lake_havasu(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ)
        return value.astimezone(LAKE_HAVASU_TZ)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return self._to_aware_lake_havasu(value)
