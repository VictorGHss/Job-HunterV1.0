"""Add ai_usage_ledger, ai_quota_scopes and ai_circuit_breakers tables

Revision ID: 0011_ai_usage_ledger
Revises: 0010_application_materials
Create Date: 2026-11-18 00:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_ai_usage_ledger"
down_revision: Union[str, None] = "0010_application_materials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_quota_scopes",
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope_key", name=op.f("pk_ai_quota_scopes")),
    )

    op.create_table(
        "ai_circuit_breakers",
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="closed",
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "half_open_probe_in_flight",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("half_open_probe_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_reason", sa.String(length=64), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_ai_circuit_breakers_non_negative_failures"),
        ),
        sa.PrimaryKeyConstraint("provider_key", name=op.f("pk_ai_circuit_breakers")),
    )

    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("version_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="reserved",
        ),
        sa.Column(
            "reserved_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "usage_reported",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reserved_tokens >= 0 "
            "AND (input_tokens IS NULL OR input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0) "
            "AND (total_tokens IS NULL OR total_tokens >= 0)",
            name=op.f("ck_ai_usage_ledger_non_negative_tokens"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name=op.f("ck_ai_usage_ledger_non_negative_latency"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["application_materials.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["application_material_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_ledger")),
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_user_id"),
        "ai_usage_ledger",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_material_id"),
        "ai_usage_ledger",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_version_id"),
        "ai_usage_ledger",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_ledger_user_created",
        "ai_usage_ledger",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_ledger_created_status",
        "ai_usage_ledger",
        ["created_at", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_ledger_status_expires",
        "ai_usage_ledger",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_ledger_operation_provider",
        "ai_usage_ledger",
        ["operation_type", "provider_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_ledger_operation_provider", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_status_expires", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_created_status", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_user_created", table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_version_id"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_material_id"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_user_id"), table_name="ai_usage_ledger")
    op.drop_table("ai_usage_ledger")

    op.drop_table("ai_circuit_breakers")
    op.drop_table("ai_quota_scopes")
