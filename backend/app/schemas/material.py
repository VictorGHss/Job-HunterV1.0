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
MaterialTypeValue = Literal[
    "resume",
    "cover_letter",
    "recruiter_message",
    "freelance_proposal",
    "application_answers",
]
RecruiterChannel = Literal["linkedin", "email", "contact_form"]


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


class WritingTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=4000)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=50)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 4000)
        if not cleaned:
            raise ValueError("Texto do bloco não pode ficar vazio.")
        return cleaned


class WritingEvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=64)
    entity_type: Literal["experience", "project", "education", "skill", "language", "profile"] | None = None
    title: str = Field(..., min_length=1, max_length=255)
    summary_text: str = Field(..., min_length=1, max_length=4000)
    matched_requirements: list[str] = Field(default_factory=list, max_length=30)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        cleaned = _sanitize_short(value, 255)
        if not cleaned:
            raise ValueError("Título do bloco de evidência inválido.")
        return cleaned

    @field_validator("summary_text")
    @classmethod
    def _clean_summary(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 4000)
        if not cleaned:
            raise ValueError("Descrição do bloco de evidência inválida.")
        return cleaned

    @field_validator("matched_requirements")
    @classmethod
    def _clean_reqs(cls, values: list[str]) -> list[str]:
        return [c for v in values if (c := _sanitize_short(v, 100))]


class PendingUserInputField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=150)
    question: str = Field(..., min_length=1, max_length=500)
    required: bool = True
    status: Literal["pending", "provided"] = "pending"
    user_value: str | None = Field(default=None, max_length=2000)

    @field_validator("field_id", "label")
    @classmethod
    def _clean_short(cls, value: str) -> str:
        cleaned = _sanitize_short(value, 150)
        if not cleaned:
            raise ValueError("Identificador/rótulo de campo pendente inválido.")
        return cleaned

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 500)
        if not cleaned:
            raise ValueError("Pergunta complementar inválida.")
        return cleaned

    @field_validator("user_value")
    @classmethod
    def _clean_value(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 2000)

    @model_validator(mode="after")
    def _sync_status(self) -> "PendingUserInputField":
        if self.user_value and self.user_value.strip():
            self.status = "provided"
        else:
            self.user_value = None
            self.status = "pending"
        return self


class CoverLetterStructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    material_type: Literal["cover_letter"] = "cover_letter"
    language: TargetLanguage = "pt-BR"
    header: ResumeHeaderSection
    recipient_line: WritingTextBlock
    greeting: WritingTextBlock
    opening: WritingTextBlock
    relevance_highlights: list[WritingEvidenceBlock] = Field(default_factory=list, max_length=10)
    opportunity_alignment: WritingTextBlock | None = None
    closing: WritingTextBlock
    manual_notes: list[ResumeManualNoteItem] = Field(default_factory=list, max_length=10)
    has_unverified_manual_edits: bool = False


class RecruiterMessageStructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    material_type: Literal["recruiter_message"] = "recruiter_message"
    language: TargetLanguage = "pt-BR"
    channel: RecruiterChannel = "linkedin"
    subject: WritingTextBlock | None = None
    greeting: WritingTextBlock
    body: WritingTextBlock
    sign_off: WritingTextBlock
    character_count: int = Field(default=0, ge=0)
    manual_notes: list[ResumeManualNoteItem] = Field(default_factory=list, max_length=10)
    has_unverified_manual_edits: bool = False


class FreelanceProposalStructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    material_type: Literal["freelance_proposal"] = "freelance_proposal"
    language: TargetLanguage = "pt-BR"
    header: ResumeHeaderSection
    introduction: WritingTextBlock
    project_understanding: WritingTextBlock
    relevant_evidence: list[WritingEvidenceBlock] = Field(default_factory=list, max_length=10)
    suggested_approach: WritingTextBlock
    alignment_points: WritingTextBlock
    pending_fields: list[PendingUserInputField] = Field(default_factory=list, max_length=15)
    closing: WritingTextBlock
    manual_notes: list[ResumeManualNoteItem] = Field(default_factory=list, max_length=10)
    has_unverified_manual_edits: bool = False


class ApplicationAnswerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1, max_length=64)
    question: str = Field(..., min_length=3, max_length=500)
    question_kind: Literal[
        "technical_experience",
        "project_example",
        "education",
        "language",
        "motivation",
        "compensation",
        "availability",
        "general_personal",
    ] = "general_personal"
    answer_text: str | None = Field(default=None, max_length=4000)
    requires_user_input: bool = False
    status: Literal["answered_from_facts", "needs_user_input", "user_answered"] = "needs_user_input"
    follow_up_prompt: str | None = Field(default=None, max_length=500)
    source_fact_keys: list[str] = Field(default_factory=list, max_length=30)
    evidence_notes: list[str] = Field(default_factory=list, max_length=20)
    provenance: BlockProvenance = "confirmed_fact"

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 500)
        if not cleaned or len(cleaned) < 3:
            raise ValueError("Pergunta de candidatura deve ter ao menos 3 caracteres.")
        return cleaned

    @field_validator("answer_text", "follow_up_prompt")
    @classmethod
    def _clean_answer_or_prompt(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 4000)

    @field_validator("evidence_notes")
    @classmethod
    def _clean_evidence(cls, values: list[str]) -> list[str]:
        return [c for v in values if (c := _sanitize_short(v, 255))]


class ApplicationAnswersStructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    material_type: Literal["application_answers"] = "application_answers"
    language: TargetLanguage = "pt-BR"
    items: list[ApplicationAnswerItem] = Field(..., min_length=1, max_length=20)
    manual_notes: list[ResumeManualNoteItem] = Field(default_factory=list, max_length=10)
    has_unverified_manual_edits: bool = False


AnyMaterialStructuredContent = (
    ResumeStructuredContent
    | CoverLetterStructuredContent
    | RecruiterMessageStructuredContent
    | FreelanceProposalStructuredContent
    | ApplicationAnswersStructuredContent
)


class FreelanceInputsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: str | None = Field(default=None, max_length=500)
    estimated_delivery: str | None = Field(default=None, max_length=500)
    budget_or_price: str | None = Field(default=None, max_length=500)
    scope_clarifications: str | None = Field(default=None, max_length=1500)
    additional_requirements: str | None = Field(default=None, max_length=1500)

    @field_validator(
        "availability",
        "estimated_delivery",
        "budget_or_price",
        "scope_clarifications",
        "additional_requirements",
    )
    @classmethod
    def _clean_field(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class ApplicationAnswerUserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=3, max_length=500)
    user_answer: str | None = Field(default=None, max_length=4000)

    @field_validator("question")
    @classmethod
    def _clean_q(cls, value: str) -> str:
        cleaned = _sanitize_long(value, 500)
        if not cleaned or len(cleaned) < 3:
            raise ValueError("Pergunta inválida.")
        return cleaned

    @field_validator("user_answer")
    @classmethod
    def _clean_a(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 4000)


class WritingGenerationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: RecruiterChannel = "linkedin"
    contact_name: str | None = Field(default=None, max_length=150)
    contact_context: str | None = Field(default=None, max_length=1000)
    freelance_inputs: FreelanceInputsPayload = Field(default_factory=FreelanceInputsPayload)
    questions: list[str] = Field(default_factory=list, max_length=20)
    initial_answers: list[ApplicationAnswerUserInput] = Field(default_factory=list, max_length=20)

    @field_validator("contact_name")
    @classmethod
    def _clean_contact_name(cls, value: str | None) -> str | None:
        return _sanitize_short(value, 150)

    @field_validator("contact_context")
    @classmethod
    def _clean_contact_context(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1000)

    @field_validator("questions")
    @classmethod
    def _clean_questions(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            item = _sanitize_long(raw, 500)
            if item and len(item) >= 3:
                cleaned.append(item)
        return cleaned


class OpportunityContextInfo(BaseModel):
    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    title: str | None = None
    company_name: str | None = None
    professional_area: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None
    opportunity_type: str | None = None
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
    material_type: MaterialTypeValue = MaterialType.RESUME.value
    target_language: TargetLanguage = "pt-BR"
    contact_options: ContactInclusionOptions = Field(
        default_factory=ContactInclusionOptions
    )
    writing_options: WritingGenerationOptions = Field(
        default_factory=WritingGenerationOptions
    )


class MaterialPreAnalysisResponse(BaseModel):
    can_generate: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    material_type: MaterialTypeValue = MaterialType.RESUME.value
    compatible_material_types: list[MaterialTypeValue] = Field(
        default_factory=lambda: [
            "resume",
            "cover_letter",
            "recruiter_message",
            "application_answers",
        ]
    )
    target_language: TargetLanguage
    opportunity_context: OpportunityContextInfo
    contact_preview: ContactPreviewInfo
    used_facts: list[SelectedFactReference] = Field(default_factory=list)
    unconfirmed_warnings: list[UnconfirmedWarningItem] = Field(default_factory=list)
    missing_requirements: list[MissingRequirementItem] = Field(default_factory=list)
    additional_info_needed: list[PendingUserInputField] = Field(default_factory=list)
    confirmed_counts: dict[str, int] = Field(default_factory=dict)


class MaterialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    material_type: MaterialTypeValue = MaterialType.RESUME.value
    title: str | None = Field(default=None, min_length=2, max_length=200)
    target_language: TargetLanguage = "pt-BR"
    contact_options: ContactInclusionOptions = Field(
        default_factory=ContactInclusionOptions
    )
    writing_options: WritingGenerationOptions = Field(
        default_factory=WritingGenerationOptions
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

    structured_content: dict[str, Any]
    user_instructions: str | None = Field(default=None, max_length=1500)

    @field_validator("user_instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        return _sanitize_long(value, 1500)


class MaterialVersionDeriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_content: dict[str, Any] | None = None
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
    writing_options: WritingGenerationOptions | None = None
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
    material_type: MaterialTypeValue | str = MaterialType.RESUME.value
    version_number: int
    origin: MaterialVersionOrigin | str
    parent_version_id: uuid.UUID | None = None
    user_instructions: str | None = None
    structured_content: AnyMaterialStructuredContent
    source_facts_snapshot: dict[str, Any]
    unconfirmed_warnings: list[UnconfirmedWarningItem] = Field(default_factory=list)
    missing_requirements: list[MissingRequirementItem] = Field(default_factory=list)
    rendered_markdown: str
    rendered_plain_text: str = ""
    has_blocking_pending_fields: bool = False
    pending_requirements_count: int = 0
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
