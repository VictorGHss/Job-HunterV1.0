from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
from app.services.profile_service import get_full_profile_bundle

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


@dataclass
class AuthorizedFactBundle:
    opportunity_context: OpportunityContextInfo
    profile: ProfessionalProfile | None
    experiences: list[WorkExperience]
    projects: list[ProfessionalProject]
    educations: list[Education]
    skills: list[Skill]
    languages: list[Language]
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
    opportunity: Opportunity | None,
    application: Application | None,
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


def _build_contact_preview(confirmed_profile: ProfessionalProfile | None) -> ContactPreviewInfo:
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


def _exp_haystack(exp: WorkExperience) -> str:
    parts = [
        exp.role,
        exp.company,
        exp.description,
        " ".join(str(t) for t in (exp.technologies or [])),
        " ".join(str(t) for t in (exp.related_skills or [])),
    ]
    return _norm_text(" ".join(p for p in parts if p))


def _project_haystack(proj: ProfessionalProject) -> str:
    parts = [
        proj.name,
        proj.role,
        proj.description,
        proj.verified_results,
        " ".join(str(t) for t in (proj.technologies or [])),
    ]
    return _norm_text(" ".join(p for p in parts if p))


def _edu_haystack(edu: Education) -> str:
    parts = [edu.course, edu.field_of_study, edu.institution]
    return _norm_text(" ".join(p for p in parts if p))


def _skill_haystack(skill: Skill) -> str:
    parts = [skill.name, skill.category, skill.notes]
    return _norm_text(" ".join(p for p in parts if p))


def build_authorized_fact_bundle(
    db: Session,
    user: User,
    *,
    opportunity: Opportunity | None = None,
    application: Application | None = None,
    target_language: TargetLanguage = "pt-BR",
) -> AuthorizedFactBundle:
    """Seleciona exclusivamente fatos confirmados para currículo e analisa lacunas."""
    bundle = get_full_profile_bundle(db, user)
    opp_ctx, req_pool = _extract_requirement_pool(opportunity, application)

    confirmed_profile = (
        bundle.profile
        if bundle.profile and bundle.profile.verification_status == VerificationStatus.CONFIRMED.value
        else None
    )

    confirmed_experiences = [
        item
        for item in bundle.experiences
        if item.verification_status == VerificationStatus.CONFIRMED.value
    ]
    confirmed_projects = [
        item
        for item in bundle.projects
        if item.verification_status == VerificationStatus.CONFIRMED.value
    ]
    confirmed_educations = [
        item
        for item in bundle.educations
        if item.verification_status == VerificationStatus.CONFIRMED.value
    ]
    confirmed_skills = [
        item
        for item in bundle.skills
        if item.verification_status == VerificationStatus.CONFIRMED.value
    ]
    confirmed_languages = [
        item
        for item in bundle.languages
        if item.verification_status == VerificationStatus.CONFIRMED.value
    ]

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

    exp_scored: list[tuple[tuple[int, int, str], WorkExperience, int, list[str]]] = []
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

    proj_scored: list[tuple[tuple[int, str], ProfessionalProject, int, list[str]]] = []
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

    edu_scored: list[tuple[tuple[int, int, str], Education, int, list[str]]] = []
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

    skill_scored: list[tuple[tuple[int, int, str], Skill, int, list[str]]] = []
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

    lang_scored: list[tuple[tuple[int, int, str], Language]] = []
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

    if bundle.profile and bundle.profile.verification_status != VerificationStatus.CONFIRMED.value:
        status_val = bundle.profile.verification_status
        can_batch = status_val == VerificationStatus.PENDING_VALIDATION.value
        prof_haystack = _norm_text(
            " ".join(
                p
                for p in [
                    bundle.profile.professional_title,
                    bundle.profile.professional_summary,
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
                entity_id=bundle.profile.id,
                verification_status=status_val,  # type: ignore[arg-type]
                label="Identidade profissional e contatos",
                summary=sanitize_plain_text(
                    bundle.profile.professional_title or bundle.profile.full_name,
                    max_length=160,
                )
                or "Dados básicos do perfil",
                details={
                    "professional_title": sanitize_plain_text(bundle.profile.professional_title, max_length=120),
                    "has_summary": bool(bundle.profile.professional_summary),
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

    for exp in bundle.experiences:
        if exp.verification_status == VerificationStatus.CONFIRMED.value:
            continue
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

    for proj in bundle.projects:
        if proj.verification_status == VerificationStatus.CONFIRMED.value:
            continue
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

    for edu in bundle.educations:
        if edu.verification_status == VerificationStatus.CONFIRMED.value:
            continue
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

    for skill in bundle.skills:
        if skill.verification_status == VerificationStatus.CONFIRMED.value:
            continue
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

    for lang in bundle.languages:
        if lang.verification_status == VerificationStatus.CONFIRMED.value:
            continue
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
                        exp.eligible_as_target_role
                        for exp in bundle.experiences
                        if exp.verification_status != VerificationStatus.CONFIRMED.value
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
