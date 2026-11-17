import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
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


class InterviewFormat(StrEnum):
    ONLINE = "online"
    IN_PERSON = "in_person"
    PHONE = "phone"


class InterviewStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssessmentStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FEEDBACK_RECEIVED = "feedback_received"
    CANCELLED = "cancelled"


class ExternalInteractionType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    LINKEDIN = "linkedin"
    INTERVIEW = "interview"
    OTHER = "other"


INTERVIEW_FORMAT_LABELS_PT: dict[str, str] = {
    InterviewFormat.ONLINE.value: "Online / Vídeo",
    InterviewFormat.IN_PERSON.value: "Presencial",
    InterviewFormat.PHONE.value: "Telefone",
}

INTERVIEW_STATUS_LABELS_PT: dict[str, str] = {
    InterviewStatus.SCHEDULED.value: "Agendada",
    InterviewStatus.COMPLETED.value: "Concluída",
    InterviewStatus.CANCELLED.value: "Cancelada",
}

ASSESSMENT_STATUS_LABELS_PT: dict[str, str] = {
    AssessmentStatus.PENDING.value: "Pendente",
    AssessmentStatus.IN_PROGRESS.value: "Em andamento",
    AssessmentStatus.SUBMITTED.value: "Enviado",
    AssessmentStatus.FEEDBACK_RECEIVED.value: "Feedback recebido",
    AssessmentStatus.CANCELLED.value: "Cancelado",
}

EXTERNAL_INTERACTION_TYPE_LABELS_PT: dict[str, str] = {
    ExternalInteractionType.EMAIL.value: "E-mail",
    ExternalInteractionType.PHONE.value: "Telefone",
    ExternalInteractionType.LINKEDIN.value: "LinkedIn",
    ExternalInteractionType.INTERVIEW.value: "Entrevista",
    ExternalInteractionType.OTHER.value: "Outro contato",
}


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
    last_external_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_external_interaction_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    last_external_interaction_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    opportunity = relationship("Opportunity")
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.changed_at.desc(), ApplicationStatusHistory.created_at.desc()",
    )
    interviews: Mapped[list["ApplicationInterview"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationInterview.scheduled_at.asc(), ApplicationInterview.created_at.asc()",
    )
    assessments: Mapped[list["ApplicationAssessment"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationAssessment.deadline_at.asc(), ApplicationAssessment.created_at.desc()",
    )
    contacts: Mapped[list["ApplicationContact"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationContact.created_at.asc()",
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


class ApplicationInterview(Base, TimestampMixin):
    __tablename__ = "application_interviews"
    __table_args__ = (
        Index(
            "ix_application_interviews_app_status_scheduled",
            "application_id",
            "status",
            "scheduled_at",
        ),
    )

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
    round_name: Mapped[str] = mapped_column(String(100), nullable=False)
    interview_format: Mapped[str] = mapped_column(
        String(32),
        default=InterviewFormat.ONLINE.value,
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    previous_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    interviewers: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_received: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=InterviewStatus.SCHEDULED.value,
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    application: Mapped["Application"] = relationship(back_populates="interviews")


class ApplicationAssessment(Base, TimestampMixin):
    __tablename__ = "application_assessments"
    __table_args__ = (
        Index(
            "ix_application_assessments_app_status_deadline",
            "application_id",
            "status",
            "deadline_at",
        ),
    )

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
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instructions_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    submission_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=AssessmentStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(back_populates="assessments")


class ApplicationContact(Base, TimestampMixin):
    __tablename__ = "application_contacts"

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
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(back_populates="contacts")
