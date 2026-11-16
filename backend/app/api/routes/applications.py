import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import ApplicationStatus
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationIndicatorsResponse,
    ApplicationKanbanResponse,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusChangeRequest,
    ApplicationUpdate,
)
from app.services.application_service import (
    ApplicationDuplicateError,
    ApplicationHistoryProtectedError,
    ApplicationOpportunityNotFoundError,
    change_application_status,
    compute_application_indicators,
    create_application,
    delete_application,
    get_application_detail,
    get_applications_kanban,
    list_applications,
    update_application,
    _base_user_applications_stmt,
)

router = APIRouter(prefix="/applications", tags=["Candidaturas"])


@router.get("/kanban", response_model=ApplicationKanbanResponse)
def read_applications_kanban(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> ApplicationKanbanResponse:
    return get_applications_kanban(db, current_user, q=q)


@router.get("/indicators", response_model=ApplicationIndicatorsResponse)
def read_application_indicators(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationIndicatorsResponse:
    rows = list(db.execute(_base_user_applications_stmt(current_user.id)).scalars().all())
    return compute_application_indicators(rows)


@router.get("", response_model=ApplicationListResponse)
def read_applications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    include_closed: Annotated[bool, Query()] = True,
    closed_only: Annotated[bool, Query()] = False,
    opportunity_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    sort: Annotated[Literal["updated_desc", "created_desc", "deadline_asc"], Query()] = "updated_desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ApplicationListResponse:
    return list_applications(
        db,
        current_user,
        status_filter=status_filter.value if status_filter else None,
        include_closed=include_closed,
        closed_only=closed_only,
        opportunity_id=opportunity_id,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_application(
    payload: ApplicationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationResponse:
    try:
        return create_application(db, current_user, payload)
    except ApplicationOpportunityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ApplicationDuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/{application_id}", response_model=ApplicationResponse)
def read_application_detail(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationResponse:
    item = get_application_detail(db, current_user, application_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.put("/{application_id}", response_model=ApplicationResponse)
@router.patch("/{application_id}", response_model=ApplicationResponse)
def edit_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationResponse:
    item = update_application(db, current_user, application_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.patch("/{application_id}/status", response_model=ApplicationResponse)
def move_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusChangeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationResponse:
    try:
        item = change_application_status(db, current_user, application_id, payload)
    except ApplicationDuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_application(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    confirm_history_deletion: Annotated[bool, Query()] = False,
) -> Response:
    try:
        deleted = delete_application(
            db,
            current_user,
            application_id,
            confirm_history_deletion=confirm_history_deletion,
        )
    except ApplicationHistoryProtectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
