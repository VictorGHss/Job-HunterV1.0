from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Generic, TypeVar
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.ai_usage import AIUsageLedger, AIUsageStatus
from app.models.material import ApplicationMaterialVersion
from app.services.materials.ai._db_locks import run_atomic_with_sqlite_retry
from app.services.materials.ai.circuit_breaker import (
    check_and_acquire_circuit_execution,
    record_circuit_failure,
    record_circuit_success,
)
from app.services.materials.ai.contracts import (
    AICircuitOpenError,
    AIDisabledError,
    AIGroundingRejectedError,
    AIOverlayConflictError,
    AIReviewStateError,
    AIStaleSourceVersionError,
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
    _to_entry_snapshot,
    confirm_ai_quota_usage,
    fail_ai_quota_usage,
    release_ai_quota_reservation,
    reserve_ai_quota,
)

logger = logging.getLogger("job_hunter.materials.ai.guard")

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class GuardedAIExecutionResult(Generic[T]):
    response: LLMStructuredResponse
    validated_output: T
    ledger_entry: LedgerEntrySnapshot
    persisted_artifact: Any = None


_DOMAIN_PRE_COMMIT_EXCEPTIONS = (
    AIStaleSourceVersionError,
    AIOverlayConflictError,
    AIGroundingRejectedError,
    AIReviewStateError,
)


def execute_guarded_ai_call(
    *,
    session_factory: Callable[[], Session],
    user_id: uuid.UUID,
    request: LLMStructuredRequest,
    reserved_tokens: int,
    material_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    response_validator: Callable[[LLMStructuredResponse], T] | None = None,
    post_transaction_persister: (
        Callable[
            [Session, LedgerEntrySnapshot, LLMStructuredResponse, T],
            tuple[Any, uuid.UUID | None],
        ]
        | None
    ) = None,
    after_commit_loader: Callable[[Session, uuid.UUID | None], Any] | None = None,
    injected_provider: LLMProvider | None = None,
    settings_override: Settings | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> GuardedAIExecutionResult[T]:
    """Executa o protocolo de 8 etapas sem manter transação SQL durante o I/O externo.

    1-5. Abre sessão curta #1 -> resolve provider -> reserva cota -> valida circuit breaker
         (liberando a reserva caso o circuito esteja aberto) -> fecha sessão #1.
    6-7. Executa ``provider.generate_structured`` e ``response_validator`` fora do banco.
    8.   Abre sessão curta #2 -> opcionalmente persiste nova versão sob lock exclusivo,
         atualiza circuit breaker e finaliza registro no ledger em UM ÚNICO commit atômico
         -> fecha sessão #2.
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
        custom_code = getattr(exc, "error_code", None)
        if isinstance(custom_code, str) and custom_code:
            failure_code = custom_code
        else:
            failure_code = "validation_rejected" if response is not None else "execution_failed"
        trip_circuit = False

    # Fase 3: Nova transação curta pós-chamada para reconciliar versão, circuit breaker e ledger
    t_after = now_fn() if now_fn is not None else None
    if caught_exc is not None:
        db_post = session_factory()
        try:
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
        except Exception:
            db_post.rollback()
            raise
        finally:
            db_post.close()

    assert response is not None

    if post_transaction_persister is None:
        db_post = session_factory()
        try:
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
                persisted_artifact=None,
            )
        except Exception:
            db_post.rollback()
            raise
        finally:
            db_post.close()

    # Caminho com persistência atômica pós-transação (Versão + Circuit Breaker + Ledger em 1 commit)
    db_post = session_factory()
    candidate_version_id: uuid.UUID | None = None
    persisted_artifact: Any = None
    try:
        def _atomic_post_tx() -> tuple[LedgerEntrySnapshot, Any, uuid.UUID | None]:
            nonlocal candidate_version_id, persisted_artifact
            db_post.info["_in_composite_tx"] = True
            try:
                persisted_artifact, candidate_version_id = post_transaction_persister(
                    db_post,
                    reservation,
                    response,
                    validated,
                )
                record_circuit_success(
                    db_post,
                    provider_key=provider_key,
                    now=t_after,
                    settings_override=cfg,
                    commit=False,
                )
                entry_snap = confirm_ai_quota_usage(
                    db_post,
                    reservation_id=reservation.id,
                    user_id=user_id,
                    provider_name=response.provider_name,
                    model_name=response.model_name,
                    token_usage=response.token_usage,
                    latency_ms=response.latency_ms,
                    resolved_version_id=candidate_version_id,
                    now=t_after,
                    commit=False,
                )
                db_post.commit()
                return entry_snap, persisted_artifact, candidate_version_id
            finally:
                db_post.info.pop("_in_composite_tx", None)

        final_entry, persisted_artifact, candidate_version_id = run_atomic_with_sqlite_retry(
            db_post,
            _atomic_post_tx,
        )
        if after_commit_loader is not None:
            db_post.expire_all()
            persisted_artifact = after_commit_loader(db_post, candidate_version_id)
        return GuardedAIExecutionResult(
            response=response,
            validated_output=validated,
            ledger_entry=final_entry,
            persisted_artifact=persisted_artifact,
        )
    except Exception as persist_exc:
        db_post.rollback()
        return _reconcile_post_commit_failure(
            session_factory=session_factory,
            reservation=reservation,
            user_id=user_id,
            provider_key=provider_key,
            response=response,
            validated=validated,
            candidate_version_id=candidate_version_id,
            after_commit_loader=after_commit_loader,
            persist_exc=persist_exc,
            now=t_after,
            cfg=cfg,
        )
    finally:
        db_post.close()


def _reconcile_post_commit_failure(
    *,
    session_factory: Callable[[], Session],
    reservation: LedgerEntrySnapshot,
    user_id: uuid.UUID,
    provider_key: str,
    response: LLMStructuredResponse,
    validated: T,
    candidate_version_id: uuid.UUID | None,
    after_commit_loader: Callable[[Session, uuid.UUID | None], Any] | None,
    persist_exc: Exception,
    now: datetime | None,
    cfg: Settings,
) -> GuardedAIExecutionResult[T]:
    """Reconcilia falhas pré-commit ou commits ambíguos em sessão curta de contingência."""
    db_contingency: Session | None = None
    try:
        db_contingency = session_factory()
        ledger_row = db_contingency.scalar(
            select(AIUsageLedger).where(
                AIUsageLedger.id == reservation.id,
                AIUsageLedger.user_id == user_id,
            )
        )
        version_exists = False
        if candidate_version_id is not None:
            version_exists = (
                db_contingency.scalar(
                    select(ApplicationMaterialVersion.id).where(
                        ApplicationMaterialVersion.id == candidate_version_id
                    )
                )
                is not None
            )

        # Caso 1: Commit ambíguo que efetivamente foi persistido pelo banco
        if (
            ledger_row is not None
            and ledger_row.status == AIUsageStatus.COMPLETED.value
            and (candidate_version_id is None or version_exists)
        ):
            logger.info(
                "Commit ambíguo reconciliado como concluído reservation_id=%s version_id=%s",
                str(reservation.id),
                str(candidate_version_id),
            )
            artifact = (
                after_commit_loader(db_contingency, candidate_version_id)
                if after_commit_loader is not None
                else None
            )
            return GuardedAIExecutionResult(
                response=response,
                validated_output=validated,
                ledger_entry=_to_entry_snapshot(ledger_row),
                persisted_artifact=artifact,
            )

        # Caso 2: Transação não comitou; registra sucesso de transporte no breaker e falha técnica no ledger
        if ledger_row is not None and ledger_row.status in (
            AIUsageStatus.RESERVED.value,
            AIUsageStatus.EXPIRED.value,
        ):
            raw_code = getattr(persist_exc, "error_code", None)
            if isinstance(raw_code, str) and raw_code:
                err_code = raw_code
            elif isinstance(persist_exc, _DOMAIN_PRE_COMMIT_EXCEPTIONS):
                err_code = "stale_source_version"
            else:
                err_code = "persistence_failed"

            record_circuit_success(
                db_contingency,
                provider_key=provider_key,
                now=now,
                settings_override=cfg,
            )
            fail_ai_quota_usage(
                db_contingency,
                reservation_id=reservation.id,
                user_id=user_id,
                error_code=err_code,
                provider_name=response.provider_name,
                model_name=response.model_name,
                token_usage=response.token_usage,
                latency_ms=response.latency_ms,
                now=now,
            )
    except Exception as contingency_exc:
        if db_contingency is not None:
            try:
                db_contingency.rollback()
            except Exception:
                pass
        logger.warning(
            "Sessão de contingência indisponível para reconciliar reserva reservation_id=%s error_class=%s",
            str(reservation.id),
            contingency_exc.__class__.__name__,
        )
    finally:
        if db_contingency is not None:
            try:
                db_contingency.close()
            except Exception:
                pass

    raise persist_exc
