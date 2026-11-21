"""Add is_rejected and rejected_at to application_material_versions

Revision ID: 0012_ai_version_rejection_state
Revises: 0011_ai_usage_ledger
Create Date: 2026-11-21 11:20:00.000000

Nota operacional sobre downgrade:
Executar downgrade desta revisão remove as colunas ``is_rejected`` e ``rejected_at``
de ``application_material_versions``. Caso já existam versões rejeitadas persistidas,
o estado de rejeição dessas versões será descartado na remoção das colunas
(portanto, o downgrade não é uma operação sem perda de metadados de rejeição).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_ai_version_rejection_state"
down_revision: Union[str, None] = "0011_ai_usage_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REJECTION_CHECK_SQL = (
    "(NOT is_rejected AND rejected_at IS NULL) "
    "OR (is_rejected AND rejected_at IS NOT NULL AND NOT is_approved)"
)


def upgrade() -> None:
    with op.batch_alter_table("application_material_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_rejected",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "rejected_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "rejection_state_consistent",
            REJECTION_CHECK_SQL,
        )

    op.create_index(
        "ix_material_versions_mat_rejected_ver",
        "application_material_versions",
        ["material_id", "is_rejected", "version_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_versions_mat_rejected_ver",
        table_name="application_material_versions",
    )
    with op.batch_alter_table("application_material_versions") as batch_op:
        batch_op.drop_constraint(
            "rejection_state_consistent",
            type_="check",
        )
        batch_op.drop_column("rejected_at")
        batch_op.drop_column("is_rejected")
