"""add chat_logs disclosure render telemetry columns

Lane P2.OBS.1 — disclosure-renderer observability instrumentation.

Adds four nullable columns to ``chat_logs`` capturing the deterministic
disclosure renderer's per-turn decision (spec §7.2):

* ``disclosure_regime`` (VARCHAR(32), CHECK in 'specific_quality',
  'generic_category', 'emergency_urgent'): the placement regime selected
  by ``select_placement_regime`` from the turn's intent. NULL when the
  renderer was never invoked (flag off, non-tier-3 path).
* ``disclosure_sponsor_id`` (VARCHAR(64)): the ``Sponsor.id`` picked by
  the deterministic tie-break (highest weight, oldest created_at). NULL
  when no sponsor was picked (no candidates, no eligible candidate, tone
  failure, regime SPECIFIC_QUALITY).
* ``disclosure_tone_allowlist_passed`` (BOOLEAN): True/False when the
  tone allowlist was checked, NULL when the renderer never reached the
  check (no eligible candidate, regime SPECIFIC_QUALITY).
* ``disclosure_eligible`` (BOOLEAN): True when at least one candidate
  passed the per-regime eligibility gate (status, verified_fields,
  organic-pairing, temporal). False when candidates existed but none
  passed. NULL when no candidates were evaluated (regime
  SPECIFIC_QUALITY, or zero candidates fetched).

Plus partial index ``ix_chat_logs_disclosure_regime`` to support Phase 2
audit queries grouping by regime.

Schema design — typed columns vs JSON
─────────────────────────────────────
Phase 2's audit needs are dimension-aggregate queries: "regime=X
distribution by audience_signal", "tone-allowlist failures per sponsor",
"sponsor share by regime over time". Those queries want indexed scalar
columns and natural ``GROUP BY``, not JSON path extraction. Each field
is also stable in shape (regime is a 3-value enum, the booleans are
single questions, sponsor_id is FK-shaped) so the JSON-evolution edge
case doesn't apply. Typed columns chosen.

Spec §7.2 originally suggested logging this telemetry to
``chat_logs.llm_tokens_used`` as JSON. That suggestion is REJECTED in
this lane: ``llm_tokens_used`` is a typed ``Integer`` column already
populated by token-spend dashboards (see ``log_unified_route`` and
``app/admin/cost_analytics.py``). Repurposing it for JSON would corrupt
the typed contract and break those dashboards. The spec is updated in
the same lane to document this rejection.

Coordination — multi-head state
───────────────────────────────
Cursor is shipping a parallel migration in Lane 3
(``c9d0e1f2a3b4_expand_verification_method_constraint``). Both base on
``b4c5d6e7f8a9``. The operator resolves the multi-head state via
``alembic merge heads`` at integration time — no action needed here.

Revision ID: e7f8a9b0c1d2
Revises: b4c5d6e7f8a9
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("disclosure_regime", sa.String(32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("disclosure_sponsor_id", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("disclosure_tone_allowlist_passed", sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("disclosure_eligible", sa.Boolean(), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_chat_logs_disclosure_regime",
            sa.text(
                "disclosure_regime IS NULL OR disclosure_regime IN ("
                "'specific_quality', 'generic_category', 'emergency_urgent'"
                ")"
            ),
        )

    op.create_index(
        "ix_chat_logs_disclosure_regime",
        "chat_logs",
        ["disclosure_regime"],
        postgresql_where=sa.text("disclosure_regime IS NOT NULL"),
        sqlite_where=sa.text("disclosure_regime IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_logs_disclosure_regime", table_name="chat_logs")

    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_chat_logs_disclosure_regime", type_="check")
        batch_op.drop_column("disclosure_eligible")
        batch_op.drop_column("disclosure_tone_allowlist_passed")
        batch_op.drop_column("disclosure_sponsor_id")
        batch_op.drop_column("disclosure_regime")
