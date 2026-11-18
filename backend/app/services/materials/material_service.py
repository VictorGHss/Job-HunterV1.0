from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.base import utc_now
from app.models.application import Application
from app.models.material import (
    ApplicationMaterial,
    ApplicationMaterialLink,
    ApplicationMaterialVersion,
    MaterialType,
    MaterialVersionOrigin,
)
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.material import (
    AnyMaterialStructuredContent,
    ApplicationAnswerUserInput,
    ApplicationAnswersStructuredContent,
    ContactInclusionOptions,
    CoverLetterStructuredContent,
    ExportFormat,
    FreelanceProposalStructuredContent,
    MaterialCreateRequest,
    MaterialExportResponse,
    MaterialLinkRequest,
    MaterialLinkResponse,
    MaterialPreAnalysisResponse,
    MaterialPreAnalyzeRequest,
    MaterialRegenerateRequest,
    MaterialResponse,
    MaterialSummaryResponse,
    MaterialTypeValue,
    MaterialUnlinkRequest,
    MaterialVersionDeriveRequest,
    MaterialVersionResponse,
    MaterialVersionUpdateRequest,
    MissingRequirementItem,
    PendingUserInputField,
    RecruiterMessageStructuredContent,
    ResumeStructuredContent,
    TargetLanguage,
    UnconfirmedWarningItem,
    WritingGenerationOptions,
)
from app.services.materials.application_answers_composer import (
    analyze_questions_preview,
    compose_application_answers,
    reconcile_application_answers,
    render_application_answers_markdown,
    render_application_answers_plain_text,
)
from app.services.materials.cover_letter_composer import (
    compose_cover_letter,
    reconcile_cover_letter,
    render_cover_letter_markdown,
    render_cover_letter_plain_text,
)
from app.services.materials.fact_selector import build_authorized_fact_bundle
from app.services.materials.freelance_proposal_composer import (
    build_freelance_pending_fields,
    compose_freelance_proposal,
    reconcile_freelance_proposal,
    render_freelance_proposal_markdown,
    render_freelance_proposal_plain_text,
)
from app.services.materials.recruiter_message_composer import (
    compose_recruiter_message,
    reconcile_recruiter_message,
    render_recruiter_message_markdown,
    render_recruiter_message_plain_text,
)
from app.services.materials.resume_composer import (
    compose_deterministic_resume,
    reconcile_edited_structured_content,
    render_material_markdown,
    render_material_plain_text,
)
from app.services.materials.writing_common import determine_compatible_material_types
from app.services.opportunities.sanitization import sanitize_plain_text

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class MaterialNotFoundError(Exception):
    pass


class MaterialPreconditionError(Exception):
    pass


class MaterialImmutableError(Exception):
    pass


def _material_load_options():
    return (
        selectinload(ApplicationMaterial.opportunity),
        selectinload(ApplicationMaterial.versions),
        selectinload(ApplicationMaterial.links).selectinload(ApplicationMaterialLink.application),
        selectinload(ApplicationMaterial.links).selectinload(ApplicationMaterialLink.version),
    )


def _get_user_material(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ApplicationMaterial:
    stmt = (
        select(ApplicationMaterial)
        .options(*_material_load_options())
        .where(
            ApplicationMaterial.id == material_id,
            ApplicationMaterial.user_id == user.id,
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    material = db.scalar(stmt)
    if material is None:
        raise MaterialNotFoundError("Material não encontrado.")
    return material


def _get_user_application(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> Application:
    stmt = (
        select(Application)
        .options(selectinload(Application.opportunity))
        .where(
            Application.id == application_id,
            Application.user_id == user.id,
        )
    )
    app = db.scalar(stmt)
    if app is None:
        raise MaterialNotFoundError("Candidatura não encontrada.")
    return app


def _get_opportunity(db: Session, user: User, opportunity_id: uuid.UUID) -> Opportunity:
    """Carrega uma oportunidade verificando a política de autorização de acesso.

    Permite:
    - Oportunidades públicas/importadas: source_id IS NOT NULL.
    - Oportunidades privadas criadas pelo próprio usuário autenticado.

    Oportunidades privadas de terceiros retornam 404 idêntico ao de registro inexistente,
    sem revelar se a oportunidade existe.
    """
    stmt = select(Opportunity).where(
        Opportunity.id == opportunity_id,
        or_(
            Opportunity.source_id.is_not(None),
            Opportunity.created_by_user_id == user.id,
        ),
    )
    opp = db.scalar(stmt)
    if opp is None:
        raise MaterialNotFoundError("Oportunidade não encontrada.")
    return opp


def _resolve_target_context(
    db: Session,
    user: User,
    *,
    opportunity_id: uuid.UUID | None,
    application_id: uuid.UUID | None,
) -> tuple[Opportunity | None, Application | None]:
    application = _get_user_application(db, user, application_id) if application_id else None
    if opportunity_id is not None:
        opportunity = _get_opportunity(db, user, opportunity_id)
        if (
            application is not None
            and application.opportunity_id is not None
            and application.opportunity_id != opportunity_id
        ):
            raise MaterialPreconditionError(
                "A candidatura informada está associada a outra oportunidade."
            )
    else:
        opportunity = application.opportunity if application else None
    return opportunity, application


_DEFAULT_TITLE_PREFIX: dict[str, dict[str, str]] = {
    MaterialType.RESUME.value: {"pt-BR": "Currículo", "en": "Resume"},
    MaterialType.COVER_LETTER.value: {"pt-BR": "Carta de Apresentação", "en": "Cover Letter"},
    MaterialType.RECRUITER_MESSAGE.value: {
        "pt-BR": "Mensagem para Recrutador",
        "en": "Recruiter Message",
    },
    MaterialType.FREELANCE_PROPOSAL.value: {
        "pt-BR": "Proposta Freelance",
        "en": "Freelance Proposal",
    },
    MaterialType.APPLICATION_ANSWERS.value: {
        "pt-BR": "Respostas de Candidatura",
        "en": "Application Answers",
    },
}


def _parse_structured_for_type(
    material_type: str,
    raw_content: dict[str, Any] | AnyMaterialStructuredContent,
) -> AnyMaterialStructuredContent:
    payload = (
        raw_content.model_dump(mode="python")
        if hasattr(raw_content, "model_dump")
        else raw_content
    )
    try:
        if material_type == MaterialType.RESUME.value:
            return ResumeStructuredContent.model_validate(payload)
        if material_type == MaterialType.COVER_LETTER.value:
            return CoverLetterStructuredContent.model_validate(payload)
        if material_type == MaterialType.RECRUITER_MESSAGE.value:
            return RecruiterMessageStructuredContent.model_validate(payload)
        if material_type == MaterialType.FREELANCE_PROPOSAL.value:
            return FreelanceProposalStructuredContent.model_validate(payload)
        if material_type == MaterialType.APPLICATION_ANSWERS.value:
            return ApplicationAnswersStructuredContent.model_validate(payload)
    except ValidationError as exc:
        raise MaterialPreconditionError(
            f"Estrutura incompatível com o tipo de material '{material_type}': {exc.errors()[0].get('msg', 'dados inválidos')}."
        ) from exc
    raise MaterialPreconditionError(f"Tipo de material não suportado: '{material_type}'.")


def _compose_by_type(
    bundle: Any,
    *,
    material_type: str,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    writing_options: WritingGenerationOptions,
    user_instructions: str | None,
) -> tuple[AnyMaterialStructuredContent, dict[str, Any]]:
    try:
        if material_type == MaterialType.RESUME.value:
            return compose_deterministic_resume(
                bundle,
                target_language=target_language,
                contact_options=contact_options,
                user_instructions=user_instructions,
            )
        if material_type == MaterialType.COVER_LETTER.value:
            return compose_cover_letter(
                bundle,
                target_language=target_language,
                contact_options=contact_options,
                writing_options=writing_options,
                user_instructions=user_instructions,
            )
        if material_type == MaterialType.RECRUITER_MESSAGE.value:
            return compose_recruiter_message(
                bundle,
                target_language=target_language,
                contact_options=contact_options,
                writing_options=writing_options,
                user_instructions=user_instructions,
            )
        if material_type == MaterialType.FREELANCE_PROPOSAL.value:
            return compose_freelance_proposal(
                bundle,
                target_language=target_language,
                contact_options=contact_options,
                writing_options=writing_options,
                user_instructions=user_instructions,
            )
        if material_type == MaterialType.APPLICATION_ANSWERS.value:
            return compose_application_answers(
                bundle,
                target_language=target_language,
                contact_options=contact_options,
                writing_options=writing_options,
                user_instructions=user_instructions,
            )
    except ValueError as exc:
        raise MaterialPreconditionError(str(exc)) from exc
    raise MaterialPreconditionError(f"Tipo de material não suportado: '{material_type}'.")


def _reconcile_by_type(
    material_type: str,
    previous: AnyMaterialStructuredContent,
    edited: AnyMaterialStructuredContent,
    snapshot: dict[str, Any],
) -> AnyMaterialStructuredContent:
    try:
        if material_type == MaterialType.RESUME.value:
            assert isinstance(previous, ResumeStructuredContent) and isinstance(
                edited, ResumeStructuredContent
            )
            return reconcile_edited_structured_content(previous, edited, snapshot)
        if material_type == MaterialType.COVER_LETTER.value:
            assert isinstance(previous, CoverLetterStructuredContent) and isinstance(
                edited, CoverLetterStructuredContent
            )
            return reconcile_cover_letter(previous, edited, snapshot)
        if material_type == MaterialType.RECRUITER_MESSAGE.value:
            assert isinstance(previous, RecruiterMessageStructuredContent) and isinstance(
                edited, RecruiterMessageStructuredContent
            )
            return reconcile_recruiter_message(previous, edited, snapshot)
        if material_type == MaterialType.FREELANCE_PROPOSAL.value:
            assert isinstance(previous, FreelanceProposalStructuredContent) and isinstance(
                edited, FreelanceProposalStructuredContent
            )
            return reconcile_freelance_proposal(previous, edited, snapshot)
        if material_type == MaterialType.APPLICATION_ANSWERS.value:
            assert isinstance(previous, ApplicationAnswersStructuredContent) and isinstance(
                edited, ApplicationAnswersStructuredContent
            )
            return reconcile_application_answers(previous, edited, snapshot)
    except ValueError as exc:
        raise MaterialPreconditionError(str(exc)) from exc
    raise MaterialPreconditionError(f"Tipo de material não suportado: '{material_type}'.")


def _render_by_type(
    material_type: str,
    structured: AnyMaterialStructuredContent,
    language: TargetLanguage,
) -> tuple[str, str]:
    if material_type == MaterialType.RESUME.value:
        assert isinstance(structured, ResumeStructuredContent)
        return (
            render_material_markdown(structured, language=language),
            render_material_plain_text(structured, language=language),
        )
    if material_type == MaterialType.COVER_LETTER.value:
        assert isinstance(structured, CoverLetterStructuredContent)
        return (
            render_cover_letter_markdown(structured, language=language),
            render_cover_letter_plain_text(structured, language=language),
        )
    if material_type == MaterialType.RECRUITER_MESSAGE.value:
        assert isinstance(structured, RecruiterMessageStructuredContent)
        return (
            render_recruiter_message_markdown(structured, language=language),
            render_recruiter_message_plain_text(structured, language=language),
        )
    if material_type == MaterialType.FREELANCE_PROPOSAL.value:
        assert isinstance(structured, FreelanceProposalStructuredContent)
        return (
            render_freelance_proposal_markdown(structured, language=language),
            render_freelance_proposal_plain_text(structured, language=language),
        )
    if material_type == MaterialType.APPLICATION_ANSWERS.value:
        assert isinstance(structured, ApplicationAnswersStructuredContent)
        return (
            render_application_answers_markdown(structured, language=language),
            render_application_answers_plain_text(structured, language=language),
        )
    raise MaterialPreconditionError(f"Tipo de material não suportado: '{material_type}'.")


def _count_blocking_pending_fields(structured: AnyMaterialStructuredContent) -> int:
    if isinstance(structured, FreelanceProposalStructuredContent):
        return sum(
            1 for field in structured.pending_fields if field.required and field.status == "pending"
        )
    if isinstance(structured, ApplicationAnswersStructuredContent):
        return sum(
            1
            for item in structured.items
            if item.requires_user_input
            or item.status == "needs_user_input"
            or not (item.answer_text and item.answer_text.strip())
        )
    return 0


def _serialize_version(
    version: ApplicationMaterialVersion,
    *,
    material_type: str,
    max_version_number: int,
    linked_version_ids: set[uuid.UUID],
    target_language: TargetLanguage,
) -> MaterialVersionResponse:
    structured = _parse_structured_for_type(material_type, version.structured_content)
    markdown, plain_text = _render_by_type(material_type, structured, target_language)
    pending_count = _count_blocking_pending_fields(structured)
    is_linked = version.id in linked_version_ids
    is_mutable = (
        not version.is_approved
        and not is_linked
        and version.version_number == max_version_number
    )
    warnings = [
        UnconfirmedWarningItem.model_validate(item)
        for item in (version.unconfirmed_warnings or [])
    ]
    missing = [
        MissingRequirementItem.model_validate(item)
        for item in (version.missing_requirements or [])
    ]
    return MaterialVersionResponse(
        id=version.id,
        material_id=version.material_id,
        material_type=material_type,
        version_number=version.version_number,
        origin=version.origin,
        parent_version_id=version.parent_version_id,
        user_instructions=version.user_instructions,
        structured_content=structured,
        source_facts_snapshot=dict(version.source_facts_snapshot or {}),
        unconfirmed_warnings=warnings,
        missing_requirements=missing,
        rendered_markdown=markdown,
        rendered_plain_text=plain_text,
        has_blocking_pending_fields=pending_count > 0,
        pending_requirements_count=pending_count,
        is_approved=version.is_approved,
        approved_at=version.approved_at,
        is_linked_to_any_application=is_linked,
        is_mutable=is_mutable,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _serialize_material(material: ApplicationMaterial) -> MaterialResponse:
    versions_sorted = sorted(material.versions, key=lambda v: v.version_number, reverse=True)
    max_ver = versions_sorted[0].version_number if versions_sorted else 0
    linked_version_ids = {link.version_id for link in material.links}
    lang: TargetLanguage = "en" if material.target_language == "en" else "pt-BR"

    version_responses = [
        _serialize_version(
            ver,
            material_type=material.material_type,
            max_version_number=max_ver,
            linked_version_ids=linked_version_ids,
            target_language=lang,
        )
        for ver in versions_sorted
    ]
    links_sorted = sorted(material.links, key=lambda lk: lk.linked_at, reverse=True)
    link_responses = [
        MaterialLinkResponse(
            id=lk.id,
            application_id=lk.application_id,
            application_role_title=lk.application.role_title if lk.application else None,
            application_company_name=lk.application.company_name if lk.application else None,
            material_id=lk.material_id,
            version_id=lk.version_id,
            version_number=lk.version.version_number if lk.version else 0,
            linked_at=lk.linked_at,
            unlinked_at=lk.unlinked_at,
            is_active=lk.unlinked_at is None,
        )
        for lk in links_sorted
    ]

    return MaterialResponse(
        id=material.id,
        opportunity_id=material.opportunity_id,
        opportunity_title=material.opportunity.title if material.opportunity else None,
        opportunity_company_name=material.opportunity.company_name if material.opportunity else None,
        material_type=material.material_type,
        title=material.title,
        target_language=material.target_language,
        latest_version_number=max_ver,
        has_approved_version=any(v.is_approved for v in versions_sorted),
        versions=version_responses,
        links=link_responses,
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def _serialize_summary(material: ApplicationMaterial) -> MaterialSummaryResponse:
    versions_sorted = sorted(material.versions, key=lambda v: v.version_number, reverse=True)
    latest = versions_sorted[0] if versions_sorted else None
    active_links = sum(1 for lk in material.links if lk.unlinked_at is None)
    return MaterialSummaryResponse(
        id=material.id,
        opportunity_id=material.opportunity_id,
        opportunity_title=material.opportunity.title if material.opportunity else None,
        opportunity_company_name=material.opportunity.company_name if material.opportunity else None,
        material_type=material.material_type,
        title=material.title,
        target_language=material.target_language,
        latest_version_number=latest.version_number if latest else 0,
        latest_version_id=latest.id if latest else None,
        latest_is_approved=latest.is_approved if latest else False,
        has_approved_version=any(v.is_approved for v in versions_sorted),
        active_links_count=active_links,
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def pre_analyze_material(
    db: Session,
    user: User,
    payload: MaterialPreAnalyzeRequest,
) -> MaterialPreAnalysisResponse:
    opportunity, application = _resolve_target_context(
        db,
        user,
        opportunity_id=payload.opportunity_id,
        application_id=payload.application_id,
    )
    bundle = build_authorized_fact_bundle(
        db,
        user,
        opportunity=opportunity,
        application=application,
        target_language=payload.target_language,
    )
    additional_needed: list[PendingUserInputField] = []
    if payload.material_type == MaterialType.FREELANCE_PROPOSAL.value:
        additional_needed = build_freelance_pending_fields(
            payload.target_language,
            payload.writing_options.freelance_inputs,
        )
    elif payload.material_type == MaterialType.APPLICATION_ANSWERS.value:
        additional_needed = analyze_questions_preview(
            bundle,
            target_language=payload.target_language,
            writing_options=payload.writing_options,
        )

    return MaterialPreAnalysisResponse(
        can_generate=bundle.can_generate,
        blocking_reasons=bundle.blocking_reasons,
        material_type=payload.material_type,
        compatible_material_types=determine_compatible_material_types(bundle.opportunity_context),
        target_language=payload.target_language,
        opportunity_context=bundle.opportunity_context,
        contact_preview=bundle.contact_preview,
        used_facts=bundle.used_facts,
        unconfirmed_warnings=bundle.unconfirmed_warnings,
        missing_requirements=bundle.missing_requirements,
        additional_info_needed=additional_needed,
        confirmed_counts=bundle.confirmed_counts,
    )


def list_materials(
    db: Session,
    user: User,
    *,
    opportunity_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
    material_type: MaterialTypeValue | None = None,
) -> list[MaterialSummaryResponse]:
    stmt = (
        select(ApplicationMaterial)
        .options(
            selectinload(ApplicationMaterial.opportunity),
            selectinload(ApplicationMaterial.versions),
            selectinload(ApplicationMaterial.links),
        )
        .where(ApplicationMaterial.user_id == user.id)
    )
    if opportunity_id is not None:
        stmt = stmt.where(ApplicationMaterial.opportunity_id == opportunity_id)
    if material_type is not None:
        stmt = stmt.where(ApplicationMaterial.material_type == material_type)
    if application_id is not None:
        _get_user_application(db, user, application_id)
        stmt = stmt.where(
            ApplicationMaterial.id.in_(
                select(ApplicationMaterialLink.material_id).where(
                    ApplicationMaterialLink.user_id == user.id,
                    ApplicationMaterialLink.application_id == application_id,
                    ApplicationMaterialLink.unlinked_at.is_(None),
                )
            )
        )
    stmt = stmt.order_by(ApplicationMaterial.updated_at.desc())
    materials = list(db.scalars(stmt).all())
    return [_serialize_summary(mat) for mat in materials]


def create_material(
    db: Session,
    user: User,
    payload: MaterialCreateRequest,
) -> MaterialResponse:
    opportunity, application = _resolve_target_context(
        db,
        user,
        opportunity_id=payload.opportunity_id,
        application_id=payload.application_id,
    )
    bundle = build_authorized_fact_bundle(
        db,
        user,
        opportunity=opportunity,
        application=application,
        target_language=payload.target_language,
    )
    if not bundle.can_generate:
        raise MaterialPreconditionError("; ".join(bundle.blocking_reasons))

    structured, snapshot = _compose_by_type(
        bundle,
        material_type=payload.material_type,
        target_language=payload.target_language,
        contact_options=payload.contact_options,
        writing_options=payload.writing_options,
        user_instructions=payload.user_instructions,
    )

    default_title = payload.title
    if not default_title:
        prefix = _DEFAULT_TITLE_PREFIX.get(payload.material_type, {}).get(
            payload.target_language, "Material"
        )
        if bundle.opportunity_context.title and bundle.opportunity_context.company_name:
            default_title = (
                f"{prefix} — {bundle.opportunity_context.title} ({bundle.opportunity_context.company_name})"
            )
        elif bundle.opportunity_context.title:
            default_title = f"{prefix} — {bundle.opportunity_context.title}"
        else:
            default_title = prefix
    default_title = (sanitize_plain_text(default_title, max_length=200) or "Material")[:200]

    material = ApplicationMaterial(
        user_id=user.id,
        opportunity_id=opportunity.id if opportunity else None,
        material_type=payload.material_type,
        title=default_title,
        target_language=payload.target_language,
    )
    db.add(material)
    db.flush()

    version = ApplicationMaterialVersion(
        material_id=material.id,
        version_number=1,
        origin=MaterialVersionOrigin.GENERATED.value,
        parent_version_id=None,
        user_instructions=payload.user_instructions,
        structured_content=structured.model_dump(mode="json"),
        source_facts_snapshot=snapshot,
        unconfirmed_warnings=[item.model_dump(mode="json") for item in bundle.unconfirmed_warnings],
        missing_requirements=[item.model_dump(mode="json") for item in bundle.missing_requirements],
        is_approved=False,
        approved_at=None,
    )
    db.add(version)
    db.commit()
    db.expire_all()

    reloaded = _get_user_material(db, user, material.id)
    return _serialize_material(reloaded)


def get_material_detail(
    db: Session,
    user: User,
    material_id: uuid.UUID,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id)
    return _serialize_material(material)


def _create_next_version_with_lock(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    *,
    build_version_kwargs: Any,
) -> ApplicationMaterial:
    """Aloca próximo número de versão sob lock FOR UPDATE e retry controlado em IntegrityError."""
    attempts = 0
    while True:
        attempts += 1
        material = _get_user_material(db, user, material_id, for_update=True)
        current_max = db.scalar(
            select(func.coalesce(func.max(ApplicationMaterialVersion.version_number), 0)).where(
                ApplicationMaterialVersion.material_id == material.id
            )
        )
        next_number = int(current_max or 0) + 1
        kwargs = build_version_kwargs(material, next_number)
        new_version = ApplicationMaterialVersion(
            material_id=material.id,
            version_number=next_number,
            **kwargs,
        )
        material.updated_at = utc_now()
        db.add(new_version)
        try:
            db.commit()
            db.expire_all()
            return _get_user_material(db, user, material.id)
        except IntegrityError:
            db.rollback()
            if attempts >= 4:
                raise


def update_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialVersionUpdateRequest,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id, for_update=True)
    version = next((v for v in material.versions if v.id == version_id), None)
    if version is None:
        raise MaterialNotFoundError("Versão de material não encontrada.")

    max_ver = max((v.version_number for v in material.versions), default=0)
    is_linked = any(link.version_id == version.id for link in material.links)

    if version.is_approved:
        raise MaterialImmutableError(
            "Versão já aprovada é imutável. Crie uma versão derivada para continuar editando."
        )
    if is_linked:
        raise MaterialImmutableError(
            "Versão vinculada a candidatura é imutável para preservar rastreabilidade. Derive uma nova versão."
        )
    if version.version_number != max_ver:
        raise MaterialImmutableError(
            "Apenas o rascunho da versão mais recente pode ser editado diretamente. Derive uma nova versão."
        )

    previous = _parse_structured_for_type(material.material_type, version.structured_content)
    edited = _parse_structured_for_type(material.material_type, payload.structured_content)
    reconciled = _reconcile_by_type(
        material.material_type,
        previous,
        edited,
        version.source_facts_snapshot,
    )

    version.structured_content = reconciled.model_dump(mode="json")
    version.origin = MaterialVersionOrigin.MANUAL_EDIT.value
    if payload.user_instructions is not None:
        version.user_instructions = payload.user_instructions
    material.updated_at = utc_now()
    db.commit()
    db.expire_all()

    return _serialize_material(_get_user_material(db, user, material.id))


def derive_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialVersionDeriveRequest,
) -> MaterialResponse:
    # Valida existência e propriedade antes de preparar payload derivado
    initial_mat = _get_user_material(db, user, material_id)
    parent = next((v for v in initial_mat.versions if v.id == version_id), None)
    if parent is None:
        raise MaterialNotFoundError("Versão-base não encontrada.")

    parent_structured = _parse_structured_for_type(
        initial_mat.material_type, parent.structured_content
    )
    if payload.structured_content is not None:
        edited_structured = _parse_structured_for_type(
            initial_mat.material_type, payload.structured_content
        )
        next_structured = _reconcile_by_type(
            initial_mat.material_type,
            parent_structured,
            edited_structured,
            parent.source_facts_snapshot,
        )
    else:
        next_structured = parent_structured

    def _build_kwargs(mat: ApplicationMaterial, _next_num: int) -> dict[str, Any]:
        return {
            "origin": MaterialVersionOrigin.DERIVED.value,
            "parent_version_id": parent.id,
            "user_instructions": (
                payload.user_instructions
                if payload.user_instructions is not None
                else parent.user_instructions
            ),
            "structured_content": next_structured.model_dump(mode="json"),
            "source_facts_snapshot": dict(parent.source_facts_snapshot or {}),
            "unconfirmed_warnings": list(parent.unconfirmed_warnings or []),
            "missing_requirements": list(parent.missing_requirements or []),
            "is_approved": False,
            "approved_at": None,
        }

    updated = _create_next_version_with_lock(
        db,
        user,
        material_id,
        build_version_kwargs=_build_kwargs,
    )
    return _serialize_material(updated)


def _preserve_writing_options_on_regenerate(
    material: ApplicationMaterial,
    explicit_options: WritingGenerationOptions | None,
) -> WritingGenerationOptions:
    if explicit_options is not None:
        return explicit_options
    opts = WritingGenerationOptions()
    latest = max(material.versions, key=lambda v: v.version_number, default=None)
    if latest is None:
        return opts
    latest_parsed = _parse_structured_for_type(material.material_type, latest.structured_content)
    if isinstance(latest_parsed, RecruiterMessageStructuredContent):
        opts = opts.model_copy(update={"channel": latest_parsed.channel})
    elif isinstance(latest_parsed, ApplicationAnswersStructuredContent):
        questions = [item.question for item in latest_parsed.items]
        answers = [
            ApplicationAnswerUserInput(
                question=item.question,
                user_answer=item.answer_text if item.status == "user_answered" else None,
            )
            for item in latest_parsed.items
        ]
        opts = opts.model_copy(update={"questions": questions, "initial_answers": answers})
    return opts


def regenerate_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    payload: MaterialRegenerateRequest,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id)
    effective_lang: TargetLanguage = (
        payload.target_language
        or ("en" if material.target_language == "en" else "pt-BR")
    )
    bundle = build_authorized_fact_bundle(
        db,
        user,
        opportunity=material.opportunity,
        application=None,
        target_language=effective_lang,
    )
    if not bundle.can_generate:
        raise MaterialPreconditionError("; ".join(bundle.blocking_reasons))

    effective_writing_opts = _preserve_writing_options_on_regenerate(
        material, payload.writing_options
    )
    structured, snapshot = _compose_by_type(
        bundle,
        material_type=material.material_type,
        target_language=effective_lang,
        contact_options=payload.contact_options,
        writing_options=effective_writing_opts,
        user_instructions=payload.user_instructions,
    )

    def _build_kwargs(mat: ApplicationMaterial, _next_num: int) -> dict[str, Any]:
        latest = max(mat.versions, key=lambda v: v.version_number, default=None)
        mat.target_language = effective_lang
        return {
            "origin": MaterialVersionOrigin.REGENERATED.value,
            "parent_version_id": latest.id if latest else None,
            "user_instructions": payload.user_instructions,
            "structured_content": structured.model_dump(mode="json"),
            "source_facts_snapshot": snapshot,
            "unconfirmed_warnings": [
                item.model_dump(mode="json") for item in bundle.unconfirmed_warnings
            ],
            "missing_requirements": [
                item.model_dump(mode="json") for item in bundle.missing_requirements
            ],
            "is_approved": False,
            "approved_at": None,
        }

    updated = _create_next_version_with_lock(
        db,
        user,
        material_id,
        build_version_kwargs=_build_kwargs,
    )
    return _serialize_material(updated)


def approve_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id, for_update=True)
    version = next((v for v in material.versions if v.id == version_id), None)
    if version is None:
        raise MaterialNotFoundError("Versão de material não encontrada.")

    structured = _parse_structured_for_type(material.material_type, version.structured_content)
    blocking_count = _count_blocking_pending_fields(structured)
    if blocking_count > 0:
        raise MaterialPreconditionError(
            f"Há {blocking_count} informação(ões) obrigatória(s) pendente(s) antes de aprovar esta versão."
        )

    now = utc_now()
    if not version.is_approved:
        version.is_approved = True
        version.approved_at = now
        material.updated_at = now
        db.commit()
        db.expire_all()

    return _serialize_material(_get_user_material(db, user, material.id))


def export_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    fmt: ExportFormat,
) -> MaterialExportResponse:
    material = _get_user_material(db, user, material_id)
    version = next((v for v in material.versions if v.id == version_id), None)
    if version is None:
        raise MaterialNotFoundError("Versão de material não encontrada.")

    structured = _parse_structured_for_type(material.material_type, version.structured_content)
    lang: TargetLanguage = "en" if structured.language == "en" else "pt-BR"
    markdown_text, plain_text = _render_by_type(material.material_type, structured, lang)
    if fmt == "markdown":
        content = markdown_text
        ext = "md"
    else:
        content = plain_text
        ext = "txt"

    raw_slug = _SLUG_RE.sub("-", material.title.lower()).strip("-")[:50] or "curriculo"
    filename = f"{raw_slug}-v{version.version_number}.{ext}"

    return MaterialExportResponse(
        material_id=material.id,
        version_id=version.id,
        version_number=version.version_number,
        format=fmt,
        filename_suggestion=filename,
        content=content,
        is_approved=version.is_approved,
    )


def link_material_version(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    payload: MaterialLinkRequest,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id, for_update=True)
    application = _get_user_application(db, user, payload.application_id)

    version = next((v for v in material.versions if v.id == payload.version_id), None)
    if version is None:
        raise MaterialNotFoundError("A versão informada não pertence a este material.")

    if not version.is_approved:
        raise MaterialPreconditionError(
            "Apenas versões aprovadas podem ser vinculadas a uma candidatura."
        )

    now = utc_now()
    active_links = [
        lk
        for lk in material.links
        if lk.application_id == application.id and lk.unlinked_at is None
    ]
    for existing in active_links:
        existing.unlinked_at = now
    if active_links:
        db.flush()

    new_link = ApplicationMaterialLink(
        user_id=user.id,
        application_id=application.id,
        material_id=material.id,
        version_id=version.id,
        linked_at=now,
        unlinked_at=None,
    )
    db.add(new_link)
    material.updated_at = now
    db.commit()
    db.expire_all()

    return _serialize_material(_get_user_material(db, user, material.id))


def unlink_material(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    payload: MaterialUnlinkRequest,
) -> MaterialResponse:
    material = _get_user_material(db, user, material_id, for_update=True)
    _get_user_application(db, user, payload.application_id)

    active_link = next(
        (
            lk
            for lk in material.links
            if lk.application_id == payload.application_id and lk.unlinked_at is None
        ),
        None,
    )
    if active_link is None:
        raise MaterialNotFoundError("Nenhum vínculo ativo encontrado para esta candidatura.")

    now = utc_now()
    active_link.unlinked_at = now
    material.updated_at = now
    db.commit()
    db.expire_all()

    return _serialize_material(_get_user_material(db, user, material.id))


def delete_material(
    db: Session,
    user: User,
    material_id: uuid.UUID,
) -> None:
    material = _get_user_material(db, user, material_id)
    db.delete(material)
    db.commit()
