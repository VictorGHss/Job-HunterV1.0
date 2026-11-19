from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.opportunity import Opportunity
from app.models.profile import VerificationStatus
from app.models.user import User
from app.schemas.material import TargetLanguage
from app.services.materials.ai.ai_schemas import (
    AI_SUPPORTED_MATERIAL_TYPES,
    AIMaterialTypeLiteral,
    AuthorizedAIContext,
    AuthorizedFactItem,
    SanitizedOpportunityContext,
)
from app.services.materials.fact_selector import (
    _format_period_label,
    build_authorized_fact_bundle,
)
from app.services.opportunities.sanitization import sanitize_plain_text


def build_authorized_ai_context(
    db: Session,
    user: User,
    *,
    material_type: AIMaterialTypeLiteral,
    opportunity: Opportunity | None = None,
    application: Application | None = None,
    target_language: TargetLanguage = "pt-BR",
) -> AuthorizedAIContext:
    """Constrói o contexto factual estritamente autorizado para consumo pela IA.

    Garantias de segurança e integridade:
    1. Reutiliza `build_authorized_fact_bundle` garantindo consulta direta ao estado atual do banco.
    2. Inclui exclusivamente fatos com `verification_status == 'confirmed'`.
    3. Aplica minimização de dados: remove PII privada (telefone, e-mail pessoal, links pessoais, endereços).
    4. Mantém separação estrita entre experiências formais (`experience`) e projetos (`project`).
    5. Garante isolamento estrito de inquilino (todas as entidades devem pertencer a `user.id`).
    6. Trata o contexto de oportunidade como dado estruturado estritamente sanitizado,
       prevenindo injeções de prompt por descrições de vagas externas.
    """
    if material_type not in AI_SUPPORTED_MATERIAL_TYPES:
        raise ValueError(
            f"Tipo de material não suportado para aprimoramento por IA: '{material_type}'. "
            f"Tipos permitidos: {AI_SUPPORTED_MATERIAL_TYPES}"
        )

    bundle = build_authorized_fact_bundle(
        db,
        user,
        opportunity=opportunity,
        application=application,
        target_language=target_language,
    )

    user_id_str = str(user.id)
    authorized_facts: list[AuthorizedFactItem] = []

    # 1. Perfil profissional confirmado (minimização: sem telefone, email ou URLs privadas)
    if bundle.profile and bundle.profile.verification_status == VerificationStatus.CONFIRMED.value:
        if str(bundle.profile.user_id) == user_id_str:
            prof = bundle.profile
            fact_key = f"profile:{prof.id}"
            label = sanitize_plain_text(
                prof.professional_title or prof.full_name or "Perfil Profissional",
                max_length=200,
            )
            authorized_facts.append(
                AuthorizedFactItem(
                    fact_key=fact_key,
                    entity_type="profile",
                    entity_id=str(prof.id),
                    label=label or "Perfil Profissional",
                    role_or_title=sanitize_plain_text(prof.professional_title, max_length=200),
                    description=sanitize_plain_text(prof.professional_summary, max_length=4000),
                    summary=sanitize_plain_text(prof.professional_title, max_length=500),
                    matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
                )
            )

    # 2. Experiências profissionais confirmadas (entidade 'experience')
    for exp in bundle.experiences:
        if exp.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(exp.user_id) != user_id_str:
            continue
        fact_key = f"experience:{exp.id}"
        period_str = _format_period_label(
            exp.start_date, exp.end_date, exp.is_current, target_language
        )
        tech_list = [
            sanitize_plain_text(str(t), max_length=80)
            for t in (list(exp.technologies or []) + list(exp.related_skills or []))
            if sanitize_plain_text(str(t), max_length=80)
        ]
        authorized_facts.append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="experience",
                entity_id=str(exp.id),
                label=f"{exp.role} — {exp.company}",
                company_or_institution=sanitize_plain_text(exp.company, max_length=200),
                role_or_title=sanitize_plain_text(exp.role, max_length=200),
                period=period_str or None,
                description=sanitize_plain_text(exp.description, max_length=4000),
                technologies=tech_list[:50],
                summary=sanitize_plain_text(exp.experience_type, max_length=500),
                matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
                eligible_as_target_role=bool(exp.eligible_as_target_role),
            )
        )

    # 3. Projetos profissionais confirmados (entidade 'project' - nunca são classificados como 'experience')
    for proj in bundle.projects:
        if proj.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(proj.user_id) != user_id_str:
            continue
        fact_key = f"project:{proj.id}"
        # Projetos não possuem start_date/end_date no modelo de dados
        period_str = (
            str(proj.updated_at.year)
            if hasattr(proj, "updated_at") and proj.updated_at
            else None
        )
        tech_list = [
            sanitize_plain_text(str(t), max_length=80)
            for t in (proj.technologies or [])
            if sanitize_plain_text(str(t), max_length=80)
        ]
        authorized_facts.append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="project",
                entity_id=str(proj.id),
                label=sanitize_plain_text(proj.name, max_length=200) or "Projeto Profissional",
                company_or_institution=None,  # Projetos não são empresas contratantes
                role_or_title=sanitize_plain_text(proj.role, max_length=200),
                period=period_str or None,
                description=sanitize_plain_text(proj.description, max_length=4000),
                verified_results=sanitize_plain_text(proj.verified_results, max_length=4000),
                technologies=tech_list[:50],
                summary=sanitize_plain_text(proj.role, max_length=500),
                matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
            )
        )

    # 4. Formação acadêmica confirmada (entidade 'education')
    for edu in bundle.educations:
        if edu.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(edu.user_id) != user_id_str:
            continue
        fact_key = f"education:{edu.id}"
        period_str = _format_period_label(
            edu.start_date,
            edu.expected_graduation_date,
            edu.education_status == "in_progress",
            target_language,
        )
        authorized_facts.append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="education",
                entity_id=str(edu.id),
                label=f"{edu.course} — {edu.institution}",
                company_or_institution=sanitize_plain_text(edu.institution, max_length=200),
                role_or_title=sanitize_plain_text(edu.course, max_length=200),
                period=period_str or None,
                summary=sanitize_plain_text(edu.field_of_study, max_length=500),
                proficiency=edu.education_status,
                matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
            )
        )

    # 5. Competências confirmadas (entidade 'skill')
    for sk in bundle.skills:
        if sk.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(sk.user_id) != user_id_str:
            continue
        fact_key = f"skill:{sk.id}"
        clean_name = sanitize_plain_text(sk.name, max_length=150)
        authorized_facts.append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="skill",
                entity_id=str(sk.id),
                label=clean_name or "Habilidade",
                summary=sanitize_plain_text(sk.category, max_length=100),
                proficiency=sk.proficiency_level,
                description=sanitize_plain_text(sk.notes, max_length=1000),
                technologies=[clean_name] if clean_name else [],
                matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
            )
        )

    # 6. Idiomas confirmados (entidade 'language')
    for lang in bundle.languages:
        if lang.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(lang.user_id) != user_id_str:
            continue
        fact_key = f"language:{lang.id}"
        lang_name_raw = getattr(lang, "language_name", None) or getattr(lang, "name", None)
        clean_name = sanitize_plain_text(lang_name_raw, max_length=100)
        authorized_facts.append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="language",
                entity_id=str(lang.id),
                label=clean_name or "Idioma",
                proficiency=lang.proficiency_level,
                matched_requirements=bundle.matched_req_map.get(fact_key, [])[:20],
            )
        )

    # Contexto da oportunidade sanitizado
    sanitized_opp: SanitizedOpportunityContext | None = None
    if bundle.opportunity_context:
        opp_ctx = bundle.opportunity_context
        sanitized_opp = SanitizedOpportunityContext(
            opportunity_id=str(opp_ctx.opportunity_id) if opp_ctx.opportunity_id else None,
            application_id=str(opp_ctx.application_id) if opp_ctx.application_id else None,
            title=opp_ctx.title,
            company_name=opp_ctx.company_name,
            seniority_level=opp_ctx.seniority_level,
            professional_area=opp_ctx.professional_area,
            employment_type=opp_ctx.employment_type,
            required_technologies=opp_ctx.required_technologies[:30],
            desirable_technologies=opp_ctx.desirable_technologies[:30],
            all_technologies=opp_ctx.all_technologies[:50],
            language=opp_ctx.language,
        )

    return AuthorizedAIContext(
        user_id=user_id_str,
        material_type=material_type,
        target_language=target_language,
        authorized_facts=authorized_facts,
        opportunity=sanitized_opp,
    )
