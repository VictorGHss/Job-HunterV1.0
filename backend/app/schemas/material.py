import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.material import MaterialType, MaterialVersionOrigin
from app.services.opportunities.sanitization import (
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)

TargetLanguage = Literal["pt-BR", "en"]
BlockProvenance = Literal["confirmed_fact", "manual_edit", "user_authored"]
ExportFormat = Literal["markdown", "text"]


def _sanitize_short(value: str | None, max_len: int = 255) -> str | None:
    return sanitize_plain_text(value, max_length=max_len)


def _sanitize_long(value: str | None, max_len: int = 4000) -> str | None:
    return sanitize_external_html_text(value, max_length=max_len)


def _validate_optional_url(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return validate_safe_external_url(str(value), allow_localhost=False)


class ContactInclusionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_email: bool = True
    include_phone: bool = False
    include_location: bool = True
    include_links: bool = True


class ResumeLinkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=80)
    url: str = Field(..., min_length=8, max_length=1000)

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: str) -> str:
        cleaned = _sanitize_short(value, 80)
        if not cleaned:
            raise ValueError("Rótulo do link não pode ficar vazio.")
        return cleaned

    @field_validator("url")
    @classmethod
    def _clean_url(cls, value: str) -> str:
        return validate_safe_external_url(value, allow_localhost=False)


class ResumeHeaderSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    professional_title: str | None = Field(default=None, max_length=200)
    location_text: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    links: list[ResumeLinkItem] = Field(default_factory=list, max_length=10)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("full_name", "professional_title", "location_text", "email", "phone")
    @classmethod
    def _clean_fields(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 255)


class ResumeSummarySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=3000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=50)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 3000)
        if not cleaned:
            raise ValueError("Resumo não pode ficar vazio.")
        return cleaned


class ResumeTargetAlignmentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_role: str = Field(..., min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    highlighted_requirements: list[str] = Field(default_factory=list, max_length=30)
    alignment_note: str | None = Field(default=None, max_length=1000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=50)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("target_role", "company_name")
    @classmethod
    def _clean_short(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 255)

    @field_validator("alignment_note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1000)

    @field_validator("highlighted_requirements")
    @classmethod
    def _clean_reqs(cls, values: list[str]) -> list[str]:
        return [c for v in values if (c := _sanitize_short(v, 100))]


class ResumeExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    company: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    period_label: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    experience_type: str = Field(default="other", max_length=64)
    eligible_as_target_role: bool = False
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("company", "role", "period_label", "experience_type")
    @classmethod
    def _clean_short(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 200)

    @field_validator("description")
    @classmethod
    def _clean_desc(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 4000)

    @field_validator("technologies")
    @classmethod
    def _clean_techs(cls, values: list[str]) -> list[str]:
        return [c for v in values if (c := _sanitize_short(v, 80))]


class ResumeProjectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    links: list[ResumeLinkItem] = Field(default_factory=list, max_length=10)
    verified_results: str | None = Field(default=None, max_length=2000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("name", "role")
    @classmethod
    def _clean_short(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 200)

    @field_validator("description", "verified_results")
    @classmethod
    def _clean_long(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 4000)

    @field_validator("technologies")
    @classmethod
    def _clean_techs(cls, values: list[str]) -> list[str]:
        return [c for v in values if (c := _sanitize_short(v, 80))]


class ResumeEducationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    institution: str = Field(..., min_length=1, max_length=200)
    course: str = Field(..., min_length=1, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    education_status: str = Field(..., max_length=64)
    status_label: str = Field(..., max_length=80)
    current_semester: str | None = Field(default=None, max_length=80)
    period_label: str | None = Field(default=None, max_length=120)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator(
        "institution",
        "course",
        "field_of_study",
        "education_status",
        "status_label",
        "current_semester",
        "period_label",
    )
    @classmethod
    def _clean_short(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 200)


class ResumeSkillItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=150)
    category: str = Field(..., min_length=1, max_length=100)
    proficiency_level: str = Field(..., max_length=64)
    proficiency_label: str = Field(..., max_length=80)
    notes: str | None = Field(default=None, max_length=1000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("name", "category", "proficiency_level", "proficiency_label")
    @classmethod
    def _clean_short(cls, value: str) -> str:
        cleaned = _sanitize_short(value, 150)
        if not cleaned:
            raise ValueError("Campo obrigatório inválido.")
        return cleaned

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1000)


class ResumeLanguageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    language_name: str = Field(..., min_length=1, max_length=100)
    proficiency_level: str = Field(..., max_length=64)
    proficiency_label: str = Field(..., max_length=80)
    cefr_level: str | None = Field(default=None, max_length=16)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("language_name", "proficiency_level", "proficiency_label", "cefr_level")
    @classmethod
    def _clean_short(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 100)


class ResumeManualNoteItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=150)
    content: str = Field(..., min_length=1, max_length=2000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=10)
    provenance: BlockProvenance = "user_authored"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        cleaned = _sanitize_short(value, 150)
        if not cleaned:
            raise ValueError("Título do bloco manual inválido.")
        return cleaned

    @field_validator("content")
    @classmethod
    def _clean_content(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 2000)
        if not cleaned:
            raise ValueError("Conteúdo do bloco manual inválido.")
        return cleaned


class ResumeStructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    language: TargetLanguage = "pt-BR"
    header: ResumeHeaderSection
    summary: ResumeSummarySection | None = None
    target_alignment: ResumeTargetAlignmentSection | None = None
    experiences: list[ResumeExperienceItem] = Field(default_factory=list, max_length=30)
    projects: list[ResumeProjectItem] = Field(default_factory=list, max_length=30)
    education: list[ResumeEducationItem] = Field(default_factory=list, max_length=20)
    skills: list[ResumeSkillItem] = Field(default_factory=list, max_length=80)
    languages: list[ResumeLanguageItem] = Field(default_factory=list, max_length=20)
    manual_notes: list[ResumeManualNoteItem] = Field(default_factory=list, max_length=10)
    has_unverified_manual_edits: bool = False


class OpportunityContextInfo(BaseModel):
    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    title: str | None = None
    company_name: str | None = None
    professional_area: str | None = None
    seniority_level: str | None = None
    experience_summary: str | None = None
    required_technologies: list[str] = Field(default_factory=list)
    desirable_technologies: list[str] = Field(default_factory=list)
    all_technologies: list[str] = Field(default_factory=list)
    language: str | None = None


class SelectedFactReference(BaseModel):
    fact_key: str
    entity_type: Literal["profile", "experience", "project", "education", "skill", "language"]
    entity_id: uuid.UUID
    confirmed_at: datetime | None = None
    label: str
    summary: str
    relevance_score: int = 0
    matched_requirements: list[str] = Field(default_factory=list)
    eligible_as_target_role: bool | None = None


class UnconfirmedWarningItem(BaseModel):
    entity_type: Literal["profile", "experience", "project", "education", "skill", "language"]
    entity_id: uuid.UUID
    verification_status: Literal["pending_validation", "draft"]
    label: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    reason: str
    matched_requirements: list[str] = Field(default_factory=list)
    can_batch_confirm: bool = False


class MissingRequirementItem(BaseModel):
    requirement: str
    requirement_kind: Literal["required_technology", "desirable_technology", "general_technology", "seniority_or_area"]
    note: str
    covered_by_unconfirmed: bool = False


class ContactPreviewInfo(BaseModel):
    profile_confirmed: bool
    has_full_name: bool
    has_email: bool
    has_phone: bool
    has_location: bool
    links_count: int
    location_label: str | None = None


class MaterialPreAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    target_language: TargetLanguage = "pt-BR"
    contact_options: ContactInclusionOptions = Field(
        default_factory=ContactInclusionOptions
    )


class MaterialPreAnalysisResponse(BaseModel):
    can_generate: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    target_language: TargetLanguage
    opportunity_context: OpportunityContextInfo
    contact_preview: ContactPreviewInfo
    used_facts: list[SelectedFactReference] = Field(default_factory=list)
    unconfirmed_warnings: list[UnconfirmedWarningItem] = Field(default_factory=list)
    missing_requirements: list[MissingRequirementItem] = Field(default_factory=list)
    confirmed_counts: dict[str, int] = Field(default_factory=dict)


class MaterialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    material_type: Literal["resume"] = MaterialType.RESUME.value
    title: str | None = Field(default=None, min_length=2, max_length=200)
    target_language: TargetLanguage = "pt-BR"
    contact_options: ContactInclusionOptions = Field(
        default_factory=ContactInclusionOptions
    )
    user_instructions: str | None = Field(default=None, max_length=1500)

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 200)

    @field_validator("user_instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class MaterialVersionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_content: ResumeStructuredContent
    user_instructions: str | None = Field(default=None, max_length=1500)

    @field_validator("user_instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class MaterialVersionDeriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_content: ResumeStructuredContent | None = None
    user_instructions: str | None = Field(default=None, max_length=1500)

    @field_validator("user_instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class MaterialRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_language: TargetLanguage | None = None
    contact_options: ContactInclusionOptions = Field(
        default_factory=ContactInclusionOptions
    )
    user_instructions: str | None = Field(default=None, max_length=1500)

    @field_validator("user_instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class MaterialLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: uuid.UUID
    version_id: uuid.UUID


class MaterialUnlinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: uuid.UUID


class MaterialLinkResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    application_role_title: str | None = None
    application_company_name: str | None = None
    material_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    linked_at: datetime
    unlinked_at: datetime | None = None
    is_active: bool


class MaterialVersionResponse(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    version_number: int
    origin: MaterialVersionOrigin | str
    parent_version_id: uuid.UUID | None = None
    user_instructions: str | None = None
    structured_content: ResumeStructuredContent
    source_facts_snapshot: dict[str, Any]
    unconfirmed_warnings: list[UnconfirmedWarningItem] = Field(default_factory=list)
    missing_requirements: list[MissingRequirementItem] = Field(default_factory=list)
    rendered_markdown: str
    is_approved: bool
    approved_at: datetime | None = None
    is_linked_to_any_application: bool = False
    is_mutable: bool = True
    created_at: datetime
    updated_at: datetime


class MaterialResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    opportunity_title: str | None = None
    opportunity_company_name: str | None = None
    material_type: str
    title: str
    target_language: TargetLanguage | str
    latest_version_number: int
    has_approved_version: bool
    versions: list[MaterialVersionResponse] = Field(default_factory=list)
    links: list[MaterialLinkResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MaterialSummaryResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    opportunity_title: str | None = None
    opportunity_company_name: str | None = None
    material_type: str
    title: str
    target_language: str
    latest_version_number: int
    latest_version_id: uuid.UUID | None = None
    latest_is_approved: bool = False
    has_approved_version: bool = False
    active_links_count: int = 0
    created_at: datetime
    updated_at: datetime


class MaterialExportResponse(BaseModel):
    material_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    format: ExportFormat
    filename_suggestion: str
    content: str
    is_approved: bool
