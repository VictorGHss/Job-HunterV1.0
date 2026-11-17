import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.application import (
    ApplicationStatus,
    AssessmentStatus,
    ExternalInteractionType,
    InterviewFormat,
    InterviewStatus,
)
from app.models.opportunity import EmploymentType, SeniorityLevel, WorkMode
from app.services.opportunities.sanitization import (
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)


def _normalize_optional_url(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    return validate_safe_external_url(str(raw), allow_localhost=False)


def _normalize_optional_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_tz_aware_dt(value: datetime | None, *, field_label: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_label} deve informar explicitamente o fuso horário (ex.: 'Z' ou '-03:00')."
        )
    return value.astimezone(UTC)


def _blank_str_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: uuid.UUID | None = None
    role_title: str | None = Field(default=None, min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    personal_summary: str | None = Field(default=None, max_length=8000)
    source_name: str | None = Field(default=None, max_length=150)
    source_url: str | None = Field(default=None, max_length=1000)
    application_url: str | None = Field(default=None, max_length=1000)
    location_text: str | None = Field(default=None, max_length=255)
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    seniority_level: SeniorityLevel | None = None
    status: ApplicationStatus = ApplicationStatus.INTERESTED
    applied_at: datetime | None = None
    interview_at: datetime | None = None
    assessment_deadline_at: datetime | None = None
    expected_response_at: datetime | None = None
    next_action: str | None = Field(default=None, max_length=255)
    next_action_due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10000)
    status_note: str | None = Field(default=None, max_length=500)

    @field_validator("source_url", "application_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("role_title", "company_name", "source_name", "location_text", "next_action", "status_note")
    @classmethod
    def _sanitize_short_texts(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=255)

    @field_validator("personal_summary", "notes")
    @classmethod
    def _sanitize_long_texts(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=10000)

    @field_validator(
        "applied_at",
        "interview_at",
        "assessment_deadline_at",
        "expected_response_at",
        "next_action_due_at",
    )
    @classmethod
    def _normalize_dates(cls, value: datetime | None) -> datetime | None:
        return _normalize_optional_dt(value)

    @model_validator(mode="after")
    def _require_role_when_manual(self) -> "ApplicationCreate":
        if self.opportunity_id is None and not (self.role_title and self.role_title.strip()):
            raise ValueError(
                "Informe o título do cargo ao cadastrar uma candidatura manualmente sem oportunidade vinculada."
            )
        return self


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_title: str | None = Field(default=None, min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    personal_summary: str | None = Field(default=None, max_length=8000)
    source_name: str | None = Field(default=None, max_length=150)
    source_url: str | None = Field(default=None, max_length=1000)
    application_url: str | None = Field(default=None, max_length=1000)
    location_text: str | None = Field(default=None, max_length=255)
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    seniority_level: SeniorityLevel | None = None
    applied_at: datetime | None = None
    interview_at: datetime | None = None
    assessment_deadline_at: datetime | None = None
    expected_response_at: datetime | None = None
    next_action: str | None = Field(default=None, max_length=255)
    next_action_due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10000)

    @field_validator("source_url", "application_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("role_title", "company_name", "source_name", "location_text", "next_action")
    @classmethod
    def _sanitize_short_texts(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=255)

    @field_validator("personal_summary", "notes")
    @classmethod
    def _sanitize_long_texts(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=10000)

    @field_validator(
        "applied_at",
        "interview_at",
        "assessment_deadline_at",
        "expected_response_at",
        "next_action_due_at",
    )
    @classmethod
    def _normalize_dates(cls, value: datetime | None) -> datetime | None:
        return _normalize_optional_dt(value)


class ApplicationStatusChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=500)
    applied_at: datetime | None = None
    interview_at: datetime | None = None
    assessment_deadline_at: datetime | None = None
    expected_response_at: datetime | None = None
    next_action: str | None = Field(default=None, max_length=255)
    next_action_due_at: datetime | None = None

    @field_validator("note")
    @classmethod
    def _sanitize_note(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=500)

    @field_validator("next_action")
    @classmethod
    def _sanitize_next_action(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=255)

    @field_validator(
        "applied_at",
        "interview_at",
        "assessment_deadline_at",
        "expected_response_at",
        "next_action_due_at",
    )
    @classmethod
    def _normalize_dates(cls, value: datetime | None) -> datetime | None:
        return _normalize_optional_dt(value)


class ApplicationStatusHistoryResponse(BaseModel):
    id: uuid.UUID
    from_status: ApplicationStatus | str | None = None
    from_status_label: str | None = None
    to_status: ApplicationStatus | str
    to_status_label: str
    note: str | None = None
    changed_at: datetime


class ApplicationInterviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_name: str = Field(..., min_length=2, max_length=100)
    interview_format: InterviewFormat = InterviewFormat.ONLINE
    scheduled_at: datetime
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    meeting_url: str | None = Field(default=None, max_length=1000)
    interviewers: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=8000)
    feedback_received: str | None = Field(default=None, max_length=8000)
    status: InterviewStatus = InterviewStatus.SCHEDULED
    completed_at: datetime | None = None

    @field_validator("round_name", "interviewers")
    @classmethod
    def _sanitize_short(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_plain_text(value, max_length=500)
        return cleaned

    @field_validator("round_name")
    @classmethod
    def _validate_round_name(cls, value: str) -> str:
        cleaned = sanitize_plain_text(value, max_length=100)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Informe o nome da rodada de entrevista.")
        return cleaned

    @field_validator("notes", "feedback_received")
    @classmethod
    def _sanitize_notes(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=8000)

    @field_validator("meeting_url")
    @classmethod
    def _validate_meeting_url(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("scheduled_at")
    @classmethod
    def _validate_scheduled_at(cls, value: datetime) -> datetime:
        checked = _require_tz_aware_dt(value, field_label="scheduled_at")
        assert checked is not None
        return checked

    @field_validator("completed_at")
    @classmethod
    def _validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="completed_at")


class ApplicationInterviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_name: str | None = Field(default=None, min_length=2, max_length=100)
    interview_format: InterviewFormat | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    meeting_url: str | None = Field(default=None, max_length=1000)
    interviewers: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=8000)
    feedback_received: str | None = Field(default=None, max_length=8000)
    status: InterviewStatus | None = None
    completed_at: datetime | None = None

    @field_validator("round_name")
    @classmethod
    def _validate_round_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_plain_text(value, max_length=100)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Nome da rodada inválido.")
        return cleaned

    @field_validator("interviewers")
    @classmethod
    def _sanitize_interviewers(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=500)

    @field_validator("notes", "feedback_received")
    @classmethod
    def _sanitize_notes(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=8000)

    @field_validator("meeting_url")
    @classmethod
    def _validate_meeting_url(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("scheduled_at")
    @classmethod
    def _validate_scheduled_at(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="scheduled_at")

    @field_validator("completed_at")
    @classmethod
    def _validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="completed_at")


class ApplicationInterviewResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    round_name: str
    interview_format: InterviewFormat | str
    interview_format_label: str
    scheduled_at: datetime
    previous_scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    meeting_url: str | None = None
    interviewers: str | None = None
    notes: str | None = None
    feedback_received: str | None = None
    status: InterviewStatus | str
    status_label: str
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=8000)
    platform: str | None = Field(default=None, max_length=100)
    instructions_url: str | None = Field(default=None, max_length=1000)
    submission_url: str | None = Field(default=None, max_length=1000)
    deadline_at: datetime | None = None
    submitted_at: datetime | None = None
    status: AssessmentStatus = AssessmentStatus.PENDING
    feedback: str | None = Field(default=None, max_length=8000)
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = sanitize_plain_text(value, max_length=150)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Informe o título do desafio técnico.")
        return cleaned

    @field_validator("platform")
    @classmethod
    def _sanitize_platform(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=100)

    @field_validator("description", "feedback", "notes")
    @classmethod
    def _sanitize_long(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=8000)

    @field_validator("instructions_url", "submission_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("deadline_at")
    @classmethod
    def _validate_deadline(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="deadline_at")

    @field_validator("submitted_at")
    @classmethod
    def _validate_submitted(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="submitted_at")


class ApplicationAssessmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=8000)
    platform: str | None = Field(default=None, max_length=100)
    instructions_url: str | None = Field(default=None, max_length=1000)
    submission_url: str | None = Field(default=None, max_length=1000)
    deadline_at: datetime | None = None
    submitted_at: datetime | None = None
    status: AssessmentStatus | None = None
    feedback: str | None = Field(default=None, max_length=8000)
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_plain_text(value, max_length=150)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Título do desafio inválido.")
        return cleaned

    @field_validator("platform")
    @classmethod
    def _sanitize_platform(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=100)

    @field_validator("description", "feedback", "notes")
    @classmethod
    def _sanitize_long(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=8000)

    @field_validator("instructions_url", "submission_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("deadline_at")
    @classmethod
    def _validate_deadline(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="deadline_at")

    @field_validator("submitted_at")
    @classmethod
    def _validate_submitted(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware_dt(value, field_label="submitted_at")


class ApplicationAssessmentResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    title: str
    description: str | None = None
    platform: str | None = None
    instructions_url: str | None = None
    submission_url: str | None = None
    deadline_at: datetime | None = None
    submitted_at: datetime | None = None
    status: AssessmentStatus | str
    status_label: str
    is_overdue: bool = False
    is_due_soon_24h: bool = False
    feedback: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=150)
    role_title: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    linkedin_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("email", mode="before")
    @classmethod
    def _clean_blank_email(cls, value: object) -> object:
        return _blank_str_to_none(value)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = sanitize_plain_text(value, max_length=150)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Informe o nome completo do contato.")
        return cleaned

    @field_validator("role_title")
    @classmethod
    def _sanitize_role(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=100)

    @field_validator("linkedin_url")
    @classmethod
    def _validate_linkedin(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=4000)


class ApplicationContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=150)
    role_title: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    linkedin_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("email", mode="before")
    @classmethod
    def _clean_blank_email(cls, value: object) -> object:
        return _blank_str_to_none(value)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_plain_text(value, max_length=150)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Nome do contato inválido.")
        return cleaned

    @field_validator("role_title")
    @classmethod
    def _sanitize_role(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=100)

    @field_validator("linkedin_url")
    @classmethod
    def _validate_linkedin(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=4000)


class ApplicationContactResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    name: str
    role_title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ExternalInteractionRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_type: ExternalInteractionType = ExternalInteractionType.EMAIL
    interaction_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("interaction_at")
    @classmethod
    def _validate_interaction_at(cls, value: datetime | None) -> datetime | None:
        checked = _require_tz_aware_dt(value, field_label="interaction_at")
        if checked is not None and checked > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError(
                "A data da interação externa registrada não pode estar no futuro."
            )
        return checked

    @field_validator("note")
    @classmethod
    def _sanitize_note(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value, max_length=1000)


class AgendaEventResponse(BaseModel):
    id: str
    event_type: Literal["interview", "assessment", "next_action", "expected_response"]
    source_kind: Literal["structured", "legacy"]
    entity_id: uuid.UUID
    application_id: uuid.UUID
    company_name: str | None = None
    role_title: str
    application_status: ApplicationStatus | str
    application_status_label: str
    title: str
    subtitle: str | None = None
    scheduled_at: datetime
    status: str
    status_label: str
    is_overdue: bool
    is_today: bool
    is_imminent: bool
    urgency: Literal["overdue", "imminent", "upcoming"]
    action_url: str | None = None


class AgendaSummaryResponse(BaseModel):
    total_count: int
    overdue_count: int
    imminent_24h_count: int
    today_count: int
    interviews_count: int
    assessments_count: int
    actions_count: int
    reference_now_utc: datetime


class ApplicationAgendaResponse(BaseModel):
    days: int
    summary: AgendaSummaryResponse
    events: list[AgendaEventResponse] = Field(default_factory=list)


class StaleApplicationItemResponse(BaseModel):
    application_id: uuid.UUID
    company_name: str | None = None
    role_title: str
    status: ApplicationStatus | str
    status_label: str
    last_external_interaction_at: datetime | None = None
    reference_timestamp_at: datetime
    reference_kind: Literal["external_interaction", "completed_interview", "applied_at"]
    reference_description: str
    days_without_external_interaction: int
    threshold_days: int
    notice: str
    recommended_follow_up: str


class StaleApplicationsResponse(BaseModel):
    stale_days_param: int
    total_count: int
    items: list[StaleApplicationItemResponse] = Field(default_factory=list)


class FollowUpTemplateResponse(BaseModel):
    application_id: uuid.UUID
    subject: str
    message: str
    recipient_name: str | None = None
    recipient_email: str | None = None
    context_summary: str
    used_facts: list[str] = Field(default_factory=list)
    disclaimer: str


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    opportunity_source_status: str | None = None
    company_name: str | None = None
    role_title: str
    personal_summary: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    application_url: str | None = None
    location_text: str | None = None
    employment_type: EmploymentType | str = EmploymentType.UNKNOWN.value
    work_mode: WorkMode | str = WorkMode.UNKNOWN.value
    seniority_level: SeniorityLevel | str = SeniorityLevel.UNKNOWN.value
    status: ApplicationStatus | str
    status_label: str
    is_closed: bool
    applied_at: datetime | None = None
    interview_at: datetime | None = None
    assessment_deadline_at: datetime | None = None
    expected_response_at: datetime | None = None
    next_action: str | None = None
    next_action_due_at: datetime | None = None
    next_deadline_at: datetime | None = None
    next_deadline_label: str | None = None
    notes: str | None = None
    closed_at: datetime | None = None
    last_external_interaction_at: datetime | None = None
    last_external_interaction_type: ExternalInteractionType | str | None = None
    last_external_interaction_type_label: str | None = None
    last_external_interaction_note: str | None = None
    created_at: datetime
    updated_at: datetime
    status_history: list[ApplicationStatusHistoryResponse] = Field(default_factory=list)
    interviews: list[ApplicationInterviewResponse] = Field(default_factory=list)
    assessments: list[ApplicationAssessmentResponse] = Field(default_factory=list)
    contacts: list[ApplicationContactResponse] = Field(default_factory=list)


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ApplicationIndicatorsResponse(BaseModel):
    total_count: int
    active_count: int
    applied_count: int
    assessment_count: int
    interview_count: int
    offer_count: int
    accepted_count: int
    rejected_count: int
    withdrawn_count: int
    closed_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class ApplicationKanbanColumnResponse(BaseModel):
    status: ApplicationStatus | str
    label: str
    is_closed: bool
    count: int
    items: list[ApplicationResponse] = Field(default_factory=list)


class ApplicationKanbanResponse(BaseModel):
    columns: list[ApplicationKanbanColumnResponse]
    closed_columns: list[ApplicationKanbanColumnResponse]
    closed_items: list[ApplicationResponse]
    indicators: ApplicationIndicatorsResponse
    labels: dict[str, str]


ApplicationSortOption = Literal["updated_desc", "created_desc", "deadline_asc"]
