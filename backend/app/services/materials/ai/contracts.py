from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Literal

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_FORBIDDEN_CREDENTIAL_MARKERS = (
    "sk-",
    "aiza",
    "bearer ",
    "api_key",
    "apikey",
    "secret",
    "password",
    "token=",
    "authorization",
    "http://",
    "https://",
)

QuotaScopeLiteral = Literal[
    "user_window_requests",
    "user_daily_requests",
    "user_daily_tokens",
    "global_daily_tokens",
]


class AIFoundationError(Exception):
    """Exceção base da fundação de IA assistida."""


class AIDisabledError(AIFoundationError):
    """Funcionalidade de IA desabilitada por configuração (kill switch)."""


class AIConfigurationError(AIFoundationError):
    """Configuração inválida ou insegura de provider/ambiente."""


class AIContextAuthorizationError(AIFoundationError):
    """Violação de autorização ou consistência ao montar contexto autorizado de IA."""


class AIQuotaExceededError(AIFoundationError):
    """Limite de requisições ou tokens excedido para o usuário ou instância."""

    def __init__(
        self,
        message: str,
        *,
        scope: QuotaScopeLiteral,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(message)
        self.scope: QuotaScopeLiteral = scope
        self.retry_after_seconds: int = max(1, int(retry_after_seconds))


class AIReservationNotFoundError(AIFoundationError):
    """Reserva não encontrada ou não pertencente ao usuário autenticado."""


class AIReservationStateError(AIFoundationError):
    """Transição inválida de estado para um registro do ledger de IA."""


class AICircuitOpenError(AIFoundationError):
    """Circuito aberto ou em sondagem exclusiva (half-open) impedindo chamada externa."""

    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        state: str,
        retry_after_seconds: int,
        opened_at: datetime | None = None,
        retry_available_at: datetime | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_key = provider_key
        self.state = state
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        self.opened_at = opened_at
        self.retry_available_at = retry_available_at


class LLMProviderError(AIFoundationError):
    """Falha normalizada na comunicação ou resposta de um LLMProvider."""

    error_code: str = "provider_error"


class LLMTimeoutError(LLMProviderError):
    """Timeout ao aguardar conexão ou leitura do provider."""

    error_code: str = "provider_timeout"


class LLMUpstreamError(LLMProviderError):
    """Erro transitório ou indisponibilidade reportada pelo provider."""

    error_code: str = "provider_error"


class LLMMalformedOutputError(LLMProviderError):
    """Saída do provider não é JSON estruturado válido ou viola o contrato esperado."""

    error_code: str = "malformed_output"


def validate_safe_technical_identifier(
    raw_value: str | None,
    *,
    field_name: str,
    max_length: int = 64,
    allow_none: bool = False,
) -> str | None:
    """Garante que apenas identificadores técnicos curtos entrem no ledger/circuit breaker.

    Bloqueia estruturalmente prompts, textos livres com espaços, e-mails, URLs,
    JSON ou potenciais credenciais/tokens.
    """
    if raw_value is None:
        if allow_none:
            return None
        raise ValueError(f"Identificador técnico '{field_name}' é obrigatório.")

    if not isinstance(raw_value, str):
        raise ValueError(f"Identificador técnico '{field_name}' deve ser texto.")

    cleaned = raw_value.strip()
    if not cleaned:
        if allow_none:
            return None
        raise ValueError(f"Identificador técnico '{field_name}' não pode ser vazio.")

    if len(cleaned) > max_length:
        raise ValueError(
            f"Identificador técnico '{field_name}' excede o limite de {max_length} caracteres."
        )

    lowered = cleaned.lower()
    if "@" in cleaned or any(marker in lowered for marker in _FORBIDDEN_CREDENTIAL_MARKERS):
        raise ValueError(
            f"Identificador técnico '{field_name}' contém padrão proibido (PII, URL ou credencial)."
        )

    if not _SAFE_IDENTIFIER_RE.match(cleaned):
        raise ValueError(
            f"Identificador técnico '{field_name}' deve conter apenas caracteres técnicos seguros ([A-Za-z0-9_.:/-])."
        )

    return cleaned


@dataclass(frozen=True, slots=True)
class LLMTokenUsage:
    """Metadados reais de utilização de tokens reportados pelo provider.

    Nunca deve ser instanciado com estimativas inventadas; quando um provider
    não informar consumo real, utilize ``None`` em ``LLMStructuredResponse.token_usage``.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Contagens de tokens não podem ser negativas.")
        computed = self.input_tokens + self.output_tokens
        if self.total_tokens is None:
            object.__setattr__(self, "total_tokens", computed)
        elif self.total_tokens < computed:
            raise ValueError(
                "total_tokens informado pelo provider não pode ser inferior a input_tokens + output_tokens."
            )

    @property
    def resolved_total_tokens(self) -> int:
        return int(self.total_tokens if self.total_tokens is not None else (self.input_tokens + self.output_tokens))


@dataclass(frozen=True, slots=True)
class LLMStructuredRequest:
    """Solicitação estruturada agnóstica de fornecedor (sem tool-calling)."""

    operation_type: str
    schema_name: str
    response_schema: dict[str, Any]
    system_instruction: str
    structured_input: dict[str, Any]
    max_output_tokens: int = 1200
    temperature: float = 0.2
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        validate_safe_technical_identifier(
            self.operation_type,
            field_name="operation_type",
            max_length=64,
        )
        validate_safe_technical_identifier(
            self.schema_name,
            field_name="schema_name",
            max_length=64,
        )
        if not isinstance(self.response_schema, dict) or not self.response_schema:
            raise ValueError("response_schema deve ser um dicionário JSON Schema não vazio.")
        if not isinstance(self.structured_input, dict):
            raise ValueError("structured_input deve ser um dicionário estruturado.")
        if not self.system_instruction or not self.system_instruction.strip():
            raise ValueError("system_instruction não pode ser vazia.")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens deve ser maior que zero.")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature deve estar entre 0.0 e 2.0.")
        if self.timeout_seconds is not None and not (0.0 < self.timeout_seconds < 25.0):
            raise ValueError("timeout_seconds deve ser maior que zero e menor que 25 segundos.")


@dataclass(frozen=True, slots=True)
class LLMStructuredResponse:
    """Resposta estruturada normalizada de um LLMProvider."""

    data: dict[str, Any]
    provider_name: str
    model_name: str
    latency_ms: int
    token_usage: LLMTokenUsage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.data, dict):
            raise LLMMalformedOutputError("Payload retornado pelo provider não é um objeto JSON.")
        validate_safe_technical_identifier(
            self.provider_name,
            field_name="provider_name",
            max_length=64,
        )
        validate_safe_technical_identifier(
            self.model_name,
            field_name="model_name",
            max_length=120,
        )
        if self.latency_ms < 0:
            raise ValueError("latency_ms não pode ser negativo.")


class LLMProvider(ABC):
    """Contrato agnóstico para provedores de geração estruturada sem tool-calling.

    Separação arquitetural preservada:
    - O provider apenas transforma ``LLMStructuredRequest`` em ``LLMStructuredResponse``.
    - Não decide origem de versão (``origin``), proveniência de blocos (``provenance``)
      nem aprovação humana (``is_approved``).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identificador técnico curto do provider (ex.: 'disabled', 'mock')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identificador técnico do modelo configurado."""

    @abstractmethod
    def generate_structured(self, request: LLMStructuredRequest) -> LLMStructuredResponse:
        """Executa solicitação estruturada ou lança exceção normalizada."""
