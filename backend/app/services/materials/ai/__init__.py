"""Fundação e infraestrutura de IA assistida opcional (Subfase 04.4.1).

Mantém separação estrita entre:
1. Contrato agnóstico de provider (``LLMProvider``, ``DisabledLLMProvider``, ``MockLLMProvider``).
2. Controle atômico de cotas, reservas e ledger sem conteúdo/PII (``quota_service``).
3. Circuit breaker persistido em banco SQL compartilhável entre workers (``circuit_breaker``).
"""
from app.services.materials.ai.circuit_breaker import (
    CircuitBreakerSnapshot,
    check_and_acquire_circuit_execution,
    get_circuit_state,
    record_circuit_failure,
    record_circuit_success,
)
from app.services.materials.ai.contracts import (
    AICircuitOpenError,
    AIConfigurationError,
    AIDisabledError,
    AIFoundationError,
    AIQuotaExceededError,
    AIReservationNotFoundError,
    AIReservationStateError,
    LLMMalformedOutputError,
    LLMProvider,
    LLMProviderError,
    LLMStructuredRequest,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMTokenUsage,
    LLMUpstreamError,
    QuotaScopeLiteral,
    validate_safe_technical_identifier,
)
from app.services.materials.ai.execution_guard import (
    GuardedAIExecutionResult,
    execute_guarded_ai_call,
)
from app.services.materials.ai.providers import (
    DisabledLLMProvider,
    MockLLMProvider,
    MockScenario,
    resolve_llm_provider,
)
from app.services.materials.ai.quota_service import (
    LedgerEntrySnapshot,
    QuotaAvailability,
    confirm_ai_quota_usage,
    expire_abandoned_reservations,
    fail_ai_quota_usage,
    get_ledger_entry_for_user,
    get_quota_availability,
    release_ai_quota_reservation,
    reserve_ai_quota,
)

__all__ = [
    "AICircuitOpenError",
    "AIConfigurationError",
    "AIDisabledError",
    "AIFoundationError",
    "AIQuotaExceededError",
    "AIReservationNotFoundError",
    "AIReservationStateError",
    "CircuitBreakerSnapshot",
    "DisabledLLMProvider",
    "GuardedAIExecutionResult",
    "LLMMalformedOutputError",
    "LLMProvider",
    "LLMProviderError",
    "LLMStructuredRequest",
    "LLMStructuredResponse",
    "LLMTimeoutError",
    "LLMTokenUsage",
    "LLMUpstreamError",
    "LedgerEntrySnapshot",
    "MockLLMProvider",
    "MockScenario",
    "QuotaAvailability",
    "QuotaScopeLiteral",
    "check_and_acquire_circuit_execution",
    "confirm_ai_quota_usage",
    "execute_guarded_ai_call",
    "expire_abandoned_reservations",
    "fail_ai_quota_usage",
    "get_circuit_state",
    "get_ledger_entry_for_user",
    "get_quota_availability",
    "record_circuit_failure",
    "record_circuit_success",
    "release_ai_quota_reservation",
    "reserve_ai_quota",
    "resolve_llm_provider",
    "validate_safe_technical_identifier",
]
