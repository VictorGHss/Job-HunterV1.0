from __future__ import annotations

from typing import Any

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
    ContextTruncationMetadata,
    SanitizedOpportunityContext,
    serialize_canonical_provider_payload,
)
from app.services.materials.ai.contracts import AIContextAuthorizationError
from app.services.materials.ai.safety import redact_free_text_pii
from app.services.materials.fact_selector import (
    ProjectedApplicationRecord,
    ProjectedOpportunityRecord,
    _format_period_label,
    build_authorized_fact_bundle,
    project_persisted_application_for_user,
    project_persisted_opportunity_for_user,
)
from app.services.opportunities.sanitization import sanitize_plain_text

DEFAULT_MAX_FACTS = 60
DEFAULT_MAX_PAYLOAD_BYTES = 24_000

# Caps por categoria garantindo que grandes volumes em uma única entidade (ex.: 155 skills)
# nunca causem ValidationError nem expulsem experiências, projetos, formação ou idiomas.
_ENTITY_CATEGORY_CAPS: dict[str, int] = {
    "profile": 1,
    "experience": 12,
    "project": 10,
    "education": 6,
    "language": 6,
    "skill": 25,
}


def _authorize_target_entities(
    db: Session,
    user: User,
    *,
    opportunity: Opportunity | None,
    application: Application | None,
) -> tuple[ProjectedOpportunityRecord | None, ProjectedApplicationRecord | None]:
    """Revalida autorização de Application e Opportunity contra o banco atual via projeção escalar.

    Não hidrata nem sobrescreve instâncias ORM presentes em `Session.identity_map` (NC-01 / NC-03):
    - `application` deve existir no banco e pertencer a `user.id`.
    - `opportunity` deve ser pública (`source_id IS NOT NULL`) ou privada do próprio `user.id`.
    - Se ambos forem fornecidos, `application.opportunity_id` persistido deve ser igual a `opportunity.id`.
    - Se `application` referenciar uma oportunidade, essa oportunidade também é validada no banco.
    """
    verified_app: ProjectedApplicationRecord | None = None
    verified_opp: ProjectedOpportunityRecord | None = None
    in_memory_app_opp_id = application.opportunity_id if application is not None else None

    with db.no_autoflush:
        if application is not None:
            if application.user_id != user.id:
                raise AIContextAuthorizationError(
                    "Candidatura não autorizada para o usuário autenticado."
                )
            verified_app = project_persisted_application_for_user(
                db, user.id, application.id
            )
            if verified_app is None:
                raise AIContextAuthorizationError(
                    "Candidatura não encontrada ou não autorizada para o usuário autenticado."
                )

            # Defesa adicional (D3): se a instância em memória havia sido adulterada para apontar
            # para uma oportunidade não autorizada para o usuário, bloqueia explicitamente.
            if (
                in_memory_app_opp_id is not None
                and in_memory_app_opp_id != verified_app.opportunity_id
            ):
                if (
                    project_persisted_opportunity_for_user(
                        db, user.id, in_memory_app_opp_id
                    )
                    is None
                ):
                    raise AIContextAuthorizationError(
                        "A oportunidade referenciada pela candidatura não está autorizada para este usuário."
                    )

        if opportunity is not None:
            is_public = opportunity.source_id is not None
            is_own_private = (
                opportunity.source_id is None and opportunity.created_by_user_id == user.id
            )
            if not (is_public or is_own_private):
                raise AIContextAuthorizationError(
                    "Oportunidade não autorizada para o usuário autenticado."
                )
            verified_opp = project_persisted_opportunity_for_user(
                db, user.id, opportunity.id
            )
            if verified_opp is None:
                raise AIContextAuthorizationError(
                    "Oportunidade não encontrada ou não autorizada para o usuário autenticado."
                )

        if verified_app is not None and verified_opp is not None:
            if verified_app.opportunity_id != verified_opp.id:
                raise AIContextAuthorizationError(
                    "Inconsistência de contexto: a candidatura informada não corresponde à oportunidade fornecida."
                )
        elif verified_app is not None and verified_app.opportunity_id is not None:
            verified_opp = project_persisted_opportunity_for_user(
                db, user.id, verified_app.opportunity_id
            )
            if verified_opp is None:
                raise AIContextAuthorizationError(
                    "A oportunidade vinculada à candidatura não está autorizada para este usuário."
                )

    return verified_opp, verified_app


def _clean_and_redact(
    raw_value: str | None,
    *,
    max_length: int,
    stats: dict[str, int],
) -> str | None:
    """Aplica sanitização de texto simples + redação fail-closed de PII."""
    sanitized = sanitize_plain_text(raw_value, max_length=max_length)
    if not sanitized:
        return None
    redacted, changed = redact_free_text_pii(sanitized)
    if changed:
        if redacted is None:
            stats["pii_omitted"] += 1
        else:
            stats["pii_redacted"] += 1
    if redacted is None:
        return None
    if len(redacted) > max_length:
        return redacted[: max_length - 3].rstrip() + "..."
    return redacted


def build_authorized_ai_context(
    db: Session,
    user: User,
    *,
    material_type: AIMaterialTypeLiteral,
    opportunity: Opportunity | None = None,
    application: Application | None = None,
    target_language: TargetLanguage = "pt-BR",
    max_facts: int = DEFAULT_MAX_FACTS,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> AuthorizedAIContext:
    """Constrói o contexto factual estritamente autorizado para consumo pela IA.

    Garantias de segurança e integridade:
    1. Revalida autorização de `application` e `opportunity` no banco antes de ler qualquer dado.
    2. Reutiliza `build_authorized_fact_bundle` consultando diretamente o estado atual do banco.
    3. Inclui exclusivamente fatos com `verification_status == 'confirmed'`.
    4. Aplica minimização de dados e redação fail-closed de PII em todos os campos de texto livre.
    5. Mantém separação estrita entre experiências formais (`experience`) e projetos (`project`),
       nunca fabricando datas de projetos a partir de `updated_at` ou `created_at`.
    6. Aplica orçamento determinístico de fatos e bytes UTF-8 com metadados internos de truncamento.
    7. Mantém `user_id` e `truncation_metadata` excluídos da serialização destinada ao provider.
    """
    if material_type not in AI_SUPPORTED_MATERIAL_TYPES:
        raise ValueError(
            f"Tipo de material não suportado para aprimoramento por IA: '{material_type}'. "
            f"Tipos permitidos: {AI_SUPPORTED_MATERIAL_TYPES}"
        )

    effective_max_facts = max(1, min(max_facts, DEFAULT_MAX_FACTS))
    effective_max_bytes = max(1024, min(max_payload_bytes, DEFAULT_MAX_PAYLOAD_BYTES))

    verified_opp, verified_app = _authorize_target_entities(
        db,
        user,
        opportunity=opportunity,
        application=application,
    )

    with db.no_autoflush:
        bundle = build_authorized_fact_bundle(
            db,
            user,
            opportunity=verified_opp,
            application=verified_app,
            target_language=target_language,
        )

    user_id_str = str(user.id)
    pii_stats = {"pii_redacted": 0, "pii_omitted": 0}
    candidates_by_type: dict[str, list[AuthorizedFactItem]] = {
        "profile": [],
        "experience": [],
        "project": [],
        "education": [],
        "language": [],
        "skill": [],
    }

    # 1. Perfil profissional confirmado (sem campos de contato e com redação em texto livre)
    if bundle.profile and bundle.profile.verification_status == VerificationStatus.CONFIRMED.value:
        if str(bundle.profile.user_id) == user_id_str:
            prof = bundle.profile
            fact_key = f"profile:{prof.id}"
            clean_title = _clean_and_redact(
                prof.professional_title, max_length=200, stats=pii_stats
            )
            clean_summary = _clean_and_redact(
                prof.professional_summary, max_length=2000, stats=pii_stats
            )
            clean_label = clean_title or "Perfil Profissional"
            candidates_by_type["profile"].append(
                AuthorizedFactItem(
                    fact_key=fact_key,
                    entity_type="profile",
                    entity_id=str(prof.id),
                    label=clean_label,
                    role_or_title=clean_title,
                    description=clean_summary,
                    summary=clean_title,
                )
            )

    # 2. Experiências profissionais confirmadas (entidade 'experience')
    for exp in bundle.experiences:
        if exp.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(exp.user_id) != user_id_str:
            continue
        fact_key = f"experience:{exp.id}"
        clean_role = _clean_and_redact(exp.role, max_length=200, stats=pii_stats) or "Experiência"
        clean_company = (
            _clean_and_redact(exp.company, max_length=200, stats=pii_stats) or "Organização"
        )
        clean_label = (
            sanitize_plain_text(f"{clean_role} — {clean_company}", max_length=200)
            or "Experiência Profissional"
        )
        period_str = _format_period_label(
            exp.start_date, exp.end_date, exp.is_current, target_language
        )
        clean_desc = _clean_and_redact(exp.description, max_length=2000, stats=pii_stats)
        tech_list: list[str] = []
        seen_techs: set[str] = set()
        for raw_t in list(exp.technologies or []) + list(exp.related_skills or []):
            clean_t = _clean_and_redact(str(raw_t), max_length=80, stats=pii_stats)
            if clean_t and clean_t.lower() not in seen_techs:
                seen_techs.add(clean_t.lower())
                tech_list.append(clean_t)
                if len(tech_list) >= 30:
                    break
        candidates_by_type["experience"].append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="experience",
                entity_id=str(exp.id),
                label=clean_label,
                company_or_institution=clean_company,
                role_or_title=clean_role,
                period=period_str or None,
                description=clean_desc,
                technologies=tech_list,
                summary=sanitize_plain_text(exp.experience_type, max_length=100),
                eligible_as_target_role=bool(exp.eligible_as_target_role),
            )
        )

    # 3. Projetos profissionais confirmados (entidade 'project' — nunca fabrica data com updated_at)
    for proj in bundle.projects:
        if proj.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(proj.user_id) != user_id_str:
            continue
        fact_key = f"project:{proj.id}"
        clean_name = (
            _clean_and_redact(proj.name, max_length=200, stats=pii_stats) or "Projeto Profissional"
        )
        clean_role = _clean_and_redact(proj.role, max_length=200, stats=pii_stats)
        clean_desc = _clean_and_redact(proj.description, max_length=2000, stats=pii_stats)
        clean_results = _clean_and_redact(
            proj.verified_results, max_length=1500, stats=pii_stats
        )
        tech_list = []
        seen_techs = set()
        for raw_t in proj.technologies or []:
            clean_t = _clean_and_redact(str(raw_t), max_length=80, stats=pii_stats)
            if clean_t and clean_t.lower() not in seen_techs:
                seen_techs.add(clean_t.lower())
                tech_list.append(clean_t)
                if len(tech_list) >= 30:
                    break
        candidates_by_type["project"].append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="project",
                entity_id=str(proj.id),
                label=clean_name,
                company_or_institution=None,
                role_or_title=clean_role,
                period=None,  # Projetos sem data factual confirmada nunca inferem updated_at/created_at
                description=clean_desc,
                verified_results=clean_results,
                technologies=tech_list,
                summary=clean_role,
            )
        )

    # 4. Formação acadêmica confirmada (entidade 'education')
    for edu in bundle.educations:
        if edu.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(edu.user_id) != user_id_str:
            continue
        fact_key = f"education:{edu.id}"
        clean_course = _clean_and_redact(edu.course, max_length=200, stats=pii_stats) or "Curso"
        clean_inst = (
            _clean_and_redact(edu.institution, max_length=200, stats=pii_stats) or "Instituição"
        )
        clean_label = (
            sanitize_plain_text(f"{clean_course} — {clean_inst}", max_length=200)
            or "Formação Acadêmica"
        )
        period_str = _format_period_label(
            edu.start_date,
            edu.expected_graduation_date,
            edu.education_status == "in_progress",
            target_language,
        )
        candidates_by_type["education"].append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="education",
                entity_id=str(edu.id),
                label=clean_label,
                company_or_institution=clean_inst,
                role_or_title=clean_course,
                period=period_str or None,
                summary=_clean_and_redact(edu.field_of_study, max_length=500, stats=pii_stats),
                proficiency=sanitize_plain_text(edu.education_status, max_length=80),
            )
        )

    # 5. Idiomas confirmados (entidade 'language')
    for lang in bundle.languages:
        if lang.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(lang.user_id) != user_id_str:
            continue
        fact_key = f"language:{lang.id}"
        lang_name_raw = getattr(lang, "language_name", None) or getattr(lang, "name", None)
        clean_name = _clean_and_redact(lang_name_raw, max_length=100, stats=pii_stats)
        candidates_by_type["language"].append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="language",
                entity_id=str(lang.id),
                label=clean_name or "Idioma",
                proficiency=sanitize_plain_text(lang.proficiency_level, max_length=80),
            )
        )

    # 6. Competências confirmadas (entidade 'skill')
    for sk in bundle.skills:
        if sk.verification_status != VerificationStatus.CONFIRMED.value:
            continue
        if str(sk.user_id) != user_id_str:
            continue
        fact_key = f"skill:{sk.id}"
        clean_name = _clean_and_redact(sk.name, max_length=150, stats=pii_stats)
        if not clean_name:
            continue
        candidates_by_type["skill"].append(
            AuthorizedFactItem(
                fact_key=fact_key,
                entity_type="skill",
                entity_id=str(sk.id),
                label=clean_name,
                summary=_clean_and_redact(sk.category, max_length=100, stats=pii_stats),
                proficiency=sanitize_plain_text(sk.proficiency_level, max_length=80),
                description=_clean_and_redact(sk.notes, max_length=500, stats=pii_stats),
                technologies=[clean_name],
            )
        )

    # Contexto da oportunidade sanitizado (sem vazar PII nem misturar com competências do usuário)
    sanitized_opp: SanitizedOpportunityContext | None = None
    if verified_opp is not None or verified_app is not None:
        opp_ctx = bundle.opportunity_context
        clean_req_techs = [
            t
            for raw in opp_ctx.required_technologies[:20]
            if (t := _clean_and_redact(raw, max_length=80, stats=pii_stats))
        ]
        clean_des_techs = [
            t
            for raw in opp_ctx.desirable_technologies[:20]
            if (t := _clean_and_redact(raw, max_length=80, stats=pii_stats))
        ]
        clean_all_techs = [
            t
            for raw in opp_ctx.all_technologies[:30]
            if (t := _clean_and_redact(raw, max_length=80, stats=pii_stats))
        ]
        sanitized_opp = SanitizedOpportunityContext(
            title=_clean_and_redact(opp_ctx.title, max_length=255, stats=pii_stats),
            company_name=_clean_and_redact(opp_ctx.company_name, max_length=200, stats=pii_stats),
            seniority_level=sanitize_plain_text(opp_ctx.seniority_level, max_length=64),
            professional_area=sanitize_plain_text(opp_ctx.professional_area, max_length=80),
            employment_type=sanitize_plain_text(opp_ctx.employment_type, max_length=64),
            required_technologies=clean_req_techs,
            desirable_technologies=clean_des_techs,
            all_technologies=clean_all_techs,
            language=sanitize_plain_text(opp_ctx.language, max_length=32),
        )

    # Seleção determinística com orçamento por categoria, teto de fatos e orçamento agregado em bytes
    total_available = sum(len(items) for items in candidates_by_type.values())
    ordered_selected: list[AuthorizedFactItem] = []
    overflow_pool: list[AuthorizedFactItem] = []
    dropped_by_type: dict[str, int] = {}

    category_order = ("profile", "experience", "project", "education", "language", "skill")
    for cat in category_order:
        items = candidates_by_type[cat]
        cap = _ENTITY_CATEGORY_CAPS[cat]
        ordered_selected.extend(items[:cap])
        if len(items) > cap:
            overflow_pool.extend(items[cap:])

    # Se ainda houver folga abaixo de effective_max_facts, aproveita overflow preservando ordem canônica
    remaining_slots = max(0, effective_max_facts - len(ordered_selected))
    if remaining_slots > 0 and overflow_pool:
        ordered_selected.extend(overflow_pool[:remaining_slots])
        overflow_pool = overflow_pool[remaining_slots:]

    truncated_by_fact_limit = False
    if len(ordered_selected) > effective_max_facts:
        extra_dropped = ordered_selected[effective_max_facts:]
        ordered_selected = ordered_selected[:effective_max_facts]
        overflow_pool = extra_dropped + overflow_pool

    for item in overflow_pool:
        truncated_by_fact_limit = True
        dropped_by_type[item.entity_type] = dropped_by_type.get(item.entity_type, 0) + 1

    # Aplicação do orçamento agregado em bytes UTF-8 sobre o payload canônico real do provider (NC-04)
    opp_dump = sanitized_opp.model_dump(mode="json") if sanitized_opp is not None else None
    final_facts: list[AuthorizedFactItem] = []
    final_facts_dumped: list[dict[str, Any]] = []
    truncated_by_byte_budget = False

    for fact in ordered_selected:
        fact_dumped = fact.model_dump(mode="json")
        candidate_payload = {
            "material_type": material_type,
            "target_language": target_language,
            "candidate_confirmed_facts": [*final_facts_dumped, fact_dumped],
            "target_opportunity_context": opp_dump,
        }
        candidate_bytes = len(serialize_canonical_provider_payload(candidate_payload))
        if candidate_bytes > effective_max_bytes:
            truncated_by_byte_budget = True
            dropped_by_type[fact.entity_type] = dropped_by_type.get(fact.entity_type, 0) + 1
            continue
        final_facts.append(fact)
        final_facts_dumped.append(fact_dumped)

    final_payload = {
        "material_type": material_type,
        "target_language": target_language,
        "candidate_confirmed_facts": final_facts_dumped,
        "target_opportunity_context": opp_dump,
    }
    exact_serialized_bytes = len(serialize_canonical_provider_payload(final_payload))

    dropped_total = total_available - len(final_facts)
    trunc_meta = ContextTruncationMetadata(
        total_confirmed_facts_available=total_available,
        included_facts_count=len(final_facts),
        dropped_facts_count=dropped_total,
        dropped_by_entity_type=dropped_by_type,
        truncated_by_fact_limit=truncated_by_fact_limit,
        truncated_by_byte_budget=truncated_by_byte_budget,
        pii_redacted_fields_count=pii_stats["pii_redacted"],
        pii_omitted_fields_count=pii_stats["pii_omitted"],
        serialized_bytes=exact_serialized_bytes,
        max_facts_limit=effective_max_facts,
        max_payload_bytes=effective_max_bytes,
    )

    return AuthorizedAIContext(
        user_id=user_id_str,
        material_type=material_type,
        target_language=target_language,
        authorized_facts=final_facts,
        opportunity=sanitized_opp,
        truncation_metadata=trunc_meta,
    )
