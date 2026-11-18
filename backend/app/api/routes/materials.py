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
    MaterialCreateRequest,
    MaterialExportResponse,
    MaterialLinkRequest,
    MaterialPreAnalysisResponse,
    MaterialPreAnalyzeRequest,
    MaterialRegenerateRequest,
    MaterialResponse,
    MaterialSummaryResponse,
    MaterialUnlinkRequest,
    MaterialVersionDeriveRequest,
    MaterialVersionUpdateRequest,
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


def _handle_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MaterialNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, MaterialImmutableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, MaterialPreconditionError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
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
) -> list[MaterialSummaryResponse]:
    try:
        return list_materials(
            db,
            current_user,
            opportunity_id=opportunity_id,
            application_id=application_id,
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
