import math
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.application import (
    ACTIVE_APPLICATION_STATUSES,
    APPLICATION_STATUS_LABELS_PT,
    CLOSED_APPLICATION_STATUSES,
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
)
from app.models.opportunity import (
    EmploymentType,
    Opportunity,
    SeniorityLevel,
    WorkMode,
)
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationIndicatorsResponse,
    ApplicationKanbanColumnResponse,
    ApplicationKanbanResponse,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusChangeRequest,
    ApplicationStatusHistoryResponse,
    ApplicationUpdate,
)
from app.services.opportunities.matching import resolve_opportunity_seniority_and_experience
from app.services.opportunities.sanitization import (
    sanitize_external_html_text,
    sanitize_plain_text,
)

_SENT_OR_PROGRESSED_STATUSES = frozenset(
    {
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.ASSESSMENT.value,
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.OFFER.value,
        ApplicationStatus.ACCEPTED.value,
    }
)


class ApplicationOpportunityNotFoundError(LookupError):
    """Lançada quando a oportunidade referenciada não existe ou não pertence ao usuário."""


class ApplicationDuplicateError(ValueError):
    """Lançada quando já existe candidatura ativa do usuário para a mesma oportunidade."""

    def __init__(self, message: str, *, existing_application_id: uuid.UUID) -> None:
        super().__init__(message)
        self.existing_application_id = existing_application_id


class ApplicationHistoryProtectedError(ValueError):
    """Impede exclusão silenciosa de candidatura com histórico relevante sem confirmação explícita."""


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _compute_next_deadline(app_row: Application) -> tuple[datetime | None, str | None]:
    if app_row.status in CLOSED_APPLICATION_STATUSES:
        return (None, None)

    candidates: list[tuple[datetime, str]] = []
    for dt_val, label in (
        (app_row.assessment_deadline_at, "Prazo de teste técnico"),
        (app_row.interview_at, "Entrevista"),
        (app_row.next_action_due_at, "Próxima ação"),
        (app_row.expected_response_at, "Retorno previsto"),
    ):
        dt_utc = _ensure_utc(dt_val)
        if dt_utc is not None:
            candidates.append((dt_utc, label))

    if not candidates:
        return (None, None)

    now = datetime.now(UTC)
    upcoming = [pair for pair in candidates if pair[0] >= now]
    chosen = min(upcoming, key=lambda pair: pair[0]) if upcoming else max(candidates, key=lambda pair: pair[0])
    return chosen


def _serialize_history(item: ApplicationStatusHistory) -> ApplicationStatusHistoryResponse:
    return ApplicationStatusHistoryResponse(
        id=item.id,
        from_status=item.from_status,
        from_status_label=(
            APPLICATION_STATUS_LABELS_PT.get(item.from_status, item.from_status)
            if item.from_status
            else None
        ),
        to_status=item.to_status,
        to_status_label=APPLICATION_STATUS_LABELS_PT.get(item.to_status, item.to_status),
        note=item.note,
        changed_at=_ensure_utc(item.changed_at) or item.changed_at,
    )


def _serialize_application(app_row: Application) -> ApplicationResponse:
    next_dt, next_label = _compute_next_deadline(app_row)
    opp_status = app_row.opportunity.source_status if app_row.opportunity is not None else None
    history = [_serialize_history(h) for h in (app_row.status_history or [])]

    return ApplicationResponse(
        id=app_row.id,
        opportunity_id=app_row.opportunity_id,
        opportunity_source_status=opp_status,
        company_name=app_row.company_name,
        role_title=app_row.role_title,
        personal_summary=app_row.personal_summary,
        source_name=app_row.source_name,
        source_url=app_row.source_url,
        application_url=app_row.application_url,
        location_text=app_row.location_text,
        employment_type=app_row.employment_type,
        work_mode=app_row.work_mode,
        seniority_level=app_row.seniority_level,
        status=app_row.status,
        status_label=APPLICATION_STATUS_LABELS_PT.get(app_row.status, app_row.status),
        is_closed=app_row.status in CLOSED_APPLICATION_STATUSES,
        applied_at=_ensure_utc(app_row.applied_at),
        interview_at=_ensure_utc(app_row.interview_at),
        assessment_deadline_at=_ensure_utc(app_row.assessment_deadline_at),
        expected_response_at=_ensure_utc(app_row.expected_response_at),
        next_action=app_row.next_action,
        next_action_due_at=_ensure_utc(app_row.next_action_due_at),
        next_deadline_at=next_dt,
        next_deadline_label=next_label,
        notes=app_row.notes,
        closed_at=_ensure_utc(app_row.closed_at),
        created_at=_ensure_utc(app_row.created_at) or app_row.created_at,
        updated_at=_ensure_utc(app_row.updated_at) or app_row.updated_at,
        status_history=history,
    )


def _base_user_applications_stmt(user_id: uuid.UUID):
    return (
        select(Application)
        .options(
            selectinload(Application.opportunity),
            selectinload(Application.status_history),
        )
        .where(Application.user_id == user_id)
    )


def _get_owned_application(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> Application | None:
    return db.execute(
        _base_user_applications_stmt(user.id).where(Application.id == application_id)
    ).scalar_one_or_none()


def compute_application_indicators(items: list[Application]) -> ApplicationIndicatorsResponse:
    counts: Counter[str] = Counter(item.status for item in items)
    active_count = sum(counts[st] for st in ACTIVE_APPLICATION_STATUSES)
    closed_count = sum(counts[st] for st in CLOSED_APPLICATION_STATUSES)
    applied_count = sum(
        1
        for item in items
        if item.applied_at is not None or item.status in _SENT_OR_PROGRESSED_STATUSES
    )
    return ApplicationIndicatorsResponse(
        total_count=len(items),
        active_count=active_count,
        applied_count=applied_count,
        assessment_count=counts[ApplicationStatus.ASSESSMENT.value],
        interview_count=counts[ApplicationStatus.INTERVIEW.value],
        offer_count=counts[ApplicationStatus.OFFER.value],
        accepted_count=counts[ApplicationStatus.ACCEPTED.value],
        rejected_count=counts[ApplicationStatus.REJECTED.value],
        withdrawn_count=counts[ApplicationStatus.WITHDRAWN.value],
        closed_count=closed_count,
        status_counts={
            st: counts[st]
            for st in (*ACTIVE_APPLICATION_STATUSES, *CLOSED_APPLICATION_STATUSES)
        },
    )


def create_application(
    db: Session,
    user: User,
    payload: ApplicationCreate,
) -> ApplicationResponse:
    now = datetime.now(UTC)
    opp: Opportunity | None = None

    if payload.opportunity_id is not None:
        opp = db.execute(
            select(Opportunity)
            .options(selectinload(Opportunity.source))
            .where(
                Opportunity.id == payload.opportunity_id,
                or_(
                    Opportunity.source_id.is_not(None),
                    Opportunity.created_by_user_id == user.id,
                ),
            )
        ).scalar_one_or_none()
        if opp is None:
            raise ApplicationOpportunityNotFoundError(
                "Oportunidade referenciada não encontrada para acompanhamento."
            )

        existing_active = db.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.opportunity_id == opp.id,
                Application.status.in_(ACTIVE_APPLICATION_STATUSES),
            )
        ).scalar_one_or_none()
        if existing_active is not None:
            status_label = APPLICATION_STATUS_LABELS_PT.get(
                existing_active.status, existing_active.status
            )
            raise ApplicationDuplicateError(
                f"Já existe uma candidatura ativa para esta oportunidade na etapa '{status_label}'.",
                existing_application_id=existing_active.id,
            )

    if opp is not None:
        resolved_sen = resolve_opportunity_seniority_and_experience(opp)[0]
        role_title = payload.role_title or sanitize_plain_text(opp.title, max_length=255) or opp.title
        company_name = (
            payload.company_name
            if payload.company_name is not None
            else sanitize_plain_text(opp.company_name, max_length=200)
        )
        personal_summary = (
            payload.personal_summary
            if payload.personal_summary is not None
            else sanitize_external_html_text(opp.description, max_length=4000)
        )
        source_name = (
            payload.source_name
            if payload.source_name is not None
            else (opp.source.name if opp.source is not None else "Cadastro manual privado")
        )
        source_url = payload.source_url if payload.source_url is not None else opp.source_url
        application_url = (
            payload.application_url
            if payload.application_url is not None
            else (opp.application_url or opp.source_url)
        )
        fallback_location = opp.location_text or (
            ", ".join(opp.eligible_countries) if opp.eligible_countries else None
        )
        location_text = (
            payload.location_text
            if payload.location_text is not None
            else sanitize_plain_text(fallback_location, max_length=255)
        )
        employment_type = (
            payload.employment_type.value
            if payload.employment_type is not None
            else opp.employment_type
        ) or EmploymentType.UNKNOWN.value
        work_mode = (
            payload.work_mode.value
            if payload.work_mode is not None
            else opp.work_mode
        ) or WorkMode.UNKNOWN.value
        seniority_level = (
            payload.seniority_level.value
            if payload.seniority_level is not None
            else resolved_sen
        ) or SeniorityLevel.UNKNOWN.value
    else:
        role_title = payload.role_title or ""
        company_name = payload.company_name
        personal_summary = payload.personal_summary
        source_name = payload.source_name or "Cadastro manual privado"
        source_url = payload.source_url
        application_url = payload.application_url
        location_text = payload.location_text
        employment_type = (
            payload.employment_type.value
            if payload.employment_type is not None
            else EmploymentType.UNKNOWN.value
        )
        work_mode = (
            payload.work_mode.value
            if payload.work_mode is not None
            else WorkMode.UNKNOWN.value
        )
        seniority_level = (
            payload.seniority_level.value
            if payload.seniority_level is not None
            else SeniorityLevel.UNKNOWN.value
        )

    initial_status = payload.status.value
    applied_at = payload.applied_at
    if applied_at is None and initial_status in _SENT_OR_PROGRESSED_STATUSES:
        applied_at = now
    closed_at = now if initial_status in CLOSED_APPLICATION_STATUSES else None

    app_row = Application(
        user_id=user.id,
        opportunity_id=opp.id if opp is not None else None,
        company_name=company_name,
        role_title=role_title,
        personal_summary=personal_summary,
        source_name=source_name,
        source_url=source_url,
        application_url=application_url,
        location_text=location_text,
        employment_type=employment_type,
        work_mode=work_mode,
        seniority_level=seniority_level,
        status=initial_status,
        applied_at=applied_at,
        interview_at=payload.interview_at,
        assessment_deadline_at=payload.assessment_deadline_at,
        expected_response_at=payload.expected_response_at,
        next_action=payload.next_action,
        next_action_due_at=payload.next_action_due_at,
        notes=payload.notes,
        closed_at=closed_at,
    )
    db.add(app_row)
    db.flush()

    initial_history = ApplicationStatusHistory(
        application_id=app_row.id,
        user_id=user.id,
        from_status=None,
        to_status=initial_status,
        note=payload.status_note or (
            "Candidatura criada a partir de oportunidade do catálogo."
            if opp is not None
            else "Candidatura criada manualmente."
        ),
        changed_at=now,
        created_at=now,
    )
    db.add(initial_history)
    db.commit()

    created = _get_owned_application(db, user, app_row.id)
    assert created is not None
    return _serialize_application(created)


def list_applications(
    db: Session,
    user: User,
    *,
    status_filter: str | None = None,
    include_closed: bool = True,
    closed_only: bool = False,
    opportunity_id: uuid.UUID | None = None,
    q: str | None = None,
    sort: str = "updated_desc",
    page: int = 1,
    page_size: int = 20,
) -> ApplicationListResponse:
    stmt = _base_user_applications_stmt(user.id)

    if status_filter:
        stmt = stmt.where(Application.status == status_filter)
    elif closed_only:
        stmt = stmt.where(Application.status.in_(CLOSED_APPLICATION_STATUSES))
    elif not include_closed:
        stmt = stmt.where(Application.status.in_(ACTIVE_APPLICATION_STATUSES))

    if opportunity_id is not None:
        stmt = stmt.where(Application.opportunity_id == opportunity_id)

    rows = list(db.execute(stmt).scalars().all())

    if q and q.strip():
        needle = q.strip().lower()
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                [
                    row.role_title or "",
                    row.company_name or "",
                    row.source_name or "",
                    row.location_text or "",
                    row.next_action or "",
                    row.notes or "",
                ]
            ).lower()
        ]

    if sort == "created_desc":
        rows.sort(
            key=lambda r: (_ensure_utc(r.created_at) or r.created_at).timestamp(),
            reverse=True,
        )
    elif sort == "deadline_asc":
        rows.sort(
            key=lambda r: (
                0 if _compute_next_deadline(r)[0] is not None else 1,
                (_compute_next_deadline(r)[0] or datetime.max.replace(tzinfo=UTC)).timestamp(),
                -(_ensure_utc(r.updated_at) or r.updated_at).timestamp(),
            )
        )
    else:
        rows.sort(
            key=lambda r: (_ensure_utc(r.updated_at) or r.updated_at).timestamp(),
            reverse=True,
        )

    total = len(rows)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * page_size
    end = start + page_size

    return ApplicationListResponse(
        items=[_serialize_application(row) for row in rows[start:end]],
        total=total,
        page=safe_page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_applications_kanban(
    db: Session,
    user: User,
    *,
    q: str | None = None,
) -> ApplicationKanbanResponse:
    all_rows = list(
        db.execute(_base_user_applications_stmt(user.id)).scalars().all()
    )
    indicators = compute_application_indicators(all_rows)

    filtered_rows = all_rows
    if q and q.strip():
        needle = q.strip().lower()
        filtered_rows = [
            row
            for row in all_rows
            if needle
            in " ".join(
                [
                    row.role_title or "",
                    row.company_name or "",
                    row.source_name or "",
                    row.location_text or "",
                    row.next_action or "",
                    row.notes or "",
                ]
            ).lower()
        ]

    filtered_rows.sort(
        key=lambda r: (_ensure_utc(r.updated_at) or r.updated_at).timestamp(),
        reverse=True,
    )

    by_status: dict[str, list[ApplicationResponse]] = {
        st: [] for st in (*ACTIVE_APPLICATION_STATUSES, *CLOSED_APPLICATION_STATUSES)
    }
    for row in filtered_rows:
        dto = _serialize_application(row)
        by_status.setdefault(row.status, []).append(dto)

    columns = [
        ApplicationKanbanColumnResponse(
            status=st,
            label=APPLICATION_STATUS_LABELS_PT[st],
            is_closed=False,
            count=len(by_status[st]),
            items=by_status[st],
        )
        for st in ACTIVE_APPLICATION_STATUSES
    ]

    closed_columns = [
        ApplicationKanbanColumnResponse(
            status=st,
            label=APPLICATION_STATUS_LABELS_PT[st],
            is_closed=True,
            count=len(by_status[st]),
            items=by_status[st],
        )
        for st in CLOSED_APPLICATION_STATUSES
    ]
    closed_items = [
        _serialize_application(row)
        for row in filtered_rows
        if row.status in CLOSED_APPLICATION_STATUSES
    ]

    return ApplicationKanbanResponse(
        columns=columns,
        closed_columns=closed_columns,
        closed_items=closed_items,
        indicators=indicators,
        labels=dict(APPLICATION_STATUS_LABELS_PT),
    )


def get_application_detail(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> ApplicationResponse | None:
    app_row = _get_owned_application(db, user, application_id)
    if app_row is None:
        return None
    return _serialize_application(app_row)


def update_application(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
) -> ApplicationResponse | None:
    app_row = _get_owned_application(db, user, application_id)
    if app_row is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in {"employment_type", "work_mode", "seniority_level"} and value is not None:
            setattr(app_row, field, value.value if hasattr(value, "value") else value)
        else:
            setattr(app_row, field, value)

    app_row.updated_at = datetime.now(UTC)
    db.commit()
    refreshed = _get_owned_application(db, user, application_id)
    assert refreshed is not None
    return _serialize_application(refreshed)


def change_application_status(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ApplicationStatusChangeRequest,
) -> ApplicationResponse | None:
    app_row = _get_owned_application(db, user, application_id)
    if app_row is None:
        return None

    now = datetime.now(UTC)
    previous_status = app_row.status
    target_status = payload.status.value

    if (
        previous_status in CLOSED_APPLICATION_STATUSES
        and target_status in ACTIVE_APPLICATION_STATUSES
        and app_row.opportunity_id is not None
    ):
        other_active = db.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.opportunity_id == app_row.opportunity_id,
                Application.id != app_row.id,
                Application.status.in_(ACTIVE_APPLICATION_STATUSES),
            )
        ).scalar_one_or_none()
        if other_active is not None:
            raise ApplicationDuplicateError(
                "Já existe outra candidatura ativa para esta oportunidade.",
                existing_application_id=other_active.id,
            )

    app_row.status = target_status
    if payload.applied_at is not None:
        app_row.applied_at = payload.applied_at
    elif target_status in _SENT_OR_PROGRESSED_STATUSES and app_row.applied_at is None:
        app_row.applied_at = now

    if payload.interview_at is not None:
        app_row.interview_at = payload.interview_at
    if payload.assessment_deadline_at is not None:
        app_row.assessment_deadline_at = payload.assessment_deadline_at
    if payload.expected_response_at is not None:
        app_row.expected_response_at = payload.expected_response_at
    if "next_action" in payload.model_fields_set:
        app_row.next_action = payload.next_action
    if "next_action_due_at" in payload.model_fields_set:
        app_row.next_action_due_at = payload.next_action_due_at

    if target_status in CLOSED_APPLICATION_STATUSES:
        if app_row.closed_at is None or previous_status != target_status:
            app_row.closed_at = now
    else:
        app_row.closed_at = None

    app_row.updated_at = now

    if previous_status != target_status or payload.note:
        history_entry = ApplicationStatusHistory(
            application_id=app_row.id,
            user_id=user.id,
            from_status=previous_status,
            to_status=target_status,
            note=payload.note,
            changed_at=now,
            created_at=now,
        )
        db.add(history_entry)

    db.commit()
    refreshed = _get_owned_application(db, user, application_id)
    assert refreshed is not None
    return _serialize_application(refreshed)


def delete_application(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    *,
    confirm_history_deletion: bool = False,
) -> bool:
    app_row = _get_owned_application(db, user, application_id)
    if app_row is None:
        return False

    has_progressed_history = (
        len(app_row.status_history or []) > 1
        or app_row.status
        not in {
            ApplicationStatus.INTERESTED.value,
            ApplicationStatus.PREPARING.value,
        }
    )
    if has_progressed_history and not confirm_history_deletion:
        raise ApplicationHistoryProtectedError(
            "Esta candidatura já possui histórico de movimentações no processo seletivo. "
            "Para preservar o histórico, mova para 'Desistência' ou confirme explicitamente a exclusão completa."
        )

    db.delete(app_row)
    db.commit()
    return True
