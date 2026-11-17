import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import ApplicationStatus
from app.models.user import User
from app.schemas.application import (
    ApplicationAgendaResponse,
    ApplicationAssessmentCreate,
    ApplicationAssessmentResponse,
    ApplicationAssessmentUpdate,
    ApplicationContactCreate,
    ApplicationContactResponse,
    ApplicationContactUpdate,
    ApplicationCreate,
    ApplicationIndicatorsResponse,
    ApplicationInterviewCreate,
    ApplicationInterviewResponse,
    ApplicationInterviewUpdate,
    ApplicationKanbanResponse,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusChangeRequest,
    ApplicationUpdate,
    ExternalInteractionRecordRequest,
    FollowUpTemplateResponse,
    StaleApplicationsResponse,
)
from app.services.application_process_service import (
    create_application_assessment,
    create_application_contact,
    create_application_interview,
    delete_application_assessment,
    delete_application_contact,
    delete_application_interview,
    generate_follow_up_template,
    get_applications_agenda,
    get_stale_applications,
    list_application_assessments,
    list_application_contacts,
    list_application_interviews,
    record_external_interaction,
    update_application_assessment,
    update_application_contact,
    update_application_interview,
)
from app.services.application_service import (
    ApplicationDuplicateError,
    ApplicationHistoryProtectedError,
    ApplicationOpportunityNotFoundError,
    _base_user_applications_stmt,
    _serialize_application,
    change_application_status,
    compute_application_indicators,
    create_application,
    delete_application,
    get_application_detail,
    get_applications_kanban,
    list_applications,
    update_application,
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


@router.get("/agenda", response_model=ApplicationAgendaResponse)
def read_applications_agenda(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    include_overdue: Annotated[bool, Query()] = True,
) -> ApplicationAgendaResponse:
    return get_applications_agenda(
        db,
        current_user,
        days=days,
        include_overdue=include_overdue,
    )


@router.get("/stale", response_model=StaleApplicationsResponse)
def read_stale_applications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    stale_days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> StaleApplicationsResponse:
    return get_stale_applications(
        db,
        current_user,
        stale_days=stale_days,
    )


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


# ---------------------------------------------------------------------------
# Follow-up e Interação Externa (Fase 03.2)
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/follow-up-template",
    response_model=FollowUpTemplateResponse,
)
def read_application_follow_up_template(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FollowUpTemplateResponse:
    template = generate_follow_up_template(db, current_user, application_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return template


@router.post(
    "/{application_id}/external-interaction",
    response_model=ApplicationResponse,
)
def post_application_external_interaction(
    application_id: uuid.UUID,
    payload: ExternalInteractionRecordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationResponse:
    app_row = record_external_interaction(db, current_user, application_id, payload)
    if app_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return _serialize_application(app_row)


# ---------------------------------------------------------------------------
# Entrevistas (Fase 03.2)
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/interviews",
    response_model=list[ApplicationInterviewResponse],
)
def read_application_interviews(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ApplicationInterviewResponse]:
    items = list_application_interviews(db, current_user, application_id)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return items


@router.post(
    "/{application_id}/interviews",
    response_model=ApplicationInterviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_application_interview(
    application_id: uuid.UUID,
    payload: ApplicationInterviewCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationInterviewResponse:
    item = create_application_interview(db, current_user, application_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.patch(
    "/{application_id}/interviews/{interview_id}",
    response_model=ApplicationInterviewResponse,
)
def patch_application_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    payload: ApplicationInterviewUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationInterviewResponse:
    item = update_application_interview(
        db, current_user, application_id, interview_id, payload
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista ou candidatura não encontrada.",
        )
    return item


@router.delete(
    "/{application_id}/interviews/{interview_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_application_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    deleted = delete_application_interview(db, current_user, application_id, interview_id)
    if deleted is None or deleted is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista ou candidatura não encontrada.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Testes Técnicos (Fase 03.2)
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/assessments",
    response_model=list[ApplicationAssessmentResponse],
)
def read_application_assessments(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ApplicationAssessmentResponse]:
    items = list_application_assessments(db, current_user, application_id)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return items


@router.post(
    "/{application_id}/assessments",
    response_model=ApplicationAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_application_assessment(
    application_id: uuid.UUID,
    payload: ApplicationAssessmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationAssessmentResponse:
    item = create_application_assessment(db, current_user, application_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.patch(
    "/{application_id}/assessments/{assessment_id}",
    response_model=ApplicationAssessmentResponse,
)
def patch_application_assessment(
    application_id: uuid.UUID,
    assessment_id: uuid.UUID,
    payload: ApplicationAssessmentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationAssessmentResponse:
    item = update_application_assessment(
        db, current_user, application_id, assessment_id, payload
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teste técnico ou candidatura não encontrada.",
        )
    return item


@router.delete(
    "/{application_id}/assessments/{assessment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_application_assessment(
    application_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    deleted = delete_application_assessment(
        db, current_user, application_id, assessment_id
    )
    if deleted is None or deleted is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teste técnico ou candidatura não encontrada.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Contatos (Fase 03.2)
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/contacts",
    response_model=list[ApplicationContactResponse],
)
def read_application_contacts(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ApplicationContactResponse]:
    items = list_application_contacts(db, current_user, application_id)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return items


@router.post(
    "/{application_id}/contacts",
    response_model=ApplicationContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_application_contact(
    application_id: uuid.UUID,
    payload: ApplicationContactCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationContactResponse:
    item = create_application_contact(db, current_user, application_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada.",
        )
    return item


@router.patch(
    "/{application_id}/contacts/{contact_id}",
    response_model=ApplicationContactResponse,
)
def patch_application_contact(
    application_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: ApplicationContactUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationContactResponse:
    item = update_application_contact(
        db, current_user, application_id, contact_id, payload
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contato ou candidatura não encontrada.",
        )
    return item


@router.delete(
    "/{application_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_application_contact(
    application_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    deleted = delete_application_contact(db, current_user, application_id, contact_id)
    if deleted is None or deleted is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contato ou candidatura não encontrada.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
