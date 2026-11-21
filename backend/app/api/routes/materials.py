from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.material import (
    ExportFormat,
    MaterialAIEnhanceRequest,
    MaterialCreateRequest,
    MaterialExportResponse,
    MaterialLinkRequest,
    MaterialPreAnalysisResponse,
    MaterialPreAnalyzeRequest,
    MaterialRegenerateRequest,
    MaterialResponse,
    MaterialSummaryResponse,
    MaterialTypeValue,
    MaterialUnlinkRequest,
    MaterialVersionDeriveRequest,
    MaterialVersionUpdateRequest,
)
from app.services.materials.ai import (
    AICircuitOpenError,
    AIConfigurationError,
    AIContextAuthorizationError,
    AIDisabledError,
    AIFoundationError,
    AIGroundingRejectedError,
    AIOverlayConflictError,
    AIQuotaExceededError,
    AIReservationNotFoundError,
    AIReservationStateError,
    AIReviewStateError,
    AIStaleSourceVersionError,
    LLMMalformedOutputError,
    LLMProvider,
    LLMProviderError,
    LLMTimeoutError,
    LLMUpstreamError,
    enhance_material_version_with_ai,
    reject_ai_assisted_version,
)
from app.services.materials.export import (
    DocumentExportRenderError,
    DocumentExportValidationError,
    DocumentFormat,
    DocumentTemplateId,
    export_material_document,
)
from app.services.materials.material_service import (
    MaterialImmutableError,
    MaterialNotFoundError,
    MaterialPreconditionError,
    approve_material_version,
    create_material,
    delete_material,
    derive_material_version,
    export_material_version,
    get_material_detail,
    link_material_version,
    list_materials,
    pre_analyze_material,
    regenerate_material_version,
    unlink_material,
    update_material_version,
)

router = APIRouter(prefix="/materials", tags=["Materiais de Candidatura"])


def get_optional_llm_provider() -> LLMProvider | None:
    """Dependência injetável para testes; em produção retorna None para resolução por configuração."""
    return None


def _handle_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MaterialNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (AIContextAuthorizationError, AIReservationNotFoundError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material ou versão não encontrada.",
        )
    if isinstance(exc, MaterialImmutableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (AIStaleSourceVersionError, AIReviewStateError, AIReservationStateError)):
        err_code = getattr(exc, "error_code", "conflict")
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-AI-Error-Code": str(err_code)},
        )
    if isinstance(exc, (AIGroundingRejectedError, AIOverlayConflictError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
            headers={"X-AI-Error-Code": str(exc.error_code)},
        )
    if isinstance(exc, (MaterialPreconditionError, DocumentExportValidationError)):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    if isinstance(exc, AIQuotaExceededError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={
                "Retry-After": str(exc.retry_after_seconds),
                "X-AI-Error-Code": f"quota_exceeded:{exc.scope}",
            },
        )
    if isinstance(exc, AIDisabledError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O aprimoramento assistido por IA está desabilitado nesta instância.",
            headers={"X-AI-Error-Code": "ai_disabled"},
        )
    if isinstance(exc, AIConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuração do serviço de IA indisponível nesta instância.",
            headers={"X-AI-Error-Code": "ai_misconfigured"},
        )
    if isinstance(exc, AICircuitOpenError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de IA temporariamente em proteção contra falhas. Aguarde antes de tentar novamente.",
            headers={
                "Retry-After": str(exc.retry_after_seconds),
                "X-AI-Error-Code": "circuit_open",
            },
        )
    if isinstance(exc, LLMTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="O provedor de IA excedeu o tempo limite de resposta. Tente novamente.",
            headers={"X-AI-Error-Code": "provider_timeout"},
        )
    if isinstance(exc, LLMMalformedOutputError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="O provedor de IA retornou uma resposta estruturada inválida.",
            headers={"X-AI-Error-Code": "malformed_output"},
        )
    if isinstance(exc, (LLMUpstreamError, LLMProviderError)):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha de comunicação com o provedor de IA. Tente novamente em instantes.",
            headers={"X-AI-Error-Code": "provider_error"},
        )
    if isinstance(exc, DocumentExportRenderError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise exc


@router.post("/pre-analyze", response_model=MaterialPreAnalysisResponse)
def pre_analyze_material_endpoint(
    payload: MaterialPreAnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialPreAnalysisResponse:
    try:
        return pre_analyze_material(db, current_user, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.get("", response_model=list[MaterialSummaryResponse])
def list_materials_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    opportunity_id: uuid.UUID | None = Query(default=None),
    application_id: uuid.UUID | None = Query(default=None),
    material_type: MaterialTypeValue | None = Query(default=None),
) -> list[MaterialSummaryResponse]:
    try:
        return list_materials(
            db,
            current_user,
            opportunity_id=opportunity_id,
            application_id=application_id,
            material_type=material_type,
        )
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post("", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
def create_material_endpoint(
    payload: MaterialCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return create_material(db, current_user, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.get("/{material_id}", response_model=MaterialResponse)
def get_material_detail_endpoint(
    material_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return get_material_detail(db, current_user, material_id)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.put("/{material_id}/versions/{version_id}", response_model=MaterialResponse)
def update_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialVersionUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return update_material_version(db, current_user, material_id, version_id, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post(
    "/{material_id}/versions/{version_id}/derive",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def derive_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialVersionDeriveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return derive_material_version(db, current_user, material_id, version_id, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post(
    "/{material_id}/regenerate",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def regenerate_material_version_endpoint(
    material_id: uuid.UUID,
    payload: MaterialRegenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return regenerate_material_version(db, current_user, material_id, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{material_id}/versions/{version_id}/approve", response_model=MaterialResponse)
def approve_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return approve_material_version(db, current_user, material_id, version_id)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post(
    "/{material_id}/versions/{version_id}/ai-enhance",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def ai_enhance_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialAIEnhanceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    injected_provider: Annotated[LLMProvider | None, Depends(get_optional_llm_provider)] = None,
) -> MaterialResponse:
    try:
        return enhance_material_version_with_ai(
            db,
            current_user,
            material_id=material_id,
            version_id=version_id,
            payload=payload,
            injected_provider=injected_provider,
        )
    except (
        MaterialNotFoundError,
        MaterialImmutableError,
        MaterialPreconditionError,
        AIFoundationError,
    ) as exc:
        raise _handle_service_error(exc) from exc


@router.post(
    "/{material_id}/versions/{version_id}/reject-ai",
    response_model=MaterialResponse,
)
def reject_ai_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return reject_ai_assisted_version(
            db,
            current_user,
            material_id=material_id,
            version_id=version_id,
        )
    except (
        MaterialNotFoundError,
        MaterialImmutableError,
        MaterialPreconditionError,
        AIFoundationError,
    ) as exc:
        raise _handle_service_error(exc) from exc


@router.get("/{material_id}/versions/{version_id}/export", response_model=MaterialExportResponse)
def export_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    format: ExportFormat = Query(default="markdown"),
) -> MaterialExportResponse:
    try:
        return export_material_version(db, current_user, material_id, version_id, format)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.get("/{material_id}/versions/{version_id}/download")
def download_material_version_endpoint(
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    format: DocumentFormat = Query(...),
    template: DocumentTemplateId = Query(default="classic_ats"),
    allow_draft: bool = Query(default=False),
) -> Response:
    try:
        artifact = export_material_document(
            db,
            current_user,
            material_id=material_id,
            version_id=version_id,
            export_format=format,
            template_id=template,
            allow_draft=allow_draft,
        )
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": artifact.content_disposition,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Pragma": "no-cache",
            },
        )
    except (
        MaterialNotFoundError,
        MaterialImmutableError,
        MaterialPreconditionError,
        DocumentExportValidationError,
        DocumentExportRenderError,
    ) as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{material_id}/link", response_model=MaterialResponse)
def link_material_version_endpoint(
    material_id: uuid.UUID,
    payload: MaterialLinkRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return link_material_version(db, current_user, material_id, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{material_id}/unlink", response_model=MaterialResponse)
def unlink_material_endpoint(
    material_id: uuid.UUID,
    payload: MaterialUnlinkRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialResponse:
    try:
        return unlink_material(db, current_user, material_id, payload)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_endpoint(
    material_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        delete_material(db, current_user, material_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MaterialNotFoundError, MaterialImmutableError, MaterialPreconditionError) as exc:
        raise _handle_service_error(exc) from exc
