import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.profile import JsonType


class SourceType(StrEnum):
    JSON_API = "json_api"
    RSS = "rss"
    MANUAL = "manual"


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    JUNIOR = "junior"
    FREELANCE = "freelance"
    OTHER = "other"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    INTERNSHIP = "internship"
    ENTRY_LEVEL = "entry_level"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    STAFF_PRINCIPAL = "staff_principal"
    MANAGEMENT = "management"
    UNKNOWN = "unknown"


class ExperienceRequirementMode(StrEnum):
    NOT_SPECIFIED = "not_specified"
    NONE_REQUIRED = "none_required"
    PREFERRED = "preferred"
    REQUIRED = "required"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    INTERNSHIP = "internship"
    CLT = "clt"
    PJ = "pj"
    FREELANCE = "freelance"
    TEMPORARY = "temporary"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProfessionalArea(StrEnum):
    SOFTWARE_DEVELOPMENT = "software_development"
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DATA = "data"
    ARTIFICIAL_INTELLIGENCE = "artificial_intelligence"
    DEVOPS_CLOUD = "devops_cloud"
    API_INTEGRATIONS = "api_integrations"
    INFRASTRUCTURE = "infrastructure"
    TECHNICAL_SUPPORT = "technical_support"
    CUSTOMER_SUPPORT = "customer_support"
    MARKETING_SALES = "marketing_sales"
    HEALTHCARE = "healthcare"
    ADMINISTRATION = "administration"
    OTHER = "other"
    UNKNOWN = "unknown"


class ExternalSourceStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    REMOVED = "removed"
    SOURCE_UNAVAILABLE = "source_unavailable"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"


class SyncRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class OpportunitySource(Base, TimestampMixin):
    __tablename__ = "opportunity_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default=SourceType.JSON_API.value, nullable=False
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    terms_url: Mapped[str] = mapped_column(String(500), nullable=False)
    attribution_text: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    refresh_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=3600, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    source_links: Mapped[list["OpportunitySourceLink"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    sync_runs: Mapped[list["OpportunitySyncRun"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_opportunities_source_external",
        ),
        Index("ix_opportunities_source_url", "source_id", "source_url"),
        Index("ix_opportunities_user_published", "created_by_user_id", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    opportunity_type: Mapped[str] = mapped_column(
        String(32),
        default=OpportunityType.UNKNOWN.value,
        index=True,
        nullable=False,
    )
    seniority_level: Mapped[str] = mapped_column(
        String(32),
        default=SeniorityLevel.UNKNOWN.value,
        index=True,
        nullable=False,
    )
    experience_requirement_mode: Mapped[str] = mapped_column(
        String(32),
        default=ExperienceRequirementMode.NOT_SPECIFIED.value,
        index=True,
        nullable=False,
    )
    experience_min_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    experience_preferred_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    experience_summary: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    employment_type: Mapped[str] = mapped_column(
        String(32),
        default=EmploymentType.UNKNOWN.value,
        index=True,
        nullable=False,
    )
    work_mode: Mapped[str] = mapped_column(
        String(32),
        default=WorkMode.UNKNOWN.value,
        index=True,
        nullable=False,
    )
    professional_area: Mapped[str] = mapped_column(
        String(64),
        default=ProfessionalArea.UNKNOWN.value,
        index=True,
        nullable=False,
    )
    secondary_areas: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )

    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    eligible_countries: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    eligibility_unknown: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)

    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(32), nullable=True)

    requirements: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    technologies: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )

    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_status: Mapped[str] = mapped_column(
        String(32),
        default=ExternalSourceStatus.ACTIVE.value,
        index=True,
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_status_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    missing_sync_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )

    source: Mapped["OpportunitySource | None"] = relationship(
        back_populates="opportunities"
    )
    source_links: Mapped[list["OpportunitySourceLink"]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
        order_by="OpportunitySourceLink.is_primary.desc(), OpportunitySourceLink.first_seen_at.asc()",
    )
    user_states: Mapped[list["OpportunityUserState"]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    applications = relationship(
        "Application",
        back_populates="opportunity",
    )


class OpportunitySourceLink(Base, TimestampMixin):
    __tablename__ = "opportunity_source_links"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_opp_source_links_source_external",
        ),
        Index("ix_opp_source_links_source_url", "source_id", "source_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_status: Mapped[str] = mapped_column(
        String(32),
        default=ExternalSourceStatus.ACTIVE.value,
        index=True,
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eligible_countries: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    missing_sync_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="source_links")
    source: Mapped["OpportunitySource"] = relationship(back_populates="source_links")


class OpportunityUserState(Base, TimestampMixin):
    __tablename__ = "opportunity_user_states"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "opportunity_id",
            name="uq_opportunity_user_state_user_opp",
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
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="user_states")


class OpportunitySyncRun(Base):
    __tablename__ = "opportunity_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    intra_source_duplicate_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    cross_source_duplicate_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_opportunities_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    open_opportunities_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    closed_or_expired_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    unconfirmed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source: Mapped["OpportunitySource"] = relationship(back_populates="sync_runs")
