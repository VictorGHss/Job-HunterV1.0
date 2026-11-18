from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.materials.ai.circuit_breaker import (
    check_and_acquire_circuit_execution,
    record_circuit_failure,
    record_circuit_success,
)
from app.services.materials.ai.contracts import (
    AICircuitOpenError,
    AIDisabledError,
    LLMMalformedOutputError,
    LLMProvider,
    LLMProviderError,
    LLMStructuredRequest,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMUpstreamError,
)
from app.services.materials.ai.providers import resolve_llm_provider
from app.services.materials.ai.quota_service import (
    LedgerEntrySnapshot,
    confirm_ai_quota_usage,
    fail_ai_quota_usage,
    release_ai_quota_reservation,
    reserve_ai_quota,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class GuardedAIExecutionResult(Generic[T]):
    response: LLMStructuredResponse
    validated_output: T
    ledger_entry: LedgerEntrySnapshot


def execute_guarded_ai_call(
    *,
    session_factory: Callable[[], Session],
    user_id: uuid.UUID,
    request: LLMStructuredRequest,
    reserved_tokens: int,
    material_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    response_validator: Callable[[LLMStructuredResponse], T] | None = None,
    injected_provider: LLMProvider | None = None,
    settings_override: Settings | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> GuardedAIExecutionResult[T]:
    """Executa o protocolo de 8 etapas sem manter transação SQL durante o I/O externo.

    1-5. Abre sessão curta #1 -> resolve provider -> reserva cota -> valida circuit breaker
         (liberando a reserva caso o circuito esteja aberto) -> fecha sessão #1.
    6-7. Executa ``provider.generate_structured`` e ``response_validator`` fora do banco.
    8.   Abre sessão curta #2 -> atualiza circuit breaker e finaliza registro no ledger -> fecha sessão #2.
    """
    cfg = settings_override or get_settings()
    provider = resolve_llm_provider(
        settings_override=cfg,
        injected_provider=injected_provider,
    )
    if not cfg.ai_assisted_enabled:
        raise AIDisabledError(
            "Aprimoramento assistido por IA está desabilitado nesta instância."
        )

    provider_key = provider.provider_name
    t_before = now_fn() if now_fn is not None else None

    # Fase 1: Transação curta pré-chamada (nenhum lock sobrevive ao fechamento de db_pre)
    db_pre = session_factory()
    reservation: LedgerEntrySnapshot | None = None
    try:
        reservation = reserve_ai_quota(
            db_pre,
            user_id=user_id,
            operation_type=request.operation_type,
            reserved_tokens=reserved_tokens,
            material_id=material_id,
            version_id=version_id,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            now=t_before,
            settings_override=cfg,
        )
        try:
            check_and_acquire_circuit_execution(
                db_pre,
                provider_key=provider_key,
                now=t_before,
                settings_override=cfg,
            )
        except AICircuitOpenError:
            release_ai_quota_reservation(
                db_pre,
                reservation_id=reservation.id,
                user_id=user_id,
                reason_code="circuit_open",
                now=t_before,
            )
            raise
    except Exception:
        db_pre.rollback()
        raise
    finally:
        db_pre.close()

    assert reservation is not None

    # Fase 2: Execução do provider e validação da resposta FORA de qualquer sessão de banco
    response: LLMStructuredResponse | None = None
    validated: T
    caught_exc: Exception | None = None
    failure_code: str = "provider_error"
    trip_circuit: bool = False

    try:
        response = provider.generate_structured(request)
        if response_validator is not None:
            validated = response_validator(response)
        else:
            validated = response.data  # type: ignore[assignment]
    except (LLMTimeoutError, LLMUpstreamError, LLMMalformedOutputError) as exc:
        caught_exc = exc
        failure_code = exc.error_code
        trip_circuit = True
    except LLMProviderError as exc:
        caught_exc = exc
        failure_code = exc.error_code
        trip_circuit = True
    except Exception as exc:
        caught_exc = exc
        failure_code = "validation_rejected" if response is not None else "execution_failed"
        trip_circuit = False

    # Fase 3: Nova transação curta pós-chamada para reconciliar ledger e circuit breaker
    t_after = now_fn() if now_fn is not None else None
    db_post = session_factory()
    try:
        if caught_exc is not None:
            if trip_circuit:
                record_circuit_failure(
                    db_post,
                    provider_key=provider_key,
                    reason_code=failure_code,
                    now=t_after,
                    settings_override=cfg,
                )
            elif response is not None:
                # Transporte do provider respondeu; fecha eventual sonda half-open
                record_circuit_success(
                    db_post,
                    provider_key=provider_key,
                    now=t_after,
                    settings_override=cfg,
                )
            fail_ai_quota_usage(
                db_post,
                reservation_id=reservation.id,
                user_id=user_id,
                error_code=failure_code,
                provider_name=response.provider_name if response else provider.provider_name,
                model_name=response.model_name if response else provider.model_name,
                token_usage=response.token_usage if response else None,
                latency_ms=response.latency_ms if response else None,
                now=t_after,
            )
            raise caught_exc

        assert response is not None
        record_circuit_success(
            db_post,
            provider_key=provider_key,
            now=t_after,
            settings_override=cfg,
        )
        final_entry = confirm_ai_quota_usage(
            db_post,
            reservation_id=reservation.id,
            user_id=user_id,
            provider_name=response.provider_name,
            model_name=response.model_name,
            token_usage=response.token_usage,
            latency_ms=response.latency_ms,
            now=t_after,
        )
        return GuardedAIExecutionResult(
            response=response,
            validated_output=validated,
            ledger_entry=final_entry,
        )
    except Exception:
        db_post.rollback()
        raise
    finally:
        db_post.close()
