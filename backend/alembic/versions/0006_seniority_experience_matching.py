"""Add seniority_level and structured experience requirement columns for phase 02.6

Revision ID: 0006_seniority_experience_matching
Revises: 0005_lifecycle_traceability
Create Date: 2026-11-15 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_seniority_experience"
down_revision: Union[str, None] = "0005_lifecycle_traceability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "seniority_level",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "experience_requirement_mode",
                sa.String(length=32),
                nullable=False,
                server_default="not_specified",
            )
        )
        batch_op.add_column(
            sa.Column("experience_min_years", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("experience_preferred_years", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("experience_summary", sa.String(length=255), nullable=True)
        )
        batch_op.create_index(
            op.f("ix_opportunities_seniority_level"),
            ["seniority_level"],
            unique=False,
        )
        batch_op.create_index(
            op.f("ix_opportunities_experience_requirement_mode"),
            ["experience_requirement_mode"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_index(op.f("ix_opportunities_experience_requirement_mode"))
        batch_op.drop_index(op.f("ix_opportunities_seniority_level"))
        batch_op.drop_column("experience_summary")
        batch_op.drop_column("experience_preferred_years")
        batch_op.drop_column("experience_min_years")
        batch_op.drop_column("experience_requirement_mode")
        batch_op.drop_column("seniority_level")
