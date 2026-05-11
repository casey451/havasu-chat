"""Phase 1A — unified ENTITY core + 11 extension tables (additive).

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-14

Creates ``entities`` and extension tables per docs/maintainability/master_build_plan.md
§4 Phase 1. Adds nullable ``sponsors.entity_type`` for the ENTITY transition.

No data writes — tables ship empty. Legacy providers/events/programs unchanged.

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="seed"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"], unique=False)
    op.create_index("ix_entities_slug", "entities", ["slug"], unique=True)

    op.create_table(
        "entity_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_entity_categories_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_entity_categories_category_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "category_id",
            name="uq_entity_categories_entity_category",
        ),
    )
    op.create_index("ix_entity_categories_entity_id", "entity_categories", ["entity_id"])
    op.create_index("ix_entity_categories_category_id", "entity_categories", ["category_id"])

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("address_normalized", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("zip", sa.String(length=16), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("google_place_id", sa.String(length=64), nullable=True),
        sa.Column("district", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_locations_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", name="uq_locations_entity_id"),
    )
    op.create_index("ix_locations_entity_id", "locations", ["entity_id"])
    op.create_index("ix_locations_google_place_id", "locations", ["google_place_id"])

    op.create_table(
        "hours",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("is_24h", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_hours_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hours_entity_id", "hours", ["entity_id"])

    op.create_table(
        "seasonal_hours",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("season", sa.String(length=16), nullable=False),
        sa.Column("applies_from", sa.Date(), nullable=True),
        sa.Column("applies_to", sa.Date(), nullable=True),
        sa.Column("hours_overlay", sa.JSON(), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_seasonal_hours_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seasonal_hours_entity_id", "seasonal_hours", ["entity_id"])

    op.create_table(
        "contact_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_contact_points_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_points_entity_id", "contact_points", ["entity_id"])

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_features_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "key", name="uq_features_entity_key"),
    )
    op.create_index("ix_features_entity_id", "features", ["entity_id"])

    op.create_table(
        "offerings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_text", sa.String(length=64), nullable=True),
        sa.Column("price_min_cents", sa.Integer(), nullable=True),
        sa.Column("price_max_cents", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_offerings_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offerings_entity_id", "offerings", ["entity_id"])

    op.create_table(
        "service_areas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("zone_name", sa.String(length=128), nullable=False),
        sa.Column("zone_type", sa.String(length=32), nullable=False),
        sa.Column("radius_miles", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_service_areas_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_areas_entity_id", "service_areas", ["entity_id"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("schedule_type", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("recurrence_rule", sa.String(length=255), nullable=True),
        sa.Column("days_of_week", sa.JSON(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("capacity_label", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_schedules_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedules_entity_id", "schedules", ["entity_id"])

    op.create_table(
        "source_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field_path", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_method", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_source_evidence_entity_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_evidence_entity_id", "source_evidence", ["entity_id"])

    op.create_table(
        "sponsorship_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("sponsor_id", sa.String(), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_sponsorship_slots_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sponsor_id"],
            ["sponsors.id"],
            name="fk_sponsorship_slots_sponsor_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "sponsor_id",
            "slot_type",
            name="uq_sponsorship_slots_entity_sponsor_slot",
        ),
    )
    op.create_index("ix_sponsorship_slots_entity_id", "sponsorship_slots", ["entity_id"])
    op.create_index("ix_sponsorship_slots_sponsor_id", "sponsorship_slots", ["sponsor_id"])

    with op.batch_alter_table("sponsors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entity_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sponsors", schema=None) as batch_op:
        batch_op.drop_column("entity_type")

    op.drop_index("ix_sponsorship_slots_sponsor_id", table_name="sponsorship_slots")
    op.drop_index("ix_sponsorship_slots_entity_id", table_name="sponsorship_slots")
    op.drop_table("sponsorship_slots")

    op.drop_index("ix_source_evidence_entity_id", table_name="source_evidence")
    op.drop_table("source_evidence")

    op.drop_index("ix_schedules_entity_id", table_name="schedules")
    op.drop_table("schedules")

    op.drop_index("ix_service_areas_entity_id", table_name="service_areas")
    op.drop_table("service_areas")

    op.drop_index("ix_offerings_entity_id", table_name="offerings")
    op.drop_table("offerings")

    op.drop_index("ix_features_entity_id", table_name="features")
    op.drop_table("features")

    op.drop_index("ix_contact_points_entity_id", table_name="contact_points")
    op.drop_table("contact_points")

    op.drop_index("ix_seasonal_hours_entity_id", table_name="seasonal_hours")
    op.drop_table("seasonal_hours")

    op.drop_index("ix_hours_entity_id", table_name="hours")
    op.drop_table("hours")

    op.drop_index("ix_locations_google_place_id", table_name="locations")
    op.drop_index("ix_locations_entity_id", table_name="locations")
    op.drop_table("locations")

    op.drop_index("ix_entity_categories_category_id", table_name="entity_categories")
    op.drop_index("ix_entity_categories_entity_id", table_name="entity_categories")
    op.drop_table("entity_categories")

    op.drop_index("ix_entities_slug", table_name="entities")
    op.drop_index("ix_entities_entity_type", table_name="entities")
    op.drop_table("entities")
