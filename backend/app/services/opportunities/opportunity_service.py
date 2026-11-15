import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import (
    Opportunity,
    OpportunitySource,
    OpportunityUserState,
    WorkMode,
)
from app.models.user import User
from app.schemas.opportunity import (
    ManualOpportunityCreate,
    ManualOpportunityUpdate,
    OpportunityListResponse,
    OpportunityMatchEvaluation,
    OpportunityResponse,
    OpportunitySourcePublicResponse,
    OpportunityUserStateResponse,
    OpportunityUserStateUpdate,
)
from app.services.opportunities.matching import evaluate_opportunity_for_user
from app.services.opportunities.sanitization import (
    compute_opportunity_content_hash,
    normalize_canonical_url,
)
from app.services.opportunities.sync_service import ensure_default_sources
from app.services.profile_service import get_or_create_profile


class GlobalOpportunityImmutableError(PermissionError):
    """Lançado quando um usuário tenta alterar um registro global de provedor externo."""


def _serialize_opportunity(
    opp: Opportunity,
    state: OpportunityUserState | None,
    match: OpportunityMatchEvaluation,
) -> OpportunityResponse:
    source_dto = (
        OpportunitySourcePublicResponse.model_validate(opp.source)
        if opp.source is not None
        else None
    )
    state_dto = (
        OpportunityUserStateResponse(
            is_saved=state.is_saved,
            is_dismissed=state.is_dismissed,
            last_viewed_at=state.last_viewed_at,
        )
        if state is not None
        else OpportunityUserStateResponse()
    )
    return OpportunityResponse(
        id=opp.id,
        is_manual=opp.created_by_user_id is not None and opp.source_id is None,
        external_id=opp.external_id,
        title=opp.title,
        company_name=opp.company_name,
        description=opp.description,
        opportunity_type=opp.opportunity_type,
        employment_type=opp.employment_type,
        work_mode=opp.work_mode,
        location_text=opp.location_text,
        city=opp.city,
        state=opp.state,
        country=opp.country,
        eligible_countries=list(opp.eligible_countries or []),
        eligibility_unknown=opp.eligibility_unknown,
        language=opp.language,
        salary_min=opp.salary_min,
        salary_max=opp.salary_max,
        salary_currency=opp.salary_currency,
        salary_period=opp.salary_period,
        requirements=list(opp.requirements or []),
        technologies=list(opp.technologies or []),
        source_url=opp.source_url,
        application_url=opp.application_url,
        published_at=opp.published_at,
        deadline_at=opp.deadline_at,
        source_status=opp.source_status,
        first_seen_at=opp.first_seen_at,
        last_seen_at=opp.last_seen_at,
        source=source_dto,
        user_state=state_dto,
        match=match,
    )


def _visible_to_user_filter(user_id: uuid.UUID):
    return or_(
        Opportunity.source_id.is_not(None),
        Opportunity.created_by_user_id == user_id,
    )


def _matches_query_filters(
    opp: Opportunity,
    state: OpportunityUserState | None,
    match: OpportunityMatchEvaluation,
    *,
    q: str | None,
    opportunity_type: str | None,
    work_mode: str | None,
    employment_type: str | None,
    location: str | None,
    country: str | None,
    source_slug: str | None,
    published_after: datetime | None,
    saved_only: bool,
    include_dismissed: bool,
    include_excluded: bool,
) -> bool:
    is_saved = state.is_saved if state else False
    is_dismissed = state.is_dismissed if state else False

    if saved_only and not is_saved:
        return False
    if not include_dismissed and is_dismissed:
        return False
    if not include_excluded and not match.eligible:
        return False

    if opportunity_type:
        if opp.opportunity_type != opportunity_type:
            return False

    if work_mode and opp.work_mode != work_mode:
        return False

    if employment_type and opp.employment_type != employment_type:
        return False

    if source_slug:
        slug_norm = source_slug.strip().lower()
        if slug_norm == "manual":
            if opp.created_by_user_id is None or opp.source_id is not None:
                return False
        elif opp.source is None or opp.source.slug.lower() != slug_norm:
            return False

    if published_after is not None:
        ref_dt = opp.published_at or opp.first_seen_at
        if ref_dt.tzinfo is None:
            ref_dt = ref_dt.replace(tzinfo=UTC)
        cmp_after = (
            published_after.replace(tzinfo=UTC)
            if published_after.tzinfo is None
            else published_after
        )
        if ref_dt < cmp_after:
            return False

    if location and location.strip():
        loc_q = location.strip().lower()
        loc_blob = " ".join(
            part
            for part in (
                opp.location_text,
                opp.city,
                opp.state,
                opp.country,
                " ".join(opp.eligible_countries or []),
            )
            if part
        ).lower()
        if loc_q not in loc_blob:
            return False

    if country and country.strip():
        ctry_q = country.strip().lower()
        ctry_blob = " ".join(
            [opp.country or "", opp.location_text or "", " ".join(opp.eligible_countries or [])]
        ).lower()
        if ctry_q not in ctry_blob:
            return False

    if q and q.strip():
        needle = q.strip().lower()
        searchable = " ".join(
            [
                opp.title or "",
                opp.company_name or "",
                opp.description or "",
                " ".join(opp.technologies or []),
                " ".join(opp.requirements or []),
                opp.location_text or "",
            ]
        ).lower()
        if needle not in searchable:
            return False

    return True


def list_opportunities(
    db: Session,
    user: User,
    *,
    q: str | None = None,
    opportunity_type: str | None = None,
    work_mode: str | None = None,
    employment_type: str | None = None,
    location: str | None = None,
    country: str | None = None,
    source_slug: str | None = None,
    published_after: datetime | None = None,
    saved_only: bool = False,
    include_dismissed: bool = False,
    include_excluded: bool = False,
    sort: str = "recent",
    page: int = 1,
    page_size: int = 20,
) -> OpportunityListResponse:
    ensure_default_sources(db)
    profile = get_or_create_profile(db, user)

    stmt = (
        select(Opportunity)
        .options(selectinload(Opportunity.source))
        .where(_visible_to_user_filter(user.id))
    )
    opportunities = db.execute(stmt).scalars().all()

    states = db.execute(
        select(OpportunityUserState).where(OpportunityUserState.user_id == user.id)
    ).scalars().all()
    state_by_opp_id = {st.opportunity_id: st for st in states}

    evaluated: list[tuple[Opportunity, OpportunityUserState | None, OpportunityMatchEvaluation]] = []
    for opp in opportunities:
        state = state_by_opp_id.get(opp.id)
        match = evaluate_opportunity_for_user(
            opp,
            profile,
            target_category=opportunity_type,
        )
        if _matches_query_filters(
            opp,
            state,
            match,
            q=q,
            opportunity_type=opportunity_type,
            work_mode=work_mode,
            employment_type=employment_type,
            location=location,
            country=country,
            source_slug=source_slug,
            published_after=published_after,
            saved_only=saved_only,
            include_dismissed=include_dismissed,
            include_excluded=include_excluded,
        ):
            evaluated.append((opp, state, match))

    def _sort_key(item):
        opp = item[0]
        dt = opp.published_at or opp.first_seen_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (dt.timestamp(), opp.first_seen_at.timestamp())

    if sort == "oldest":
        evaluated.sort(key=_sort_key, reverse=False)
    else:
        evaluated.sort(key=_sort_key, reverse=True)

    total = len(evaluated)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * page_size
    end = start + page_size

    items = [
        _serialize_opportunity(opp, state, match)
        for opp, state, match in evaluated[start:end]
    ]

    return OpportunityListResponse(
        items=items,
        total=total,
        page=safe_page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_opportunity_for_user(
    db: Session,
    user: User,
    opportunity_id: uuid.UUID,
) -> OpportunityResponse | None:
    opp = db.execute(
        select(Opportunity)
        .options(selectinload(Opportunity.source))
        .where(
            Opportunity.id == opportunity_id,
            _visible_to_user_filter(user.id),
        )
    ).scalar_one_or_none()
    if opp is None:
        return None

    profile = get_or_create_profile(db, user)
    state = db.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()
    match = evaluate_opportunity_for_user(opp, profile)
    return _serialize_opportunity(opp, state, match)


def create_manual_opportunity(
    db: Session,
    user: User,
    payload: ManualOpportunityCreate,
) -> OpportunityResponse:
    now = datetime.now(UTC)
    canonical_source_url = normalize_canonical_url(payload.source_url)

    eligibility_unknown = payload.eligibility_unknown
    if eligibility_unknown is None:
        eligibility_unknown = (
            payload.work_mode == WorkMode.REMOTE
            and not payload.eligible_countries
            and not payload.country
        )

    content_hash = compute_opportunity_content_hash(
        title=payload.title,
        company_name=payload.company_name,
        source_url=canonical_source_url,
        work_mode=payload.work_mode.value,
        employment_type=payload.employment_type.value,
        location_text=payload.location_text,
        description=payload.description,
    )

    opp = Opportunity(
        source_id=None,
        created_by_user_id=user.id,
        external_id=None,
        title=payload.title,
        company_name=payload.company_name,
        description=payload.description,
        opportunity_type=payload.opportunity_type.value,
        employment_type=payload.employment_type.value,
        work_mode=payload.work_mode.value,
        location_text=payload.location_text,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        eligible_countries=payload.eligible_countries,
        eligibility_unknown=eligibility_unknown,
        language=payload.language,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        salary_currency=payload.salary_currency,
        salary_period=payload.salary_period,
        requirements=payload.requirements,
        technologies=payload.technologies,
        source_url=canonical_source_url,
        application_url=payload.application_url,
        published_at=payload.published_at or now,
        deadline_at=None,
        source_status="active",
        first_seen_at=now,
        last_seen_at=now,
        last_status_check_at=now,
        missing_sync_count=0,
        content_hash=content_hash,
        raw_metadata={"manual": True},
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)

    profile = get_or_create_profile(db, user)
    match = evaluate_opportunity_for_user(opp, profile)
    return _serialize_opportunity(opp, None, match)


def update_manual_opportunity(
    db: Session,
    user: User,
    opportunity_id: uuid.UUID,
    payload: ManualOpportunityUpdate,
) -> OpportunityResponse | None:
    opp = db.execute(
        select(Opportunity)
        .options(selectinload(Opportunity.source))
        .where(Opportunity.id == opportunity_id)
    ).scalar_one_or_none()
    if opp is None:
        return None

    if opp.source_id is not None:
        raise GlobalOpportunityImmutableError(
            "Oportunidades coletadas de provedores externos não podem ser editadas por usuários."
        )
    if opp.created_by_user_id != user.id:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in {"opportunity_type", "employment_type", "work_mode", "source_status"} and value is not None:
            setattr(opp, field, value.value if hasattr(value, "value") else value)
        elif field == "source_url" and value is not None:
            setattr(opp, field, normalize_canonical_url(value))
        else:
            setattr(opp, field, value)

    opp.content_hash = compute_opportunity_content_hash(
        title=opp.title,
        company_name=opp.company_name,
        source_url=opp.source_url,
        work_mode=opp.work_mode,
        employment_type=opp.employment_type,
        location_text=opp.location_text,
        description=opp.description,
    )
    db.commit()
    db.refresh(opp)

    profile = get_or_create_profile(db, user)
    state = db.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()
    match = evaluate_opportunity_for_user(opp, profile)
    return _serialize_opportunity(opp, state, match)


def update_opportunity_user_state(
    db: Session,
    user: User,
    opportunity_id: uuid.UUID,
    payload: OpportunityUserStateUpdate,
) -> OpportunityUserStateResponse | None:
    opp = db.execute(
        select(Opportunity).where(
            Opportunity.id == opportunity_id,
            _visible_to_user_filter(user.id),
        )
    ).scalar_one_or_none()
    if opp is None:
        return None

    state = db.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()

    if state is None:
        is_saved = bool(payload.is_saved) if payload.is_saved is not None else False
        is_dismissed = bool(payload.is_dismissed) if payload.is_dismissed is not None else False
        if is_dismissed and payload.is_dismissed is True:
            is_saved = False
        elif is_saved and payload.is_saved is True:
            is_dismissed = False
        state = OpportunityUserState(
            user_id=user.id,
            opportunity_id=opp.id,
            is_saved=is_saved,
            is_dismissed=is_dismissed,
            last_viewed_at=datetime.now(UTC) if payload.mark_viewed else None,
        )
        db.add(state)
    else:
        if payload.is_saved is not None:
            state.is_saved = payload.is_saved
            if payload.is_saved:
                state.is_dismissed = False
        if payload.is_dismissed is not None:
            state.is_dismissed = payload.is_dismissed
            if payload.is_dismissed:
                state.is_saved = False
        if payload.mark_viewed:
            state.last_viewed_at = datetime.now(UTC)

    db.commit()
    db.refresh(state)
    return OpportunityUserStateResponse(
        is_saved=state.is_saved,
        is_dismissed=state.is_dismissed,
        last_viewed_at=state.last_viewed_at,
    )


def list_public_sources(db: Session) -> list[OpportunitySource]:
    return ensure_default_sources(db)
