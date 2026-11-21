from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import math
import uuid

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.ai_usage import AIUsageLedger, AIUsageStatus
from app.models.material import ApplicationMaterial, ApplicationMaterialVersion
from app.models.user import AccountStatus, User
from app.services.materials.ai._db_locks import (
    acquire_quota_scope_locks,
    ensure_utc,
    prepare_atomic_write_transaction,
    run_atomic_with_sqlite_retry,
)
from app.services.materials.ai.contracts import (
    AIDisabledError,
    AIQuotaExceededError,
    AIReservationNotFoundError,
    AIReservationStateError,
    LLMTokenUsage,
    validate_safe_technical_identifier,
)

logger = logging.getLogger("job_hunter.materials.ai.quota")

_REQUEST_CONSUMING_STATUSES: tuple[str, ...] = (
    AIUsageStatus.RESERVED.value,
    AIUsageStatus.COMPLETED.value,
    AIUsageStatus.FAILED.value,
)


@dataclass(frozen=True, slots=True)
class QuotaAvailability:
    """Disponibilidade atual de cotas de IA para um usuário específico em UTC."""

    ai_enabled: bool
    window_seconds: int
    user_window_used_requests: int
    user_window_remaining_requests: int
    user_window_max_requests: int
    user_daily_used_requests: int
    user_daily_remaining_requests: int
    user_daily_max_requests: int
    user_daily_used_tokens: int
    user_daily_remaining_tokens: int
    user_daily_max_tokens: int
    global_daily_remaining_tokens: int
    effective_remaining_tokens: int
    can_reserve: bool


@dataclass(frozen=True, slots=True)
class LedgerEntrySnapshot:
    """Projeção imutável e sem conteúdo sensível de um registro em ai_usage_ledger."""

    id: uuid.UUID
    user_id: uuid.UUID
    material_id: uuid.UUID | None
    version_id: uuid.UUID | None
    operation_type: str
    provider_name: str | None
    model_name: str | None
    status: AIUsageStatus
    reserved_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    usage_reported: bool
    latency_ms: int | None
    error_code: str | None
    expires_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _to_entry_snapshot(entry: AIUsageLedger) -> LedgerEntrySnapshot:
    return LedgerEntrySnapshot(
        id=entry.id,
        user_id=entry.user_id,
        material_id=entry.material_id,
        version_id=entry.version_id,
        operation_type=entry.operation_type,
        provider_name=entry.provider_name,
        model_name=entry.model_name,
        status=AIUsageStatus(entry.status),
        reserved_tokens=int(entry.reserved_tokens),
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        total_tokens=entry.total_tokens,
        usage_reported=bool(entry.usage_reported),
        latency_ms=entry.latency_ms,
        error_code=entry.error_code,
        expires_at=ensure_utc(entry.expires_at),
        completed_at=ensure_utc(entry.completed_at) if entry.completed_at else None,
        created_at=ensure_utc(entry.created_at),
        updated_at=ensure_utc(entry.updated_at),
    )


def _utc_day_bounds(now_utc: datetime) -> tuple[datetime, datetime, str]:
    day_start = datetime(
        now_utc.year,
        now_utc.month,
        now_utc.day,
        0,
        0,
        0,
        tzinfo=UTC,
    )
    day_end = day_start + timedelta(days=1)
    return day_start, day_end, day_start.date().isoformat()


def _token_contribution_expression():
    """Expressão SQL exata para contabilização de tokens sem inventar consumo.

    - ``reserved`` ativa: contabiliza ``reserved_tokens`` para segurar orçamento em voo.
    - ``completed`` ou ``failed`` com ``usage_reported=True``: contabiliza ``total_tokens`` real.
    - ``usage_reported=False`` ou estados ``released``/``expired``: contabiliza ``0``.
    """
    return case(
        (AIUsageLedger.status == AIUsageStatus.RESERVED.value, AIUsageLedger.reserved_tokens),
        (
            and_(
                AIUsageLedger.status.in_(
                    [AIUsageStatus.COMPLETED.value, AIUsageStatus.FAILED.value]
                ),
                AIUsageLedger.usage_reported.is_(True),
                AIUsageLedger.total_tokens.is_not(None),
            ),
            AIUsageLedger.total_tokens,
        ),
        else_=0,
    )


def _expire_overdue_inline(db: Session, current_time: datetime) -> int:
    result = db.execute(
        update(AIUsageLedger)
        .where(
            AIUsageLedger.status == AIUsageStatus.RESERVED.value,
            AIUsageLedger.expires_at <= current_time,
        )
        .values(
            status=AIUsageStatus.EXPIRED.value,
            error_code="reservation_expired",
            completed_at=current_time,
            updated_at=current_time,
        )
    )
    db.flush()
    return int(result.rowcount or 0)


def _verify_active_user_and_optional_refs(
    db: Session,
    *,
    user_id: uuid.UUID,
    material_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
) -> None:
    user_status = db.scalar(select(User.account_status).where(User.id == user_id))
    if user_status != AccountStatus.ACTIVE.value:
        raise AIReservationNotFoundError("Usuário não encontrado ou inativo.")

    if material_id is not None:
        mat_exists = db.scalar(
            select(ApplicationMaterial.id).where(
                ApplicationMaterial.id == material_id,
                ApplicationMaterial.user_id == user_id,
            )
        )
        if mat_exists is None:
            raise AIReservationNotFoundError("Material informado não encontrado.")

    if version_id is not None:
        assert material_id is not None
        ver_exists = db.scalar(
            select(ApplicationMaterialVersion.id).where(
                ApplicationMaterialVersion.id == version_id,
                ApplicationMaterialVersion.material_id == material_id,
            )
        )
        if ver_exists is None:
            raise AIReservationNotFoundError("Versão de material informada não encontrada.")


def _compute_usage_counters(
    db: Session,
    *,
    user_id: uuid.UUID,
    current_time: datetime,
    window_seconds: int,
) -> tuple[int, datetime | None, int, int, int]:
    day_start, day_end, _ = _utc_day_bounds(current_time)
    window_start = current_time - timedelta(seconds=window_seconds)
    token_expr = _token_contribution_expression()

    window_row = db.execute(
        select(
            func.count(AIUsageLedger.id),
            func.min(AIUsageLedger.created_at),
        ).where(
            AIUsageLedger.user_id == user_id,
            AIUsageLedger.created_at >= window_start,
            AIUsageLedger.status.in_(_REQUEST_CONSUMING_STATUSES),
        )
    ).one()
    user_window_reqs = int(window_row[0] or 0)
    oldest_in_window = ensure_utc(window_row[1]) if window_row[1] is not None else None

    user_daily_row = db.execute(
        select(
            func.count(
                case(
                    (AIUsageLedger.status.in_(_REQUEST_CONSUMING_STATUSES), 1),
                    else_=None,
                )
            ),
            func.coalesce(func.sum(token_expr), 0),
        ).where(
            AIUsageLedger.user_id == user_id,
            AIUsageLedger.created_at >= day_start,
            AIUsageLedger.created_at < day_end,
        )
    ).one()
    user_daily_reqs = int(user_daily_row[0] or 0)
    user_daily_tokens = int(user_daily_row[1] or 0)

    global_daily_tokens = int(
        db.scalar(
            select(func.coalesce(func.sum(token_expr), 0)).where(
                AIUsageLedger.created_at >= day_start,
                AIUsageLedger.created_at < day_end,
            )
        )
        or 0
    )

    return (
        user_window_reqs,
        oldest_in_window,
        user_daily_reqs,
        user_daily_tokens,
        global_daily_tokens,
    )


def expire_abandoned_reservations(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Expira em transação curta todas as reservas abandonadas com expires_at <= now."""
    current_time = ensure_utc(now or datetime.now(UTC))

    def _tx() -> int:
        prepare_atomic_write_transaction(db)
        expired_count = _expire_overdue_inline(db, current_time)
        db.commit()
        return expired_count

    count = run_atomic_with_sqlite_retry(db, _tx)
    if count > 0:
        logger.info("Reservas de IA abandonadas expiradas count=%d", count)
    return count


def get_quota_availability(
    db: Session,
    *,
    user_id: uuid.UUID,
    requested_tokens: int = 0,
    now: datetime | None = None,
    settings_override: Settings | None = None,
) -> QuotaAvailability:
    """Consulta disponibilidade atual de cotas do usuário em UTC (expirando vencidas antes)."""
    if requested_tokens < 0:
        raise ValueError("requested_tokens não pode ser negativo.")

    cfg = settings_override or get_settings()
    current_time = ensure_utc(now or datetime.now(UTC))
    _, _, day_key = _utc_day_bounds(current_time)

    def _tx() -> QuotaAvailability:
        acquire_quota_scope_locks(
            db,
            [
                (f"global:{day_key}", "global"),
                (f"user:{user_id}", "user"),
            ],
            current_time,
        )
        try:
            _verify_active_user_and_optional_refs(
                db,
                user_id=user_id,
                material_id=None,
                version_id=None,
            )
        except Exception:
            db.rollback()
            raise

        _expire_overdue_inline(db, current_time)
        (
            win_reqs,
            _oldest,
            day_reqs,
            user_tokens,
            global_tokens,
        ) = _compute_usage_counters(
            db,
            user_id=user_id,
            current_time=current_time,
            window_seconds=cfg.ai_rate_limit_window_seconds,
        )
        db.commit()

        win_rem = max(0, cfg.ai_user_window_max_requests - win_reqs)
        day_req_rem = max(0, cfg.ai_user_daily_max_requests - day_reqs)
        user_tok_rem = max(0, cfg.ai_user_daily_max_tokens - user_tokens)
        global_tok_rem = max(0, cfg.ai_global_daily_max_tokens - global_tokens)
        eff_tok_rem = min(user_tok_rem, global_tok_rem)

        can_reserve = (
            bool(cfg.ai_assisted_enabled)
            and win_rem >= 1
            and day_req_rem >= 1
            and user_tok_rem >= requested_tokens
            and global_tok_rem >= requested_tokens
        )
        return QuotaAvailability(
            ai_enabled=cfg.ai_assisted_enabled,
            window_seconds=cfg.ai_rate_limit_window_seconds,
            user_window_used_requests=win_reqs,
            user_window_remaining_requests=win_rem,
            user_window_max_requests=cfg.ai_user_window_max_requests,
            user_daily_used_requests=day_reqs,
            user_daily_remaining_requests=day_req_rem,
            user_daily_max_requests=cfg.ai_user_daily_max_requests,
            user_daily_used_tokens=user_tokens,
            user_daily_remaining_tokens=user_tok_rem,
            user_daily_max_tokens=cfg.ai_user_daily_max_tokens,
            global_daily_remaining_tokens=global_tok_rem,
            effective_remaining_tokens=eff_tok_rem,
            can_reserve=can_reserve,
        )

    return run_atomic_with_sqlite_retry(db, _tx)


def reserve_ai_quota(
    db: Session,
    *,
    user_id: uuid.UUID,
    operation_type: str,
    reserved_tokens: int,
    material_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    now: datetime | None = None,
    settings_override: Settings | None = None,
) -> LedgerEntrySnapshot:
    """Reserva atomicamente uma utilização de IA antes de qualquer chamada externa.

    Garante em transação curta serializada por escopos (global + usuário):
    1. Kill switch habilitado.
    2. Validação de posse de usuário, material e versão.
    3. Expiração de eventuais reservas abandonadas vencidas.
    4. Verificação das 4 cotas (janela curta, diária de reqs, diária de tokens por usuário e global).
    5. Persistência imediata com commit liberando os locks de banco antes do I/O externo.
    """
    cfg = settings_override or get_settings()
    if not cfg.ai_assisted_enabled:
        raise AIDisabledError(
            "Aprimoramento assistido por IA está desabilitado por configuração."
        )

    if reserved_tokens < 0:
        raise ValueError("reserved_tokens não pode ser negativo.")
    if version_id is not None and material_id is None:
        raise ValueError("material_id deve ser informado quando version_id estiver presente.")

    clean_op = validate_safe_technical_identifier(
        operation_type,
        field_name="operation_type",
        max_length=64,
    )
    clean_provider = validate_safe_technical_identifier(
        provider_name,
        field_name="provider_name",
        max_length=64,
        allow_none=True,
    )
    clean_model = validate_safe_technical_identifier(
        model_name,
        field_name="model_name",
        max_length=120,
        allow_none=True,
    )
    assert clean_op is not None

    current_time = ensure_utc(now or datetime.now(UTC))
    _, day_end, day_key = _utc_day_bounds(current_time)

    def _tx() -> LedgerEntrySnapshot:
        acquire_quota_scope_locks(
            db,
            [
                (f"global:{day_key}", "global"),
                (f"user:{user_id}", "user"),
            ],
            current_time,
        )
        try:
            _verify_active_user_and_optional_refs(
                db,
                user_id=user_id,
                material_id=material_id,
                version_id=version_id,
            )
        except Exception:
            db.rollback()
            raise

        _expire_overdue_inline(db, current_time)
        (
            win_reqs,
            oldest_in_window,
            day_reqs,
            user_tokens,
            global_tokens,
        ) = _compute_usage_counters(
            db,
            user_id=user_id,
            current_time=current_time,
            window_seconds=cfg.ai_rate_limit_window_seconds,
        )

        seconds_until_day_end = max(
            1, math.ceil((day_end - current_time).total_seconds())
        )

        if win_reqs + 1 > cfg.ai_user_window_max_requests:
            if oldest_in_window is not None:
                window_unlock_at = oldest_in_window + timedelta(
                    seconds=cfg.ai_rate_limit_window_seconds
                )
                retry_win = max(
                    1, math.ceil((window_unlock_at - current_time).total_seconds())
                )
            else:
                retry_win = cfg.ai_rate_limit_window_seconds
            db.commit()
            raise AIQuotaExceededError(
                "Limite de requisições de IA na janela atual atingido.",
                scope="user_window_requests",
                retry_after_seconds=retry_win,
            )

        if day_reqs + 1 > cfg.ai_user_daily_max_requests:
            db.commit()
            raise AIQuotaExceededError(
                "Limite diário de requisições de IA por usuário atingido.",
                scope="user_daily_requests",
                retry_after_seconds=seconds_until_day_end,
            )

        if user_tokens + reserved_tokens > cfg.ai_user_daily_max_tokens:
            db.commit()
            raise AIQuotaExceededError(
                "Limite diário de tokens de IA por usuário atingido.",
                scope="user_daily_tokens",
                retry_after_seconds=seconds_until_day_end,
            )

        if global_tokens + reserved_tokens > cfg.ai_global_daily_max_tokens:
            db.commit()
            raise AIQuotaExceededError(
                "Orçamento global diário de tokens de IA atingido nesta instância.",
                scope="global_daily_tokens",
                retry_after_seconds=seconds_until_day_end,
            )

        expires_at = current_time + timedelta(seconds=cfg.ai_reservation_ttl_seconds)
        entry = AIUsageLedger(
            id=uuid.uuid4(),
            user_id=user_id,
            material_id=material_id,
            version_id=version_id,
            operation_type=clean_op,
            provider_name=clean_provider,
            model_name=clean_model,
            status=AIUsageStatus.RESERVED.value,
            reserved_tokens=reserved_tokens,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            usage_reported=False,
            latency_ms=None,
            error_code=None,
            expires_at=expires_at,
            completed_at=None,
            created_at=current_time,
            updated_at=current_time,
        )
        db.add(entry)
        db.commit()
        return _to_entry_snapshot(entry)

    snapshot = run_atomic_with_sqlite_retry(db, _tx)
    logger.info(
        "Reserva de cota de IA criada reservation_id=%s operation=%s reserved_tokens=%d",
        str(snapshot.id),
        snapshot.operation_type,
        snapshot.reserved_tokens,
    )
    return snapshot


def _load_owned_entry_for_transition(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    user_id: uuid.UUID,
    current_time: datetime,
    allow_transaction_reset: bool = True,
) -> AIUsageLedger:
    _, _, day_key = _utc_day_bounds(current_time)
    acquire_quota_scope_locks(
        db,
        [
            (f"global:{day_key}", "global"),
            (f"user:{user_id}", "user"),
        ],
        current_time,
        allow_transaction_reset=allow_transaction_reset,
    )
    stmt = select(AIUsageLedger).where(
        AIUsageLedger.id == reservation_id,
        AIUsageLedger.user_id == user_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()

    entry = db.scalar(stmt)
    if entry is None:
        if allow_transaction_reset:
            db.rollback()
        raise AIReservationNotFoundError("Reserva de IA não encontrada.")
    return entry


def confirm_ai_quota_usage(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    user_id: uuid.UUID,
    provider_name: str,
    model_name: str,
    token_usage: LLMTokenUsage | None = None,
    latency_ms: int | None = None,
    resolved_version_id: uuid.UUID | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> LedgerEntrySnapshot:
    """Confirma conclusão de operação de IA em transação curta pós-chamada externa.

    Quando ``token_usage`` é ``None`` (provider não informou consumo), persiste
    ``input_tokens=None``, ``output_tokens=None``, ``total_tokens=None`` e
    ``usage_reported=False``, sem inventar valores de consumo.
    """
    clean_provider = validate_safe_technical_identifier(
        provider_name,
        field_name="provider_name",
        max_length=64,
    )
    clean_model = validate_safe_technical_identifier(
        model_name,
        field_name="model_name",
        max_length=120,
    )
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms não pode ser negativo.")

    current_time = ensure_utc(now or datetime.now(UTC))

    def _tx() -> LedgerEntrySnapshot:
        entry = _load_owned_entry_for_transition(
            db,
            reservation_id=reservation_id,
            user_id=user_id,
            current_time=current_time,
            allow_transaction_reset=commit,
        )
        if entry.status not in (
            AIUsageStatus.RESERVED.value,
            AIUsageStatus.EXPIRED.value,
        ):
            if commit:
                db.rollback()
            raise AIReservationStateError(
                f"Não é possível confirmar reserva no estado '{entry.status}'."
            )

        if resolved_version_id is not None:
            if entry.material_id is None:
                if commit:
                    db.rollback()
                raise AIReservationStateError(
                    "Não é possível vincular version_id a uma reserva sem material_id."
                )
            ver_exists = db.scalar(
                select(ApplicationMaterialVersion.id).where(
                    ApplicationMaterialVersion.id == resolved_version_id,
                    ApplicationMaterialVersion.material_id == entry.material_id,
                )
            )
            if ver_exists is None:
                if commit:
                    db.rollback()
                raise AIReservationNotFoundError(
                    "Versão gerada informada para confirmação do ledger não pertence ao material."
                )
            entry.version_id = resolved_version_id

        entry.provider_name = clean_provider
        entry.model_name = clean_model
        entry.status = AIUsageStatus.COMPLETED.value
        entry.error_code = None
        entry.latency_ms = latency_ms
        if token_usage is not None:
            entry.input_tokens = token_usage.input_tokens
            entry.output_tokens = token_usage.output_tokens
            entry.total_tokens = token_usage.resolved_total_tokens
            entry.usage_reported = True
        else:
            entry.input_tokens = None
            entry.output_tokens = None
            entry.total_tokens = None
            entry.usage_reported = False

        entry.completed_at = current_time
        entry.updated_at = current_time
        if commit:
            db.commit()
        else:
            db.flush()
        return _to_entry_snapshot(entry)

    if not commit:
        return _tx()
    snapshot = run_atomic_with_sqlite_retry(db, _tx)
    logger.info(
        "Reserva de IA confirmada reservation_id=%s provider=%s usage_reported=%s latency_ms=%s",
        str(snapshot.id),
        snapshot.provider_name,
        snapshot.usage_reported,
        snapshot.latency_ms,
    )
    return snapshot


def fail_ai_quota_usage(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    user_id: uuid.UUID,
    error_code: str,
    provider_name: str | None = None,
    model_name: str | None = None,
    token_usage: LLMTokenUsage | None = None,
    latency_ms: int | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> LedgerEntrySnapshot:
    """Registra falha de operação que chegou a iniciar execução externa.

    Mantém rastreabilidade e contabilização da tentativa no limite de requisições,
    liberando ``reserved_tokens`` caso o provider não tenha informado ``token_usage``.
    """
    clean_error = validate_safe_technical_identifier(
        error_code,
        field_name="error_code",
        max_length=64,
    )
    clean_provider = validate_safe_technical_identifier(
        provider_name,
        field_name="provider_name",
        max_length=64,
        allow_none=True,
    )
    clean_model = validate_safe_technical_identifier(
        model_name,
        field_name="model_name",
        max_length=120,
        allow_none=True,
    )
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms não pode ser negativo.")

    current_time = ensure_utc(now or datetime.now(UTC))

    def _tx() -> LedgerEntrySnapshot:
        entry = _load_owned_entry_for_transition(
            db,
            reservation_id=reservation_id,
            user_id=user_id,
            current_time=current_time,
            allow_transaction_reset=commit,
        )
        if entry.status not in (
            AIUsageStatus.RESERVED.value,
            AIUsageStatus.EXPIRED.value,
        ):
            if commit:
                db.rollback()
            raise AIReservationStateError(
                f"Não é possível registrar falha para reserva no estado '{entry.status}'."
            )

        if clean_provider is not None:
            entry.provider_name = clean_provider
        if clean_model is not None:
            entry.model_name = clean_model
        entry.status = AIUsageStatus.FAILED.value
        entry.error_code = clean_error
        entry.latency_ms = latency_ms
        if token_usage is not None:
            entry.input_tokens = token_usage.input_tokens
            entry.output_tokens = token_usage.output_tokens
            entry.total_tokens = token_usage.resolved_total_tokens
            entry.usage_reported = True
        else:
            entry.input_tokens = None
            entry.output_tokens = None
            entry.total_tokens = None
            entry.usage_reported = False

        entry.completed_at = current_time
        entry.updated_at = current_time
        if commit:
            db.commit()
        else:
            db.flush()
        return _to_entry_snapshot(entry)

    if not commit:
        return _tx()
    snapshot = run_atomic_with_sqlite_retry(db, _tx)
    logger.warning(
        "Operação de IA encerrada com falha reservation_id=%s error_code=%s latency_ms=%s",
        str(snapshot.id),
        snapshot.error_code,
        snapshot.latency_ms,
    )
    return snapshot


def release_ai_quota_reservation(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    user_id: uuid.UUID,
    reason_code: str = "released_before_call",
    now: datetime | None = None,
) -> LedgerEntrySnapshot:
    """Libera explicitamente uma reserva ativa antes de iniciar qualquer chamada externa.

    Devolve integralmente o slot de requisição e os tokens reservados, mantendo
    o registro auditável no estado ``released``.
    """
    clean_reason = validate_safe_technical_identifier(
        reason_code,
        field_name="reason_code",
        max_length=64,
    )
    current_time = ensure_utc(now or datetime.now(UTC))

    def _tx() -> LedgerEntrySnapshot:
        entry = _load_owned_entry_for_transition(
            db,
            reservation_id=reservation_id,
            user_id=user_id,
            current_time=current_time,
        )
        if entry.status != AIUsageStatus.RESERVED.value:
            db.rollback()
            raise AIReservationStateError(
                f"Apenas reservas no estado 'reserved' podem ser liberadas (atual: '{entry.status}')."
            )

        entry.status = AIUsageStatus.RELEASED.value
        entry.error_code = clean_reason
        entry.input_tokens = None
        entry.output_tokens = None
        entry.total_tokens = None
        entry.usage_reported = False
        entry.latency_ms = None
        entry.completed_at = current_time
        entry.updated_at = current_time
        db.commit()
        return _to_entry_snapshot(entry)

    snapshot = run_atomic_with_sqlite_retry(db, _tx)
    logger.info(
        "Reserva de IA liberada antes de chamada externa reservation_id=%s reason=%s",
        str(snapshot.id),
        snapshot.error_code,
    )
    return snapshot


def get_ledger_entry_for_user(
    db: Session,
    *,
    entry_id: uuid.UUID,
    user_id: uuid.UUID,
) -> LedgerEntrySnapshot:
    """Retorna um registro do ledger garantindo isolamento estrito por user_id."""
    entry = db.scalar(
        select(AIUsageLedger).where(
            AIUsageLedger.id == entry_id,
            AIUsageLedger.user_id == user_id,
        )
    )
    if entry is None:
        raise AIReservationNotFoundError("Registro de utilização de IA não encontrado.")
    return _to_entry_snapshot(entry)
