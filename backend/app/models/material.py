import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utc_now
from app.models.profile import JsonType


class MaterialType(StrEnum):
    RESUME = "resume"


class MaterialVersionOrigin(StrEnum):
    GENERATED = "generated"
    MANUAL_EDIT = "manual_edit"
    REGENERATED = "regenerated"
    DERIVED = "derived"


ACTIVE_MATERIAL_LINK_UNIQUE_INDEX_NAME = "uq_active_link_per_app_material"
ACTIVE_MATERIAL_LINK_PREDICATE_SQL = "unlinked_at IS NULL"


class ApplicationMaterial(Base, TimestampMixin):
    __tablename__ = "application_materials"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_application_materials_user_id_id"),
        Index("ix_application_materials_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    material_type: Mapped[str] = mapped_column(
        String(32),
        default=MaterialType.RESUME.value,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    target_language: Mapped[str] = mapped_column(
        String(16),
        default="pt-BR",
        nullable=False,
    )

    opportunity = relationship("Opportunity")
    versions: Mapped[list["ApplicationMaterialVersion"]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="ApplicationMaterialVersion.version_number.desc()",
    )
    links: Mapped[list["ApplicationMaterialLink"]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="ApplicationMaterialLink.linked_at.desc()",
        overlaps="material_links",
    )


class ApplicationMaterialVersion(Base, TimestampMixin):
    __tablename__ = "application_material_versions"
    __table_args__ = (
        UniqueConstraint(
            "material_id",
            "version_number",
            name="uq_material_versions_mat_ver_num",
        ),
        UniqueConstraint(
            "material_id",
            "id",
            name="uq_material_versions_mat_id_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(
        String(32),
        default=MaterialVersionOrigin.GENERATED.value,
        nullable=False,
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_material_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Única fonte editável canônica de conteúdo (Markdown é sempre derivado em tempo real)
    structured_content: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
    )
    source_facts_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
    )
    unconfirmed_warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType,
        default=list,
        nullable=False,
    )
    missing_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType,
        default=list,
        nullable=False,
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    material: Mapped["ApplicationMaterial"] = relationship(
        back_populates="versions",
        foreign_keys=[material_id],
    )
    links: Mapped[list["ApplicationMaterialLink"]] = relationship(
        back_populates="version",
        foreign_keys="ApplicationMaterialLink.version_id",
        overlaps="links,material",
    )


class ApplicationMaterialLink(Base):
    __tablename__ = "application_material_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "application_id"],
            ["applications.user_id", "applications.id"],
            name="fk_mat_links_user_app",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "material_id"],
            ["application_materials.user_id", "application_materials.id"],
            name="fk_mat_links_user_mat",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["material_id", "version_id"],
            ["application_material_versions.material_id", "application_material_versions.id"],
            name="fk_mat_links_mat_ver",
            ondelete="CASCADE",
        ),
        Index(
            ACTIVE_MATERIAL_LINK_UNIQUE_INDEX_NAME,
            "application_id",
            "material_id",
            unique=True,
            postgresql_where=text(ACTIVE_MATERIAL_LINK_PREDICATE_SQL),
            sqlite_where=text(ACTIVE_MATERIAL_LINK_PREDICATE_SQL),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    unlinked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    application = relationship(
        "Application",
        back_populates="material_links",
        foreign_keys=[application_id],
        primaryjoin="ApplicationMaterialLink.application_id == Application.id",
        overlaps="links,material",
    )
    material: Mapped["ApplicationMaterial"] = relationship(
        back_populates="links",
        foreign_keys=[material_id],
        primaryjoin="ApplicationMaterialLink.material_id == ApplicationMaterial.id",
        overlaps="application,material_links,links,version",
    )
    version: Mapped["ApplicationMaterialVersion"] = relationship(
        back_populates="links",
        foreign_keys=[version_id],
        primaryjoin="ApplicationMaterialLink.version_id == ApplicationMaterialVersion.id",
        overlaps="links,material,application,material_links",
    )
