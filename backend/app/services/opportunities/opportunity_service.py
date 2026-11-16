import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import (
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySourceLink,
    OpportunityUserState,
    SeniorityLevel,
    WorkMode,
)
from app.models.profile import (
    Education,
    ProfessionalProject,
    Skill,
    WorkExperience,
)
from app.models.user import User
from app.schemas.opportunity import (
    ManualOpportunityCreate,
    ManualOpportunityUpdate,
    OpportunityListResponse,
    OpportunityMatchEvaluation,
    OpportunityResponse,
    OpportunitySourceLinkResponse,
    OpportunitySourcePublicResponse,
    OpportunityUserStateResponse,
    OpportunityUserStateUpdate,
)
from app.services.opportunities.classification import classify_opportunity
from app.services.opportunities.matching import (
    evaluate_opportunity_for_user,
    resolve_opportunity_areas,
    resolve_opportunity_seniority_and_experience,
)
from app.services.opportunities.sanitization import (
    compute_opportunity_content_hash,
    normalize_canonical_url,
)
from app.services.opportunities.sync_service import ensure_default_sources
from app.services.profile_service import get_or_create_profile


class GlobalOpportunityImmutableError(PermissionError):
    """Lançado quando um usuário tenta alterar um registro global de provedor externo."""


def _build_status_uncertainty_note(opp: Opportunity) -> str | None:
    st = (opp.source_status or "active").lower()
    if st in {ExternalSourceStatus.UNKNOWN.value, ExternalSourceStatus.UNCONFIRMED.value}:
        return (
            "Esta publicação deixou de aparecer nas consultas parciais mais recentes da fonte, "
            "sem confirmação explícita de encerramento."
        )
    if st == ExternalSourceStatus.SOURCE_UNAVAILABLE.value:
        return "A fonte de origem esteve temporariamente indisponível na última verificação."
    if opp.source is not None and opp.source.last_error_summary:
        return (
            f"Última verificação da fonte ({opp.source.name}) registrou falha temporária; "
            "estado preservado."
        )
    if opp.missing_sync_count > 0 and st == ExternalSourceStatus.ACTIVE.value:
        return (
            f"Ausente em {opp.missing_sync_count} consulta(s) recente(s) de feed limitado; "
            "mantida como aberta."
        )
    return None


def _serialize_source_links(opp: Opportunity) -> list[OpportunitySourceLinkResponse]:
    links = list(getattr(opp, "source_links", None) or [])
    result: list[OpportunitySourceLinkResponse] = []
    for link in links:
        src = link.source or opp.source
        result.append(
            OpportunitySourceLinkResponse(
                id=link.id,
                source_id=link.source_id,
                source_slug=src.slug if src is not None else "unknown",
                source_name=src.name if src is not None else "Fonte externa",
                external_id=link.external_id,
                source_url=link.source_url,
                application_url=link.application_url,
                is_primary=link.is_primary,
                source_status=link.source_status,
                published_at=link.published_at,
                deadline_at=link.deadline_at,
                location_text=link.location_text,
                eligible_countries=list(link.eligible_countries or []),
                salary_min=link.salary_min,
                salary_max=link.salary_max,
                salary_currency=link.salary_currency,
                salary_period=link.salary_period,
                first_seen_at=link.first_seen_at,
                last_seen_at=link.last_seen_at,
                last_checked_at=link.last_checked_at,
                missing_sync_count=link.missing_sync_count,
            )
        )
    if not result and opp.source_id is not None and opp.source is not None:
        result.append(
            OpportunitySourceLinkResponse(
                id=opp.id,
                source_id=opp.source_id,
                source_slug=opp.source.slug,
                source_name=opp.source.name,
                external_id=str(opp.external_id or opp.id),
                source_url=opp.source_url,
                application_url=opp.application_url,
                is_primary=True,
                source_status=opp.source_status,
                published_at=opp.published_at,
                deadline_at=opp.deadline_at,
                location_text=opp.location_text,
                eligible_countries=list(opp.eligible_countries or []),
                salary_min=opp.salary_min,
                salary_max=opp.salary_max,
                salary_currency=opp.salary_currency,
                salary_period=opp.salary_period,
                first_seen_at=opp.first_seen_at,
                last_seen_at=opp.last_seen_at,
                last_checked_at=opp.last_status_check_at or opp.last_seen_at,
                missing_sync_count=opp.missing_sync_count,
            )
        )
    return result


def _load_user_matching_context(db: Session, user_id: uuid.UUID):
    skills = db.execute(select(Skill).where(Skill.user_id == user_id)).scalars().all()
    experiences = db.execute(
        select(WorkExperience).where(WorkExperience.user_id == user_id)
    ).scalars().all()
    educations = db.execute(
        select(Education).where(Education.user_id == user_id)
    ).scalars().all()
    projects = db.execute(
        select(ProfessionalProject).where(ProfessionalProject.user_id == user_id)
    ).scalars().all()
    return (skills, experiences, educations, projects)


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
    primary_area, secondary_areas = resolve_opportunity_areas(opp)
    sen_level, exp_mode, exp_min, exp_pref, exp_sum, _, _ = (
        resolve_opportunity_seniority_and_experience(opp)
    )
    return OpportunityResponse(
        id=opp.id,
        is_manual=opp.created_by_user_id is not None and opp.source_id is None,
        external_id=opp.external_id,
        title=opp.title,
        company_name=opp.company_name,
        description=opp.description,
        opportunity_type=opp.opportunity_type,
        seniority_level=sen_level,
        experience_requirement_mode=exp_mode,
        experience_min_years=exp_min,
        experience_preferred_years=exp_pref,
        experience_summary=exp_sum,
        employment_type=opp.employment_type,
        work_mode=opp.work_mode,
        professional_area=primary_area,
        secondary_areas=secondary_areas,
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
        last_status_check_at=opp.last_status_check_at or opp.last_seen_at,
        status_uncertainty_note=_build_status_uncertainty_note(opp),
        source=source_dto,
        source_links=_serialize_source_links(opp),
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
    seniority_level: str | None = None,
    compatibility: str | None = None,
    work_mode: str | None,
    employment_type: str | None,
    professional_area: str | None = None,
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
    if compatibility:
        if match.overall_compatibility != compatibility:
            return False
    elif not include_excluded and not match.eligible:
        return False

    if opportunity_type:
        if opp.opportunity_type != opportunity_type:
            return False

    if seniority_level:
        resolved_sen = (getattr(opp, "seniority_level", None) or "").strip()
        if not resolved_sen or resolved_sen == SeniorityLevel.UNKNOWN.value:
            resolved_sen = resolve_opportunity_seniority_and_experience(opp)[0]
        if resolved_sen != seniority_level:
            return False

    if work_mode and opp.work_mode != work_mode:
        return False

    if employment_type and opp.employment_type != employment_type:
        return False

    if professional_area:
        primary_area, secondary_areas = resolve_opportunity_areas(opp)
        if primary_area != professional_area and professional_area not in secondary_areas:
            return False

    if source_slug:
        slug_norm = source_slug.strip().lower()
        if slug_norm == "manual":
            if opp.created_by_user_id is None or opp.source_id is not None:
                return False
        else:
            primary_match = opp.source is not None and opp.source.slug.lower() == slug_norm
            secondary_match = any(
                link.source is not None and link.source.slug.lower() == slug_norm
                for link in (getattr(opp, "source_links", None) or [])
            )
            if not primary_match and not secondary_match:
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
    seniority_level: str | None = None,
    compatibility: str | None = None,
    work_mode: str | None = None,
    employment_type: str | None = None,
    professional_area: str | None = None,
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
    skills, experiences, educations, projects = _load_user_matching_context(db, user.id)

    stmt = (
        select(Opportunity)
        .options(
            selectinload(Opportunity.source),
            selectinload(Opportunity.source_links).selectinload(OpportunitySourceLink.source),
        )
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
            skills=skills,
            experiences=experiences,
            educations=educations,
            projects=projects,
        )
        if _matches_query_filters(
            opp,
            state,
            match,
            q=q,
            opportunity_type=opportunity_type,
            seniority_level=seniority_level,
            compatibility=compatibility,
            work_mode=work_mode,
            employment_type=employment_type,
            professional_area=professional_area,
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
        .options(
            selectinload(Opportunity.source),
            selectinload(Opportunity.source_links).selectinload(OpportunitySourceLink.source),
        )
        .where(
            Opportunity.id == opportunity_id,
            _visible_to_user_filter(user.id),
        )
    ).scalar_one_or_none()
    if opp is None:
        return None

    profile = get_or_create_profile(db, user)
    skills, experiences, educations, projects = _load_user_matching_context(db, user.id)
    state = db.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()
    match = evaluate_opportunity_for_user(
        opp,
        profile,
        skills=skills,
        experiences=experiences,
        educations=educations,
        projects=projects,
    )
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

    decision_manual = classify_opportunity(
        title=payload.title,
        tags=payload.technologies,
        description=payload.description,
        requirements=payload.requirements,
    )
    if payload.professional_area is not None and payload.professional_area.value != "unknown":
        primary_area = payload.professional_area.value
        secondary_areas = list(payload.secondary_areas or [])
    else:
        primary_area = decision_manual.professional_area
        secondary_areas = list(decision_manual.secondary_areas)

    resolved_seniority = (
        payload.seniority_level.value
        if payload.seniority_level is not None
        else decision_manual.seniority_level
    )

    opp = Opportunity(
        source_id=None,
        created_by_user_id=user.id,
        external_id=None,
        title=payload.title,
        company_name=payload.company_name,
        description=payload.description,
        opportunity_type=payload.opportunity_type.value,
        seniority_level=resolved_seniority,
        experience_requirement_mode=decision_manual.experience_requirement_mode,
        experience_min_years=decision_manual.experience_min_years,
        experience_preferred_years=decision_manual.experience_preferred_years,
        experience_summary=decision_manual.experience_summary,
        employment_type=payload.employment_type.value,
        work_mode=payload.work_mode.value,
        professional_area=primary_area,
        secondary_areas=secondary_areas,
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
    skills, experiences, educations, projects = _load_user_matching_context(db, user.id)
    match = evaluate_opportunity_for_user(
        opp,
        profile,
        skills=skills,
        experiences=experiences,
        educations=educations,
        projects=projects,
    )
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
        if (
            field
            in {
                "opportunity_type",
                "seniority_level",
                "employment_type",
                "work_mode",
                "source_status",
                "professional_area",
            }
            and value is not None
        ):
            setattr(opp, field, value.value if hasattr(value, "value") else value)
        elif field == "source_url" and value is not None:
            setattr(opp, field, normalize_canonical_url(value))
        else:
            setattr(opp, field, value)

    if any(k in update_data for k in ("title", "description", "technologies")):
        dec_upd = classify_opportunity(
            title=opp.title,
            tags=list(opp.technologies or []),
            description=opp.description,
            requirements=list(opp.requirements or []),
        )
        if "professional_area" not in update_data:
            opp.professional_area = dec_upd.professional_area
            opp.secondary_areas = list(dec_upd.secondary_areas)
        if "seniority_level" not in update_data:
            opp.seniority_level = dec_upd.seniority_level
        opp.experience_requirement_mode = dec_upd.experience_requirement_mode
        opp.experience_min_years = dec_upd.experience_min_years
        opp.experience_preferred_years = dec_upd.experience_preferred_years
        opp.experience_summary = dec_upd.experience_summary

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
    skills, experiences, educations, projects = _load_user_matching_context(db, user.id)
    state = db.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()
    match = evaluate_opportunity_for_user(
        opp,
        profile,
        skills=skills,
        experiences=experiences,
        educations=educations,
        projects=projects,
    )
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


def list_public_sources(db: Session) -> list[OpportunitySourcePublicResponse]:
    sources = ensure_default_sources(db)
    opps = (
        db.execute(
            select(Opportunity.source_id, Opportunity.source_status).where(
                Opportunity.source_id.is_not(None)
            )
        )
        .all()
    )
    counts_by_src: dict[uuid.UUID, list[int]] = {}
    for src_id, st in opps:
        if src_id is None:
            continue
        bucket = counts_by_src.setdefault(src_id, [0, 0, 0, 0])
        bucket[0] += 1
        st_low = (st or "active").lower()
        if st_low == ExternalSourceStatus.ACTIVE.value:
            bucket[1] += 1
        elif st_low in {
            ExternalSourceStatus.EXPIRED.value,
            ExternalSourceStatus.CLOSED.value,
            ExternalSourceStatus.REMOVED.value,
        }:
            bucket[2] += 1
        else:
            bucket[3] += 1

    result: list[OpportunitySourcePublicResponse] = []
    for src in sources:
        u_cnt, o_cnt, c_cnt, unc_cnt = counts_by_src.get(src.id, [0, 0, 0, 0])
        dto = OpportunitySourcePublicResponse.model_validate(src)
        dto.unique_opportunities_count = u_cnt
        dto.open_opportunities_count = o_cnt
        dto.closed_or_expired_count = c_cnt
        dto.unconfirmed_count = unc_cnt
        result.append(dto)
    return result
