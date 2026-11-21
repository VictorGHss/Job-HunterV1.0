from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.ai_usage import AICircuitBreakerRecord, AICircuitState
from app.services.materials.ai._db_locks import (
    ensure_utc,
    prepare_atomic_write_transaction,
    run_atomic_with_sqlite_retry,
)
from app.services.materials.ai.contracts import (
    AICircuitOpenError,
    validate_safe_technical_identifier,
)


@dataclass(frozen=True, slots=True)
class CircuitBreakerSnapshot:
    provider_key: str
    state: AICircuitState
    consecutive_failures: int
    opened_at: datetime | None
    retry_available_at: datetime | None
    half_open_probe_in_flight: bool
    last_failure_at: datetime | None
    last_failure_reason: str | None
    last_success_at: datetime | None
    can_execute: bool
    retry_after_seconds: int


def _normalize_provider_key(provider_key: str) -> str:
    cleaned = validate_safe_technical_identifier(
        provider_key,
        field_name="provider_key",
        max_length=64,
    )
    assert cleaned is not None
    return cleaned.lower()


def _lock_or_create_breaker_row(
    db: Session,
    provider_key: str,
    now: datetime,
    *,
    allow_transaction_reset: bool = True,
) -> AICircuitBreakerRecord:
    dialect_name = prepare_atomic_write_transaction(
        db,
        allow_transaction_reset=allow_transaction_reset,
    )
    init_values = {
        "provider_key": provider_key,
        "state": AICircuitState.CLOSED.value,
        "consecutive_failures": 0,
        "opened_at": None,
        "retry_available_at": None,
        "half_open_probe_in_flight": False,
        "half_open_probe_started_at": None,
        "last_failure_at": None,
        "last_failure_reason": None,
        "last_success_at": None,
        "created_at": now,
        "updated_at": now,
    }

    if dialect_name == "postgresql":
        db.execute(
            pg_insert(AICircuitBreakerRecord)
            .values([init_values])
            .on_conflict_do_nothing(index_elements=["provider_key"])
        )
        row = db.scalar(
            select(AICircuitBreakerRecord)
            .where(AICircuitBreakerRecord.provider_key == provider_key)
            .with_for_update()
        )
        assert row is not None
        return row

    if dialect_name == "sqlite":
        db.execute(
            sqlite_insert(AICircuitBreakerRecord)
            .values([init_values])
            .on_conflict_do_update(
                index_elements=["provider_key"],
                set_={"updated_at": now},
            )
        )
        row = db.scalar(
            select(AICircuitBreakerRecord).where(
                AICircuitBreakerRecord.provider_key == provider_key
            )
        )
        assert row is not None
        return row

    row = db.get(AICircuitBreakerRecord, provider_key)
    if row is None:
        row = AICircuitBreakerRecord(**init_values)
        db.add(row)
        db.flush()
    return row


def _to_snapshot(
    row: AICircuitBreakerRecord,
    *,
    now: datetime,
    probe_ttl_seconds: int,
) -> CircuitBreakerSnapshot:
    state_enum = AICircuitState(row.state)
    opened_at = ensure_utc(row.opened_at) if row.opened_at else None
    retry_at = ensure_utc(row.retry_available_at) if row.retry_available_at else None
    last_fail = ensure_utc(row.last_failure_at) if row.last_failure_at else None
    last_ok = ensure_utc(row.last_success_at) if row.last_success_at else None
    probe_started = (
        ensure_utc(row.half_open_probe_started_at)
        if row.half_open_probe_started_at
        else None
    )

    can_execute = True
    retry_after = 0
    if state_enum == AICircuitState.OPEN:
        if retry_at is not None and now < retry_at:
            can_execute = False
            retry_after = max(1, math.ceil((retry_at - now).total_seconds()))
    elif state_enum == AICircuitState.HALF_OPEN and row.half_open_probe_in_flight:
        if probe_started is not None:
            probe_expires = probe_started + timedelta(seconds=probe_ttl_seconds)
            if now < probe_expires:
                can_execute = False
                retry_after = max(1, math.ceil((probe_expires - now).total_seconds()))

    return CircuitBreakerSnapshot(
        provider_key=row.provider_key,
        state=state_enum,
        consecutive_failures=row.consecutive_failures,
        opened_at=opened_at,
        retry_available_at=retry_at,
        half_open_probe_in_flight=row.half_open_probe_in_flight,
        last_failure_at=last_fail,
        last_failure_reason=row.last_failure_reason,
        last_success_at=last_ok,
        can_execute=can_execute,
        retry_after_seconds=retry_after,
    )


def get_circuit_state(
    db: Session,
    *,
    provider_key: str = "default",
    now: datetime | None = None,
    settings_override: Settings | None = None,
) -> CircuitBreakerSnapshot:
    """Consulta o estado compartilhado atual do circuit breaker sem alterá-lo."""
    cfg = settings_override or get_settings()
    current_time = ensure_utc(now or datetime.now(UTC))
    key = _normalize_provider_key(provider_key)

    row = db.scalar(
        select(AICircuitBreakerRecord).where(
            AICircuitBreakerRecord.provider_key == key
        )
    )
    if row is None:
        return CircuitBreakerSnapshot(
            provider_key=key,
            state=AICircuitState.CLOSED,
            consecutive_failures=0,
            opened_at=None,
            retry_available_at=None,
            half_open_probe_in_flight=False,
            last_failure_at=None,
            last_failure_reason=None,
            last_success_at=None,
            can_execute=True,
            retry_after_seconds=0,
        )

    return _to_snapshot(
        row,
        now=current_time,
        probe_ttl_seconds=cfg.ai_reservation_ttl_seconds,
    )


def check_and_acquire_circuit_execution(
    db: Session,
    *,
    provider_key: str = "default",
    now: datetime | None = None,
    settings_override: Settings | None = None,
) -> CircuitBreakerSnapshot:
    """Verifica atomicamente se uma chamada externa pode prosseguir.

    - Se ``closed``: permite execução imediata.
    - Se ``open`` e dentro do cooldown: lança ``AICircuitOpenError``.
    - Se ``open`` e ``now >= retry_available_at``: transiciona atomicamente para
      ``half_open`` marcando uma única sonda em voo (``half_open_probe_in_flight=True``).
    - Se ``half_open`` com sonda ativa dentro do TTL: bloqueia chamadas concorrentes
      com ``AICircuitOpenError`` para evitar sobrecarga na recuperação.
    """
    cfg = settings_override or get_settings()
    current_time = ensure_utc(now or datetime.now(UTC))
    key = _normalize_provider_key(provider_key)

    def _tx() -> CircuitBreakerSnapshot:
        row = _lock_or_create_breaker_row(db, key, current_time)
        state_val = row.state

        if state_val == AICircuitState.OPEN.value:
            retry_at = (
                ensure_utc(row.retry_available_at)
                if row.retry_available_at
                else current_time
            )
            if current_time < retry_at:
                retry_secs = max(1, math.ceil((retry_at - current_time).total_seconds()))
                opened_at = ensure_utc(row.opened_at) if row.opened_at else None
                db.commit()
                raise AICircuitOpenError(
                    "Circuit breaker aberto por indisponibilidade recente do provider.",
                    provider_key=key,
                    state=AICircuitState.OPEN.value,
                    retry_after_seconds=retry_secs,
                    opened_at=opened_at,
                    retry_available_at=retry_at,
                )

            # Cooldown encerrado -> entra em half_open permitindo 1 sonda exclusiva
            row.state = AICircuitState.HALF_OPEN.value
            row.half_open_probe_in_flight = True
            row.half_open_probe_started_at = current_time
            row.updated_at = current_time
            db.commit()
            return CircuitBreakerSnapshot(
                provider_key=key,
                state=AICircuitState.HALF_OPEN,
                consecutive_failures=row.consecutive_failures,
                opened_at=ensure_utc(row.opened_at) if row.opened_at else None,
                retry_available_at=retry_at,
                half_open_probe_in_flight=True,
                last_failure_at=ensure_utc(row.last_failure_at) if row.last_failure_at else None,
                last_failure_reason=row.last_failure_reason,
                last_success_at=ensure_utc(row.last_success_at) if row.last_success_at else None,
                can_execute=True,
                retry_after_seconds=0,
            )

        if state_val == AICircuitState.HALF_OPEN.value:
            probe_started = (
                ensure_utc(row.half_open_probe_started_at)
                if row.half_open_probe_started_at
                else None
            )
            probe_ttl = timedelta(seconds=cfg.ai_reservation_ttl_seconds)
            if (
                row.half_open_probe_in_flight
                and probe_started is not None
                and current_time < (probe_started + probe_ttl)
            ):
                retry_secs = max(
                    1,
                    math.ceil(((probe_started + probe_ttl) - current_time).total_seconds()),
                )
                opened_at = ensure_utc(row.opened_at) if row.opened_at else None
                retry_at = ensure_utc(row.retry_available_at) if row.retry_available_at else None
                db.commit()
                raise AICircuitOpenError(
                    "Circuit breaker em sondagem de recuperação (half-open); aguarde a conclusão.",
                    provider_key=key,
                    state=AICircuitState.HALF_OPEN.value,
                    retry_after_seconds=retry_secs,
                    opened_at=opened_at,
                    retry_available_at=retry_at,
                )

            # Sonda anterior inexistente ou expirada -> assume nova sonda
            row.half_open_probe_in_flight = True
            row.half_open_probe_started_at = current_time
            row.updated_at = current_time
            db.commit()
            return CircuitBreakerSnapshot(
                provider_key=key,
                state=AICircuitState.HALF_OPEN,
                consecutive_failures=row.consecutive_failures,
                opened_at=ensure_utc(row.opened_at) if row.opened_at else None,
                retry_available_at=ensure_utc(row.retry_available_at) if row.retry_available_at else None,
                half_open_probe_in_flight=True,
                last_failure_at=ensure_utc(row.last_failure_at) if row.last_failure_at else None,
                last_failure_reason=row.last_failure_reason,
                last_success_at=ensure_utc(row.last_success_at) if row.last_success_at else None,
                can_execute=True,
                retry_after_seconds=0,
            )

        db.commit()
        return _to_snapshot(
            row,
            now=current_time,
            probe_ttl_seconds=cfg.ai_reservation_ttl_seconds,
        )

    return run_atomic_with_sqlite_retry(db, _tx)


def record_circuit_success(
    db: Session,
    *,
    provider_key: str = "default",
    now: datetime | None = None,
    settings_override: Settings | None = None,
    commit: bool = True,
) -> CircuitBreakerSnapshot:
    """Registra sucesso na comunicação com o provider e fecha/restaura o circuito."""
    cfg = settings_override or get_settings()
    current_time = ensure_utc(now or datetime.now(UTC))
    key = _normalize_provider_key(provider_key)

    def _tx() -> CircuitBreakerSnapshot:
        row = _lock_or_create_breaker_row(
            db,
            key,
            current_time,
            allow_transaction_reset=commit,
        )
        row.state = AICircuitState.CLOSED.value
        row.consecutive_failures = 0
        row.opened_at = None
        row.retry_available_at = None
        row.half_open_probe_in_flight = False
        row.half_open_probe_started_at = None
        row.last_success_at = current_time
        row.updated_at = current_time
        if commit:
            db.commit()
        else:
            db.flush()
        return _to_snapshot(
            row,
            now=current_time,
            probe_ttl_seconds=cfg.ai_reservation_ttl_seconds,
        )

    if not commit:
        return _tx()
    return run_atomic_with_sqlite_retry(db, _tx)


def record_circuit_failure(
    db: Session,
    *,
    provider_key: str = "default",
    reason_code: str = "provider_error",
    now: datetime | None = None,
    settings_override: Settings | None = None,
    commit: bool = True,
) -> CircuitBreakerSnapshot:
    """Registra falha técnica do provider e abre/reabre o circuito quando aplicável."""
    cfg = settings_override or get_settings()
    current_time = ensure_utc(now or datetime.now(UTC))
    key = _normalize_provider_key(provider_key)
    clean_reason = validate_safe_technical_identifier(
        reason_code,
        field_name="reason_code",
        max_length=64,
    )

    def _tx() -> CircuitBreakerSnapshot:
        row = _lock_or_create_breaker_row(
            db,
            key,
            current_time,
            allow_transaction_reset=commit,
        )
        prev_state = row.state
        next_failures = int(row.consecutive_failures) + 1
        row.consecutive_failures = next_failures
        row.last_failure_at = current_time
        row.last_failure_reason = clean_reason
        row.half_open_probe_in_flight = False
        row.half_open_probe_started_at = None

        cooldown = timedelta(seconds=cfg.ai_circuit_breaker_cooldown_seconds)
        should_open = (
            prev_state == AICircuitState.HALF_OPEN.value
            or next_failures >= cfg.ai_circuit_breaker_failure_threshold
        )
        if should_open:
            row.state = AICircuitState.OPEN.value
            if prev_state != AICircuitState.OPEN.value or row.opened_at is None:
                row.opened_at = current_time
            row.retry_available_at = current_time + cooldown

        row.updated_at = current_time
        if commit:
            db.commit()
        else:
            db.flush()
        return _to_snapshot(
            row,
            now=current_time,
            probe_ttl_seconds=cfg.ai_reservation_ttl_seconds,
        )

    if not commit:
        return _tx()
    return run_atomic_with_sqlite_retry(db, _tx)
