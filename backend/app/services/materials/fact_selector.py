from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.opportunity import Opportunity, SeniorityLevel
from app.models.profile import (
    Education,
    EducationStatus,
    Language,
    LanguageProficiency,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    SkillProficiency,
    VerificationStatus,
    WorkExperience,
)
from app.models.user import User
from app.schemas.material import (
    ContactPreviewInfo,
    MissingRequirementItem,
    OpportunityContextInfo,
    SelectedFactReference,
    TargetLanguage,
    UnconfirmedWarningItem,
)
from app.services.opportunities.classification import (
    PROFESSIONAL_AREA_LABELS_PT,
    SENIORITY_LABELS_PT,
)
from app.services.opportunities.matching import (
    _TECH_ALIASES,
    _contains_term,
    resolve_opportunity_areas,
    resolve_opportunity_seniority_and_experience,
)
from app.services.opportunities.sanitization import (
    sanitize_external_html_text,
    sanitize_plain_text,
)

_PROFICIENCY_RANK: dict[str, int] = {
    SkillProficiency.EXPERT.value: 5,
    SkillProficiency.ADVANCED.value: 4,
    SkillProficiency.INTERMEDIATE.value: 3,
    SkillProficiency.BASIC.value: 2,
    SkillProficiency.BEGINNER.value: 1,
    LanguageProficiency.NATIVE.value: 5,
    LanguageProficiency.FLUENT.value: 4,
    LanguageProficiency.ADVANCED.value: 3,
    LanguageProficiency.INTERMEDIATE.value: 2,
    LanguageProficiency.BASIC.value: 1,
}

_PORTUGUESE_LANGUAGE_NAMES = frozenset({"português", "portugues", "portuguese", "pt", "pt-br"})
_ENGLISH_LANGUAGE_NAMES = frozenset({"inglês", "ingles", "english", "en", "en-us", "en-gb"})


@dataclass(frozen=True, slots=True)
class ProjectedProfileRecord:
    """Projeção escalar imutável de ProfessionalProfile independente do Identity Map."""

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
    preferences: dict[str, Any]
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedExperienceRecord:
    """Projeção escalar imutável de WorkExperience independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    company: str
    role: str
    description: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    experience_type: str
    technologies: list[str]
    related_skills: list[str]
    eligible_as_target_role: bool
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedProjectRecord:
    """Projeção escalar imutável de ProfessionalProject independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    role: str | None
    technologies: list[str]
    links: dict[str, str]
    verified_results: str | None
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedEducationRecord:
    """Projeção escalar imutável de Education independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    institution: str
    course: str
    field_of_study: str | None
    current_semester: str | None
    start_date: date | None
    expected_graduation_date: date | None
    education_status: str
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedSkillRecord:
    """Projeção escalar imutável de Skill independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    category: str
    proficiency_level: str
    notes: str | None
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedLanguageRecord:
    """Projeção escalar imutável de Language independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    language_name: str
    proficiency_level: str
    cefr_level: str | None
    verification_status: str
    confirmed_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProjectedOpportunityRecord:
    """Projeção escalar imutável de Opportunity independente do Identity Map."""

    id: uuid.UUID
    source_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    title: str
    company_name: str | None
    description: str | None
    requirements: list[str]
    technologies: list[str]
    opportunity_type: str
    seniority_level: str
    experience_requirement_mode: str
    experience_min_years: int | None
    experience_preferred_years: int | None
    experience_summary: str | None
    employment_type: str
    work_mode: str
    professional_area: str
    secondary_areas: list[str]
    language: str | None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectedApplicationRecord:
    """Projeção escalar imutável de Application independente do Identity Map."""

    id: uuid.UUID
    user_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    role_title: str | None
    company_name: str | None
    seniority_level: str | None
    employment_type: str | None
    opportunity: ProjectedOpportunityRecord | None = None


def project_persisted_opportunity_for_user(
    db: Session,
    user_id: uuid.UUID,
    opportunity_id: uuid.UUID,
) -> ProjectedOpportunityRecord | None:
    """Projeta colunas de Opportunity diretamente do banco SQL (sem usar nem alterar o Identity Map)."""
    stmt = select(
        Opportunity.id,
        Opportunity.source_id,
        Opportunity.created_by_user_id,
        Opportunity.title,
        Opportunity.company_name,
        Opportunity.description,
        Opportunity.requirements,
        Opportunity.technologies,
        Opportunity.opportunity_type,
        Opportunity.seniority_level,
        Opportunity.experience_requirement_mode,
        Opportunity.experience_min_years,
        Opportunity.experience_preferred_years,
        Opportunity.experience_summary,
        Opportunity.employment_type,
        Opportunity.work_mode,
        Opportunity.professional_area,
        Opportunity.secondary_areas,
        Opportunity.language,
        Opportunity.raw_metadata,
    ).where(
        Opportunity.id == opportunity_id,
        or_(
            Opportunity.source_id.is_not(None),
            Opportunity.created_by_user_id == user_id,
        ),
    )
    with db.no_autoflush:
        row = db.execute(stmt).mappings().one_or_none()
    if row is None:
        return None
    return ProjectedOpportunityRecord(
        id=row["id"],
        source_id=row["source_id"],
        created_by_user_id=row["created_by_user_id"],
        title=row["title"],
        company_name=row["company_name"],
        description=row["description"],
        requirements=list(row["requirements"] or []),
        technologies=list(row["technologies"] or []),
        opportunity_type=row["opportunity_type"],
        seniority_level=row["seniority_level"],
        experience_requirement_mode=row["experience_requirement_mode"],
        experience_min_years=row["experience_min_years"],
        experience_preferred_years=row["experience_preferred_years"],
        experience_summary=row["experience_summary"],
        employment_type=row["employment_type"],
        work_mode=row["work_mode"],
        professional_area=row["professional_area"],
        secondary_areas=list(row["secondary_areas"] or []),
        language=row["language"],
        raw_metadata=copy.deepcopy(row["raw_metadata"]) if isinstance(row["raw_metadata"], dict) else {},
    )


def project_persisted_application_for_user(
    db: Session,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
) -> ProjectedApplicationRecord | None:
    """Projeta colunas de Application diretamente do banco SQL (sem usar nem alterar o Identity Map)."""
    stmt = select(
        Application.id,
        Application.user_id,
        Application.opportunity_id,
        Application.role_title,
        Application.company_name,
        Application.seniority_level,
        Application.employment_type,
    ).where(
        Application.id == application_id,
        Application.user_id == user_id,
    )
    with db.no_autoflush:
        row = db.execute(stmt).mappings().one_or_none()
    if row is None:
        return None
    opp_id = row["opportunity_id"]
    linked_opp = (
        project_persisted_opportunity_for_user(db, user_id, opp_id)
        if opp_id is not None
        else None
    )
    return ProjectedApplicationRecord(
        id=row["id"],
        user_id=row["user_id"],
        opportunity_id=opp_id,
        role_title=row["role_title"],
        company_name=row["company_name"],
        seniority_level=row["seniority_level"],
        employment_type=row["employment_type"],
        opportunity=linked_opp,
    )


def _project_persisted_profile_entities(
    db: Session,
    user_id: uuid.UUID,
) -> tuple[
    ProjectedProfileRecord | None,
    list[ProjectedExperienceRecord],
    list[ProjectedProjectRecord],
    list[ProjectedEducationRecord],
    list[ProjectedSkillRecord],
    list[ProjectedLanguageRecord],
    ProjectedProfileRecord | None,
    list[ProjectedExperienceRecord],
    list[ProjectedProjectRecord],
    list[ProjectedEducationRecord],
    list[ProjectedSkillRecord],
    list[ProjectedLanguageRecord],
]:
    """Lê as 6 entidades de perfil diretamente via projeção escalar de colunas no SQL.

    Garantias:
    - Filtra `user_id == user_id` e `verification_status == 'confirmed'` diretamente no SQL
      para todas as entidades confirmadas.
    - Nunca hidrata nem consulta instâncias ORM do `Session.identity_map`.
    - Nunca executa `populate_existing=True` nem descarta alterações dirty pendentes na Session.
    - Nunca chama `get_or_create_profile` (zero escrita colateral durante leitura).
    """
    confirmed_val = VerificationStatus.CONFIRMED.value

    prof_cols = (
        ProfessionalProfile.id,
        ProfessionalProfile.user_id,
        ProfessionalProfile.full_name,
        ProfessionalProfile.professional_email,
        ProfessionalProfile.phone,
        ProfessionalProfile.city,
        ProfessionalProfile.state,
        ProfessionalProfile.country,
        ProfessionalProfile.professional_title,
        ProfessionalProfile.professional_summary,
        ProfessionalProfile.linkedin_url,
        ProfessionalProfile.github_url,
        ProfessionalProfile.portfolio_url,
        ProfessionalProfile.preferences,
        ProfessionalProfile.verification_status,
        ProfessionalProfile.confirmed_at,
        ProfessionalProfile.created_at,
        ProfessionalProfile.updated_at,
    )
    exp_cols = (
        WorkExperience.id,
        WorkExperience.user_id,
        WorkExperience.company,
        WorkExperience.role,
        WorkExperience.description,
        WorkExperience.start_date,
        WorkExperience.end_date,
        WorkExperience.is_current,
        WorkExperience.experience_type,
        WorkExperience.technologies,
        WorkExperience.related_skills,
        WorkExperience.eligible_as_target_role,
        WorkExperience.verification_status,
        WorkExperience.confirmed_at,
        WorkExperience.created_at,
        WorkExperience.updated_at,
    )
    proj_cols = (
        ProfessionalProject.id,
        ProfessionalProject.user_id,
        ProfessionalProject.name,
        ProfessionalProject.description,
        ProfessionalProject.role,
        ProfessionalProject.technologies,
        ProfessionalProject.links,
        ProfessionalProject.verified_results,
        ProfessionalProject.verification_status,
        ProfessionalProject.confirmed_at,
        ProfessionalProject.created_at,
        ProfessionalProject.updated_at,
    )
    edu_cols = (
        Education.id,
        Education.user_id,
        Education.institution,
        Education.course,
        Education.field_of_study,
        Education.current_semester,
        Education.start_date,
        Education.expected_graduation_date,
        Education.education_status,
        Education.verification_status,
        Education.confirmed_at,
        Education.created_at,
        Education.updated_at,
    )
    skill_cols = (
        Skill.id,
        Skill.user_id,
        Skill.name,
        Skill.category,
        Skill.proficiency_level,
        Skill.notes,
        Skill.verification_status,
        Skill.confirmed_at,
        Skill.created_at,
        Skill.updated_at,
    )
    lang_cols = (
        Language.id,
        Language.user_id,
        Language.language_name,
        Language.proficiency_level,
        Language.cefr_level,
        Language.verification_status,
        Language.confirmed_at,
        Language.created_at,
        Language.updated_at,
    )

    def _to_prof(r: Any) -> ProjectedProfileRecord:
        return ProjectedProfileRecord(
            id=r["id"],
            user_id=r["user_id"],
            full_name=r["full_name"],
            professional_email=r["professional_email"],
            phone=r["phone"],
            city=r["city"],
            state=r["state"],
            country=r["country"],
            professional_title=r["professional_title"],
            professional_summary=r["professional_summary"],
            linkedin_url=r["linkedin_url"],
            github_url=r["github_url"],
            portfolio_url=r["portfolio_url"],
            preferences=copy.deepcopy(r["preferences"]) if isinstance(r["preferences"], dict) else {},
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def _to_exp(r: Any) -> ProjectedExperienceRecord:
        return ProjectedExperienceRecord(
            id=r["id"],
            user_id=r["user_id"],
            company=r["company"],
            role=r["role"],
            description=r["description"],
            start_date=r["start_date"],
            end_date=r["end_date"],
            is_current=bool(r["is_current"]),
            experience_type=r["experience_type"],
            technologies=list(r["technologies"] or []),
            related_skills=list(r["related_skills"] or []),
            eligible_as_target_role=bool(r["eligible_as_target_role"]),
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def _to_proj(r: Any) -> ProjectedProjectRecord:
        return ProjectedProjectRecord(
            id=r["id"],
            user_id=r["user_id"],
            name=r["name"],
            description=r["description"],
            role=r["role"],
            technologies=list(r["technologies"] or []),
            links=dict(r["links"] or {}),
            verified_results=r["verified_results"],
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def _to_edu(r: Any) -> ProjectedEducationRecord:
        return ProjectedEducationRecord(
            id=r["id"],
            user_id=r["user_id"],
            institution=r["institution"],
            course=r["course"],
            field_of_study=r["field_of_study"],
            current_semester=r["current_semester"],
            start_date=r["start_date"],
            expected_graduation_date=r["expected_graduation_date"],
            education_status=r["education_status"],
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def _to_skill(r: Any) -> ProjectedSkillRecord:
        return ProjectedSkillRecord(
            id=r["id"],
            user_id=r["user_id"],
            name=r["name"],
            category=r["category"],
            proficiency_level=r["proficiency_level"],
            notes=r["notes"],
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def _to_lang(r: Any) -> ProjectedLanguageRecord:
        return ProjectedLanguageRecord(
            id=r["id"],
            user_id=r["user_id"],
            language_name=r["language_name"],
            proficiency_level=r["proficiency_level"],
            cefr_level=r["cefr_level"],
            verification_status=r["verification_status"],
            confirmed_at=r["confirmed_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    exp_order = (
        WorkExperience.is_current.desc(),
        WorkExperience.start_date.desc().nullslast(),
        WorkExperience.created_at.desc(),
    )

    with db.no_autoflush:
        # 1. Consultas SQL filtrando estritamente verification_status == 'confirmed' no banco
        c_prof_row = (
            db.execute(
                select(*prof_cols).where(
                    ProfessionalProfile.user_id == user_id,
                    ProfessionalProfile.verification_status == confirmed_val,
                )
            )
            .mappings()
            .one_or_none()
        )
        c_exp_rows = (
            db.execute(
                select(*exp_cols)
                .where(
                    WorkExperience.user_id == user_id,
                    WorkExperience.verification_status == confirmed_val,
                )
                .order_by(*exp_order)
            )
            .mappings()
            .all()
        )
        c_proj_rows = (
            db.execute(
                select(*proj_cols)
                .where(
                    ProfessionalProject.user_id == user_id,
                    ProfessionalProject.verification_status == confirmed_val,
                )
                .order_by(ProfessionalProject.created_at.desc())
            )
            .mappings()
            .all()
        )
        c_edu_rows = (
            db.execute(
                select(*edu_cols)
                .where(
                    Education.user_id == user_id,
                    Education.verification_status == confirmed_val,
                )
                .order_by(Education.created_at.desc())
            )
            .mappings()
            .all()
        )
        c_skill_rows = (
            db.execute(
                select(*skill_cols)
                .where(
                    Skill.user_id == user_id,
                    Skill.verification_status == confirmed_val,
                )
                .order_by(Skill.category.asc(), Skill.name.asc())
            )
            .mappings()
            .all()
        )
        c_lang_rows = (
            db.execute(
                select(*lang_cols)
                .where(
                    Language.user_id == user_id,
                    Language.verification_status == confirmed_val,
                )
                .order_by(Language.created_at.asc())
            )
            .mappings()
            .all()
        )

        # 2. Consultas SQL separadas para avisos de itens não confirmados (unconfirmed_warnings)
        u_prof_row = (
            db.execute(
                select(*prof_cols).where(
                    ProfessionalProfile.user_id == user_id,
                    ProfessionalProfile.verification_status != confirmed_val,
                )
            )
            .mappings()
            .one_or_none()
        )
        u_exp_rows = (
            db.execute(
                select(*exp_cols)
                .where(
                    WorkExperience.user_id == user_id,
                    WorkExperience.verification_status != confirmed_val,
                )
                .order_by(*exp_order)
            )
            .mappings()
            .all()
        )
        u_proj_rows = (
            db.execute(
                select(*proj_cols)
                .where(
                    ProfessionalProject.user_id == user_id,
                    ProfessionalProject.verification_status != confirmed_val,
                )
                .order_by(ProfessionalProject.created_at.desc())
            )
            .mappings()
            .all()
        )
        u_edu_rows = (
            db.execute(
                select(*edu_cols)
                .where(
                    Education.user_id == user_id,
                    Education.verification_status != confirmed_val,
                )
                .order_by(Education.created_at.desc())
            )
            .mappings()
            .all()
        )
        u_skill_rows = (
            db.execute(
                select(*skill_cols)
                .where(
                    Skill.user_id == user_id,
                    Skill.verification_status != confirmed_val,
                )
                .order_by(Skill.category.asc(), Skill.name.asc())
            )
            .mappings()
            .all()
        )
        u_lang_rows = (
            db.execute(
                select(*lang_cols)
                .where(
                    Language.user_id == user_id,
                    Language.verification_status != confirmed_val,
                )
                .order_by(Language.created_at.asc())
            )
            .mappings()
            .all()
        )

    return (
        _to_prof(c_prof_row) if c_prof_row is not None else None,
        [_to_exp(r) for r in c_exp_rows],
        [_to_proj(r) for r in c_proj_rows],
        [_to_edu(r) for r in c_edu_rows],
        [_to_skill(r) for r in c_skill_rows],
        [_to_lang(r) for r in c_lang_rows],
        _to_prof(u_prof_row) if u_prof_row is not None else None,
        [_to_exp(r) for r in u_exp_rows],
        [_to_proj(r) for r in u_proj_rows],
        [_to_edu(r) for r in u_edu_rows],
        [_to_skill(r) for r in u_skill_rows],
        [_to_lang(r) for r in u_lang_rows],
    )


@dataclass
class AuthorizedFactBundle:
    opportunity_context: OpportunityContextInfo
    profile: ProjectedProfileRecord | ProfessionalProfile | None
    experiences: list[ProjectedExperienceRecord] | list[WorkExperience]
    projects: list[ProjectedProjectRecord] | list[ProfessionalProject]
    educations: list[ProjectedEducationRecord] | list[Education]
    skills: list[ProjectedSkillRecord] | list[Skill]
    languages: list[ProjectedLanguageRecord] | list[Language]
    used_facts: list[SelectedFactReference]
    unconfirmed_warnings: list[UnconfirmedWarningItem]
    missing_requirements: list[MissingRequirementItem]
    confirmed_counts: dict[str, int]
    can_generate: bool
    blocking_reasons: list[str]
    contact_preview: ContactPreviewInfo
    matched_req_map: dict[str, list[str]] = field(default_factory=dict)


def _norm_text(value: str | None) -> str:
    cleaned = sanitize_external_html_text(value, max_length=4000) or ""
    return cleaned.strip().lower()


def _matches_requirement(haystack: str, requirement: str) -> bool:
    if not haystack or not requirement:
        return False
    req_norm = requirement.strip().lower()
    if not req_norm:
        return False
    if _contains_term(haystack, req_norm):
        return True
    aliases = _TECH_ALIASES.get(req_norm, ())
    return any(_contains_term(haystack, alias.lower()) for alias in aliases)


def _extract_requirement_pool(
    opportunity: ProjectedOpportunityRecord | Opportunity | None,
    application: ProjectedApplicationRecord | Application | None,
) -> tuple[OpportunityContextInfo, list[tuple[str, str]]]:
    """Extrai requisitos normalizados tratando texto externo apenas como dado de busca."""
    target_opp = opportunity or (application.opportunity if application else None)

    if target_opp is None and application is None:
        return OpportunityContextInfo(), []

    if target_opp is None and application is not None:
        role_title = sanitize_plain_text(application.role_title, max_length=255)
        company_name = sanitize_plain_text(application.company_name, max_length=200)
        inferred_techs: list[str] = []
        title_haystack = _norm_text(role_title)
        for tech in _TECH_ALIASES:
            if _matches_requirement(title_haystack, tech):
                inferred_techs.append(tech)
        ctx = OpportunityContextInfo(
            application_id=application.id,
            title=role_title,
            company_name=company_name,
            seniority_level=application.seniority_level,
            employment_type=application.employment_type,
            all_technologies=inferred_techs[:20],
        )
        return ctx, [(tech, "general_technology") for tech in inferred_techs[:20]]

    assert target_opp is not None
    primary_area, _secondary = resolve_opportunity_areas(target_opp)
    seniority_level, _mode, _min_y, _pref_y, exp_summary, req_techs, des_techs = (
        resolve_opportunity_seniority_and_experience(target_opp)
    )

    seen_techs: set[str] = set()
    req_pool: list[tuple[str, str]] = []
    required_list: list[str] = []
    desirable_list: list[str] = []
    all_list: list[str] = []

    def _push(raw_name: str, kind: str) -> None:
        cleaned = sanitize_plain_text(raw_name, max_length=80)
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen_techs:
            return
        seen_techs.add(key)
        all_list.append(cleaned)
        if kind == "required_technology":
            required_list.append(cleaned)
        elif kind == "desirable_technology":
            desirable_list.append(cleaned)
        req_pool.append((cleaned, kind))

    for tech in req_techs:
        _push(tech, "required_technology")
    for tech in des_techs:
        _push(tech, "desirable_technology")
    for tech in target_opp.technologies or []:
        _push(str(tech), "general_technology")

    # Também captura tecnologias explícitas no título/requisitos sanitizados via _TECH_ALIASES
    title_and_reqs = " ".join(
        part
        for part in [
            _norm_text(target_opp.title),
            " ".join(_norm_text(str(item)) for item in (target_opp.requirements or [])),
        ]
        if part
    )
    if title_and_reqs:
        for tech in _TECH_ALIASES:
            if tech not in seen_techs and _matches_requirement(title_and_reqs, tech):
                _push(tech, "general_technology")

    ctx = OpportunityContextInfo(
        opportunity_id=target_opp.id,
        application_id=application.id if application else None,
        title=sanitize_plain_text(target_opp.title, max_length=255),
        company_name=sanitize_plain_text(target_opp.company_name, max_length=200),
        professional_area=primary_area,
        seniority_level=seniority_level,
        employment_type=target_opp.employment_type,
        opportunity_type=target_opp.opportunity_type,
        experience_summary=sanitize_plain_text(exp_summary, max_length=255),
        required_technologies=required_list[:20],
        desirable_technologies=desirable_list[:20],
        all_technologies=all_list[:25],
        language=sanitize_plain_text(target_opp.language, max_length=32),
    )
    return ctx, req_pool[:25]


def _format_period_label(
    start_date: Any,
    end_date: Any,
    is_current: bool,
    target_language: TargetLanguage,
) -> str:
    start_str = start_date.strftime("%m/%Y") if start_date else None
    if is_current:
        end_str = "Present" if target_language == "en" else "Atual"
    elif end_date:
        end_str = end_date.strftime("%m/%Y")
    else:
        end_str = None

    if start_str and end_str:
        return f"{start_str} – {end_str}"
    if start_str:
        return start_str
    if end_str:
        return end_str
    return ""


def _build_contact_preview(
    confirmed_profile: ProjectedProfileRecord | ProfessionalProfile | None,
) -> ContactPreviewInfo:
    if confirmed_profile is None:
        return ContactPreviewInfo(
            profile_confirmed=False,
            has_full_name=False,
            has_email=False,
            has_phone=False,
            has_location=False,
            links_count=0,
            location_label=None,
        )

    loc_parts = [
        p
        for p in [
            sanitize_plain_text(confirmed_profile.city, max_length=120),
            sanitize_plain_text(confirmed_profile.state, max_length=120),
            sanitize_plain_text(confirmed_profile.country, max_length=120),
        ]
        if p
    ]
    links_count = sum(
        1
        for url in [
            confirmed_profile.linkedin_url,
            confirmed_profile.github_url,
            confirmed_profile.portfolio_url,
        ]
        if url and url.strip()
    )
    return ContactPreviewInfo(
        profile_confirmed=True,
        has_full_name=bool(confirmed_profile.full_name and confirmed_profile.full_name.strip()),
        has_email=bool(
            confirmed_profile.professional_email and confirmed_profile.professional_email.strip()
        ),
        has_phone=bool(confirmed_profile.phone and confirmed_profile.phone.strip()),
        has_location=bool(loc_parts),
        links_count=links_count,
        location_label=", ".join(loc_parts) if loc_parts else None,
    )


def _score_matches(
    haystack: str,
    req_pool: list[tuple[str, str]],
) -> tuple[int, list[str]]:
    score = 0
    matched: list[str] = []
    for req_name, kind in req_pool:
        if _matches_requirement(haystack, req_name):
            matched.append(req_name)
            if kind == "required_technology":
                score += 20
            elif kind == "desirable_technology":
                score += 10
            else:
                score += 12
    return score, matched


def _profile_target_areas(profile: Any) -> list[str]:
    raw = profile.preferences
    prefs = raw.model_dump() if hasattr(raw, "model_dump") else (raw or {})
    collected: list[str] = []
    for key in ("internships", "junior_developer"):
        block = prefs.get(key) or {}
        collected.extend(str(item) for item in (block.get("priority_areas") or []))
    freelance = prefs.get("freelance") or {}
    collected.extend(str(item) for item in (freelance.get("priority_categories") or []))
    return collected


def _exp_haystack(exp: ProjectedExperienceRecord | WorkExperience) -> str:
    parts = [
        exp.role,
        exp.company,
        exp.description,
        " ".join(str(t) for t in (exp.technologies or [])),
        " ".join(str(t) for t in (exp.related_skills or [])),
    ]
    return _norm_text(" ".join(p for p in parts if p))


def _project_haystack(proj: ProjectedProjectRecord | ProfessionalProject) -> str:
    parts = [
        proj.name,
        proj.role,
        proj.description,
        proj.verified_results,
        " ".join(str(t) for t in (proj.technologies or [])),
    ]
    return _norm_text(" ".join(p for p in parts if p))


def _edu_haystack(edu: ProjectedEducationRecord | Education) -> str:
    parts = [edu.course, edu.field_of_study, edu.institution]
    return _norm_text(" ".join(p for p in parts if p))


def _skill_haystack(skill: ProjectedSkillRecord | Skill) -> str:
    parts = [skill.name, skill.category, skill.notes]
    return _norm_text(" ".join(p for p in parts if p))


def build_authorized_fact_bundle(
    db: Session,
    user: User,
    *,
    opportunity: ProjectedOpportunityRecord | Opportunity | None = None,
    application: ProjectedApplicationRecord | Application | None = None,
    target_language: TargetLanguage = "pt-BR",
) -> AuthorizedFactBundle:
    """Seleciona exclusivamente fatos confirmados persistidos no banco (via projeção escalar) e analisa lacunas."""
    (
        confirmed_profile,
        confirmed_experiences,
        confirmed_projects,
        confirmed_educations,
        confirmed_skills,
        confirmed_languages,
        unconfirmed_profile,
        unconfirmed_experiences,
        unconfirmed_projects,
        unconfirmed_educations,
        unconfirmed_skills,
        unconfirmed_languages,
    ) = _project_persisted_profile_entities(db, user.id)

    resolved_opp: ProjectedOpportunityRecord | Opportunity | None = opportunity
    if opportunity is not None and not isinstance(opportunity, ProjectedOpportunityRecord):
        opp_id = getattr(opportunity, "id", None)
        if opp_id is not None:
            persisted_opp = project_persisted_opportunity_for_user(db, user.id, opp_id)
            if persisted_opp is not None:
                resolved_opp = persisted_opp

    resolved_app: ProjectedApplicationRecord | Application | None = application
    if application is not None and not isinstance(application, ProjectedApplicationRecord):
        app_id = getattr(application, "id", None)
        if app_id is not None:
            persisted_app = project_persisted_application_for_user(db, user.id, app_id)
            if persisted_app is not None:
                resolved_app = persisted_app

    opp_ctx, req_pool = _extract_requirement_pool(resolved_opp, resolved_app)

    # Ranqueamento determinístico separado (experiências nunca se misturam com projetos)
    matched_req_map: dict[str, list[str]] = {}
    used_facts: list[SelectedFactReference] = []

    if confirmed_profile is not None:
        prof_fact_key = f"profile:{confirmed_profile.id}"
        prof_haystack = _norm_text(
            " ".join(
                p
                for p in [
                    confirmed_profile.professional_title,
                    confirmed_profile.professional_summary,
                    " ".join(_profile_target_areas(confirmed_profile)),
                ]
                if p
            )
        )
        prof_score, prof_matched = _score_matches(prof_haystack, req_pool)
        matched_req_map[prof_fact_key] = prof_matched
        used_facts.append(
            SelectedFactReference(
                fact_key=prof_fact_key,
                entity_type="profile",
                entity_id=confirmed_profile.id,
                confirmed_at=confirmed_profile.confirmed_at,
                label=sanitize_plain_text(
                    confirmed_profile.full_name or confirmed_profile.professional_title,
                    max_length=160,
                )
                or "Perfil profissional",
                summary=sanitize_plain_text(
                    confirmed_profile.professional_title or confirmed_profile.professional_summary,
                    max_length=200,
                )
                or "Identidade profissional confirmada",
                relevance_score=prof_score + 10,
                matched_requirements=prof_matched,
            )
        )

    exp_scored: list[tuple[tuple[int, int, str], ProjectedExperienceRecord, int, list[str]]] = []
    for exp in confirmed_experiences:
        haystack = _exp_haystack(exp)
        score, matched = _score_matches(haystack, req_pool)
        if exp.eligible_as_target_role:
            score += 25
        if opp_ctx.title and exp.role and _contains_term(haystack, opp_ctx.title.lower()):
            score += 15
        if exp.is_current:
            score += 4
        sort_key = (
            score,
            1 if exp.is_current else 0,
            (exp.end_date or exp.start_date).isoformat() if (exp.end_date or exp.start_date) else "",
        )
        exp_scored.append((sort_key, exp, score, matched))
    exp_scored.sort(key=lambda row: row[0], reverse=True)
    ordered_experiences = [row[1] for row in exp_scored]

    for _, exp, score, matched in exp_scored:
        fact_key = f"experience:{exp.id}"
        matched_req_map[fact_key] = matched
        used_facts.append(
            SelectedFactReference(
                fact_key=fact_key,
                entity_type="experience",
                entity_id=exp.id,
                confirmed_at=exp.confirmed_at,
                label=f"{exp.role} — {exp.company}",
                summary=_format_period_label(exp.start_date, exp.end_date, exp.is_current, target_language)
                or exp.experience_type,
                relevance_score=score,
                matched_requirements=matched,
                eligible_as_target_role=exp.eligible_as_target_role,
            )
        )

    proj_scored: list[tuple[tuple[int, str], ProjectedProjectRecord, int, list[str]]] = []
    for proj in confirmed_projects:
        haystack = _project_haystack(proj)
        score, matched = _score_matches(haystack, req_pool)
        if proj.verified_results:
            score += 5
        sort_key = (
            score,
            proj.updated_at.isoformat() if proj.updated_at else "",
        )
        proj_scored.append((sort_key, proj, score, matched))
    proj_scored.sort(key=lambda row: row[0], reverse=True)
    ordered_projects = [row[1] for row in proj_scored]

    for _, proj, score, matched in proj_scored:
        fact_key = f"project:{proj.id}"
        matched_req_map[fact_key] = matched
        used_facts.append(
            SelectedFactReference(
                fact_key=fact_key,
                entity_type="project",
                entity_id=proj.id,
                confirmed_at=proj.confirmed_at,
                label=proj.name,
                summary=sanitize_plain_text(proj.role, max_length=120) or "Projeto profissional",
                relevance_score=score,
                matched_requirements=matched,
            )
        )

    edu_scored: list[tuple[tuple[int, int, str], ProjectedEducationRecord, int, list[str]]] = []
    for edu in confirmed_educations:
        haystack = _edu_haystack(edu)
        score, matched = _score_matches(haystack, req_pool)
        status_priority = (
            2
            if edu.education_status in {EducationStatus.COMPLETED.value, EducationStatus.IN_PROGRESS.value}
            else 1
        )
        sort_key = (
            score,
            status_priority,
            (edu.expected_graduation_date or edu.start_date).isoformat()
            if (edu.expected_graduation_date or edu.start_date)
            else "",
        )
        edu_scored.append((sort_key, edu, score, matched))
    edu_scored.sort(key=lambda row: row[0], reverse=True)
    ordered_educations = [row[1] for row in edu_scored]

    for _, edu, score, matched in edu_scored:
        fact_key = f"education:{edu.id}"
        matched_req_map[fact_key] = matched
        used_facts.append(
            SelectedFactReference(
                fact_key=fact_key,
                entity_type="education",
                entity_id=edu.id,
                confirmed_at=edu.confirmed_at,
                label=f"{edu.course} — {edu.institution}",
                summary=edu.education_status,
                relevance_score=score,
                matched_requirements=matched,
            )
        )

    skill_scored: list[tuple[tuple[int, int, str], ProjectedSkillRecord, int, list[str]]] = []
    for skill in confirmed_skills:
        haystack = _skill_haystack(skill)
        score, matched = _score_matches(haystack, req_pool)
        prof_rank = _PROFICIENCY_RANK.get(skill.proficiency_level, 0)
        sort_key = (score, prof_rank, skill.name.lower())
        skill_scored.append((sort_key, skill, score, matched))
    skill_scored.sort(key=lambda row: row[0], reverse=True)
    ordered_skills = [row[1] for row in skill_scored]

    for _, skill, score, matched in skill_scored:
        fact_key = f"skill:{skill.id}"
        matched_req_map[fact_key] = matched
        used_facts.append(
            SelectedFactReference(
                fact_key=fact_key,
                entity_type="skill",
                entity_id=skill.id,
                confirmed_at=skill.confirmed_at,
                label=skill.name,
                summary=f"{skill.category} ({skill.proficiency_level})",
                relevance_score=score,
                matched_requirements=matched,
            )
        )

    lang_scored: list[tuple[tuple[int, int, str], ProjectedLanguageRecord]] = []
    for lang in confirmed_languages:
        lang_norm = lang.language_name.strip().lower()
        target_bonus = 0
        if target_language == "en" and lang_norm in _ENGLISH_LANGUAGE_NAMES:
            target_bonus = 2
        elif target_language == "pt-BR" and lang_norm in _PORTUGUESE_LANGUAGE_NAMES:
            target_bonus = 2
        elif opp_ctx.language and opp_ctx.language.lower() in lang_norm:
            target_bonus = 1
        prof_rank = _PROFICIENCY_RANK.get(lang.proficiency_level, 0)
        lang_scored.append(((target_bonus, prof_rank, lang.language_name.lower()), lang))
    lang_scored.sort(key=lambda row: row[0], reverse=True)
    ordered_languages = [row[1] for row in lang_scored]

    for _, lang in lang_scored:
        fact_key = f"language:{lang.id}"
        matched_req_map[fact_key] = []
        used_facts.append(
            SelectedFactReference(
                fact_key=fact_key,
                entity_type="language",
                entity_id=lang.id,
                confirmed_at=lang.confirmed_at,
                label=lang.language_name,
                summary=lang.proficiency_level,
                relevance_score=1,
                matched_requirements=[],
            )
        )

    # Cobertura confirmada por requisito
    confirmed_matched_reqs: set[str] = set()
    for req_list in matched_req_map.values():
        for req_name in req_list:
            confirmed_matched_reqs.add(req_name.lower())

    # Avisos sobre itens relevantes ainda não confirmados (pending_validation ou draft)
    unconfirmed_warnings: list[UnconfirmedWarningItem] = []
    unconfirmed_covered_reqs: set[str] = set()

    if unconfirmed_profile is not None:
        status_val = unconfirmed_profile.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        prof_haystack = _norm_text(
            " ".join(
                p
                for p in [
                    unconfirmed_profile.professional_title,
                    unconfirmed_profile.professional_summary,
                ]
                if p
            )
        )
        _, p_matched = _score_matches(prof_haystack, req_pool)
        for req_name in p_matched:
            unconfirmed_covered_reqs.add(req_name.lower())
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="profile",
                entity_id=unconfirmed_profile.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label="Identidade profissional e contatos",
                summary=sanitize_plain_text(
                    unconfirmed_profile.professional_title or unconfirmed_profile.full_name,
                    max_length=160,
                )
                or "Dados básicos do perfil",
                details={
                    "professional_title": sanitize_plain_text(unconfirmed_profile.professional_title, max_length=120),
                    "has_summary": bool(unconfirmed_profile.professional_summary),
                },
                reason=(
                    "Perfil principal aguarda validação para liberar cabeçalho/contatos e título profissional."
                    if can_batch
                    else "Perfil principal está em rascunho; edite e confirme na página de Perfil."
                ),
                matched_requirements=p_matched,
                can_batch_confirm=can_batch,
            )
        )

    for exp in unconfirmed_experiences:
        status_val = exp.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        _, matched = _score_matches(_exp_haystack(exp), req_pool)
        for req_name in matched:
            unconfirmed_covered_reqs.add(req_name.lower())
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="experience",
                entity_id=exp.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label=f"{exp.role} — {exp.company}",
                summary=_format_period_label(exp.start_date, exp.end_date, exp.is_current, target_language)
                or exp.experience_type,
                details={
                    "company": exp.company,
                    "role": exp.role,
                    "experience_type": exp.experience_type,
                    "eligible_as_target_role": exp.eligible_as_target_role,
                    "technologies": list(exp.technologies or [])[:12],
                },
                reason=(
                    "Experiência relevante para a vaga, mas ainda não confirmada."
                    if matched
                    else "Experiência cadastrada aguardando confirmação antes de entrar em currículos."
                ),
                matched_requirements=matched,
                can_batch_confirm=can_batch,
            )
        )

    for proj in unconfirmed_projects:
        status_val = proj.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        _, matched = _score_matches(_project_haystack(proj), req_pool)
        for req_name in matched:
            unconfirmed_covered_reqs.add(req_name.lower())
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="project",
                entity_id=proj.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label=proj.name,
                summary=sanitize_plain_text(proj.role, max_length=120) or "Projeto profissional",
                details={
                    "name": proj.name,
                    "role": proj.role,
                    "technologies": list(proj.technologies or [])[:12],
                },
                reason=(
                    "Projeto cobre requisitos da vaga, mas está aguardando validação."
                    if matched and can_batch
                    else (
                        "Projeto em rascunho; revise e confirme na página de Perfil para incluí-lo."
                        if not can_batch
                        else "Projeto aguardando confirmação."
                    )
                ),
                matched_requirements=matched,
                can_batch_confirm=can_batch,
            )
        )

    for edu in unconfirmed_educations:
        status_val = edu.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        _, matched = _score_matches(_edu_haystack(edu), req_pool)
        for req_name in matched:
            unconfirmed_covered_reqs.add(req_name.lower())
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="education",
                entity_id=edu.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label=f"{edu.course} — {edu.institution}",
                summary=edu.education_status,
                details={
                    "institution": edu.institution,
                    "course": edu.course,
                    "education_status": edu.education_status,
                    "current_semester": edu.current_semester,
                },
                reason="Formação acadêmica aguardando confirmação para constar no currículo.",
                matched_requirements=matched,
                can_batch_confirm=can_batch,
            )
        )

    for skill in unconfirmed_skills:
        status_val = skill.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        _, matched = _score_matches(_skill_haystack(skill), req_pool)
        for req_name in matched:
            unconfirmed_covered_reqs.add(req_name.lower())
        # Para evitar ruído excessivo se houver dezenas de skills, inclui todas as pendentes
        # (ou todas relevantes + pendentes até limite razoável) com prioridade às que dão match.
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="skill",
                entity_id=skill.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label=skill.name,
                summary=f"{skill.category} · {skill.proficiency_level}",
                details={
                    "category": skill.category,
                    "proficiency_level": skill.proficiency_level,
                },
                reason=(
                    "Habilidade exigida ou relacionada à vaga aguardando confirmação."
                    if matched
                    else "Habilidade técnica aguardando confirmação para uso em currículos."
                ),
                matched_requirements=matched,
                can_batch_confirm=can_batch,
            )
        )

    for lang in unconfirmed_languages:
        status_val = lang.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        unconfirmed_warnings.append(
            UnconfirmedWarningItem(
                entity_type="language",
                entity_id=lang.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label=lang.language_name,
                summary=f"{lang.proficiency_level}" + (f" ({lang.cefr_level})" if lang.cefr_level else ""),
                details={
                    "proficiency_level": lang.proficiency_level,
                    "cefr_level": lang.cefr_level,
                },
                reason="Idioma aguardando confirmação para inclusão no currículo.",
                matched_requirements=[],
                can_batch_confirm=can_batch,
            )
        )

    # Ordena avisos colocando primeiro os que dão match com a vaga e depois os que podem ser confirmados em lote
    unconfirmed_warnings.sort(
        key=lambda item: (
            1 if item.matched_requirements else 0,
            1 if item.can_batch_confirm else 0,
            len(item.matched_requirements),
        ),
        reverse=True,
    )

    # Requisitos da vaga sem evidência confirmada
    missing_requirements: list[MissingRequirementItem] = []
    for req_name, req_kind in req_pool:
        if req_name.lower() in confirmed_matched_reqs:
            continue
        covered_unconf = req_name.lower() in unconfirmed_covered_reqs
        if covered_unconf:
            note = (
                f"Não há fato confirmado para '{req_name}', mas existe item não confirmado relacionado no perfil."
            )
        elif req_kind == "required_technology":
            note = f"Requisito obrigatório '{req_name}' sem evidência confirmada no perfil."
        else:
            note = f"Requisito '{req_name}' sem evidência confirmada no perfil."
        missing_requirements.append(
            MissingRequirementItem(
                requirement=req_name,
                requirement_kind=req_kind,  # type: ignore[arg-type]
                note=note,
                covered_by_unconfirmed=covered_unconf,
            )
        )

    # Verifica lacuna de experiência elegível como atuação-alvo quando a vaga não for apenas entrada/estágio
    if opp_ctx.seniority_level and opp_ctx.seniority_level not in {
        SeniorityLevel.INTERNSHIP.value,
        SeniorityLevel.ENTRY_LEVEL.value,
        SeniorityLevel.UNKNOWN.value,
    }:
        has_eligible_target_exp = any(exp.eligible_as_target_role for exp in ordered_experiences)
        if not has_eligible_target_exp and ordered_experiences:
            sen_label = SENIORITY_LABELS_PT.get(opp_ctx.seniority_level, opp_ctx.seniority_level)
            area_label = PROFESSIONAL_AREA_LABELS_PT.get(
                opp_ctx.professional_area or "", opp_ctx.professional_area or "área da vaga"
            )
            missing_requirements.append(
                MissingRequirementItem(
                    requirement=f"Experiência confirmada elegível na atuação-alvo ({sen_label} · {area_label})",
                    requirement_kind="seniority_or_area",
                    note=(
                        "Suas experiências confirmadas atuais estão marcadas como fora da atuação-alvo "
                        "(eligible_as_target_role=False); projetos e habilidades sustentam a candidatura sem mascarar experiência prévia."
                    ),
                    covered_by_unconfirmed=any(
                        exp.eligible_as_target_role for exp in unconfirmed_experiences
                    ),
                )
            )

    confirmed_counts = {
        "profile": 1 if confirmed_profile is not None else 0,
        "experiences": len(ordered_experiences),
        "projects": len(ordered_projects),
        "educations": len(ordered_educations),
        "skills": len(ordered_skills),
        "languages": len(ordered_languages),
    }
    substantive_confirmed = (
        confirmed_counts["experiences"]
        + confirmed_counts["projects"]
        + confirmed_counts["educations"]
        + confirmed_counts["skills"]
    )

    blocking_reasons: list[str] = []
    if substantive_confirmed == 0:
        blocking_reasons.append(
            "Nenhum bloco substantivo confirmado foi encontrado no seu perfil (experiência, projeto, formação acadêmica ou habilidade técnica). "
            "Idiomas ou dados de contato isolados não permitem gerar currículo."
        )
        pending_count = sum(1 for item in unconfirmed_warnings if item.can_batch_confirm)
        if pending_count > 0:
            blocking_reasons.append(
                f"Há {pending_count} item(ns) aguardando validação que você pode revisar e confirmar em lote antes de gerar."
            )

    return AuthorizedFactBundle(
        opportunity_context=opp_ctx,
        profile=confirmed_profile,
        experiences=ordered_experiences,
        projects=ordered_projects,
        educations=ordered_educations,
        skills=ordered_skills,
        languages=ordered_languages,
        used_facts=used_facts,
        unconfirmed_warnings=unconfirmed_warnings,
        missing_requirements=missing_requirements,
        confirmed_counts=confirmed_counts,
        can_generate=len(blocking_reasons) == 0,
        blocking_reasons=blocking_reasons,
        contact_preview=_build_contact_preview(confirmed_profile),
        matched_req_map=matched_req_map,
    )
