"""Unified safety-rule audit report (Phase A2).

Read-only companion to the dispatcher. Where ``dispatch_alerts`` couples
evaluation with subscriber lookup + send/record, this module evaluates EVERY
V1 safety rule against the conditions cache and returns a structured, honest
audit. It writes NOTHING to the database and sends NOTHING -- it is the
"emit a dry-run report" entry point for the rule engine.

Each rule entry reports:
  - ``fired``: whether the existing evaluator says the rule tripped
  - ``trigger_data``: the evaluator's trigger payload (unchanged)
  - ``sources``: per-source freshness (present / missing / stale)
  - ``data_available``: True only if every required source is present AND fresh
  - ``status``: one of "fired", "clear", "data_unavailable"

This honors the "honest unavailable when data is stale" requirement: when a
rule's inputs are missing or stale we surface ``data_unavailable`` rather than
silently reporting "clear". Thresholds are read-only here -- none are defined
or mutated in this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.alerts.evaluator import AlertEvaluation, evaluate_alert_type
from app.alerts.thresholds import ALERT_TYPES_V1, EVENT_TRAFFIC_DEFERRED
from app.conditions.cache import read_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_USGS,
)

# Which cache sources each safety rule reads. Mirrors the imports in
# evaluator.py; kept here so the report can describe freshness without
# re-implementing the evaluation logic.
RULE_SOURCES: dict[str, tuple[str, ...]] = {
    "heat_advisory": (SOURCE_NWS_ALERTS, SOURCE_NWS_CURRENT, SOURCE_NWS_FORECAST),
    "aqi_alert": (SOURCE_AIRNOW,),
    "lake_hazard": (SOURCE_NWS_ALERTS, SOURCE_USGS),
}

STATUS_FIRED = "fired"
STATUS_CLEAR = "clear"
STATUS_DATA_UNAVAILABLE = "data_unavailable"


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    present: bool
    is_stale: bool
    fetched_at: str | None


@dataclass(frozen=True)
class RuleReport:
    alert_type: str
    fired: bool
    status: str
    data_available: bool
    trigger_data: dict[str, Any]
    sources: list[SourceFreshness] = field(default_factory=list)


@dataclass(frozen=True)
class SafetyReport:
    generated_at: str
    dry_run: bool
    rules: list[RuleReport]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_freshness(db: Session, source: str, now: datetime | None) -> SourceFreshness:
    row = read_source(db, source, now=now) if now is not None else read_source(db, source)
    if row is None:
        return SourceFreshness(source=source, present=False, is_stale=True, fetched_at=None)
    return SourceFreshness(
        source=source,
        present=True,
        is_stale=bool(row.is_stale),
        fetched_at=row.fetched_at.isoformat() if row.fetched_at else None,
    )


def _build_rule_report(
    db: Session, alert_type: str, now: datetime | None
) -> RuleReport:
    sources = [_source_freshness(db, s, now) for s in RULE_SOURCES.get(alert_type, ())]
    data_available = bool(sources) and all(
        s.present and not s.is_stale for s in sources
    )

    evaluation: AlertEvaluation = evaluate_alert_type(db, alert_type)

    if evaluation.fired:
        status = STATUS_FIRED
    elif not data_available:
        status = STATUS_DATA_UNAVAILABLE
    else:
        status = STATUS_CLEAR

    return RuleReport(
        alert_type=alert_type,
        fired=evaluation.fired,
        status=status,
        data_available=data_available,
        trigger_data=dict(evaluation.trigger_data),
        sources=sources,
    )


def build_safety_report(
    db: Session,
    *,
    alert_type_filter: str | None = None,
    now: datetime | None = None,
) -> SafetyReport:
    """Evaluate all V1 safety rules read-only and return a structured audit.

    Pure read: never writes to the DB, never dispatches. ``event_traffic`` is
    deferred (per thresholds.EVENT_TRAFFIC_DEFERRED) and is skipped.
    """
    if alert_type_filter:
        types: tuple[str, ...] = (alert_type_filter,)
    else:
        types = ALERT_TYPES_V1

    rules: list[RuleReport] = []
    for alert_type in types:
        if alert_type == EVENT_TRAFFIC_DEFERRED:
            continue
        rules.append(_build_rule_report(db, alert_type, now))

    generated = (now or datetime.now(UTC).replace(tzinfo=None)).isoformat()
    return SafetyReport(generated_at=generated, dry_run=True, rules=rules)
