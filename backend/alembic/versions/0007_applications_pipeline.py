"""Add applications and application_status_history tables for phase 03.1

Revision ID: 0007_applications_pipeline
Revises: 0006_seniority_experience
Create Date: 2026-11-16 00:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_applications_pipeline"
down_revision: Union[str, None] = "0006_seniority_experience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("role_title", sa.String(length=255), nullable=False),
        sa.Column("personal_summary", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=150), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("application_url", sa.String(length=1000), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
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
        sa.Column(
            "seniority_level",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="interested",
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interview_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action", sa.String(length=255), nullable=True),
        sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    op.create_index(op.f("ix_applications_user_id"), "applications", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_applications_opportunity_id"),
        "applications",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(op.f("ix_applications_status"), "applications", ["status"], unique=False)
    op.create_index(
        "ix_applications_user_status",
        "applications",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_applications_user_opportunity_status",
        "applications",
        ["user_id", "opportunity_id", "status"],
        unique=False,
    )

    op.create_table(
        "application_status_history",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_status_history")),
    )
    op.create_index(
        op.f("ix_application_status_history_application_id"),
        "application_status_history",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_status_history_user_id"),
        "application_status_history",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_status_history_changed_at"),
        "application_status_history",
        ["changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_status_history_changed_at"),
        table_name="application_status_history",
    )
    op.drop_index(
        op.f("ix_application_status_history_user_id"),
        table_name="application_status_history",
    )
    op.drop_index(
        op.f("ix_application_status_history_application_id"),
        table_name="application_status_history",
    )
    op.drop_table("application_status_history")

    op.drop_index("ix_applications_user_opportunity_status", table_name="applications")
    op.drop_index("ix_applications_user_status", table_name="applications")
    op.drop_index(op.f("ix_applications_status"), table_name="applications")
    op.drop_index(op.f("ix_applications_opportunity_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_user_id"), table_name="applications")
    op.drop_table("applications")
