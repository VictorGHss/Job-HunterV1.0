import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

JsonType = JSON().with_variant(JSONB(), "postgresql")


class VerificationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_VALIDATION = "pending_validation"
    CONFIRMED = "confirmed"


class ExperienceType(StrEnum):
    INTERNSHIP = "internship"
    JUNIOR = "junior"
    FREELANCE = "freelance"
    PJ = "pj"
    CLT = "clt"
    ACADEMIC = "academic"
    OTHER = "other"


class EducationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"
    PLANNED = "planned"


class SkillProficiency(StrEnum):
    BEGINNER = "beginner"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class LanguageProficiency(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    FLUENT = "fluent"
    NATIVE = "native"


def default_career_preferences() -> dict[str, Any]:
    """Retorna uma estrutura neutra e genérica de preferências para novos usuários."""
    return {
        "internships": {
            "enabled": True,
            "priority_areas": [],
            "preferred_languages": [],
            "excluded_areas": [],
        },
        "junior_developer": {
            "enabled": True,
            "priority_areas": [],
            "block_clt": False,
            "accepted_contract_types": [],
            "excluded_areas": [],
        },
        "freelance": {
            "enabled": True,
            "scopes": [],
            "priority_categories": [],
            "preferred_languages": [],
        },
        "source_restrictions": {
            "workana_enabled": True,
            "workana_disabled_reason": "",
            "gupy_mode": "selective_high_compatibility",
            "auto_execute_tests": False,
            "pay_premium_or_fees_without_approval": False,
            "strict_platform_terms_compliance": True,
        },
    }


class ProfessionalProfile(Base, TimestampMixin):
    __tablename__ = "professional_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    professional_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    professional_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        default=default_career_preferences,
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.DRAFT.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class WorkExperience(Base, TimestampMixin):
    __tablename__ = "work_experiences"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    experience_type: Mapped[str] = mapped_column(
        String(64),
        default=ExperienceType.INTERNSHIP.value,
        nullable=False,
    )
    technologies: Mapped[list[str]] = mapped_column(
        JsonType,
        default=list,
        nullable=False,
    )
    related_skills: Mapped[list[str]] = mapped_column(
        JsonType,
        default=list,
        nullable=False,
    )
    eligible_as_target_role: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.PENDING_VALIDATION.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Education(Base, TimestampMixin):
    __tablename__ = "educations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(200), nullable=False)
    field_of_study: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_semester: Mapped[str | None] = mapped_column(String(80), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    education_status: Mapped[str] = mapped_column(
        String(64),
        default=EducationStatus.IN_PROGRESS.value,
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.PENDING_VALIDATION.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    proficiency_level: Mapped[str] = mapped_column(
        String(64),
        default=SkillProficiency.INTERMEDIATE.value,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.PENDING_VALIDATION.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Language(Base, TimestampMixin):
    __tablename__ = "languages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    language_name: Mapped[str] = mapped_column(String(100), nullable=False)
    proficiency_level: Mapped[str] = mapped_column(
        String(64),
        default=LanguageProficiency.INTERMEDIATE.value,
        nullable=False,
    )
    cefr_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.PENDING_VALIDATION.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ProfessionalProject(Base, TimestampMixin):
    __tablename__ = "professional_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(
        JsonType,
        default=list,
        nullable=False,
    )
    links: Mapped[dict[str, str]] = mapped_column(
        JsonType,
        default=dict,
        nullable=False,
    )
    verified_results: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.DRAFT.value,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
