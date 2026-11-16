import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.opportunity import (
    EmploymentType,
    OpportunityType,
    ProfessionalArea,
    WorkMode,
)
from app.models.user import User
from app.schemas.opportunity import (
    ManualOpportunityCreate,
    ManualOpportunityUpdate,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunitySourcePublicResponse,
    OpportunityUserStateResponse,
    OpportunityUserStateUpdate,
)
from app.services.opportunities.opportunity_service import (
    GlobalOpportunityImmutableError,
    create_manual_opportunity,
    get_opportunity_for_user,
    list_opportunities,
    list_public_sources,
    update_manual_opportunity,
    update_opportunity_user_state,
)

router = APIRouter(prefix="/opportunities", tags=["Oportunidades"])


@router.get("/sources", response_model=list[OpportunitySourcePublicResponse])
def list_sources(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[OpportunitySourcePublicResponse]:
    del current_user
    sources = list_public_sources(db)
    return [OpportunitySourcePublicResponse.model_validate(src) for src in sources]


@router.get("", response_model=OpportunityListResponse)
def search_opportunities(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    type: Annotated[OpportunityType | None, Query()] = None,
    work_mode: Annotated[WorkMode | None, Query()] = None,
    employment_type: Annotated[EmploymentType | None, Query()] = None,
    area: Annotated[ProfessionalArea | None, Query()] = None,
    location: Annotated[str | None, Query(max_length=120)] = None,
    country: Annotated[str | None, Query(max_length=120)] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    published_after: Annotated[datetime | None, Query()] = None,
    saved_only: Annotated[bool, Query()] = False,
    include_dismissed: Annotated[bool, Query()] = False,
    include_excluded: Annotated[bool, Query()] = False,
    sort: Annotated[Literal["recent", "oldest"], Query()] = "recent",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> OpportunityListResponse:
    return list_opportunities(
        db,
        current_user,
        q=q,
        opportunity_type=type.value if type else None,
        work_mode=work_mode.value if work_mode else None,
        employment_type=employment_type.value if employment_type else None,
        professional_area=area.value if area else None,
        location=location,
        country=country,
        source_slug=source,
        published_after=published_after,
        saved_only=saved_only,
        include_dismissed=include_dismissed,
        include_excluded=include_excluded,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/manual",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_manual_opportunity(
    payload: ManualOpportunityCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OpportunityResponse:
    return create_manual_opportunity(db, current_user, payload)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity_detail(
    opportunity_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OpportunityResponse:
    item = get_opportunity_for_user(db, current_user, opportunity_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidade não encontrada.",
        )
    return item


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
def edit_manual_opportunity(
    opportunity_id: uuid.UUID,
    payload: ManualOpportunityUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OpportunityResponse:
    try:
        updated = update_manual_opportunity(db, current_user, opportunity_id, payload)
    except GlobalOpportunityImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidade manual não encontrada.",
        )
    return updated


@router.patch(
    "/{opportunity_id}/state",
    response_model=OpportunityUserStateResponse,
)
def patch_opportunity_state(
    opportunity_id: uuid.UUID,
    payload: OpportunityUserStateUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OpportunityUserStateResponse:
    state = update_opportunity_user_state(db, current_user, opportunity_id, payload)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidade não encontrada.",
        )
    return state
