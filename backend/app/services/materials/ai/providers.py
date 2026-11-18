from __future__ import annotations

from collections.abc import Sequence
import copy
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.materials.ai.contracts import (
    AIConfigurationError,
    AIDisabledError,
    LLMMalformedOutputError,
    LLMProvider,
    LLMStructuredRequest,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMTokenUsage,
    LLMUpstreamError,
    validate_safe_technical_identifier,
)


class DisabledLLMProvider(LLMProvider):
    """Implementação segura padrão quando o aprimoramento com IA está desabilitado."""

    @property
    def provider_name(self) -> str:
        return "disabled"

    @property
    def model_name(self) -> str:
        return "none"

    def generate_structured(self, request: LLMStructuredRequest) -> LLMStructuredResponse:
        del request
        raise AIDisabledError(
            "Aprimoramento assistido por IA está desabilitado nesta instância."
        )


@dataclass(frozen=True, slots=True)
class MockScenario:
    """Cenário determinístico individual para uso exclusivo em testes automatizados."""

    response_data: Any = None
    token_usage: LLMTokenUsage | None = None
    latency_ms: int = 12
    simulate_timeout: bool = False
    simulate_provider_error: bool = False
    simulate_invalid_output: bool = False


class MockLLMProvider(LLMProvider):
    """Provider determinístico para testes (estritamente bloqueado em produção)."""

    def __init__(
        self,
        *,
        response_data: Any = None,
        token_usage: LLMTokenUsage | None = None,
        latency_ms: int = 12,
        simulate_timeout: bool = False,
        simulate_provider_error: bool = False,
        simulate_invalid_output: bool = False,
        scenarios: Sequence[MockScenario] | None = None,
        provider_name: str = "mock",
        model_name: str = "mock-structured-v1",
        settings_override: Settings | None = None,
    ) -> None:
        cfg = settings_override or get_settings()
        if cfg.environment == "production":
            raise AIConfigurationError(
                "MockLLMProvider é exclusivo para testes e não pode ser utilizado em produção."
            )

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
        assert clean_provider is not None and clean_model is not None

        self._provider_name = clean_provider
        self._model_name = clean_model
        self._settings_override = settings_override
        self._default_scenario = MockScenario(
            response_data={"ok": True} if response_data is None else response_data,
            token_usage=token_usage,
            latency_ms=latency_ms,
            simulate_timeout=simulate_timeout,
            simulate_provider_error=simulate_provider_error,
            simulate_invalid_output=simulate_invalid_output,
        )
        self._scenarios = list(scenarios) if scenarios is not None else []
        self.call_count: int = 0
        self.last_operation_type: str | None = None
        self.last_schema_name: str | None = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _assert_non_production(self) -> None:
        cfg = self._settings_override or get_settings()
        if cfg.environment == "production":
            raise AIConfigurationError(
                "Execução de MockLLMProvider bloqueada em ambiente de produção."
            )

    def generate_structured(self, request: LLMStructuredRequest) -> LLMStructuredResponse:
        self._assert_non_production()
        scenario_idx = self.call_count
        self.call_count += 1
        self.last_operation_type = request.operation_type
        self.last_schema_name = request.schema_name

        scenario = (
            self._scenarios[scenario_idx]
            if scenario_idx < len(self._scenarios)
            else self._default_scenario
        )

        if scenario.simulate_timeout:
            raise LLMTimeoutError("Timeout simulado ao aguardar resposta do provider.")

        if scenario.simulate_provider_error:
            raise LLMUpstreamError("Falha simulada de comunicação com o provider.")

        if scenario.simulate_invalid_output or not isinstance(scenario.response_data, dict):
            raise LLMMalformedOutputError(
                "Resposta simulada inválida: payload não corresponde a um objeto JSON estruturado."
            )

        required_keys = request.response_schema.get("required")
        if isinstance(required_keys, list):
            missing = [key for key in required_keys if key not in scenario.response_data]
            if missing:
                raise LLMMalformedOutputError(
                    "Resposta simulada não preencheu todos os campos obrigatórios do schema."
                )

        return LLMStructuredResponse(
            data=copy.deepcopy(scenario.response_data),
            provider_name=self._provider_name,
            model_name=self._model_name,
            latency_ms=max(0, int(scenario.latency_ms)),
            token_usage=scenario.token_usage,
        )


def resolve_llm_provider(
    *,
    settings_override: Settings | None = None,
    injected_provider: LLMProvider | None = None,
) -> LLMProvider:
    """Resolve o provider ativo respeitando kill switch e trava anti-mock em produção."""
    cfg = settings_override or get_settings()

    if cfg.environment == "production" and (
        cfg.ai_provider == "mock" or isinstance(injected_provider, MockLLMProvider)
    ):
        raise AIConfigurationError(
            "Provider mock é proibido em ambiente de produção."
        )

    if not cfg.ai_assisted_enabled:
        return DisabledLLMProvider()

    if injected_provider is not None:
        return injected_provider

    provider_slug = cfg.ai_provider.strip().lower()
    if provider_slug == "disabled":
        return DisabledLLMProvider()

    if provider_slug == "mock":
        effective_model = (
            cfg.ai_model
            if cfg.ai_model and cfg.ai_model != "none"
            else "mock-structured-v1"
        )
        return MockLLMProvider(
            model_name=effective_model,
            settings_override=cfg,
        )

    raise AIConfigurationError(
        f"Provider de IA '{provider_slug}' não está implementado nesta subfase."
    )
