import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.application import ApplicationStatus
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
    created_at: datetime
    updated_at: datetime
    status_history: list[ApplicationStatusHistoryResponse] = Field(default_factory=list)


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
