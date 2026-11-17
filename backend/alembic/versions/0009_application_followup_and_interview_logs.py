"""Add application interviews, assessments, contacts and external interaction tracking

Revision ID: 0009_followup_interview_logs
Revises: 0008_active_app_uniq
Create Date: 2026-11-16 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_followup_interview_logs"
down_revision: Union[str, None] = "0008_active_app_uniq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_external_interaction_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_external_interaction_type",
                sa.String(length=32),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_external_interaction_note",
                sa.Text(),
                nullable=True,
            )
        )

    op.create_index(
        op.f("ix_applications_last_external_interaction_at"),
        "applications",
        ["last_external_interaction_at"],
        unique=False,
    )

    op.create_table(
        "application_interviews",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("round_name", sa.String(length=100), nullable=False),
        sa.Column(
            "interview_format",
            sa.String(length=32),
            nullable=False,
            server_default="online",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("meeting_url", sa.String(length=1000), nullable=True),
        sa.Column("interviewers", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("feedback_received", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_interviews")),
    )
    op.create_index(
        op.f("ix_application_interviews_application_id"),
        "application_interviews",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_interviews_scheduled_at"),
        "application_interviews",
        ["scheduled_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_interviews_status"),
        "application_interviews",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_application_interviews_app_status_scheduled",
        "application_interviews",
        ["application_id", "status", "scheduled_at"],
        unique=False,
    )

    op.create_table(
        "application_assessments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("instructions_url", sa.String(length=1000), nullable=True),
        sa.Column("submission_url", sa.String(length=1000), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_assessments")),
    )
    op.create_index(
        op.f("ix_application_assessments_application_id"),
        "application_assessments",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_assessments_deadline_at"),
        "application_assessments",
        ["deadline_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_assessments_status"),
        "application_assessments",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_application_assessments_app_status_deadline",
        "application_assessments",
        ["application_id", "status", "deadline_at"],
        unique=False,
    )

    op.create_table(
        "application_contacts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("role_title", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("linkedin_url", sa.String(length=1000), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_contacts")),
    )
    op.create_index(
        op.f("ix_application_contacts_application_id"),
        "application_contacts",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_contacts_application_id"),
        table_name="application_contacts",
    )
    op.drop_table("application_contacts")

    op.drop_index(
        "ix_application_assessments_app_status_deadline",
        table_name="application_assessments",
    )
    op.drop_index(
        op.f("ix_application_assessments_status"),
        table_name="application_assessments",
    )
    op.drop_index(
        op.f("ix_application_assessments_deadline_at"),
        table_name="application_assessments",
    )
    op.drop_index(
        op.f("ix_application_assessments_application_id"),
        table_name="application_assessments",
    )
    op.drop_table("application_assessments")

    op.drop_index(
        "ix_application_interviews_app_status_scheduled",
        table_name="application_interviews",
    )
    op.drop_index(
        op.f("ix_application_interviews_status"),
        table_name="application_interviews",
    )
    op.drop_index(
        op.f("ix_application_interviews_scheduled_at"),
        table_name="application_interviews",
    )
    op.drop_index(
        op.f("ix_application_interviews_application_id"),
        table_name="application_interviews",
    )
    op.drop_table("application_interviews")

    op.drop_index(
        op.f("ix_applications_last_external_interaction_at"),
        table_name="applications",
    )
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("last_external_interaction_note")
        batch_op.drop_column("last_external_interaction_type")
        batch_op.drop_column("last_external_interaction_at")
