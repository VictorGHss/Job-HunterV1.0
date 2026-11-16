"""Add partial unique index for active user applications per opportunity

Revision ID: 0008_active_app_uniq
Revises: 0007_applications_pipeline
Create Date: 2026-11-16 01:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_active_app_uniq"
down_revision: Union[str, None] = "0007_applications_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PARTIAL_UNIQUE_INDEX_NAME = "uq_active_application_per_user_opp"
_ACTIVE_STATUSES_WHERE = (
    "opportunity_id IS NOT NULL AND status IN "
    "('interested', 'preparing', 'applied', 'assessment', 'interview', 'offer')"
)


def upgrade() -> None:
    op.create_index(
        _PARTIAL_UNIQUE_INDEX_NAME,
        "applications",
        ["user_id", "opportunity_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATUSES_WHERE),
        sqlite_where=sa.text(_ACTIVE_STATUSES_WHERE),
    )


def downgrade() -> None:
    op.drop_index(_PARTIAL_UNIQUE_INDEX_NAME, table_name="applications")
