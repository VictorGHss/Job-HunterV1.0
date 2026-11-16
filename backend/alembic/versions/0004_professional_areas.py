"""Add professional_area and secondary_areas to opportunities for phase 02.3

Revision ID: 0004_professional_areas
Revises: 0003_opportunity_discovery
Create Date: 2026-11-15 21:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_professional_areas"
down_revision: Union[str, None] = "0003_opportunity_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

json_type = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "professional_area",
                sa.String(length=64),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "secondary_areas",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.create_index(
            op.f("ix_opportunities_professional_area"),
            ["professional_area"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_index(op.f("ix_opportunities_professional_area"))
        batch_op.drop_column("secondary_areas")
        batch_op.drop_column("professional_area")
