import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    SourceType,
    SyncRunStatus,
    WorkMode,
)
from app.services.opportunities.sanitization import (
    normalize_string_list,
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)


class OpportunitySourcePublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    source_type: SourceType | str
    base_url: str
    terms_url: str
    attribution_text: str
    enabled: bool
    refresh_interval_seconds: int
    last_synced_at: datetime | None = None
    last_success_at: datetime | None = None


class OpportunityUserStateResponse(BaseModel):
    is_saved: bool = False
    is_dismissed: bool = False
    last_viewed_at: datetime | None = None


class OpportunityMatchEvaluation(BaseModel):
    eligible: bool
    geographic_eligibility: Literal["eligible", "excluded", "unknown"]
    inclusion_reasons: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    is_manual: bool
    external_id: str | None = None
    title: str
    company_name: str | None = None
    description: str | None = None
    opportunity_type: OpportunityType | str
    employment_type: EmploymentType | str
    work_mode: WorkMode | str
    location_text: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    eligible_countries: list[str] = Field(default_factory=list)
    eligibility_unknown: bool = False
    language: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    requirements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    source_url: str
    application_url: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    source_status: ExternalSourceStatus | str
    first_seen_at: datetime
    last_seen_at: datetime
    source: OpportunitySourcePublicResponse | None = None
    user_state: OpportunityUserStateResponse
    match: OpportunityMatchEvaluation


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ManualOpportunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=15000)
    opportunity_type: OpportunityType = OpportunityType.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    work_mode: WorkMode = WorkMode.UNKNOWN
    location_text: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    eligible_countries: list[str] = Field(default_factory=list)
    eligibility_unknown: bool | None = None
    language: str | None = Field(default=None, max_length=64)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=16)
    salary_period: str | None = Field(default=None, max_length=32)
    requirements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    source_url: str = Field(min_length=8, max_length=1000)
    application_url: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = sanitize_plain_text(value, max_length=255)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Título válido é obrigatório.")
        return cleaned

    @field_validator("company_name", "location_text", "city", "state", "country", "language", "salary_currency", "salary_period")
    @classmethod
    def clean_optional_strings(cls, value: str | None) -> str | None:
        return sanitize_plain_text(value, max_length=255)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value)

    @field_validator("eligible_countries", "requirements", "technologies")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return normalize_string_list(value)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return validate_safe_external_url(value)

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_safe_external_url(value)


class ManualOpportunityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=15000)
    opportunity_type: OpportunityType | None = None
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    location_text: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=120)
    eligible_countries: list[str] | None = None
    source_status: ExternalSourceStatus | None = None
    technologies: list[str] | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    application_url: str | None = Field(default=None, max_length=1000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_plain_text(value, max_length=255)
        if not cleaned or len(cleaned) < 2:
            raise ValueError("Título válido é obrigatório.")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return sanitize_external_html_text(value)

    @field_validator("source_url", "application_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_safe_external_url(value)


class OpportunityUserStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_saved: bool | None = None
    is_dismissed: bool | None = None
    mark_viewed: bool = False


class SyncRunSummary(BaseModel):
    source_slug: str
    status: SyncRunStatus | str
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_summary: str | None = None
