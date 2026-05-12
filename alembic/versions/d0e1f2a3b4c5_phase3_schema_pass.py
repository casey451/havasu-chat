"""Phase 3.1 — v1.1 schema additions (districts, alerts, conditions cache, peer recs).

Revision ID: d0e1f2a3b4c5
Revises: f9e8d7c6b5a4
Create Date: 2026-05-12

Additive only: five new tables, seven new ``entities`` columns, ``users.preferred_mode``.
No data backfill (Phase 3.2). Boolean defaults use ``sa.true()`` / ``sa.false()``;
timestamps use ``sa.func.now()`` where a server default is required.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "districts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("paragraph", sa.Text(), nullable=False),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_districts_slug"),
    )
    op.create_index(
        "ix_districts_display_order",
        "districts",
        ["display_order"],
        unique=False,
    )

    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column(
            "delivery_channel",
            sa.String(length=16),
            nullable=False,
            server_default="email",
        ),
        sa.Column("paused_until", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_alert_subscriptions_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "alert_type IN ('heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic')",
            name="ck_alert_subscriptions_alert_type",
        ),
        sa.CheckConstraint(
            "delivery_channel IN ('email', 'sms')",
            name="ck_alert_subscriptions_delivery_channel",
        ),
        sa.UniqueConstraint(
            "user_id",
            "alert_type",
            "delivery_channel",
            name="uq_alert_subscriptions_user_type_channel",
        ),
    )
    op.create_index(
        "ix_alert_subscriptions_user_id",
        "alert_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_alert_subscriptions_alert_type",
        "alert_subscriptions",
        ["alert_type"],
        unique=False,
    )

    op.create_table(
        "alerts_dispatched",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_data", sa.JSON(), nullable=False),
        sa.Column(
            "dispatched_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivery_status", sa.String(length=20), nullable=False),
        sa.Column("body_snippet", sa.String(length=280), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["alert_subscriptions.id"],
            name="fk_alerts_dispatched_subscription_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "delivery_status IN ('queued', 'sent', 'failed', 'bounced')",
            name="ck_alerts_dispatched_delivery_status",
        ),
    )
    op.create_index(
        "ix_alerts_dispatched_subscription_id",
        "alerts_dispatched",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_dispatched_dispatched_at",
        "alerts_dispatched",
        ["dispatched_at"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_dispatched_delivery_status",
        "alerts_dispatched",
        ["delivery_status"],
        unique=False,
    )

    op.create_table(
        "external_conditions_cache",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.PrimaryKeyConstraint("source"),
    )
    op.create_index(
        "ix_external_conditions_cache_fetched_at",
        "external_conditions_cache",
        ["fetched_at"],
        unique=False,
    )

    op.create_table(
        "peer_recommendations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recommender_user_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["recommender_user_id"],
            ["users.id"],
            name="fk_peer_recommendations_recommender_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_peer_recommendations_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_peer_recommendations_approved_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'rejected')",
            name="ck_peer_recommendations_status",
        ),
        sa.UniqueConstraint(
            "recommender_user_id",
            "entity_id",
            name="uq_peer_recommendations_recommender_entity",
        ),
    )
    op.create_index(
        "ix_peer_recommendations_entity_id_status",
        "peer_recommendations",
        ["entity_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_peer_recommendations_recommender_user_id",
        "peer_recommendations",
        ["recommender_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_peer_recommendations_status",
        "peer_recommendations",
        ["status"],
        unique=False,
    )

    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("heat_exposure", sa.String(length=20), nullable=True))
        batch_op.create_check_constraint(
            "ck_entities_heat_exposure",
            sa.text(
                "heat_exposure IS NULL OR heat_exposure IN ("
                "'indoor', 'shaded', 'outdoor', 'water_adjacent'"
                ")"
            ),
        )
        batch_op.add_column(sa.Column("crowd_notes", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_mobile_service",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("boat_access", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("seasonal_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("district_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_entities_district_id",
            "districts",
            ["district_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_entities_district_id",
            ["district_id"],
            unique=False,
        )
        batch_op.add_column(
            sa.Column(
                "featured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.create_index(
            "ix_entities_featured",
            ["featured"],
            unique=False,
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "preferred_mode",
                sa.String(length=16),
                nullable=False,
                server_default="default",
            )
        )
        batch_op.create_check_constraint(
            "ck_users_preferred_mode",
            sa.text("preferred_mode IN ('default', 'boat')"),
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("ck_users_preferred_mode", type_="check")
        batch_op.drop_column("preferred_mode")

    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.drop_index("ix_entities_featured")
        batch_op.drop_column("featured")
        batch_op.drop_index("ix_entities_district_id")
        batch_op.drop_constraint("fk_entities_district_id", type_="foreignkey")
        batch_op.drop_column("district_id")
        batch_op.drop_column("seasonal_hours")
        batch_op.drop_column("boat_access")
        batch_op.drop_column("is_mobile_service")
        batch_op.drop_column("crowd_notes")
        batch_op.drop_constraint("ck_entities_heat_exposure", type_="check")
        batch_op.drop_column("heat_exposure")

    op.drop_index("ix_peer_recommendations_status", table_name="peer_recommendations")
    op.drop_index(
        "ix_peer_recommendations_recommender_user_id",
        table_name="peer_recommendations",
    )
    op.drop_index(
        "ix_peer_recommendations_entity_id_status",
        table_name="peer_recommendations",
    )
    op.drop_table("peer_recommendations")

    op.drop_index(
        "ix_external_conditions_cache_fetched_at",
        table_name="external_conditions_cache",
    )
    op.drop_table("external_conditions_cache")

    op.drop_index(
        "ix_alerts_dispatched_delivery_status",
        table_name="alerts_dispatched",
    )
    op.drop_index(
        "ix_alerts_dispatched_dispatched_at",
        table_name="alerts_dispatched",
    )
    op.drop_index(
        "ix_alerts_dispatched_subscription_id",
        table_name="alerts_dispatched",
    )
    op.drop_table("alerts_dispatched")

    op.drop_index(
        "ix_alert_subscriptions_alert_type",
        table_name="alert_subscriptions",
    )
    op.drop_index(
        "ix_alert_subscriptions_user_id",
        table_name="alert_subscriptions",
    )
    op.drop_table("alert_subscriptions")

    op.drop_index("ix_districts_display_order", table_name="districts")
    op.drop_table("districts")
