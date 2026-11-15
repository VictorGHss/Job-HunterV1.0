"""Add auth_rate_limits table for persistent brute-force protection

Revision ID: 0002_auth_rate_limiting
Revises: 0001_initial_foundation
Create Date: 2026-11-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_auth_rate_limiting"
down_revision: Union[str, None] = "0001_initial_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_rate_limits")),
        sa.UniqueConstraint(
            "scope_type",
            "scope_key",
            name="uq_auth_rate_limits_scope_type_key",
        ),
    )
    op.create_index(
        op.f("ix_auth_rate_limits_scope_key"),
        "auth_rate_limits",
        ["scope_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_rate_limits_scope_key"), table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
