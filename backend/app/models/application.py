import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utc_now
from app.models.opportunity import EmploymentType, SeniorityLevel, WorkMode


class ApplicationStatus(StrEnum):
    INTERESTED = "interested"
    PREPARING = "preparing"
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


ACTIVE_APPLICATION_STATUSES: tuple[str, ...] = (
    ApplicationStatus.INTERESTED.value,
    ApplicationStatus.PREPARING.value,
    ApplicationStatus.APPLIED.value,
    ApplicationStatus.ASSESSMENT.value,
    ApplicationStatus.INTERVIEW.value,
    ApplicationStatus.OFFER.value,
)

CLOSED_APPLICATION_STATUSES: tuple[str, ...] = (
    ApplicationStatus.ACCEPTED.value,
    ApplicationStatus.REJECTED.value,
    ApplicationStatus.WITHDRAWN.value,
)

APPLICATION_STATUS_LABELS_PT: dict[str, str] = {
    ApplicationStatus.INTERESTED.value: "Interesse",
    ApplicationStatus.PREPARING.value: "Preparação",
    ApplicationStatus.APPLIED.value: "Candidatura enviada",
    ApplicationStatus.ASSESSMENT.value: "Teste técnico",
    ApplicationStatus.INTERVIEW.value: "Entrevista",
    ApplicationStatus.OFFER.value: "Proposta",
    ApplicationStatus.ACCEPTED.value: "Aprovado",
    ApplicationStatus.REJECTED.value: "Rejeitado",
    ApplicationStatus.WITHDRAWN.value: "Desistência",
}


ACTIVE_APPLICATION_UNIQUE_INDEX_NAME = "uq_active_application_per_user_opp"
ACTIVE_APPLICATION_PREDICATE_SQL = (
    "opportunity_id IS NOT NULL AND status IN "
    "('interested', 'preparing', 'applied', 'assessment', 'interview', 'offer')"
)


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_opportunity_status", "user_id", "opportunity_id", "status"),
        Index(
            ACTIVE_APPLICATION_UNIQUE_INDEX_NAME,
            "user_id",
            "opportunity_id",
            unique=True,
            postgresql_where=text(ACTIVE_APPLICATION_PREDICATE_SQL),
            sqlite_where=text(ACTIVE_APPLICATION_PREDICATE_SQL),
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
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Snapshots preservados mesmo se a oportunidade global for atualizada ou removida
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    personal_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[str] = mapped_column(
        String(32),
        default=EmploymentType.UNKNOWN.value,
        nullable=False,
    )
    work_mode: Mapped[str] = mapped_column(
        String(32),
        default=WorkMode.UNKNOWN.value,
        nullable=False,
    )
    seniority_level: Mapped[str] = mapped_column(
        String(32),
        default=SeniorityLevel.UNKNOWN.value,
        nullable=False,
    )

    # Estado atual no pipeline, datas relevantes e acompanhamento privado
    status: Mapped[str] = mapped_column(
        String(32),
        default=ApplicationStatus.INTERESTED.value,
        nullable=False,
        index=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    interview_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    assessment_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expected_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_action_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    opportunity = relationship("Opportunity")
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.changed_at.desc(), ApplicationStatusHistory.created_at.desc()",
    )


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    application: Mapped["Application"] = relationship(back_populates="status_history")
