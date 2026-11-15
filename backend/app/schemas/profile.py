import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator, model_validator

from app.models.profile import (
    EducationStatus,
    ExperienceType,
    LanguageProficiency,
    SkillProficiency,
    VerificationStatus,
)

email_adapter = TypeAdapter(EmailStr)
VALID_CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


def clean_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def validate_optional_url(value: str | None) -> str | None:
    cleaned = clean_optional_str(value)
    if cleaned is None:
        return None
    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", cleaned, re.IGNORECASE):
        raise ValueError("URL inválida. Utilize o formato completo iniciando com http:// ou https://.")
    return cleaned


def clean_string_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = item.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)
    return result


class InternshipPreferencesSchema(BaseModel):
    enabled: bool = True
    priority_areas: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    excluded_areas: list[str] = Field(default_factory=list)

    @field_validator("priority_areas", "preferred_languages", "excluded_areas")
    @classmethod
    def clean_lists(cls, v: list[str]) -> list[str]:
        return clean_string_list(v)


class JuniorDeveloperPreferencesSchema(BaseModel):
    enabled: bool = True
    priority_areas: list[str] = Field(default_factory=list)
    block_clt: bool = False
    accepted_contract_types: list[str] = Field(default_factory=list)
    excluded_areas: list[str] = Field(default_factory=list)

    @field_validator("priority_areas", "accepted_contract_types", "excluded_areas")
    @classmethod
    def clean_lists(cls, v: list[str]) -> list[str]:
        return clean_string_list(v)


class FreelancePreferencesSchema(BaseModel):
    enabled: bool = True
    scopes: list[str] = Field(default_factory=list)
    priority_categories: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)

    @field_validator("scopes", "priority_categories", "preferred_languages")
    @classmethod
    def clean_lists(cls, v: list[str]) -> list[str]:
        return clean_string_list(v)


class SourceRestrictionsSchema(BaseModel):
    workana_enabled: bool = True
    workana_disabled_reason: str = ""
    gupy_mode: Literal["disabled", "selective_high_compatibility", "enabled"] = (
        "selective_high_compatibility"
    )
    auto_execute_tests: bool = False
    pay_premium_or_fees_without_approval: bool = False
    strict_platform_terms_compliance: bool = True


class CareerPreferencesSchema(BaseModel):
    internships: InternshipPreferencesSchema = Field(default_factory=InternshipPreferencesSchema)
    junior_developer: JuniorDeveloperPreferencesSchema = Field(
        default_factory=JuniorDeveloperPreferencesSchema
    )
    freelance: FreelancePreferencesSchema = Field(default_factory=FreelancePreferencesSchema)
    source_restrictions: SourceRestrictionsSchema = Field(default_factory=SourceRestrictionsSchema)


class ProfessionalProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    professional_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    professional_title: str | None = Field(default=None, max_length=200)
    professional_summary: str | None = Field(default=None, max_length=5000)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    preferences: CareerPreferencesSchema | None = None
    verification_status: VerificationStatus | None = None

    @field_validator(
        "full_name",
        "phone",
        "city",
        "state",
        "country",
        "professional_title",
        "professional_summary",
    )
    @classmethod
    def clean_str_fields(cls, v: str | None) -> str | None:
        return clean_optional_str(v)

    @field_validator("professional_email")
    @classmethod
    def validate_email_field(cls, v: str | None) -> str | None:
        cleaned = clean_optional_str(v)
        if cleaned is None:
            return None
        validated = email_adapter.validate_python(cleaned)
        return str(validated).lower()

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return validate_optional_url(v)


class ProfessionalProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None
    professional_email: str | None
    phone: str | None
    city: str | None
    state: str | None
    country: str | None
    professional_title: str | None
    professional_summary: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    preferences: CareerPreferencesSchema
    verification_status: VerificationStatus
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- WorkExperience ---
class WorkExperienceBase(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    experience_type: ExperienceType = ExperienceType.INTERNSHIP
    technologies: list[str] = Field(default_factory=list)
    related_skills: list[str] = Field(default_factory=list)
    eligible_as_target_role: bool = True
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("company", "role")
    @classmethod
    def validate_required_str(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Este campo não pode ficar em branco.")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_desc(cls, v: str | None) -> str | None:
        return clean_optional_str(v)

    @field_validator("technologies", "related_skills")
    @classmethod
    def clean_lists(cls, v: list[str]) -> list[str]:
        return clean_string_list(v)

    @model_validator(mode="after")
    def validate_dates(self) -> "WorkExperienceBase":
        if self.is_current:
            self.end_date = None
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("A data de término não pode ser anterior à data de início.")
        return self


class WorkExperienceCreate(WorkExperienceBase):
    pass


class WorkExperienceUpdate(WorkExperienceBase):
    pass


class WorkExperienceResponse(WorkExperienceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Education ---
class EducationBase(BaseModel):
    institution: str = Field(..., min_length=1, max_length=200)
    course: str = Field(..., min_length=1, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    current_semester: str | None = Field(default=None, max_length=80)
    start_date: date | None = None
    expected_graduation_date: date | None = None
    education_status: EducationStatus = EducationStatus.IN_PROGRESS
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("institution", "course")
    @classmethod
    def validate_required_str(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Este campo não pode ficar em branco.")
        return cleaned

    @field_validator("field_of_study", "current_semester")
    @classmethod
    def clean_optional(cls, v: str | None) -> str | None:
        return clean_optional_str(v)

    @model_validator(mode="after")
    def validate_dates(self) -> "EducationBase":
        if (
            self.start_date
            and self.expected_graduation_date
            and self.expected_graduation_date < self.start_date
        ):
            raise ValueError("A previsão de conclusão não pode ser anterior à data de início.")
        return self


class EducationCreate(EducationBase):
    pass


class EducationUpdate(EducationBase):
    pass


class EducationResponse(EducationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Skill ---
class SkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    category: str = Field(..., min_length=1, max_length=100)
    proficiency_level: SkillProficiency = SkillProficiency.INTERMEDIATE
    notes: str | None = Field(default=None, max_length=2000)
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("name", "category")
    @classmethod
    def validate_required_str(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Este campo não pode ficar em branco.")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str | None) -> str | None:
        return clean_optional_str(v)


class SkillCreate(SkillBase):
    pass


class SkillUpdate(SkillBase):
    pass


class SkillResponse(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Language ---
class LanguageBase(BaseModel):
    language_name: str = Field(..., min_length=1, max_length=100)
    proficiency_level: LanguageProficiency = LanguageProficiency.INTERMEDIATE
    cefr_level: str | None = Field(default=None, max_length=16)
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("language_name")
    @classmethod
    def validate_required_str(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome do idioma não pode ficar em branco.")
        return cleaned

    @field_validator("cefr_level")
    @classmethod
    def validate_cefr(cls, v: str | None) -> str | None:
        cleaned = clean_optional_str(v)
        if cleaned is None:
            return None
        upper = cleaned.upper()
        if upper not in VALID_CEFR_LEVELS:
            raise ValueError(
                f"Nível CEFR inválido. Valores aceitos: {', '.join(sorted(VALID_CEFR_LEVELS))}."
            )
        return upper


class LanguageCreate(LanguageBase):
    pass


class LanguageUpdate(LanguageBase):
    pass


class LanguageResponse(LanguageBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- ProfessionalProject ---
class ProfessionalProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    role: str | None = Field(default=None, max_length=150)
    technologies: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    verified_results: str | None = Field(default=None, max_length=5000)
    verification_status: VerificationStatus = VerificationStatus.DRAFT

    @field_validator("name")
    @classmethod
    def validate_required_str(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome do projeto não pode ficar em branco.")
        return cleaned

    @field_validator("description", "role", "verified_results")
    @classmethod
    def clean_optional(cls, v: str | None) -> str | None:
        return clean_optional_str(v)

    @field_validator("technologies")
    @classmethod
    def clean_tech_list(cls, v: list[str]) -> list[str]:
        return clean_string_list(v)

    @field_validator("links")
    @classmethod
    def validate_links_dict(cls, v: dict[str, str]) -> dict[str, str]:
        cleaned_links: dict[str, str] = {}
        for label, url in v.items():
            clean_label = label.strip()
            clean_url = validate_optional_url(url)
            if clean_label and clean_url:
                cleaned_links[clean_label] = clean_url
        return cleaned_links


class ProfessionalProjectCreate(ProfessionalProjectBase):
    pass


class ProfessionalProjectUpdate(ProfessionalProjectBase):
    pass


class ProfessionalProjectResponse(ProfessionalProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProfileValidationSummary(BaseModel):
    profile_confirmed: bool
    confirmed_count: int
    pending_or_draft_count: int
    total_items: int
    ready_for_future_applications: bool


class FullProfileBundleResponse(BaseModel):
    profile: ProfessionalProfileResponse
    experiences: list[WorkExperienceResponse]
    educations: list[EducationResponse]
    skills: list[SkillResponse]
    languages: list[LanguageResponse]
    projects: list[ProfessionalProjectResponse]
    validation_summary: ProfileValidationSummary


# --- Schemas rigorosos para importação local de seed privado ---
SeedVerificationStatus = Literal["draft", "pending_validation"]


class ProfileSeedProfileSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    professional_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    professional_title: str | None = Field(default=None, max_length=200)
    professional_summary: str | None = Field(default=None, max_length=5000)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    preferences: CareerPreferencesSchema | None = None
    verification_status: SeedVerificationStatus = "pending_validation"

    @field_validator(
        "full_name",
        "phone",
        "city",
        "state",
        "country",
        "professional_title",
        "professional_summary",
    )
    @classmethod
    def clean_str_fields(cls, v: str | None) -> str | None:
        return clean_optional_str(v)

    @field_validator("professional_email")
    @classmethod
    def validate_email_field(cls, v: str | None) -> str | None:
        cleaned = clean_optional_str(v)
        if cleaned is None:
            return None
        validated = email_adapter.validate_python(cleaned)
        return str(validated).lower()

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return validate_optional_url(v)


class SeedWorkExperienceItem(WorkExperienceBase):
    model_config = ConfigDict(extra="forbid")
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("verification_status")
    @classmethod
    def enforce_unconfirmed_seed(cls, v: VerificationStatus) -> VerificationStatus:
        if v == VerificationStatus.CONFIRMED:
            raise ValueError(
                "Itens importados via seed não podem entrar automaticamente como 'confirmed'."
            )
        return v


class SeedEducationItem(EducationBase):
    model_config = ConfigDict(extra="forbid")
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("verification_status")
    @classmethod
    def enforce_unconfirmed_seed(cls, v: VerificationStatus) -> VerificationStatus:
        if v == VerificationStatus.CONFIRMED:
            raise ValueError(
                "Itens importados via seed não podem entrar automaticamente como 'confirmed'."
            )
        return v


class SeedSkillItem(SkillBase):
    model_config = ConfigDict(extra="forbid")
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("verification_status")
    @classmethod
    def enforce_unconfirmed_seed(cls, v: VerificationStatus) -> VerificationStatus:
        if v == VerificationStatus.CONFIRMED:
            raise ValueError(
                "Itens importados via seed não podem entrar automaticamente como 'confirmed'."
            )
        return v


class SeedLanguageItem(LanguageBase):
    model_config = ConfigDict(extra="forbid")
    verification_status: VerificationStatus = VerificationStatus.PENDING_VALIDATION

    @field_validator("verification_status")
    @classmethod
    def enforce_unconfirmed_seed(cls, v: VerificationStatus) -> VerificationStatus:
        if v == VerificationStatus.CONFIRMED:
            raise ValueError(
                "Itens importados via seed não podem entrar automaticamente como 'confirmed'."
            )
        return v


class SeedProjectItem(ProfessionalProjectBase):
    model_config = ConfigDict(extra="forbid")
    verification_status: VerificationStatus = VerificationStatus.DRAFT

    @field_validator("verification_status")
    @classmethod
    def enforce_unconfirmed_seed(cls, v: VerificationStatus) -> VerificationStatus:
        if v == VerificationStatus.CONFIRMED:
            raise ValueError(
                "Itens importados via seed não podem entrar automaticamente como 'confirmed'."
            )
        return v


class ProfileSeedDocumentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    profile: ProfileSeedProfileSchema = Field(default_factory=ProfileSeedProfileSchema)
    experiences: list[SeedWorkExperienceItem] = Field(default_factory=list)
    educations: list[SeedEducationItem] = Field(default_factory=list)
    skills: list[SeedSkillItem] = Field(default_factory=list)
    languages: list[SeedLanguageItem] = Field(default_factory=list)
    projects: list[SeedProjectItem] = Field(default_factory=list)


class ProfileSeedImportSummary(BaseModel):
    profile_created: bool
    profile_fields_filled: int
    preferences_applied: bool
    experiences_created: int
    experiences_skipped: int
    educations_created: int
    educations_skipped: int
    skills_created: int
    skills_skipped: int
    languages_created: int
    languages_skipped: int
    projects_created: int
    projects_skipped: int
