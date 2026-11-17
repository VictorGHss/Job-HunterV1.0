import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.application import (
    APPLICATION_STATUS_LABELS_PT,
    ASSESSMENT_STATUS_LABELS_PT,
    CLOSED_APPLICATION_STATUSES,
    EXTERNAL_INTERACTION_TYPE_LABELS_PT,
    INTERVIEW_FORMAT_LABELS_PT,
    INTERVIEW_STATUS_LABELS_PT,
    Application,
    ApplicationAssessment,
    ApplicationContact,
    ApplicationInterview,
    ApplicationStatus,
    ApplicationStatusHistory,
    AssessmentStatus,
    ExternalInteractionType,
    InterviewStatus,
)
from app.models.user import User
from app.schemas.application import (
    AgendaEventResponse,
    AgendaSummaryResponse,
    ApplicationAgendaResponse,
    ApplicationAssessmentCreate,
    ApplicationAssessmentResponse,
    ApplicationAssessmentUpdate,
    ApplicationContactCreate,
    ApplicationContactResponse,
    ApplicationContactUpdate,
    ApplicationInterviewCreate,
    ApplicationInterviewResponse,
    ApplicationInterviewUpdate,
    ExternalInteractionRecordRequest,
    FollowUpTemplateResponse,
    StaleApplicationItemResponse,
    StaleApplicationsResponse,
)

DEFAULT_STALE_DAYS_BY_STATUS: dict[str, int] = {
    ApplicationStatus.APPLIED.value: 10,
    ApplicationStatus.INTERVIEW.value: 7,
}


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _load_owned_application_with_children(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> Application | None:
    stmt = (
        select(Application)
        .options(
            selectinload(Application.opportunity),
            selectinload(Application.status_history),
            selectinload(Application.interviews),
            selectinload(Application.assessments),
            selectinload(Application.contacts),
        )
        .where(Application.id == application_id, Application.user_id == user.id)
    )
    return db.execute(stmt).scalar_one_or_none()


def serialize_interview(item: ApplicationInterview) -> ApplicationInterviewResponse:
    scheduled = ensure_utc(item.scheduled_at) or item.scheduled_at
    return ApplicationInterviewResponse(
        id=item.id,
        application_id=item.application_id,
        round_name=item.round_name,
        interview_format=item.interview_format,
        interview_format_label=INTERVIEW_FORMAT_LABELS_PT.get(
            item.interview_format, item.interview_format
        ),
        scheduled_at=scheduled,
        previous_scheduled_at=ensure_utc(item.previous_scheduled_at),
        duration_minutes=item.duration_minutes,
        meeting_url=item.meeting_url,
        interviewers=item.interviewers,
        notes=item.notes,
        feedback_received=item.feedback_received,
        status=item.status,
        status_label=INTERVIEW_STATUS_LABELS_PT.get(item.status, item.status),
        completed_at=ensure_utc(item.completed_at),
        created_at=ensure_utc(item.created_at) or item.created_at,
        updated_at=ensure_utc(item.updated_at) or item.updated_at,
    )


def serialize_assessment(
    item: ApplicationAssessment,
    *,
    now: datetime | None = None,
) -> ApplicationAssessmentResponse:
    ref_now = now or datetime.now(UTC)
    deadline_utc = ensure_utc(item.deadline_at)
    is_active = item.status in {
        AssessmentStatus.PENDING.value,
        AssessmentStatus.IN_PROGRESS.value,
    }
    is_overdue = bool(is_active and deadline_utc is not None and deadline_utc < ref_now)
    is_due_soon_24h = bool(
        is_active
        and deadline_utc is not None
        and ref_now <= deadline_utc <= ref_now + timedelta(hours=24)
    )
    return ApplicationAssessmentResponse(
        id=item.id,
        application_id=item.application_id,
        title=item.title,
        description=item.description,
        platform=item.platform,
        instructions_url=item.instructions_url,
        submission_url=item.submission_url,
        deadline_at=deadline_utc,
        submitted_at=ensure_utc(item.submitted_at),
        status=item.status,
        status_label=ASSESSMENT_STATUS_LABELS_PT.get(item.status, item.status),
        is_overdue=is_overdue,
        is_due_soon_24h=is_due_soon_24h,
        feedback=item.feedback,
        notes=item.notes,
        created_at=ensure_utc(item.created_at) or item.created_at,
        updated_at=ensure_utc(item.updated_at) or item.updated_at,
    )


def serialize_contact(item: ApplicationContact) -> ApplicationContactResponse:
    return ApplicationContactResponse(
        id=item.id,
        application_id=item.application_id,
        name=item.name,
        role_title=item.role_title,
        email=item.email,
        linkedin_url=item.linkedin_url,
        notes=item.notes,
        created_at=ensure_utc(item.created_at) or item.created_at,
        updated_at=ensure_utc(item.updated_at) or item.updated_at,
    )


def sync_application_interview_summary(
    db: Session,
    app_row: Application,
    *,
    now: datetime | None = None,
) -> None:
    """
    Mantém `Application.interview_at` sincronizado com a entrevista futura
    (`status='scheduled'` e `scheduled_at >= now`) mais próxima.
    Se não houver entrevista futura agendada entre as rodadas estruturadas,
    limpa o campo resumo para evitar exibição de datas obsoletas na compatibilidade.
    """
    ref_now = now or datetime.now(UTC)
    interviews = list(
        db.execute(
            select(ApplicationInterview).where(
                ApplicationInterview.application_id == app_row.id
            )
        )
        .scalars()
        .all()
    )
    upcoming_scheduled = [
        ensure_utc(iv.scheduled_at)
        for iv in interviews
        if iv.status == InterviewStatus.SCHEDULED.value
        and ensure_utc(iv.scheduled_at) is not None
        and ensure_utc(iv.scheduled_at) >= ref_now  # type: ignore[operator]
    ]
    app_row.interview_at = min(upcoming_scheduled) if upcoming_scheduled else None


def sync_application_assessment_summary(
    db: Session,
    app_row: Application,
    *,
    now: datetime | None = None,
) -> None:
    """
    Mantém `Application.assessment_deadline_at` coerente com o prazo pendente
    (`pending`/`in_progress`) mais próximo nos desafios estruturados.
    """
    ref_now = now or datetime.now(UTC)
    assessments = list(
        db.execute(
            select(ApplicationAssessment).where(
                ApplicationAssessment.application_id == app_row.id
            )
        )
        .scalars()
        .all()
    )
    active_deadlines = [
        ensure_utc(asmt.deadline_at)
        for asmt in assessments
        if asmt.status in {AssessmentStatus.PENDING.value, AssessmentStatus.IN_PROGRESS.value}
        and ensure_utc(asmt.deadline_at) is not None
    ]
    upcoming = [dt for dt in active_deadlines if dt is not None and dt >= ref_now]
    if upcoming:
        app_row.assessment_deadline_at = min(upcoming)
    elif active_deadlines:
        app_row.assessment_deadline_at = max(dt for dt in active_deadlines if dt is not None)
    else:
        app_row.assessment_deadline_at = None


def _apply_monotonic_external_interaction_summary(
    db: Session,
    *,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    interaction_at: datetime,
    interaction_type: str,
    interaction_note: str | None,
    updated_at: datetime,
) -> bool:
    """
    Atualiza atomicamente os 3 campos de resumo da última interação externa apenas
    quando ainda não houver registro ou o novo instante normalizado em UTC for
    >= ao timestamp atualmente armazenado (garantindo monotonicidade mesmo sob
    transações concorrentes). Para timestamps idênticos (`==`), atualiza os três
    campos em conjunto de forma determinística.
    """
    normalized_at = ensure_utc(interaction_at) or updated_at
    stmt = (
        update(Application)
        .where(
            Application.id == application_id,
            Application.user_id == user_id,
            or_(
                Application.last_external_interaction_at.is_(None),
                Application.last_external_interaction_at <= normalized_at,
            ),
        )
        .values(
            last_external_interaction_at=normalized_at,
            last_external_interaction_type=interaction_type,
            last_external_interaction_note=interaction_note,
            updated_at=updated_at,
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(stmt)
    return bool(result.rowcount)


def _maybe_record_interview_interaction(
    db: Session,
    user: User,
    app_row: Application,
    interview: ApplicationInterview,
    *,
    effective_at: datetime,
    updated_at: datetime,
) -> None:
    effective_utc = ensure_utc(effective_at) or updated_at
    current_at = ensure_utc(app_row.last_external_interaction_at)
    if current_at is not None and effective_utc < current_at:
        return

    note_text = f"Entrevista concluída: {interview.round_name}"
    if interview.feedback_received:
        snippet = interview.feedback_received.strip().splitlines()[0][:240]
        note_text = f"{note_text} — {snippet}"

    # Persiste alterações ORM pendentes (ex.: `interview_at`) antes do UPDATE atômico
    db.flush()
    _apply_monotonic_external_interaction_summary(
        db,
        application_id=app_row.id,
        user_id=user.id,
        interaction_at=effective_utc,
        interaction_type=ExternalInteractionType.INTERVIEW.value,
        interaction_note=note_text,
        updated_at=updated_at,
    )
    db.expire(app_row)


# ---------------------------------------------------------------------------
# Entrevistas
# ---------------------------------------------------------------------------


def list_application_interviews(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> list[ApplicationInterviewResponse] | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None
    items = sorted(
        app_row.interviews,
        key=lambda iv: (
            (ensure_utc(iv.scheduled_at) or iv.scheduled_at).timestamp(),
            (ensure_utc(iv.created_at) or iv.created_at).timestamp(),
        ),
    )
    return [serialize_interview(item) for item in items]


def create_application_interview(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ApplicationInterviewCreate,
) -> ApplicationInterviewResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    now = datetime.now(UTC)
    status_val = payload.status.value
    completed_at = payload.completed_at
    if status_val == InterviewStatus.COMPLETED.value and completed_at is None:
        completed_at = now
    elif status_val != InterviewStatus.COMPLETED.value:
        completed_at = None

    interview = ApplicationInterview(
        application_id=app_row.id,
        round_name=payload.round_name,
        interview_format=payload.interview_format.value,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        meeting_url=payload.meeting_url,
        interviewers=payload.interviewers,
        notes=payload.notes,
        feedback_received=payload.feedback_received,
        status=status_val,
        completed_at=completed_at,
    )
    db.add(interview)
    db.flush()

    sync_application_interview_summary(db, app_row, now=now)
    if status_val == InterviewStatus.COMPLETED.value:
        effective = ensure_utc(completed_at) or ensure_utc(payload.scheduled_at) or now
        _maybe_record_interview_interaction(
            db,
            user,
            app_row,
            interview,
            effective_at=effective,
            updated_at=now,
        )

    db.commit()
    db.refresh(interview)
    return serialize_interview(interview)


def update_application_interview(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    payload: ApplicationInterviewUpdate,
) -> ApplicationInterviewResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    interview = db.execute(
        select(ApplicationInterview).where(
            ApplicationInterview.id == interview_id,
            ApplicationInterview.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if interview is None:
        return None

    now = datetime.now(UTC)
    previous_status = interview.status
    previous_scheduled_utc = ensure_utc(interview.scheduled_at)
    update_data = payload.model_dump(exclude_unset=True)

    # Reagendamento preserva status 'scheduled' e guarda a data anterior como contexto leve
    if "scheduled_at" in update_data and update_data["scheduled_at"] is not None:
        new_scheduled_utc = ensure_utc(update_data["scheduled_at"])
        if previous_scheduled_utc is not None and new_scheduled_utc != previous_scheduled_utc:
            interview.previous_scheduled_at = previous_scheduled_utc
        interview.scheduled_at = new_scheduled_utc  # type: ignore[assignment]

    for field in (
        "round_name",
        "duration_minutes",
        "meeting_url",
        "interviewers",
        "notes",
        "feedback_received",
    ):
        if field in update_data:
            setattr(interview, field, update_data[field])

    if "interview_format" in update_data and update_data["interview_format"] is not None:
        fmt = update_data["interview_format"]
        interview.interview_format = fmt.value if hasattr(fmt, "value") else fmt

    if "status" in update_data and update_data["status"] is not None:
        st = update_data["status"]
        interview.status = st.value if hasattr(st, "value") else st

    if interview.status == InterviewStatus.COMPLETED.value:
        if "completed_at" in update_data and update_data["completed_at"] is not None:
            interview.completed_at = ensure_utc(update_data["completed_at"])
        elif interview.completed_at is None or previous_status != InterviewStatus.COMPLETED.value:
            interview.completed_at = now
    elif interview.status == InterviewStatus.CANCELLED.value:
        interview.completed_at = None
    elif "completed_at" in update_data:
        interview.completed_at = ensure_utc(update_data["completed_at"])

    interview.updated_at = now
    db.flush()

    sync_application_interview_summary(db, app_row, now=now)
    if interview.status == InterviewStatus.COMPLETED.value and (
        previous_status != InterviewStatus.COMPLETED.value or "completed_at" in update_data
    ):
        effective = ensure_utc(interview.completed_at) or ensure_utc(interview.scheduled_at) or now
        _maybe_record_interview_interaction(
            db,
            user,
            app_row,
            interview,
            effective_at=effective,
            updated_at=now,
        )

    db.commit()
    db.refresh(interview)
    return serialize_interview(interview)


def delete_application_interview(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
) -> bool | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    interview = db.execute(
        select(ApplicationInterview).where(
            ApplicationInterview.id == interview_id,
            ApplicationInterview.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if interview is None:
        return False

    db.delete(interview)
    db.flush()
    sync_application_interview_summary(db, app_row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Testes Técnicos
# ---------------------------------------------------------------------------


def list_application_assessments(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> list[ApplicationAssessmentResponse] | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None
    now = datetime.now(UTC)
    items = sorted(
        app_row.assessments,
        key=lambda a: (
            0 if a.deadline_at is not None else 1,
            (ensure_utc(a.deadline_at) or datetime.max.replace(tzinfo=UTC)).timestamp(),
            -(ensure_utc(a.created_at) or a.created_at).timestamp(),
        ),
    )
    return [serialize_assessment(item, now=now) for item in items]


def create_application_assessment(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ApplicationAssessmentCreate,
) -> ApplicationAssessmentResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    now = datetime.now(UTC)
    status_val = payload.status.value
    submitted_at = payload.submitted_at
    if (
        status_val in {AssessmentStatus.SUBMITTED.value, AssessmentStatus.FEEDBACK_RECEIVED.value}
        and submitted_at is None
    ):
        submitted_at = now
    elif payload.submission_url and status_val == AssessmentStatus.PENDING.value:
        status_val = AssessmentStatus.SUBMITTED.value
        if submitted_at is None:
            submitted_at = now

    assessment = ApplicationAssessment(
        application_id=app_row.id,
        title=payload.title,
        description=payload.description,
        platform=payload.platform,
        instructions_url=payload.instructions_url,
        submission_url=payload.submission_url,
        deadline_at=payload.deadline_at,
        submitted_at=submitted_at,
        status=status_val,
        feedback=payload.feedback,
        notes=payload.notes,
    )
    db.add(assessment)
    db.flush()

    sync_application_assessment_summary(db, app_row, now=now)
    db.commit()
    db.refresh(assessment)
    return serialize_assessment(assessment, now=now)


def update_application_assessment(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    assessment_id: uuid.UUID,
    payload: ApplicationAssessmentUpdate,
) -> ApplicationAssessmentResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    assessment = db.execute(
        select(ApplicationAssessment).where(
            ApplicationAssessment.id == assessment_id,
            ApplicationAssessment.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if assessment is None:
        return None

    now = datetime.now(UTC)
    update_data = payload.model_dump(exclude_unset=True)

    for field in (
        "title",
        "description",
        "platform",
        "instructions_url",
        "submission_url",
        "feedback",
        "notes",
    ):
        if field in update_data:
            setattr(assessment, field, update_data[field])

    if "deadline_at" in update_data:
        assessment.deadline_at = ensure_utc(update_data["deadline_at"])
    if "submitted_at" in update_data:
        assessment.submitted_at = ensure_utc(update_data["submitted_at"])

    if "status" in update_data and update_data["status"] is not None:
        st = update_data["status"]
        assessment.status = st.value if hasattr(st, "value") else st

    if (
        assessment.status
        in {AssessmentStatus.SUBMITTED.value, AssessmentStatus.FEEDBACK_RECEIVED.value}
        and assessment.submitted_at is None
    ):
        assessment.submitted_at = now
    elif assessment.status == AssessmentStatus.PENDING.value and assessment.submission_url:
        assessment.status = AssessmentStatus.SUBMITTED.value
        if assessment.submitted_at is None:
            assessment.submitted_at = now

    assessment.updated_at = now
    db.flush()

    sync_application_assessment_summary(db, app_row, now=now)
    db.commit()
    db.refresh(assessment)
    return serialize_assessment(assessment, now=now)


def delete_application_assessment(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    assessment_id: uuid.UUID,
) -> bool | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    assessment = db.execute(
        select(ApplicationAssessment).where(
            ApplicationAssessment.id == assessment_id,
            ApplicationAssessment.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if assessment is None:
        return False

    db.delete(assessment)
    db.flush()
    sync_application_assessment_summary(db, app_row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Contatos (Recrutadores / Entrevistadores / Gestores)
# ---------------------------------------------------------------------------


def list_application_contacts(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> list[ApplicationContactResponse] | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None
    items = sorted(
        app_row.contacts,
        key=lambda c: (ensure_utc(c.created_at) or c.created_at).timestamp(),
    )
    return [serialize_contact(item) for item in items]


def create_application_contact(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ApplicationContactCreate,
) -> ApplicationContactResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    # Nota: nunca atualizar `last_external_interaction_at` ao cadastrar contato.
    contact = ApplicationContact(
        application_id=app_row.id,
        name=payload.name,
        role_title=payload.role_title,
        email=str(payload.email) if payload.email is not None else None,
        linkedin_url=payload.linkedin_url,
        notes=payload.notes,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return serialize_contact(contact)


def update_application_contact(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: ApplicationContactUpdate,
) -> ApplicationContactResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    contact = db.execute(
        select(ApplicationContact).where(
            ApplicationContact.id == contact_id,
            ApplicationContact.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if contact is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field in ("name", "role_title", "linkedin_url", "notes"):
        if field in update_data:
            setattr(contact, field, update_data[field])
    if "email" in update_data:
        email_val = update_data["email"]
        contact.email = str(email_val) if email_val is not None else None

    contact.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(contact)
    return serialize_contact(contact)


def delete_application_contact(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> bool | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    contact = db.execute(
        select(ApplicationContact).where(
            ApplicationContact.id == contact_id,
            ApplicationContact.application_id == app_row.id,
        )
    ).scalar_one_or_none()
    if contact is None:
        return False

    db.delete(contact)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Interação Externa Explícita
# ---------------------------------------------------------------------------


def record_external_interaction(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    payload: ExternalInteractionRecordRequest,
) -> Application | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    now = datetime.now(UTC)
    interaction_at = ensure_utc(payload.interaction_at) or now
    interaction_type = payload.interaction_type.value
    type_label = EXTERNAL_INTERACTION_TYPE_LABELS_PT.get(interaction_type, interaction_type)

    history_note = f"Interação externa registrada ({type_label})."
    if payload.note:
        history_note = f"{history_note} {payload.note[:380]}"

    # O histórico registra integralmente toda interação informada (inclusive retroativa)
    # com sua data efetiva real, sem criar transição artificial de etapa.
    db.add(
        ApplicationStatusHistory(
            application_id=app_row.id,
            user_id=user.id,
            from_status=app_row.status,
            to_status=app_row.status,
            note=history_note,
            changed_at=interaction_at,
            created_at=now,
        )
    )
    db.flush()

    # Atualiza os 3 campos de resumo de forma atômica e monotônica somente se
    # não houver interação registrada ou se `interaction_at >= atual` no banco.
    current_at = ensure_utc(app_row.last_external_interaction_at)
    if current_at is None or interaction_at >= current_at:
        _apply_monotonic_external_interaction_summary(
            db,
            application_id=app_row.id,
            user_id=user.id,
            interaction_at=interaction_at,
            interaction_type=interaction_type,
            interaction_note=payload.note,
            updated_at=now,
        )

    db.commit()
    db.expire(app_row)
    return _load_owned_application_with_children(db, user, application_id)


# ---------------------------------------------------------------------------
# Agenda Cronológica Unificada
# ---------------------------------------------------------------------------


def get_applications_agenda(
    db: Session,
    user: User,
    *,
    days: int = 30,
    include_overdue: bool = True,
    now: datetime | None = None,
) -> ApplicationAgendaResponse:
    ref_now = ensure_utc(now) or datetime.now(UTC)
    window_end = ref_now + timedelta(days=days)
    imminent_end = ref_now + timedelta(hours=24)

    rows = list(
        db.execute(
            select(Application)
            .options(
                selectinload(Application.interviews),
                selectinload(Application.assessments),
            )
            .where(
                Application.user_id == user.id,
                Application.status.notin_(CLOSED_APPLICATION_STATUSES),
            )
        )
        .scalars()
        .all()
    )

    events: list[AgendaEventResponse] = []

    def _in_window(dt: datetime | None) -> datetime | None:
        dt_utc = ensure_utc(dt)
        if dt_utc is None:
            return None
        if dt_utc > window_end:
            return None
        if not include_overdue and dt_utc < ref_now:
            return None
        return dt_utc

    def _urgency_flags(dt_utc: datetime) -> tuple[bool, bool, bool, str]:
        is_overdue = dt_utc < ref_now
        is_today = dt_utc.date() == ref_now.date()
        is_imminent = ref_now <= dt_utc <= imminent_end
        if is_overdue:
            urgency = "overdue"
        elif is_imminent:
            urgency = "imminent"
        else:
            urgency = "upcoming"
        return is_overdue, is_today, is_imminent, urgency

    for app_row in rows:
        app_status_label = APPLICATION_STATUS_LABELS_PT.get(app_row.status, app_row.status)

        # 1. Entrevistas estruturadas (`status='scheduled'`) com fallback exclusivo quando não houver rodadas
        if app_row.interviews:
            for iv in app_row.interviews:
                if iv.status != InterviewStatus.SCHEDULED.value:
                    continue
                dt_utc = _in_window(iv.scheduled_at)
                if dt_utc is None:
                    continue
                is_overdue, is_today, is_imminent, urgency = _urgency_flags(dt_utc)
                fmt_label = INTERVIEW_FORMAT_LABELS_PT.get(
                    iv.interview_format, iv.interview_format
                )
                subtitle_parts = [fmt_label]
                if iv.interviewers:
                    subtitle_parts.append(iv.interviewers)
                if iv.previous_scheduled_at is not None:
                    subtitle_parts.append("Reagendada")
                events.append(
                    AgendaEventResponse(
                        id=f"interview:{iv.id}",
                        event_type="interview",
                        source_kind="structured",
                        entity_id=iv.id,
                        application_id=app_row.id,
                        company_name=app_row.company_name,
                        role_title=app_row.role_title,
                        application_status=app_row.status,
                        application_status_label=app_status_label,
                        title=f"Entrevista: {iv.round_name}",
                        subtitle=" • ".join(subtitle_parts),
                        scheduled_at=dt_utc,
                        status=iv.status,
                        status_label=INTERVIEW_STATUS_LABELS_PT.get(iv.status, iv.status),
                        is_overdue=is_overdue,
                        is_today=is_today,
                        is_imminent=is_imminent,
                        urgency=urgency,  # type: ignore[arg-type]
                        action_url=iv.meeting_url,
                    )
                )
        else:
            legacy_iv_dt = _in_window(app_row.interview_at)
            if legacy_iv_dt is not None:
                is_overdue, is_today, is_imminent, urgency = _urgency_flags(legacy_iv_dt)
                events.append(
                    AgendaEventResponse(
                        id=f"legacy_interview:{app_row.id}",
                        event_type="interview",
                        source_kind="legacy",
                        entity_id=app_row.id,
                        application_id=app_row.id,
                        company_name=app_row.company_name,
                        role_title=app_row.role_title,
                        application_status=app_row.status,
                        application_status_label=app_status_label,
                        title="Entrevista agendada",
                        subtitle="Registro resumido da candidatura",
                        scheduled_at=legacy_iv_dt,
                        status="scheduled",
                        status_label="Agendada",
                        is_overdue=is_overdue,
                        is_today=is_today,
                        is_imminent=is_imminent,
                        urgency=urgency,  # type: ignore[arg-type]
                        action_url=app_row.application_url or app_row.source_url,
                    )
                )

        # 2. Testes técnicos estruturados pendentes (`pending`/`in_progress`) sem duplicar campo legado
        if app_row.assessments:
            for asmt in app_row.assessments:
                if asmt.status not in {
                    AssessmentStatus.PENDING.value,
                    AssessmentStatus.IN_PROGRESS.value,
                }:
                    continue
                dt_utc = _in_window(asmt.deadline_at)
                if dt_utc is None:
                    continue
                is_overdue, is_today, is_imminent, urgency = _urgency_flags(dt_utc)
                subtitle = f"Plataforma: {asmt.platform}" if asmt.platform else None
                events.append(
                    AgendaEventResponse(
                        id=f"assessment:{asmt.id}",
                        event_type="assessment",
                        source_kind="structured",
                        entity_id=asmt.id,
                        application_id=app_row.id,
                        company_name=app_row.company_name,
                        role_title=app_row.role_title,
                        application_status=app_row.status,
                        application_status_label=app_status_label,
                        title=f"Teste técnico: {asmt.title}",
                        subtitle=subtitle,
                        scheduled_at=dt_utc,
                        status=asmt.status,
                        status_label=ASSESSMENT_STATUS_LABELS_PT.get(asmt.status, asmt.status),
                        is_overdue=is_overdue,
                        is_today=is_today,
                        is_imminent=is_imminent,
                        urgency=urgency,  # type: ignore[arg-type]
                        action_url=asmt.instructions_url or asmt.submission_url,
                    )
                )
        else:
            legacy_asmt_dt = _in_window(app_row.assessment_deadline_at)
            if legacy_asmt_dt is not None:
                is_overdue, is_today, is_imminent, urgency = _urgency_flags(legacy_asmt_dt)
                events.append(
                    AgendaEventResponse(
                        id=f"legacy_assessment:{app_row.id}",
                        event_type="assessment",
                        source_kind="legacy",
                        entity_id=app_row.id,
                        application_id=app_row.id,
                        company_name=app_row.company_name,
                        role_title=app_row.role_title,
                        application_status=app_row.status,
                        application_status_label=app_status_label,
                        title="Prazo de teste técnico",
                        subtitle="Prazo legado da candidatura",
                        scheduled_at=legacy_asmt_dt,
                        status="pending",
                        status_label="Pendente",
                        is_overdue=is_overdue,
                        is_today=is_today,
                        is_imminent=is_imminent,
                        urgency=urgency,  # type: ignore[arg-type]
                        action_url=app_row.application_url or app_row.source_url,
                    )
                )

        # 3. Próxima ação operacional definida na candidatura
        next_action_dt = _in_window(app_row.next_action_due_at)
        if next_action_dt is not None:
            is_overdue, is_today, is_imminent, urgency = _urgency_flags(next_action_dt)
            events.append(
                AgendaEventResponse(
                    id=f"next_action:{app_row.id}",
                    event_type="next_action",
                    source_kind="structured",
                    entity_id=app_row.id,
                    application_id=app_row.id,
                    company_name=app_row.company_name,
                    role_title=app_row.role_title,
                    application_status=app_row.status,
                    application_status_label=app_status_label,
                    title=app_row.next_action or "Próxima ação registrada",
                    subtitle="Ação planejada no processo",
                    scheduled_at=next_action_dt,
                    status="pending",
                    status_label="Pendente",
                    is_overdue=is_overdue,
                    is_today=is_today,
                    is_imminent=is_imminent,
                    urgency=urgency,  # type: ignore[arg-type]
                    action_url=app_row.application_url or app_row.source_url,
                )
            )

        # 4. Data prevista de retorno (informativa)
        expected_dt = _in_window(app_row.expected_response_at)
        if expected_dt is not None:
            is_overdue, is_today, is_imminent, urgency = _urgency_flags(expected_dt)
            events.append(
                AgendaEventResponse(
                    id=f"expected_response:{app_row.id}",
                    event_type="expected_response",
                    source_kind="structured",
                    entity_id=app_row.id,
                    application_id=app_row.id,
                    company_name=app_row.company_name,
                    role_title=app_row.role_title,
                    application_status=app_row.status,
                    application_status_label=app_status_label,
                    title="Retorno previsto da empresa",
                    subtitle="Previsão informada manualmente",
                    scheduled_at=expected_dt,
                    status="scheduled",
                    status_label="Previsto",
                    is_overdue=is_overdue,
                    is_today=is_today,
                    is_imminent=is_imminent,
                    urgency=urgency,  # type: ignore[arg-type]
                    action_url=app_row.application_url or app_row.source_url,
                )
            )

    # Ordenação estrita por timestamp normalizado em UTC (nunca string!)
    events.sort(key=lambda ev: (ev.scheduled_at.timestamp(), ev.id))

    summary = AgendaSummaryResponse(
        total_count=len(events),
        overdue_count=sum(1 for ev in events if ev.is_overdue),
        imminent_24h_count=sum(1 for ev in events if ev.is_imminent),
        today_count=sum(1 for ev in events if ev.is_today),
        interviews_count=sum(1 for ev in events if ev.event_type == "interview"),
        assessments_count=sum(1 for ev in events if ev.event_type == "assessment"),
        actions_count=sum(
            1 for ev in events if ev.event_type in {"next_action", "expected_response"}
        ),
        reference_now_utc=ref_now,
    )
    return ApplicationAgendaResponse(days=days, summary=summary, events=events)


# ---------------------------------------------------------------------------
# Detecção de Processos Sem Interação Externa Registrada
# ---------------------------------------------------------------------------


def _has_future_scheduled_interview(app_row: Application, *, now: datetime) -> bool:
    if app_row.interviews:
        return any(
            iv.status == InterviewStatus.SCHEDULED.value
            and (ensure_utc(iv.scheduled_at) or now) >= now
            for iv in app_row.interviews
        )
    legacy_iv = ensure_utc(app_row.interview_at)
    return legacy_iv is not None and legacy_iv >= now


def get_stale_applications(
    db: Session,
    user: User,
    *,
    stale_days: int = 7,
    now: datetime | None = None,
) -> StaleApplicationsResponse:
    """
    Identifica candidaturas ativas em `applied` ou `interview` cujo período
    desde a última referência real (interação externa registrada, entrevista
    concluída ou data de envio) supera o limite configurado, sem utilizar
    `Application.updated_at` e ignorando processos com entrevista futura marcada.
    """
    ref_now = ensure_utc(now) or datetime.now(UTC)

    rows = list(
        db.execute(
            select(Application)
            .options(selectinload(Application.interviews))
            .where(
                Application.user_id == user.id,
                Application.status.in_(tuple(DEFAULT_STALE_DAYS_BY_STATUS.keys())),
            )
        )
        .scalars()
        .all()
    )

    items: list[StaleApplicationItemResponse] = []
    for app_row in rows:
        if _has_future_scheduled_interview(app_row, now=ref_now):
            continue

        threshold_days = (
            DEFAULT_STALE_DAYS_BY_STATUS[app_row.status]
            if stale_days == 7
            else stale_days
        )

        last_ext = ensure_utc(app_row.last_external_interaction_at)
        candidates: list[tuple[datetime, str, str]] = []

        if last_ext is not None:
            candidates.append(
                (
                    last_ext,
                    "external_interaction",
                    "Última interação externa registrada",
                )
            )

        if app_row.status == ApplicationStatus.APPLIED.value:
            applied_dt = ensure_utc(app_row.applied_at)
            if applied_dt is not None:
                candidates.append(
                    (applied_dt, "applied_at", "Data de envio da candidatura")
                )
        elif app_row.status == ApplicationStatus.INTERVIEW.value:
            completed_dates = [
                ensure_utc(iv.completed_at) or ensure_utc(iv.scheduled_at)
                for iv in app_row.interviews
                if iv.status == InterviewStatus.COMPLETED.value
            ]
            valid_completed = [dt for dt in completed_dates if dt is not None]
            if valid_completed:
                candidates.append(
                    (
                        max(valid_completed),
                        "completed_interview",
                        "Última entrevista concluída",
                    )
                )

        # Sem referência temporal real confiável -> não inventar data com updated_at/created_at
        if not candidates:
            continue

        ref_dt, ref_kind, ref_desc = max(candidates, key=lambda pair: pair[0])
        elapsed = ref_now - ref_dt
        if elapsed <= timedelta(days=threshold_days):
            continue

        days_without = int(elapsed.total_seconds() // 86400)
        status_label = APPLICATION_STATUS_LABELS_PT.get(app_row.status, app_row.status)
        notice = (
            f"Sem interação externa registrada há {days_without} dia(s) "
            f"(referência: {ref_desc.lower()})."
        )
        recommended_follow_up = (
            "Enviar mensagem cordial de acompanhamento para confirmar o status da etapa."
            if app_row.status == ApplicationStatus.INTERVIEW.value
            else "Registrar eventual contato já ocorrido ou enviar acompanhamento educado da candidatura."
        )

        items.append(
            StaleApplicationItemResponse(
                application_id=app_row.id,
                company_name=app_row.company_name,
                role_title=app_row.role_title,
                status=app_row.status,
                status_label=status_label,
                last_external_interaction_at=last_ext,
                reference_timestamp_at=ref_dt,
                reference_kind=ref_kind,  # type: ignore[arg-type]
                reference_description=ref_desc,
                days_without_external_interaction=days_without,
                threshold_days=threshold_days,
                notice=notice,
                recommended_follow_up=recommended_follow_up,
            )
        )

    items.sort(
        key=lambda it: (
            -it.days_without_external_interaction,
            it.reference_timestamp_at.timestamp(),
        )
    )
    return StaleApplicationsResponse(
        stale_days_param=stale_days,
        total_count=len(items),
        items=items,
    )


# ---------------------------------------------------------------------------
# Follow-up Determinístico em Português Brasileiro
# ---------------------------------------------------------------------------


def _pick_primary_contact(contacts: list[ApplicationContact]) -> ApplicationContact | None:
    if not contacts:
        return None
    recruiter_keywords = ("recruit", "talent", "rh", "people", "sele", "hr")
    for contact in contacts:
        role_low = (contact.role_title or "").lower()
        if any(kw in role_low for kw in recruiter_keywords):
            return contact
    return contacts[0]


def generate_follow_up_template(
    db: Session,
    user: User,
    application_id: uuid.UUID,
) -> FollowUpTemplateResponse | None:
    app_row = _load_owned_application_with_children(db, user, application_id)
    if app_row is None:
        return None

    primary_contact = _pick_primary_contact(list(app_row.contacts or []))
    recipient_name = primary_contact.name if primary_contact else None
    recipient_email = primary_contact.email if primary_contact else None

    first_name = recipient_name.split()[0] if recipient_name else None
    greeting = f"Olá, {first_name}," if first_name else "Olá,"

    company_clause = f" na {app_row.company_name}" if app_row.company_name else ""
    role_title = app_row.role_title

    used_facts: list[str] = [f"Cargo: {role_title}"]
    if app_row.company_name:
        used_facts.append(f"Empresa: {app_row.company_name}")
    if recipient_name:
        used_facts.append(f"Contato cadastrado: {recipient_name}")

    completed_interviews = sorted(
        [
            iv
            for iv in (app_row.interviews or [])
            if iv.status == InterviewStatus.COMPLETED.value
        ],
        key=lambda iv: (ensure_utc(iv.completed_at) or ensure_utc(iv.scheduled_at) or iv.scheduled_at).timestamp(),
        reverse=True,
    )
    submitted_assessments = [
        a
        for a in (app_row.assessments or [])
        if a.status in {AssessmentStatus.SUBMITTED.value, AssessmentStatus.FEEDBACK_RECEIVED.value}
    ]

    last_ext = ensure_utc(app_row.last_external_interaction_at)
    applied_dt = ensure_utc(app_row.applied_at)

    if completed_interviews:
        latest_iv = completed_interviews[0]
        iv_dt = ensure_utc(latest_iv.completed_at) or ensure_utc(latest_iv.scheduled_at)
        date_fragment = f" realizada em {iv_dt.strftime('%d/%m/%Y')}" if iv_dt else ""
        used_facts.append(f"Entrevista concluída: {latest_iv.round_name}")
        body_lines = [
            f"Espero que esteja tudo bem. Gostaria de agradecer novamente pela conversa na etapa \"{latest_iv.round_name}\"{date_fragment} para a vaga de {role_title}{company_clause}.",
            "Continuo com bastante interesse na oportunidade e permaneço à disposição caso precisem de alguma informação complementar para os próximos passos do processo.",
        ]
        context_summary = "Baseado em entrevista concluída registrada na candidatura."
    elif submitted_assessments:
        latest_asmt = submitted_assessments[0]
        sub_dt = ensure_utc(latest_asmt.submitted_at)
        date_fragment = f" em {sub_dt.strftime('%d/%m/%Y')}" if sub_dt else ""
        used_facts.append(f"Teste técnico enviado: {latest_asmt.title}")
        body_lines = [
            f"Espero que esteja tudo bem. Gostaria de confirmar o recebimento do desafio técnico \"{latest_asmt.title}\", enviado{date_fragment} para a vaga de {role_title}{company_clause}.",
            "Fico totalmente à disposição para esclarecer qualquer detalhe da solução ou compartilhar mais informações quando for oportuno.",
        ]
        context_summary = "Baseado no envio registrado de teste técnico."
    elif last_ext is not None:
        used_facts.append(
            f"Última interação externa: {last_ext.strftime('%d/%m/%Y')}"
        )
        body_lines = [
            f"Espero que esteja tudo bem. Gostaria de fazer um breve acompanhamento referente ao nosso último contato em {last_ext.strftime('%d/%m/%Y')} sobre o processo seletivo para {role_title}{company_clause}.",
            "Reitero meu interesse na vaga e continuo à disposição para os próximos passos ou informações adicionais.",
        ]
        context_summary = "Baseado na data real da última interação externa registrada."
    elif applied_dt is not None:
        used_facts.append(f"Data de candidatura: {applied_dt.strftime('%d/%m/%Y')}")
        body_lines = [
            f"Espero que esteja tudo bem. Enviei minha candidatura em {applied_dt.strftime('%d/%m/%Y')} para a posição de {role_title}{company_clause} e gostaria de verificar se há alguma atualização sobre o andamento do processo.",
            "Permaneço à disposição para conversar e compartilhar mais detalhes sobre minha trajetória.",
        ]
        context_summary = "Baseado no registro de envio da candidatura."
    else:
        body_lines = [
            f"Espero que esteja tudo bem. Gostaria de acompanhar o andamento do processo seletivo para a vaga de {role_title}{company_clause}.",
            "Reitero meu interesse na oportunidade e fico à disposição caso necessitem de informações adicionais.",
        ]
        context_summary = "Versão neutra segura (sem data de envio ou interação externa registrada)."

    candidate_name = user.display_name.strip() if user.display_name else "Candidato"
    full_message = "\n\n".join(
        [
            greeting,
            *body_lines,
            f"Agradeço desde já pela atenção.\nAtenciosamente,\n{candidate_name}",
        ]
    )
    subject = f"Acompanhamento — Processo seletivo {role_title}{company_clause}"

    return FollowUpTemplateResponse(
        application_id=app_row.id,
        subject=subject,
        message=full_message,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        context_summary=context_summary,
        used_facts=used_facts,
        disclaimer="Mensagem determinística gerada com base exclusiva nos registros salvos. Revise antes de enviar manualmente.",
    )
