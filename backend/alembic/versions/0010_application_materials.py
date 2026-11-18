"""Add application_materials, application_material_versions and application_material_links

Revision ID: 0010_application_materials
Revises: 0009_followup_interview_logs
Create Date: 2026-11-17 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_application_materials"
down_revision: Union[str, None] = "0009_followup_interview_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_applications_user_id_id", ["user_id", "id"]
        )

    op.create_table(
        "application_materials",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "material_type",
            sa.String(length=32),
            nullable=False,
            server_default="resume",
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "target_language",
            sa.String(length=16),
            nullable=False,
            server_default="pt-BR",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_materials")),
        sa.UniqueConstraint(
            "user_id", "id", name="uq_application_materials_user_id_id"
        ),
    )
    op.create_index(
        op.f("ix_application_materials_user_id"),
        "application_materials",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_materials_opportunity_id"),
        "application_materials",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_materials_user_updated",
        "application_materials",
        ["user_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "application_material_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "origin",
            sa.String(length=32),
            nullable=False,
            server_default="generated",
        ),
        sa.Column("parent_version_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_instructions", sa.Text(), nullable=True),
        sa.Column("structured_content", JsonType, nullable=False),
        sa.Column("source_facts_snapshot", JsonType, nullable=False),
        sa.Column("unconfirmed_warnings", JsonType, nullable=False),
        sa.Column("missing_requirements", JsonType, nullable=False),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["application_materials.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["application_material_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_material_versions")),
        sa.UniqueConstraint(
            "material_id", "version_number", name="uq_material_versions_mat_ver_num"
        ),
        sa.UniqueConstraint(
            "material_id", "id", name="uq_material_versions_mat_id_id"
        ),
    )
    op.create_index(
        op.f("ix_application_material_versions_material_id"),
        "application_material_versions",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_material_versions_is_approved"),
        "application_material_versions",
        ["is_approved"],
        unique=False,
    )

    op.create_table(
        "application_material_links",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id", "application_id"],
            ["applications.user_id", "applications.id"],
            name="fk_mat_links_user_app",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "material_id"],
            ["application_materials.user_id", "application_materials.id"],
            name="fk_mat_links_user_mat",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "version_id"],
            [
                "application_material_versions.material_id",
                "application_material_versions.id",
            ],
            name="fk_mat_links_mat_ver",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_material_links")),
    )
    op.create_index(
        op.f("ix_application_material_links_user_id"),
        "application_material_links",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_material_links_application_id"),
        "application_material_links",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_material_links_material_id"),
        "application_material_links",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_material_links_version_id"),
        "application_material_links",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_material_links_unlinked_at"),
        "application_material_links",
        ["unlinked_at"],
        unique=False,
    )
    op.create_index(
        "uq_active_link_per_app_material",
        "application_material_links",
        ["application_id", "material_id"],
        unique=True,
        postgresql_where=sa.text("unlinked_at IS NULL"),
        sqlite_where=sa.text("unlinked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_link_per_app_material",
        table_name="application_material_links",
    )
    op.drop_index(
        op.f("ix_application_material_links_unlinked_at"),
        table_name="application_material_links",
    )
    op.drop_index(
        op.f("ix_application_material_links_version_id"),
        table_name="application_material_links",
    )
    op.drop_index(
        op.f("ix_application_material_links_material_id"),
        table_name="application_material_links",
    )
    op.drop_index(
        op.f("ix_application_material_links_application_id"),
        table_name="application_material_links",
    )
    op.drop_index(
        op.f("ix_application_material_links_user_id"),
        table_name="application_material_links",
    )
    op.drop_table("application_material_links")

    op.drop_index(
        op.f("ix_application_material_versions_is_approved"),
        table_name="application_material_versions",
    )
    op.drop_index(
        op.f("ix_application_material_versions_material_id"),
        table_name="application_material_versions",
    )
    op.drop_table("application_material_versions")

    op.drop_index(
        "ix_application_materials_user_updated",
        table_name="application_materials",
    )
    op.drop_index(
        op.f("ix_application_materials_opportunity_id"),
        table_name="application_materials",
    )
    op.drop_index(
        op.f("ix_application_materials_user_id"),
        table_name="application_materials",
    )
    op.drop_table("application_materials")

    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("uq_applications_user_id_id", type_="unique")
