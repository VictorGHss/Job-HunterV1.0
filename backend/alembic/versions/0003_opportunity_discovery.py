"""Add opportunity discovery tables for phase 02

Revision ID: 0003_opportunity_discovery
Revises: 0002_auth_rate_limiting
Create Date: 2026-11-15 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_opportunity_discovery"
down_revision: Union[str, None] = "0002_auth_rate_limiting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

json_type = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def upgrade() -> None:
    op.create_table(
        "opportunity_sources",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="json_api",
        ),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("terms_url", sa.String(length=500), nullable=False),
        sa.Column("attribution_text", sa.String(length=255), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "refresh_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3600"),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_summary", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_opportunity_sources_slug")),
    )
    op.create_index(
        op.f("ix_opportunity_sources_slug"),
        "opportunity_sources",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "opportunity_type",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "employment_type",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "work_mode",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("eligible_countries", json_type, nullable=False),
        sa.Column(
            "eligibility_unknown",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(length=16), nullable=True),
        sa.Column("salary_period", sa.String(length=32), nullable=True),
        sa.Column("requirements", json_type, nullable=False),
        sa.Column("technologies", json_type, nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("application_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "missing_sync_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_metadata", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["opportunity_sources.id"],
            name=op.f("fk_opportunities_source_id_opportunity_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_opportunities_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_opportunities_source_external",
        ),
    )
    op.create_index(op.f("ix_opportunities_source_id"), "opportunities", ["source_id"])
    op.create_index(
        op.f("ix_opportunities_created_by_user_id"),
        "opportunities",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_opportunities_opportunity_type"),
        "opportunities",
        ["opportunity_type"],
    )
    op.create_index(
        op.f("ix_opportunities_employment_type"),
        "opportunities",
        ["employment_type"],
    )
    op.create_index(op.f("ix_opportunities_work_mode"), "opportunities", ["work_mode"])
    op.create_index(
        op.f("ix_opportunities_published_at"), "opportunities", ["published_at"]
    )
    op.create_index(
        op.f("ix_opportunities_source_status"), "opportunities", ["source_status"]
    )
    op.create_index(
        op.f("ix_opportunities_content_hash"), "opportunities", ["content_hash"]
    )
    op.create_index(
        "ix_opportunities_source_url", "opportunities", ["source_id", "source_url"]
    )
    op.create_index(
        "ix_opportunities_user_published",
        "opportunities",
        ["created_by_user_id", "published_at"],
    )

    op.create_table(
        "opportunity_user_states",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "is_saved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_dismissed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_opportunity_user_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_user_states_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_user_states")),
        sa.UniqueConstraint(
            "user_id",
            "opportunity_id",
            name="uq_opportunity_user_state_user_opp",
        ),
    )
    op.create_index(
        op.f("ix_opportunity_user_states_user_id"),
        "opportunity_user_states",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_opportunity_user_states_opportunity_id"),
        "opportunity_user_states",
        ["opportunity_id"],
    )

    op.create_table(
        "opportunity_sync_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "inserted_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "skipped_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["opportunity_sources.id"],
            name=op.f("fk_opportunity_sync_runs_source_id_opportunity_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_sync_runs")),
    )
    op.create_index(
        op.f("ix_opportunity_sync_runs_source_id"),
        "opportunity_sync_runs",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_opportunity_sync_runs_source_id"),
        table_name="opportunity_sync_runs",
    )
    op.drop_table("opportunity_sync_runs")

    op.drop_index(
        op.f("ix_opportunity_user_states_opportunity_id"),
        table_name="opportunity_user_states",
    )
    op.drop_index(
        op.f("ix_opportunity_user_states_user_id"),
        table_name="opportunity_user_states",
    )
    op.drop_table("opportunity_user_states")

    op.drop_index("ix_opportunities_user_published", table_name="opportunities")
    op.drop_index("ix_opportunities_source_url", table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_content_hash"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_source_status"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_published_at"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_work_mode"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_employment_type"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_opportunity_type"), table_name="opportunities")
    op.drop_index(
        op.f("ix_opportunities_created_by_user_id"),
        table_name="opportunities",
    )
    op.drop_index(op.f("ix_opportunities_source_id"), table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index(op.f("ix_opportunity_sources_slug"), table_name="opportunity_sources")
    op.drop_table("opportunity_sources")
