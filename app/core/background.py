"""Background-jobs scaffold for Option A (Railway scheduled jobs + FastAPI
``BackgroundTasks`` + Outbox(Base) must-not-lose surface).

This module is the centralized retry + Sentry + structured-logging surface
for all background work in the codebase. Two patterns it supports:

1. **Event-triggered tasks** via FastAPI ``BackgroundTasks`` (the common case)::

       background_tasks.add_task(with_retry, send_magic_link_email, email, token)

   :func:`with_retry` wraps the call with bounded retry + exponential
   backoff + a Sentry breadcrumb on exhaustion. Tasks MUST be idempotent.

2. **In-process scheduled loops** via ``asyncio.create_task`` in
   :func:`app.main.lifespan` (the ``_hourly_cleanup_loop`` pattern at
   ``app/main.py:251``)::

       async def _cache_warm_loop() -> None:
           while True:
               await asyncio.sleep(900)
               await asyncio.to_thread(warm_llm_response_cache)

   Wired into ``lifespan`` alongside the existing loop. Each loop is
   best-effort and idempotent; process restart re-starts the loop with
   the next sleep window. Cap: do NOT use this pattern for any job
   longer than ~5 seconds or any job with strict timing requirements.
   For longer + scheduled work, use a Railway scheduled-job service
   per ``docs/operations/railway_scheduled_jobs_runbook.md`` (Phase 4.4).

Phase 4.1 (this module) ships the retry helpers + the ``Outbox`` must-not-
lose surface for the magic-link send path. The full Option A → Option B
(Celery + Redis) migration path is documented in
``docs/maintainability/background_job_infrastructure_decision.md`` §7.

**Import discipline (gotcha #17 cure).** This module deliberately does NOT
import ``app.db.models`` at module top. Anything that needs the ``Outbox``
ORM class — for example :func:`deliver_outbox_row` — uses a function-scope
``from app.db.models import Outbox`` import so that the
``app.db.__init__`` -> ``entity_dual_write`` -> ``models`` load chain is
allowed to complete before this module reaches for the Outbox class. See
``app/db/__init__.py`` for the session-22 history of the cycle this
discipline prevents.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import sentry_sdk

logger = logging.getLogger(__name__)

T = TypeVar("T")


_BREADCRUMB_CATEGORY = "background-jobs"
"""Sentry breadcrumb category for all retry / exhaustion / fatal events.

Note (deviation from brief §9 row "Sentry breadcrumb shape"): the
existing ``app/contrib/rate_limiter.py`` surface uses structured
``logger.warning(extra=...)`` only — it does NOT emit Sentry breadcrumbs
directly. Sentry's logging integration auto-captures ``logger.warning``
calls as breadcrumbs once :func:`app.main._init_sentry` runs. This
module emits BOTH a structured log line AND an explicit Sentry
breadcrumb on every retry / exhaustion / fatal event because the brief
§4.1 lists the explicit breadcrumb as a hard requirement, and because
the explicit breadcrumb survives even when the logging integration is
filtered. The category string is unique to this module; rate_limiter
events still come through under its own structured-logging shape.
"""


def with_retry(
    fn: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    backoff_initial_s: float = 1.0,
    backoff_multiplier: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    fatal_on: tuple[type[BaseException], ...] = (),
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> T | None:
    """Execute ``fn`` with bounded retries on transient failure.

    On exhaustion, log to Sentry breadcrumb + structured logger and
    return ``None`` (the helper does NOT re-raise). Tasks must be
    idempotent — re-running on retry must produce the same side
    effects (or no incremental side effects).

    Parameters
    ----------
    fn
        Callable to execute.
    *args, **kwargs
        Passed through to ``fn``.
    max_attempts
        Total attempts including the initial call. Default 3.
    backoff_initial_s
        Initial backoff in seconds. Default 1.0.
    backoff_multiplier
        Backoff scaling factor. Default 2.0 → 1s, 2s, 4s for
        ``max_attempts=3``.
    retry_on
        Exception types that trigger retry. Default ``(Exception,)``.
    fatal_on
        Exception types that exit immediately without retry (e.g.,
        4xx validation errors; subset of ``retry_on`` by convention).
    sleep
        Sleep callable. Inject for tests; defaults to ``time.sleep``.

    Returns
    -------
    The function's return value on success; ``None`` on retry
    exhaustion. Caller is responsible for any return-value semantics.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1; got {max_attempts!r}")

    last_exc: BaseException | None = None
    backoff = backoff_initial_s
    fn_name = getattr(fn, "__name__", repr(fn))

    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except fatal_on as exc:
            sentry_sdk.add_breadcrumb(
                category=_BREADCRUMB_CATEGORY,
                message=f"{fn_name} fatal exception: {type(exc).__name__}",
                level="error",
                data={"fn": fn_name, "attempt": attempt, "event": "fatal"},
            )
            logger.error(
                "background_jobs.fatal",
                extra={
                    "fn": fn_name,
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "fatal",
                },
            )
            return None
        except retry_on as exc:
            last_exc = exc
            sentry_sdk.add_breadcrumb(
                category=_BREADCRUMB_CATEGORY,
                message=f"{fn_name} attempt {attempt} failed: {type(exc).__name__}",
                level="warning",
                data={
                    "fn": fn_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "retry",
                },
            )
            logger.warning(
                "background_jobs.retry",
                extra={
                    "fn": fn_name,
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "retry",
                },
            )
            if attempt < max_attempts:
                sleep(backoff)
                backoff *= backoff_multiplier

    sentry_sdk.add_breadcrumb(
        category=_BREADCRUMB_CATEGORY,
        message=(
            f"{fn_name} exhausted retries: {type(last_exc).__name__ if last_exc else 'unknown'}"
        ),
        level="error",
        data={
            "fn": fn_name,
            "attempts": max_attempts,
            "event": "exhausted",
        },
    )
    logger.error(
        "background_jobs.exhausted",
        extra={
            "fn": fn_name,
            "exc_type": type(last_exc).__name__ if last_exc else "unknown",
            "max_attempts": max_attempts,
            "event": "exhausted",
        },
    )
    return None


async def with_retry_async(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_attempts: int = 3,
    backoff_initial_s: float = 1.0,
    backoff_multiplier: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    fatal_on: tuple[type[BaseException], ...] = (),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    **kwargs: Any,
) -> T | None:
    """Async variant of :func:`with_retry` for awaitable ``fn``.

    Same semantics as the sync helper. Uses :func:`asyncio.sleep` (not
    :func:`time.sleep`) for backoff so the event loop is not blocked.
    Inject ``sleep`` for tests if needed.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1; got {max_attempts!r}")

    last_exc: BaseException | None = None
    backoff = backoff_initial_s
    fn_name = getattr(fn, "__name__", repr(fn))

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except fatal_on as exc:
            sentry_sdk.add_breadcrumb(
                category=_BREADCRUMB_CATEGORY,
                message=f"{fn_name} fatal exception: {type(exc).__name__}",
                level="error",
                data={"fn": fn_name, "attempt": attempt, "event": "fatal"},
            )
            logger.error(
                "background_jobs.fatal_async",
                extra={
                    "fn": fn_name,
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "fatal",
                },
            )
            return None
        except retry_on as exc:
            last_exc = exc
            sentry_sdk.add_breadcrumb(
                category=_BREADCRUMB_CATEGORY,
                message=f"{fn_name} attempt {attempt} failed: {type(exc).__name__}",
                level="warning",
                data={
                    "fn": fn_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "retry",
                },
            )
            logger.warning(
                "background_jobs.retry_async",
                extra={
                    "fn": fn_name,
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "event": "retry",
                },
            )
            if attempt < max_attempts:
                await sleep(backoff)
                backoff *= backoff_multiplier

    sentry_sdk.add_breadcrumb(
        category=_BREADCRUMB_CATEGORY,
        message=(
            f"{fn_name} exhausted retries: {type(last_exc).__name__ if last_exc else 'unknown'}"
        ),
        level="error",
        data={
            "fn": fn_name,
            "attempts": max_attempts,
            "event": "exhausted",
        },
    )
    logger.error(
        "background_jobs.exhausted_async",
        extra={
            "fn": fn_name,
            "exc_type": type(last_exc).__name__ if last_exc else "unknown",
            "max_attempts": max_attempts,
            "event": "exhausted",
        },
    )
    return None


# -------------------------------------------------------------------------
# Outbox must-not-lose surface
# -------------------------------------------------------------------------
#
# Phase 4.1 ships the ``Outbox`` table (see migration ``0a1b2c3d4e5f`` and
# the ORM class appended at the tail of ``app/db/models.py``). The Outbox
# is the must-not-lose channel for jobs whose silent failure is unacceptable
# — in V1, the canonical consumer is the magic-link send. A row is inserted
# into the Outbox in the same transaction as the user's signup request, the
# transaction commits, and ``deliver_outbox_row`` runs in a FastAPI
# ``BackgroundTasks`` slot to actually invoke the handler. The redrive
# script (``scripts/outbox_redrive.py``) sweeps for rows that didn't get
# delivered (process crash, BackgroundTasks dropped, etc.) on a cron
# cadence.
#
# State machine::
#
#     pending --(deliver_outbox_row picks up)--> in_flight
#     in_flight --(handler succeeded)--> delivered
#     in_flight --(transient failure)--> pending (attempts += 1, last_error set)
#     in_flight --(attempts >= OUTBOX_MAX_ATTEMPTS)--> failed
#
# Idempotency is the caller's responsibility — the handler may run more
# than once for a given row in the worst case (e.g., process crash after
# handler succeeded but before state transitioned).
#
# All Outbox-touching code below uses **function-scope imports** of the
# ``Outbox`` ORM class to preserve the gotcha-#17 cure documented at the
# top of this module.

OUTBOX_KIND_MAGIC_LINK = "magic_link"
OUTBOX_KIND_SPONSOR_NOTIFICATION = "sponsor_notification"
OUTBOX_KIND_IMAGE_PROCESSING = "image_processing"
OUTBOX_KIND_OTHER = "other"

OUTBOX_KINDS: tuple[str, ...] = (
    OUTBOX_KIND_MAGIC_LINK,
    OUTBOX_KIND_SPONSOR_NOTIFICATION,
    OUTBOX_KIND_IMAGE_PROCESSING,
    OUTBOX_KIND_OTHER,
)

OUTBOX_STATE_PENDING = "pending"
OUTBOX_STATE_IN_FLIGHT = "in_flight"
OUTBOX_STATE_DELIVERED = "delivered"
OUTBOX_STATE_FAILED = "failed"

OUTBOX_STATES: tuple[str, ...] = (
    OUTBOX_STATE_PENDING,
    OUTBOX_STATE_IN_FLIGHT,
    OUTBOX_STATE_DELIVERED,
    OUTBOX_STATE_FAILED,
)

OUTBOX_MAX_ATTEMPTS = 5
"""Maximum delivery attempts before transitioning to ``failed``.

Design memo §6.2 recommends 5. Each attempt invokes the handler via
:func:`with_retry` with its own bounded inner retry; this outer cap
defends against repeated transient failures across redrive cycles.
"""


# Registry of kind -> handler. Handlers take (payload: dict, session)
# and either return on success or raise on transient failure (the
# caller wraps the call in ``with_retry``). Populated at import time by
# :func:`register_outbox_handler`; magic-link is registered below.
_OUTBOX_HANDLERS: dict[str, Callable[..., Any]] = {}


def register_outbox_handler(kind: str, handler: Callable[..., Any]) -> None:
    """Register a handler for a given Outbox ``kind``.

    Handlers receive the deserialized payload dict (and may accept a
    session keyword argument when DB access is needed). Re-registration
    of the same kind is permitted and replaces the previous handler —
    useful for tests; in production the registration is once at import
    time via :func:`_register_default_outbox_handlers`.
    """
    if kind not in OUTBOX_KINDS:
        raise ValueError(f"Unknown Outbox kind: {kind!r}; allowed: {OUTBOX_KINDS!r}")
    _OUTBOX_HANDLERS[kind] = handler


def get_outbox_handler(kind: str) -> Callable[..., Any] | None:
    """Return the registered handler for ``kind`` or ``None``."""
    return _OUTBOX_HANDLERS.get(kind)


def _magic_link_outbox_handler(payload: dict[str, Any]) -> None:
    """Default magic-link handler. Calls ``send_magic_link`` with payload args.

    Function-scope import of :mod:`app.auth.email_sender` so importing
    this module does not pull the auth stack at module load (keeps the
    gotcha-#17 + Phase 1D import discipline intact).
    """
    from app.auth.email_sender import send_magic_link

    email = payload["email"]
    token = payload["token"]
    next_path = payload.get("next_path")
    send_magic_link(email, token, next_path=next_path)


def _register_default_outbox_handlers() -> None:
    """Wire the V1 must-not-lose kinds to their handlers.

    Phase 4.1 wires ``magic_link`` only. Phase 4.4 wires
    ``image_processing`` (alongside the image-processing retry-wrapper
    integration); sponsor_notification is V1.5.
    """
    register_outbox_handler(OUTBOX_KIND_MAGIC_LINK, _magic_link_outbox_handler)


_register_default_outbox_handlers()


def deliver_outbox_row(
    row_id: str,
    *,
    session_factory: Callable[..., Any] | None = None,
) -> bool:
    """Deliver a single Outbox row.

    Picks up the row by ID inside a fresh session, transitions
    ``pending → in_flight``, invokes the registered handler for the
    row's ``kind``, then transitions to ``delivered`` on success or
    back to ``pending`` (incrementing ``attempts``) on failure. When
    ``attempts`` reaches :data:`OUTBOX_MAX_ATTEMPTS`, transitions to
    ``failed`` instead of ``pending``.

    Each call attempts the handler exactly once — the Outbox row's
    ``attempts`` counter (combined with the redrive cron sweep) is
    the retry mechanism, not :func:`with_retry`. This keeps the state
    transitions auditable: every attempt corresponds to one row in the
    ``attempts`` counter, and ``last_error`` captures the most recent
    failure verbatim.

    Returns ``True`` if the row reached the ``delivered`` state on this
    call. Returns ``False`` for every other outcome (handler raised,
    row missing, row already delivered/failed, no handler registered
    for the row's ``kind``).

    The function-scope imports of :class:`Outbox` and ``SessionLocal``
    keep the gotcha-#17 cure intact — importing this module never pulls
    ``app.db.models`` at module top.
    """
    from app.db.database import SessionLocal as _SessionLocal
    from app.db.models import Outbox

    factory = session_factory or _SessionLocal

    # 1. Claim the row: pending -> in_flight. If row is missing or not
    #    in pending state, this is a no-op.
    with factory() as session:
        row = session.get(Outbox, row_id)
        if row is None:
            logger.warning(
                "outbox.missing",
                extra={"outbox_id": row_id, "event": "missing"},
            )
            return False
        if row.state != OUTBOX_STATE_PENDING:
            logger.info(
                "outbox.skip_non_pending",
                extra={
                    "outbox_id": row_id,
                    "state": row.state,
                    "event": "skip_non_pending",
                },
            )
            return row.state == OUTBOX_STATE_DELIVERED
        row.state = OUTBOX_STATE_IN_FLIGHT
        row.last_attempt_at = _utcnow_naive()
        kind = row.kind
        payload = dict(row.payload or {})
        attempts_before = int(row.attempts or 0)
        session.commit()

    # 2. Look up the handler. Missing handler is a soft failure — the
    #    row transitions back to pending so the operator can register
    #    a handler later and the redrive script retries.
    handler = get_outbox_handler(kind)
    if handler is None:
        logger.error(
            "outbox.no_handler",
            extra={"outbox_id": row_id, "kind": kind, "event": "no_handler"},
        )
        _record_outbox_failure(
            factory,
            row_id,
            attempts_before=attempts_before,
            error_message=f"no handler registered for kind={kind!r}",
        )
        return False

    # 3. Invoke handler once. Any exception is a delivery failure.
    error_message: str | None = None
    try:
        handler(payload)
    except BaseException as exc:  # noqa: BLE001 — explicit catch-all by design
        error_message = f"{type(exc).__name__}: {exc}"
        sentry_sdk.add_breadcrumb(
            category=_BREADCRUMB_CATEGORY,
            message=f"outbox {kind} attempt {attempts_before + 1} failed: {type(exc).__name__}",
            level="warning",
            data={
                "outbox_id": row_id,
                "kind": kind,
                "attempts": attempts_before + 1,
                "event": "outbox_attempt_failed",
            },
        )
        logger.warning(
            "outbox.attempt_failed",
            extra={
                "outbox_id": row_id,
                "kind": kind,
                "exc_type": type(exc).__name__,
                "attempts": attempts_before + 1,
                "event": "outbox_attempt_failed",
            },
        )

    # 4. Finalize state.
    if error_message is None:
        with factory() as session:
            row = session.get(Outbox, row_id)
            if row is None:
                return False
            row.state = OUTBOX_STATE_DELIVERED
            row.delivered_at = _utcnow_naive()
            row.last_error = None
            session.commit()
        return True

    _record_outbox_failure(
        factory,
        row_id,
        attempts_before=attempts_before,
        error_message=error_message,
    )
    return False


def _record_outbox_failure(
    session_factory: Callable[..., Any],
    row_id: str,
    *,
    attempts_before: int,
    error_message: str,
) -> None:
    """Transition an in_flight row back to pending (or to failed at cap).

    Shared by the no-handler path and the handler-raised path so the
    state-machine bookkeeping lives in one place.
    """
    from app.db.models import Outbox

    new_attempts = attempts_before + 1
    with session_factory() as session:
        row = session.get(Outbox, row_id)
        if row is None or row.state != OUTBOX_STATE_IN_FLIGHT:
            return
        row.attempts = new_attempts
        row.last_error = error_message[:500]
        if new_attempts >= OUTBOX_MAX_ATTEMPTS:
            row.state = OUTBOX_STATE_FAILED
            sentry_sdk.add_breadcrumb(
                category=_BREADCRUMB_CATEGORY,
                message=f"outbox {row.kind} exhausted (attempts={new_attempts})",
                level="error",
                data={
                    "outbox_id": row_id,
                    "kind": row.kind,
                    "attempts": new_attempts,
                    "event": "outbox_exhausted",
                },
            )
            logger.error(
                "outbox.exhausted",
                extra={
                    "outbox_id": row_id,
                    "kind": row.kind,
                    "attempts": new_attempts,
                    "max_attempts": OUTBOX_MAX_ATTEMPTS,
                    "event": "outbox_exhausted",
                },
            )
        else:
            row.state = OUTBOX_STATE_PENDING
        session.commit()


def enqueue_outbox(
    db: Any,
    *,
    kind: str,
    payload: dict[str, Any],
) -> str:
    """Insert a new Outbox row in the caller's open session.

    Caller is responsible for committing the surrounding transaction.
    Returns the new row's ``id`` so the caller can hand it off to
    :func:`deliver_outbox_row` via ``background_tasks.add_task``.
    """
    from app.db.models import Outbox

    if kind not in OUTBOX_KINDS:
        raise ValueError(f"Unknown Outbox kind: {kind!r}; allowed: {OUTBOX_KINDS!r}")
    row = Outbox(kind=kind, payload=payload, state=OUTBOX_STATE_PENDING)
    db.add(row)
    db.flush()  # populate row.id without committing the caller's txn
    return str(row.id)


def _utcnow_naive() -> Any:
    """Return current UTC time as a naive datetime.

    Matches the codebase convention of storing naive UTC in
    ``DateTime`` columns (see :mod:`app.db.types` notes and the
    ``_naive_utc_now`` helper in :mod:`app.auth.routes`).
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)


__all__ = [
    "OUTBOX_KINDS",
    "OUTBOX_KIND_IMAGE_PROCESSING",
    "OUTBOX_KIND_MAGIC_LINK",
    "OUTBOX_KIND_OTHER",
    "OUTBOX_KIND_SPONSOR_NOTIFICATION",
    "OUTBOX_MAX_ATTEMPTS",
    "OUTBOX_STATES",
    "OUTBOX_STATE_DELIVERED",
    "OUTBOX_STATE_FAILED",
    "OUTBOX_STATE_IN_FLIGHT",
    "OUTBOX_STATE_PENDING",
    "deliver_outbox_row",
    "enqueue_outbox",
    "get_outbox_handler",
    "register_outbox_handler",
    "with_retry",
    "with_retry_async",
]
